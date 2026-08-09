"""Story B-08 (DM-5) — modèles locaux : filtre VRAM/moteur + download hash-vérifié +
déploiement + test de complétion réel. Prouve chaque critère avec des composants injectés.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from forgeai.core.runner import FixtureRunner
from forgeai.models.local import (
    LocalModel,
    LocalModelError,
    add_local,
    deploy,
    download_verified,
    filter_available,
    check_completion,
)

CONTENT = b"POIDS-DU-MODELE-DEMO" * 64
GOOD_SHA = hashlib.sha256(CONTENT).hexdigest()


def _model(sha=GOOD_SHA, vram=4000, engine="ollama"):
    return LocalModel(name="qwen-coder-1_5b", engine=engine, vram_required_mb=vram,
                      model_ref="qwen2.5-coder:1.5b",
                      download_url="http://example/model.bin", sha256=sha)


class FixtureFetcher:
    """Écrit un contenu fixe (le vrai SHA-256 est calculé dessus) — pas de réseau."""

    def __init__(self, content=CONTENT):
        self.content = content
        self.calls = []

    def fetch(self, url, dest):
        self.calls.append(url)
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        Path(dest).write_bytes(self.content)
        return len(self.content)


class FixtureTransport:
    def __init__(self, status=200, payload=None):
        self.payload = payload or json.dumps({"choices": [{"message": {"content": "pong"}}]})
        self.status = status

    def post(self, url, headers, body, timeout):
        return self.status, self.payload


# ---------- filtre VRAM + moteur ----------

def test_filtre_vram_exclut_trop_gros():
    petit, gros = _model(vram=4000), _model(vram=48000)
    keep = filter_available([petit, gros], vram_mb=8000, engines={"ollama"})
    assert keep == [petit]


def test_filtre_moteur_exclut_backend_absent():
    m = _model(engine="vllm")
    assert filter_available([m], vram_mb=99000, engines={"ollama"}) == []
    assert filter_available([m], vram_mb=99000, engines={"vllm"}) == [m]


# ---------- download hash-vérifié ----------

def test_download_bon_hash_conserve(tmp_path):
    path = download_verified(_model(), tmp_path, FixtureFetcher())
    assert path.exists() and path.read_bytes() == CONTENT


def test_download_mauvais_hash_abandonne_et_supprime(tmp_path):
    with pytest.raises(LocalModelError) as exc:
        download_verified(_model(sha="0" * 64), tmp_path, FixtureFetcher())
    assert "SHA-256" in str(exc.value)
    assert list(tmp_path.glob("*.bin")) == []          # fichier corrompu supprimé


# ---------- déploiement (runner injecté) ----------

def test_deploy_ok():
    deploy(_model(), FixtureRunner({"ollama": ""}))    # code 0 → pas d'exception


def test_deploy_echec_leve():
    runner = FixtureRunner({})                          # commande inconnue → code 127
    with pytest.raises(LocalModelError):
        deploy(_model(), runner)


# ---------- test de complétion réel ----------

def test_completion_green():
    r = check_completion("http://127.0.0.1:11434/v1", "qwen2.5-coder:1.5b", FixtureTransport())
    assert r.ok and r.light == "GREEN"


def test_completion_red_reponse_vide():
    empty = FixtureTransport(payload=json.dumps({"choices": []}))
    r = check_completion("http://127.0.0.1:11434/v1", "m", empty)
    assert not r.ok


# ---------- orchestration bout-en-bout ----------

def test_add_local_flux_complet_journalise(tmp_path):
    events = []
    r = add_local(_model(), tmp_path, "http://127.0.0.1:11434/v1",
                  vram_mb=8000, engines={"ollama"},
                  fetcher=FixtureFetcher(), runner=FixtureRunner({"ollama": ""}),
                  transport=FixtureTransport(),
                  journal=lambda step, data: events.append((step, data)))
    assert r.ok
    steps = [e[0] for e in events]
    assert steps == ["modele_local_telecharge", "modele_local_deploye", "modele_local_valide"]


def test_add_local_vram_insuffisante_fail_fast(tmp_path):
    with pytest.raises(LocalModelError) as exc:
        add_local(_model(vram=48000), tmp_path, "http://x/v1",
                  vram_mb=8000, engines={"ollama"},
                  fetcher=FixtureFetcher(), runner=FixtureRunner({"ollama": ""}),
                  transport=FixtureTransport())
    assert "VRAM" in str(exc.value)
    assert list(tmp_path.glob("*.bin")) == []          # rien téléchargé (fail-fast avant download)


def test_add_local_completion_red_invalide_tout(tmp_path):
    empty = FixtureTransport(payload=json.dumps({"choices": []}))
    with pytest.raises(LocalModelError) as exc:
        add_local(_model(), tmp_path, "http://x/v1", vram_mb=8000, engines={"ollama"},
                  fetcher=FixtureFetcher(), runner=FixtureRunner({"ollama": ""}),
                  transport=empty)
    assert "complétion" in str(exc.value).lower()


def test_cli_add_local_vram_fail_fast(tmp_path, capsys):
    """CLI : VRAM insuffisante → échec propre (code 9), aucun téléchargement réseau."""
    from forgeai.cli import main
    dest = tmp_path / "local"
    rc = main(["model", "add-local", "--name", "trop-gros", "--engine", "ollama",
               "--model-ref", "x:70b", "--url", "http://127.0.0.1:1/m.bin",
               "--sha256", "0" * 64, "--vram-required-mb", "48000", "--vram-mb", "8000",
               "--engine-url", "http://127.0.0.1:11434/v1", "--dest", str(dest),
               "--registre", str(tmp_path / "r.jsonl")])
    assert rc == 9
    assert "ECHEC MODELE LOCAL" in capsys.readouterr().err
    assert not dest.exists() or list(dest.glob("*.bin")) == []


def test_add_local_nettoie_si_deploy_echoue(tmp_path):
    try:
        add_local(
            _model(),
            tmp_path,
            "http://localhost:11434",
            vram_mb=4000,
            engines={"ollama"},
            fetcher=FixtureFetcher(),
            runner=FixtureRunner({}),
            transport=FixtureTransport(),
        )
        assert False, "aurait dû lever LocalModelError"
    except LocalModelError:
        pass
    assert not list(tmp_path.glob("*.bin"))


def test_fetch_passe_un_timeout(monkeypatch, tmp_path):
    from forgeai.models.local import UrllibFetcher
    captured = {}

    def fake_urlopen(url, **kwargs):
        captured["timeout"] = kwargs.get("timeout")
        raise RuntimeError("stop")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    fetcher = UrllibFetcher()
    try:
        fetcher.fetch("http://x", tmp_path / "out.bin")
    except RuntimeError:
        pass
    assert captured.get("timeout") is not None and captured["timeout"] > 0


def test_download_rejette_nom_traversal(tmp_path):
    import dataclasses
    model = dataclasses.replace(_model(), name="../evil")
    try:
        download_verified(model, tmp_path, FixtureFetcher())
        assert False, "aurait dû lever LocalModelError"
    except LocalModelError:
        pass
    escaped = (tmp_path / "../evil.bin").resolve()
    assert not escaped.exists()
    assert not list(tmp_path.glob("*.bin"))


# ---------------------------------------------------------------------------
# CAND-006 (audit v7.1, P1_HIGH) — trois gardes de download_verified() dont
# AUCUNE n'était prouvée isolément : le test ci-dessus (nom "../evil") contient
# À LA FOIS "/" ET ".." — valider_nom_simple ET resolve_within le refusent
# chacun indépendamment, donc retirer L'UN OU L'AUTRE laisse ce test vert
# (mutation à cause isolée mesurée par l'audit : rc=0 dans les deux cas). La
# troisième garde (tmp.unlink(missing_ok=True) sur mismatch de hash) écrit un
# fichier `.part`, jamais `.bin` — le test de mismatch existant ne vérifie que
# `glob("*.bin")`, donc un `.part` corrompu resterait invisible sur disque.
# Les 3 tests suivants isolent chaque garde par mutation/neutralisation
# ciblée d'UNE SEULE des deux autres, comme dans C AND-001 (redirection HTTP).
# ---------------------------------------------------------------------------

def test_download_verified_slash_dans_le_nom_refuse_avant_fetch(tmp_path):
    """Isole valider_nom_simple : un nom contenant "/" mais SANS ".." (donc dont
    le chemin résultant resterait CONTENU dans dest_dir, resolve_within ne le
    bloquerait pas) doit quand même être refusé — AVANT tout appel réseau."""
    import dataclasses

    class _FetchInterdit:
        def fetch(self, url, dest, timeout=300.0):
            raise AssertionError(
                "CAND-006: fetch() ne doit jamais être appelé pour un nom "
                "de modèle invalide — la garde doit couper le chemin avant."
            )

    model = dataclasses.replace(_model(), name="sous-repertoire/modele")
    with pytest.raises(LocalModelError):
        download_verified(model, tmp_path, _FetchInterdit())
    assert not list(tmp_path.rglob("*"))  # rien créé, y compris aucun sous-répertoire


def test_download_verified_resolve_within_bloque_meme_nom_simple_neutralise(monkeypatch, tmp_path):
    """Isole resolve_within comme second rempart INDÉPENDANT : même si
    valider_nom_simple était contournée (neutralisée ici), le confinement de
    chemin doit à lui seul refuser une évasion hors de dest_dir.

    Le chemin d'évasion visé sort volontairement de `tmp_path` (c'est le point
    du test) — donc hors du nettoyage automatique de pytest en cas de garde
    défaillante. Nettoyage défensif dans un `finally` pour ne jamais laisser
    de résidu hors zone gérée, quel que soit le résultat du test."""
    import forgeai.models.local as local_mod

    monkeypatch.setattr(local_mod, "valider_nom_simple", lambda name: None)

    import dataclasses
    model = dataclasses.replace(_model(), name="../../evasion-hors-racine")
    escaped = (tmp_path / "../../evasion-hors-racine.bin").resolve()
    try:
        with pytest.raises(LocalModelError):
            download_verified(model, tmp_path, FixtureFetcher())
        assert not escaped.exists()
    finally:
        escaped.unlink(missing_ok=True)
        escaped.with_suffix(".part").unlink(missing_ok=True)


def test_download_verified_mismatch_supprime_le_fichier_part_temporaire(tmp_path):
    """Isole tmp.unlink(missing_ok=True) : sur mismatch de hash, le fichier
    TEMPORAIRE (.part, pas .bin) doit disparaître — le test de mismatch
    préexistant ne vérifiait que glob("*.bin"), jamais glob("*.part")."""
    with pytest.raises(LocalModelError):
        download_verified(_model(sha="0" * 64), tmp_path, FixtureFetcher())
    assert not list(tmp_path.glob("*.part")), "fichier .part corrompu non nettoyé"
    assert not list(tmp_path.rglob("*")), "aucune trace ne doit rester dans dest_dir"

