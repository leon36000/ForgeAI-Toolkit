"""Tests unitaires pour la persistance de l'état de préparation (REL-038A)."""
import json
import os
import stat
from pathlib import Path

import pytest

from forgeai.web import server


@pytest.fixture(autouse=True)
def _isolate_prepare_state():
    """Préserve/restaure l'état global du module entre les tests."""
    backup = dict(server._PREPARE_STATE)
    server._PREPARE_STATE.clear()
    yield
    server._PREPARE_STATE.clear()
    server._PREPARE_STATE.update(backup)


@pytest.fixture()
def prepare_tmp_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirige forgeai_home vers un répertoire temporaire vide."""
    monkeypatch.setattr(server, "forgeai_home", lambda: tmp_path)
    return tmp_path


class TestPersistPrepareState:
    def test_set_creates_file(self, prepare_tmp_path: Path):
        """_prepare_state_set("n1", ...) → le fichier existe, JSON contient version et n1."""
        state = {"done": False, "resultat": None, "erreur": None}
        server._prepare_state_set("n1", state)

        path = server._prepare_state_path()
        assert path.exists(), "Le fichier de persistance devrait exister"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["version"] == server._PREPARE_STATE_VERSION
        hosts = data["hosts"]
        assert "n1" in hosts
        assert hosts["n1"] == state

    def test_load_restores_entry(self, prepare_tmp_path: Path):
        """Vider _PREPARE_STATE puis _load_prepare_state() restaure l'entrée."""
        state = {"done": True, "resultat": "ok", "erreur": None}
        server._prepare_state_set("n1", state)

        # Simule un redémarrage : on efface la mémoire
        server._PREPARE_STATE.clear()
        assert len(server._PREPARE_STATE) == 0

        server._load_prepare_state()
        assert "n1" in server._PREPARE_STATE
        assert server._PREPARE_STATE["n1"] == state

    def test_atomic_permissions_no_residual_temp(self, prepare_tmp_path: Path):
        """Droits 0o600 et aucun fichier .tmp résiduel."""
        server._prepare_state_set("n1", {"done": False})

        path = server._prepare_state_path()
        # permissions
        mode = oct(path.stat().st_mode & 0o777)
        assert mode == "0o600", f"Permissions {mode} != 0o600"

        # aucun fichier .tmp dans le répertoire parent
        tmp_files = list(path.parent.glob("*.tmp"))
        assert not tmp_files, f"Fichiers temporaires résiduels : {tmp_files}"

    def test_corrupted_file_no_exception_empty_state(self, prepare_tmp_path: Path):
        """Fichier corrompu → pas d'exception, état vide."""
        path = server._prepare_state_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{ pas du json", encoding="utf-8")

        server._load_prepare_state()
        assert len(server._PREPARE_STATE) == 0

        # version incorrecte
        path.write_text(json.dumps({"version": 999, "hosts": {}}), encoding="utf-8")
        server._PREPARE_STATE.clear()
        server._load_prepare_state()
        assert len(server._PREPARE_STATE) == 0

    def test_mixed_valid_and_invalid_entries(self, prepare_tmp_path: Path):
        """Entrée valide + entrée malformée : seule la valide est chargée."""
        payload = {
            "version": 1,
            "hosts": {
                "n1": {"done": True, "resultat": "ok", "erreur": None},
                "n2": "pas un dict",
            },
        }
        path = server._prepare_state_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")

        server._load_prepare_state()
        assert "n1" in server._PREPARE_STATE
        assert server._PREPARE_STATE["n1"] == payload["hosts"]["n1"]
        assert "n2" not in server._PREPARE_STATE, "L'entrée malformée doit être ignorée"

    def test_redaction_of_error_secrets(self, prepare_tmp_path: Path):
        """Un erreur contenant un secret est rédigé avant écriture."""
        secret = "api_key=" + "a" * 32  # proof:allow (faux secret de test)
        state = {"done": True, "resultat": None, "erreur": secret}
        server._prepare_state_set("n1", state)

        raw = server._prepare_state_path().read_text(encoding="utf-8")
        assert secret not in raw, "Le secret ne doit pas apparaître en clair dans le fichier"  # proof:allow
        data = json.loads(raw)
        assert data["hosts"]["n1"]["erreur"] != secret, "L'erreur doit être rédigée"

    def test_lru_bound_on_load(self, prepare_tmp_path: Path):
        """Chargement borne LRU à _PREPARE_MAX entrées."""
        hosts = {
            f"host_{i:04d}": {"done": True, "resultat": i, "erreur": None}
            for i in range(server._PREPARE_MAX + 10)
        }
        payload = {"version": 1, "hosts": hosts}
        path = server._prepare_state_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")

        server._load_prepare_state()
        assert len(server._PREPARE_STATE) <= server._PREPARE_MAX, (
            f"Nombre d'entrées {len(server._PREPARE_STATE)} > {server._PREPARE_MAX}"
        )

    def test_get_returns_defensive_copy(self, prepare_tmp_path: Path):
        """_prepare_state_get renvoie une copie ; la mutation n'altère pas l'état."""
        state = {"done": False, "resultat": None, "erreur": None}
        server._prepare_state_set("n1", state)
        copy1 = server._prepare_state_get("n1")
        copy1["nouveau"] = "pollution"
        assert "nouveau" not in server._PREPARE_STATE["n1"]
        assert server._PREPARE_STATE["n1"] == state
