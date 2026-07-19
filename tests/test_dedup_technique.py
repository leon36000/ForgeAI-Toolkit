"""Tests d'audit P2.1 — dédup technique : FORGEAI_HOME, parse_stars, reco serveur."""
from __future__ import annotations

import json
import threading
import time
import urllib.request
from pathlib import Path

from forgeai import cli as cli_module
from forgeai.resources import forgeai_home
from forgeai.web import server as server_module


def _start_server() -> tuple[str, server_module.ThreadingHTTPServer]:
    server = server_module.build_server("127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.05)
    host, port = server.server_address
    return f"http://{host}:{port}", server


def test_forgeai_home_source_unique():
    server_src = Path(server_module.__file__).read_text(encoding="utf-8")
    cli_src = Path(cli_module.__file__).read_text(encoding="utf-8")

    assert "def forgeai_home(" not in server_src
    assert "from forgeai.resources import" in cli_src
    assert "forgeai_home" in cli_src
    assert callable(forgeai_home)


def test_parse_stars_source_unique():
    server_src = Path(server_module.__file__).read_text(encoding="utf-8")

    assert "def parse_stars(" not in server_src
    assert "from forgeai.catalogue.loader import parse_stars" in server_src


def test_reco_serveur():
    url, server = _start_server()
    try:
        with urllib.request.urlopen(f"{url}/api/detect") as resp:
            detect = json.loads(resp.read().decode("utf-8"))

        with urllib.request.urlopen(f"{url}/api/stacks/recommended") as resp:
            data = json.loads(resp.read().decode("utf-8"))

        assert resp.status == 200
        assert "recommended_id" in data
        assert data["recommended_id"] in {"agentique", "assistant-entreprise"}

        expected = "agentique" if len(detect.get("gpus", [])) >= 1 else "assistant-entreprise"
        assert data["recommended_id"] == expected
    finally:
        server.shutdown()
        server.server_close()


def test_non_regression():
    url, server = _start_server()
    try:
        with urllib.request.urlopen(f"{url}/api/stacks") as resp:
            stacks = json.loads(resp.read().decode("utf-8"))
        assert isinstance(stacks, list)
        assert len(stacks) == 6

        with urllib.request.urlopen(f"{url}/api/i18n/fr") as resp:
            locale = json.loads(resp.read().decode("utf-8"))
        assert resp.status == 200
        assert isinstance(locale, dict)
    finally:
        server.shutdown()
        server.server_close()
