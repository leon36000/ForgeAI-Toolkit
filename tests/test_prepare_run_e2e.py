"""Tests end-to-end de la closure _run_prepare du serveur web (issue #119/FAI-0013)."""

from __future__ import annotations

import json
import threading
import time
import urllib.request

import pytest

from forgeai.network.prepare import PrepareError
from forgeai.web import server
from forgeai.web.server import build_server


def _post_json(url: str, payload: dict) -> urllib.request.addinfourl:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    return urllib.request.urlopen(req, timeout=5)


def _get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=5) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _poll_done(base_url: str, host: str) -> dict:
    status_url = f"{base_url}/api/nodes/prepare/{host}"
    for _ in range(30):
        data = _get_json(status_url)
        if data.get("done") is True:
            return data
        time.sleep(0.1)
    pytest.fail(f"l'état 'done' n'a jamais été atteint pour {host}")


def _start_server() -> tuple:
    srv = build_server("127.0.0.1", 0)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    host, port = srv.server_address
    return srv, f"http://{host}:{port}"


def test_run_prepare_succes(monkeypatch) -> None:
    def fake_preparer_noeud(runner, host, *, appliquer, helm_present):
        return {"receptacle": "pret", "etapes": []}

    monkeypatch.setattr(server, "preparer_noeud", fake_preparer_noeud)

    srv, base_url = _start_server()
    try:
        with _post_json(
            f"{base_url}/api/nodes/prepare", {"host": "n-prep"}
        ) as resp:
            assert resp.status == 202

        data = _poll_done(base_url, "n-prep")

        assert data["done"] is True
        assert data["erreur"] is None
        assert data["resultat"]["receptacle"] == "pret"
    finally:
        srv.shutdown()
        srv.server_close()


def test_run_prepare_erreur(monkeypatch) -> None:
    def fake_preparer_noeud(runner, host, *, appliquer, helm_present):
        raise PrepareError("boom")

    monkeypatch.setattr(server, "preparer_noeud", fake_preparer_noeud)

    srv, base_url = _start_server()
    try:
        with _post_json(
            f"{base_url}/api/nodes/prepare", {"host": "n-fail"}
        ) as resp:
            assert resp.status == 202

        data = _poll_done(base_url, "n-fail")

        assert data["done"] is True
        assert data["erreur"] == "boom"
        assert data["resultat"] is None
    finally:
        srv.shutdown()
        srv.server_close()


def test_run_prepare_exception_generique(monkeypatch) -> None:
    """Une exception NON-PrepareError (bug inattendu) est capturée par le filet
    générique : le thread ne meurt jamais en silence, l'état publie une erreur."""

    def fake_preparer_noeud(runner, host, *, appliquer, helm_present):
        raise RuntimeError("kaboom inattendu")

    monkeypatch.setattr(server, "preparer_noeud", fake_preparer_noeud)

    srv, base_url = _start_server()
    try:
        with _post_json(
            f"{base_url}/api/nodes/prepare", {"host": "n-bug"}
        ) as resp:
            assert resp.status == 202

        data = _poll_done(base_url, "n-bug")

        assert data["done"] is True
        assert data["erreur"].startswith("erreur interne:")
        assert "kaboom inattendu" in data["erreur"]
        assert data["resultat"] is None
    finally:
        srv.shutdown()
        srv.server_close()
