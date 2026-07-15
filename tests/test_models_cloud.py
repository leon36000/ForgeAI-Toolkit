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
