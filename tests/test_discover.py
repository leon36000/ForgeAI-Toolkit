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
    """Runner de test : répond par préfixe d'argv."""

    def __init__(self, outputs: dict[str, tuple[int, str]]) -> None:
        self.outputs = outputs
        self.calls: list[list[str]] = []

    def run(self, argv: list[str]) -> tuple[int, str]:
        self.calls.append(argv)
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
            'sh -c command -v "$1" sh docker': (0, "/usr/bin/docker"),
            'sh -c command -v "$1" sh ollama': (0, "/usr/bin/ollama"),
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
        }
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
            'sh -c command -v "$1" sh docker': (0, "/usr/bin/docker"),
            "docker ps --format": (127, ""),
            "ss -tlnH": (0, ""),
            "nvidia-smi -L": (127, ""),
        }
    )
    sonde = _sonder(runner)
    assert sonde["conteneurs"] == []
    # inventaire ne plante pas non plus
    inv = inventaire(runner, charger_signatures())
    assert isinstance(inv["services"], list)


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
