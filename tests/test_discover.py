"""Tests du moteur de découverte d'infrastructure ForgeAI (D1)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from forgeai.network.discover import _sonder, charger_signatures, inventaire
from forgeai.resources import catalogue_path
from forgeai.web.server import build_server


class FakeRunner:
    """Runner de test : répond par préfixe d'argv, avec un cas spécial pour le sondage
    GROUPÉ des binaires (PERF — un seul appel pour tous, une ligne 1/0 par binaire
    demandé, dans l'ordre reçu) plutôt qu'un appel par binaire."""

    def __init__(
        self,
        outputs: dict[str, tuple[int, str]],
        binaires_presents: frozenset[str] = frozenset(),
    ) -> None:
        self.outputs = outputs
        self.binaires_presents = binaires_presents
        self.calls: list[list[str]] = []

    def run(self, argv: list[str]) -> tuple[int, str]:
        self.calls.append(argv)
        if (
            len(argv) >= 4
            and argv[0] == "sh" and argv[1] == "-c" and argv[3] == "sh"
            and "for b in" in argv[2]
        ):
            demandes = argv[4:]
            lignes = ["1" if b in self.binaires_presents else "0" for b in demandes]
            return 0, "\n".join(lignes)
        key = " ".join(argv)
        for prefix, (rc, stdout) in self.outputs.items():
            if key.startswith(prefix):
                return rc, stdout
        return 1, ""


def test_signatures_briques_au_catalogue() -> None:
    raw = json.loads(catalogue_path().read_text(encoding="utf-8"))
    entries = raw if isinstance(raw, list) else raw.get("entries", [])
    ids = {e["id"] for e in entries}
    for sig in charger_signatures():
        brique = sig.get("brique")
        if brique:
            assert brique in ids, f"brique inconnue au catalogue : {brique}"


def test_inventaire_detecte_ollama_qdrant() -> None:
    runner = FakeRunner(
        {
            "docker ps --format": (
                0,
                "ollama/ollama|ollama|0.0.0.0:11434->11434/tcp",
            ),
            "ss -tlnH": (
                0,
                "LISTEN 0 128 127.0.0.1:11434 *:*\n"
                "LISTEN 0 128 0.0.0.0:6333 *:*\n",
            ),
            "nvidia-smi -L": (0, "GPU 0: NVIDIA GeForce RTX 3060"),
        },
        binaires_presents=frozenset({"docker", "ollama"}),
    )
    inv = inventaire(runner, charger_signatures())
    by_id = {s["id"]: s for s in inv["services"]}

    assert by_id["ollama"]["detecte"] is True
    assert by_id["qdrant"]["detecte"] is True
    assert by_id["ollama"]["endpoint"] == "127.0.0.1:11434"
    assert by_id["qdrant"]["endpoint"] == "127.0.0.1:6333"
    assert "port" in by_id["ollama"]["via"]
    assert "conteneur" in by_id["ollama"]["via"]


def test_inventaire_absents() -> None:
    runner = FakeRunner({})
    signatures = [
        {
            "id": "foo",
            "binaire": None,
            "port": None,
            "image": None,
            "brique": None,
            "categorie": "test",
        }
    ]
    inv = inventaire(runner, signatures)
    assert len(inv["services"]) == 1
    svc = inv["services"][0]
    assert svc["detecte"] is False
    assert svc["endpoint"] is None


def test_tolerant_commande_absente() -> None:
    runner = FakeRunner(
        {
            "docker ps --format": (127, ""),
            "ss -tlnH": (0, ""),
            "nvidia-smi -L": (127, ""),
        },
        binaires_presents=frozenset({"docker"}),
    )
    sonde = _sonder(runner)
    assert sonde["conteneurs"] == []
    # inventaire ne plante pas non plus
    inv = inventaire(runner, charger_signatures())
    assert isinstance(inv["services"], list)


# --- PERF (issue soulevée en session, jamais couverte par l'audit v7.1) ----------------------
# _sonder() faisait 1 appel runner.run() PAR binaire (8 sur signatures-infra.json). Décisif en
# SSH distant : SshRunner ouvre une connexion TCP+SSH complète par appel (aucun multiplexage),
# donc 8 connexions séquentielles pour un sondage qui devrait être quasi instantané.

def test_sonder_groupe_tous_les_binaires_en_un_seul_appel() -> None:
    """Isole l'optimisation : un SEUL runner.run() pour toutes les vérifications de
    binaires, quel que soit leur nombre dans signatures-infra.json (mesuré à 8)."""
    runner = FakeRunner(
        {
            "docker ps --format": (127, ""),
            "ss -tlnH": (0, ""),
            "nvidia-smi -L": (127, ""),
        },
        binaires_presents=frozenset({"docker", "ollama"}),
    )
    _sonder(runner)

    appels_binaires = [c for c in runner.calls if len(c) >= 3 and c[0] == "sh" and "for b in" in c[2]]
    assert len(appels_binaires) == 1, (
        f"attendu 1 seul appel groupé pour tous les binaires, obtenu {len(appels_binaires)} "
        f"(régression vers un appel par binaire)"
    )
    nb_binaires_signatures = sum(1 for s in charger_signatures() if s.get("binaire"))
    assert len(appels_binaires[0]) - 4 == nb_binaires_signatures, (
        "l'appel groupé doit porter TOUS les binaires à vérifier, pas un sous-ensemble"
    )


def test_sonder_binaires_resultat_identique_a_l_ancien_appel_par_binaire() -> None:
    """Non-régression sémantique : le résultat par binaire (présent/absent) reste correct
    après le passage à un appel groupé — seule la MÉCANIQUE de l'appel a changé."""
    runner = FakeRunner(
        {"docker ps --format": (127, ""), "ss -tlnH": (0, ""), "nvidia-smi -L": (127, "")},
        binaires_presents=frozenset({"docker", "kubectl", "nvidia-smi"}),
    )
    sonde = _sonder(runner)
    assert sonde["binaires"]["docker"] is True
    assert sonde["binaires"]["kubectl"] is True
    assert sonde["binaires"]["nvidia"] is True  # id "nvidia", binaire "nvidia-smi"
    assert sonde["binaires"]["helm"] is False
    assert sonde["binaires"]["ollama"] is False


def test_api_discover_local() -> None:
    server = build_server("127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        url = f"http://127.0.0.1:{port}/api/discover?node=local"
        with urllib.request.urlopen(url, timeout=5) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert "services" in data
            assert isinstance(data["services"], list)

        url2 = f"http://127.0.0.1:{port}/api/discover?node=pc2"
        with pytest.raises(urllib.error.HTTPError, match="400"):
            urllib.request.urlopen(url2, timeout=5)
    finally:
        server.shutdown()
        server.server_close()


def test_cli_discover_distant_sans_cle() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    src = repo_root / "src"
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{src}{os.pathsep}{repo_root}{os.pathsep}{env.get('PYTHONPATH', '')}"
    proc = subprocess.run(
        # --hostkey fourni (SSH-007) pour atteindre la garde --user/--keyfile testée ici
        [sys.executable, "-m", "forgeai", "node", "discover", "pc2", "--hostkey", "SHA256:testfp"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert proc.returncode == 12
    stderr = proc.stderr.lower()
    assert "user" in stderr
    assert "keyfile" in stderr
