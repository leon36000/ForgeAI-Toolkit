from __future__ import annotations

import importlib.resources
import json
import threading
import urllib.request

import pytest

from forgeai.web.server import _asset_bytes, build_server


@pytest.fixture
def server():
    srv = build_server("127.0.0.1", 0)
    port = srv.server_address[1]
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    srv.shutdown()
    srv.server_close()


def _get(url: str) -> tuple[int, dict[str, str], bytes]:
    with urllib.request.urlopen(url, timeout=10) as resp:
        return resp.status, dict(resp.headers), resp.read()


def test_detect_endpoint(server):
    status, headers, body = _get(f"{server}/api/detect")
    assert status == 200
    assert "application/json" in headers.get("Content-Type", "")
    data = json.loads(body.decode("utf-8"))
    for key in ("cpu_model", "cpu_cores", "cpu_arch", "ram_gb", "os_name", "gpus", "disks"):
        assert key in data


def test_accueil(server):
    status, headers, body = _get(server)
    assert status == 200
    assert "text/html" in headers.get("Content-Type", "")
    text = body.decode("utf-8")
    assert "ForgeAI Toolkit" in text
    assert 'id="app"' in text


def test_assets(server):
    status, headers, body = _get(f"{server}/app.css")
    assert status == 200
    assert "text/css" in headers.get("Content-Type", "")

    status, headers, body = _get(f"{server}/app.js")
    assert status == 200
    assert "text/javascript" in headers.get("Content-Type", "")


def test_health(server):
    status, headers, body = _get(f"{server}/api/health")
    assert status == 200
    assert "application/json" in headers.get("Content-Type", "")
    assert json.loads(body.decode("utf-8")) == {"status": "ok"}


def test_404(server):
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        _get(f"{server}/nope")
    assert exc_info.value.code == 404


def test_pas_de_traversal():
    assert _asset_bytes("../server.py") is None
    assert _asset_bytes("foo/bar.css") is None
    assert _asset_bytes("foo\\bar.css") is None


def test_auto_suffisance():
    for name in ("index.html", "app.css", "app.js"):
        text = (importlib.resources.files("forgeai.web") / "assets" / name).read_text(
            encoding="utf-8"
        )
        assert "http://" not in text, f"{name} contient une référence http://"
        assert "https://" not in text, f"{name} contient une référence https://"
