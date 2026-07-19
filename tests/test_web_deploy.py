import json
import sys
import threading
import urllib.error
import urllib.request

import pytest

from forgeai.web.server import _DEPLOY_STATE, build_server


def _request(url: str, data: bytes | None = None, method: str | None = None) -> tuple[int, str]:
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        # 4xx/5xx font partie du contrat testé — retournés, pas levés
        return exc.code, exc.read().decode("utf-8")


@pytest.fixture
def server():
    srv = build_server("127.0.0.1", 0)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()
    srv.server_close()


@pytest.fixture
def fake_deploy(monkeypatch):
    cmd = [
        sys.executable,
        "-u",
        "-c",
        "print('etape 1/3 detection'); print('etape 2/3 plan'); print('etape 3/3 sante OK')",
    ]
    monkeypatch.setattr("forgeai.web.server._DEPLOY_CMD", cmd)

    with _DEPLOY_STATE["lock"]:
        proc = _DEPLOY_STATE["proc"]
        _DEPLOY_STATE["proc"] = None
        _DEPLOY_STATE["lines"].clear()
        _DEPLOY_STATE["done"] = False
        _DEPLOY_STATE["exit_code"] = None
    if proc is not None and proc.poll() is None:
        proc.terminate()
        proc.wait()

    yield

    with _DEPLOY_STATE["lock"]:
        proc = _DEPLOY_STATE["proc"]
        _DEPLOY_STATE["proc"] = None
    if proc is not None and proc.poll() is None:
        proc.terminate()
        proc.wait()


def test_summary(server):
    status, body = _request(f"{server}/api/summary?stack=agentique")
    assert status == 200
    data = json.loads(body)
    assert data["stack"]["n_deploy"] == 72
    assert isinstance(data["backends"], list)
    assert "cpu_model" in data["hardware"]


def test_summary_stack_inconnu(server):
    status, _ = _request(f"{server}/api/summary?stack=xyz")
    assert status == 404
    status, _ = _request(f"{server}/api/summary")
    assert status == 400


def test_deploy_friction_forcer(server, fake_deploy):
    payload = json.dumps({"stack": "agentique", "backend": "compose", "confirm": "oui"}).encode("utf-8")
    status, body = _request(f"{server}/api/deploy", data=payload, method="POST")
    assert status == 400
    assert "FORCER" in body
    assert _DEPLOY_STATE["proc"] is None


def test_deploy_et_sse(server, fake_deploy):
    payload = json.dumps({"stack": "agentique", "backend": "compose", "confirm": "FORCER"}).encode("utf-8")
    status, body = _request(f"{server}/api/deploy", data=payload, method="POST")
    assert status == 202
    assert json.loads(body)["started"] is True

    req = urllib.request.Request(f"{server}/api/deploy/events")
    with urllib.request.urlopen(req, timeout=15) as resp:
        stream = resp.read().decode("utf-8")

    assert "etape 1/3 detection" in stream
    assert "etape 3/3 sante OK" in stream
    assert "event: end" in stream
    assert '"exit_code": 0' in stream


def test_deploy_deja_en_cours(server, fake_deploy, monkeypatch):
    monkeypatch.setattr(
        "forgeai.web.server._DEPLOY_CMD",
        [sys.executable, "-u", "-c", "import time; time.sleep(3)"],
    )

    payload = json.dumps({"stack": "agentique", "backend": "compose", "confirm": "FORCER"}).encode("utf-8")
    status, _ = _request(f"{server}/api/deploy", data=payload, method="POST")
    assert status == 202

    status2, body2 = _request(f"{server}/api/deploy", data=payload, method="POST")
    assert status2 == 409
    assert "déploiement déjà en cours" in body2


def test_non_regression(server):
    for path in ("/api/stacks", "/api/models", "/api/nodes/status"):
        status, _ = _request(f"{server}{path}")
        assert status == 200, path
