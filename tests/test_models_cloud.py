"""Story B-09 (DM-5) — modèles cloud : provenance + clé en coffre + test réel.

Prouve les critères d'acceptation testables :
  - clé JAMAIS en clair (ni routes.json, ni registre) — empreinte seule ;
  - route ajoutée uniquement après un test de connexion réel GREEN ;
  - échec de connexion = message clair, aucune route cassée ajoutée.
"""
from __future__ import annotations

import json
import os
import stat

import pytest

from forgeai.models import probe as probe_mod
from forgeai.models.routes import PROVENANCES, RouteError, RouteStore
from forgeai.models.vault import Vault, VaultError, fingerprint, seal, unseal

SECRET = "sk-supersecret-DO-NOT-LEAK-4242"


class FixtureTransport:
    """Transport de test : réponse (status, payload) programmée; capture les appels."""

    def __init__(self, status: int, payload: str) -> None:
        self.status, self.payload = status, payload
        self.calls: list[dict] = []

    def post(self, url, headers, body, timeout):
        self.calls.append({"url": url, "headers": headers, "body": body})
        return self.status, self.payload


GREEN = FixtureTransport(200, json.dumps({"choices": [{"message": {"content": "pong"}}]}))
def _red_auth():
    return FixtureTransport(401, json.dumps({"error": "invalid key"}))


# ---------- coffre (vault) ----------

def test_vault_roundtrip():
    blob = seal(SECRET.encode(), "passphrase-forte")
    assert unseal(blob, "passphrase-forte").decode() == SECRET
    assert SECRET.encode() not in blob  # le secret n'apparaît pas en clair dans le blob


def test_vault_mauvaise_passphrase():
    blob = seal(SECRET.encode(), "bonne")
    with pytest.raises(VaultError):
        unseal(blob, "mauvaise")


def test_vault_alteration_detectee():
    blob = bytearray(seal(SECRET.encode(), "p"))
    blob[-1] ^= 0x01  # bascule un bit du ciphertext
    with pytest.raises(VaultError):
        unseal(bytes(blob), "p")


def test_fingerprint_non_reversible():
    fp = fingerprint(SECRET)
    assert fp.startswith("sha256:") and SECRET not in fp
    assert fingerprint(SECRET) == fp and fingerprint("autre") != fp


def test_vault_fichier_permissions(tmp_path):
    v = Vault(tmp_path / "sub" / "vault.json")
    v.put("route-x", SECRET, "pp")
    assert v.get("route-x", "pp") == SECRET
    mode = stat.S_IMODE(os.stat(v.path).st_mode)
    assert mode == 0o600, oct(mode)
    assert SECRET not in v.path.read_text()  # scellé, pas en clair


# ---------- probe ----------

def test_probe_green():
    r = probe_mod.probe_route("https://api.x/v1", "m", SECRET, GREEN)
    assert r.ok and r.light == "GREEN"


def test_probe_red_reseau():
    r = probe_mod.probe_route("https://api.x/v1", "m", SECRET, FixtureTransport(0, ""))
    assert not r.ok and "connexion" in r.detail.lower()


def test_probe_red_cle_refusee():
    r = probe_mod.probe_route("https://api.x/v1", "m", SECRET, _red_auth())
    assert not r.ok and r.status == 401


def test_probe_red_reponse_vide():
    empty = FixtureTransport(200, json.dumps({"choices": []}))
    r = probe_mod.probe_route("https://api.x/v1", "m", SECRET, empty)
    assert not r.ok and "vide" in r.detail.lower()


# ---------- route store ----------

def test_add_cloud_green_scelle_la_cle(tmp_path):
    store = RouteStore(tmp_path)
    route, result = store.add_cloud("openrouter-glm", "openrouter", "z-ai/glm-4.6",
                                    SECRET, "pp-coffre", transport=GREEN)
    assert result.ok and route.key_fingerprint == fingerprint(SECRET)
    # routes.json : métadonnées + empreinte, JAMAIS la clé
    raw = store.routes_path.read_text()
    assert SECRET not in raw and route.key_fingerprint in raw
    # la clé est récupérable UNIQUEMENT via le coffre + passphrase
    assert store.vault.get("openrouter-glm", "pp-coffre") == SECRET
    assert SECRET not in store.vault.path.read_text()


def test_add_cloud_red_n_ajoute_rien(tmp_path):
    store = RouteStore(tmp_path)
    with pytest.raises(RouteError) as exc:
        store.add_cloud("cassee", "openrouter", "m", SECRET, "pp", transport=_red_auth())
    assert "RED" in str(exc.value) or "401" in str(exc.value)
    assert store.list() == []                      # aucune route
    assert not store.routes_path.exists() or store.list() == []
    assert "cassee" not in store.vault.names()     # clé jamais scellée


def test_add_cloud_base_url_resolue():
    store = RouteStore.__new__(RouteStore)  # resolve_base_url est pure
    assert store.resolve_base_url("openrouter", None) == PROVENANCES["openrouter"]
    with pytest.raises(RouteError):
        store.resolve_base_url("direct", None)     # exige base_url
    assert store.resolve_base_url("direct", "https://x/v1") == "https://x/v1"
    with pytest.raises(RouteError):
        store.resolve_base_url("inconnue", None)


def test_route_dupliquee_refusee(tmp_path):
    store = RouteStore(tmp_path)
    store.add_cloud("r", "openrouter", "m", SECRET, "pp", transport=GREEN)
    with pytest.raises(RouteError):
        store.add_cloud("r", "openrouter", "m", SECRET, "pp", transport=GREEN)


def test_vault_cree_0600_sans_chmod(tmp_path, monkeypatch):
    import forgeai.models.vault as vault_mod
    monkeypatch.setattr(vault_mod.os, "chmod", lambda *a, **k: None)
    v = Vault(tmp_path / "v" / "vault.json")
    v.put("k", "secret", "pp")
    assert stat.S_IMODE(os.stat(v.path).st_mode) == 0o600


import json

from forgeai.models.routes import CloudRoute, RouteError, RouteStore


def test_cloudroute_defauts_cache():
    route = CloudRoute(
        name="n",
        provenance="openrouter",
        base_url="http://x/v1",
        model_id="m",
        key_fingerprint="sha256:abcd",
        created_at="2026-07-16",
    )
    assert route.cache is False
    assert route.cache_ttl_s is None
    assert route.cache_prefix is None
    assert "cache" in route.public_dict()


def test_routes_json_ancien_format_se_charge(tmp_path):
    route_dict = {
        "name": "r",
        "provenance": "openrouter",
        "base_url": "https://openrouter.ai/api/v1",
        "model_id": "m",
        "key_fingerprint": "sha256:abcd",
        "created_at": "2026-07-16",
    }
    (tmp_path / "routes.json").write_text(
        json.dumps([route_dict]), encoding="utf-8"
    )
    routes = RouteStore(tmp_path).list()
    assert len(routes) == 1
    assert routes[0].cache is False


def test_configure_cache_met_a_jour_et_persiste(tmp_path):
    route_dict = {
        "name": "r",
        "provenance": "openrouter",
        "base_url": "https://openrouter.ai/api/v1",
        "model_id": "m",
        "key_fingerprint": "sha256:abcd",
        "created_at": "2026-07-16",
    }
    (tmp_path / "routes.json").write_text(
        json.dumps([route_dict]), encoding="utf-8"
    )
    store = RouteStore(tmp_path)
    updated = store.configure_cache("r", True, 3600, "px")
    assert updated.cache is True
    assert updated.cache_ttl_s == 3600
    assert updated.cache_prefix == "px"
    reloaded = RouteStore(tmp_path).get("r")
    assert reloaded.cache is True
    assert reloaded.cache_ttl_s == 3600
    assert reloaded.cache_prefix == "px"


def test_configure_cache_ttl_negatif_rejete(tmp_path):
    route_dict = {
        "name": "r",
        "provenance": "openrouter",
        "base_url": "https://openrouter.ai/api/v1",
        "model_id": "m",
        "key_fingerprint": "sha256:abcd",
        "created_at": "2026-07-16",
    }
    (tmp_path / "routes.json").write_text(
        json.dumps([route_dict]), encoding="utf-8"
    )
    with pytest.raises(RouteError):
        RouteStore(tmp_path).configure_cache("r", True, -1)


def test_configure_cache_route_inconnue(tmp_path):
    (tmp_path / "routes.json").write_text(json.dumps([]), encoding="utf-8")
    with pytest.raises(RouteError):
        RouteStore(tmp_path).configure_cache("absente", True)


def test_configure_cache_replace_echoue_conserve_ancien_fichier(
    tmp_path, monkeypatch
):
    route_dict = {
        "name": "r",
        "provenance": "openrouter",
        "base_url": "https://openrouter.ai/api/v1",
        "model_id": "m",
        "key_fingerprint": "sha256:abcd",
        "created_at": "2026-07-16",
    }
    path = tmp_path / "routes.json"
    path.write_text(json.dumps([route_dict]), encoding="utf-8")
    before = path.read_bytes()
    real_replace = os.replace

    def fail_route_replace(src, dst):
        if os.fspath(dst) == os.fspath(path):
            raise OSError("panne injectee avant replace routes")
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", fail_route_replace)
    with pytest.raises(OSError, match="avant replace routes"):
        RouteStore(tmp_path).configure_cache("r", True, 60, "cache")

    assert path.read_bytes() == before
    assert RouteStore(tmp_path).get("r").cache is False


def test_vault_replace_echoue_conserve_ancien_fichier(tmp_path, monkeypatch):
    vault = Vault(tmp_path / "vault.json")
    vault.put("existante", "secret-existant", "pp")
    before = vault.path.read_bytes()
    real_replace = os.replace

    def fail_vault_replace(src, dst):
        if os.fspath(dst) == os.fspath(vault.path):
            raise OSError("panne injectee avant replace vault")
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", fail_vault_replace)
    with pytest.raises(OSError, match="avant replace vault"):
        vault.put("nouvelle", "secret-nouveau", "pp")

    assert vault.path.read_bytes() == before
    assert vault.names() == ["existante"]
    assert vault.get("existante", "pp") == "secret-existant"


def test_add_cloud_echec_commit_route_compense_la_cle_vault(
    tmp_path, monkeypatch
):
    store = RouteStore(tmp_path)

    def fail_route_commit(routes):
        raise OSError("commit routes impossible")

    monkeypatch.setattr(store, "_save", fail_route_commit)
    with pytest.raises(OSError, match="commit routes impossible"):
        store.add_cloud(
            "orpheline",
            "openrouter",
            "m",
            SECRET,
            "pp",
            transport=GREEN,
        )

    assert "orpheline" not in store.vault.names()
    assert store.list() == []


def test_add_cloud_rollback_restaure_vault_meme_si_routes_reste_indisponible(
    tmp_path, monkeypatch
):
    store = RouteStore(tmp_path)
    store.add_cloud(
        "existante",
        "openrouter",
        "m",
        "secret-existant",
        "pp",
        transport=GREEN,
    )
    real_replace = os.replace

    def fail_every_route_replace(src, dst):
        if os.fspath(dst) == os.fspath(store.routes_path):
            raise OSError("routes indisponible")
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", fail_every_route_replace)
    with pytest.raises(OSError, match="routes indisponible"):
        store.add_cloud(
            "orpheline",
            "openrouter",
            "m",
            "secret-orphelin",
            "pp",
            transport=GREEN,
        )

    assert sorted(store.vault._load()) == ["existante"]
    assert store.transaction_journal_path.exists()

    monkeypatch.undo()
    recovered = RouteStore(tmp_path)
    assert [route.name for route in recovered.list()] == ["existante"]
    assert recovered.vault.names() == ["existante"]
    assert not recovered.transaction_journal_path.exists()


def test_cli_route_configure(tmp_path):
    import json
    from forgeai.cli import main
    from forgeai.models.routes import RouteStore

    home = tmp_path / "models"
    home.mkdir()
    reg = tmp_path / "registre.jsonl"
    (home / "routes.json").write_text(json.dumps([{
        "name": "r",
        "provenance": "direct",
        "model_id": "m",
        "base_url": "http://example/v1",
        "key_fingerprint": "fp",
        "created_at": "2026-07-16",
    }]))

    rc = main(["route", "configure", "r", "--cache", "--ttl", "3600",
               "--prefix", "px", "--home", str(home), "--registre", str(reg)])
    assert rc == 0
    route = RouteStore(home).get("r")
    assert route.cache is True and route.cache_ttl_s == 3600 and route.cache_prefix == "px"
