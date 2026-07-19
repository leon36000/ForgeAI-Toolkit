from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from pathlib import Path

import pytest

import forgeai.web.server as server_mod


@contextmanager
def _running_server():
    server = server_mod.build_server("127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    url = f"http://{host}:{port}"
    time.sleep(0.05)
    try:
        yield url
    finally:
        server.shutdown()
        server.server_close()


def _request(req: urllib.request.Request):
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            data = body
        return exc.code, data


def _get(url: str):
    return _request(urllib.request.Request(url, method="GET"))


def _post(url: str, payload: dict):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    return _request(req)


@pytest.fixture
def tmp_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(server_mod, "_MODELS_HOME", tmp_path / "models")
    monkeypatch.setattr(server_mod, "_REGISTRE_PATH", tmp_path / "r.jsonl")
    return tmp_path


@pytest.fixture
def GREEN(monkeypatch: pytest.MonkeyPatch):
    class GreenTransport:
        def post(self, url, headers, body, timeout):
            return (200, '{"choices":[{"message":{"content":"pong"}}]}')

    monkeypatch.setattr(server_mod, "_PROBE_TRANSPORT", GreenTransport())
    return GreenTransport


@pytest.fixture
def RED(monkeypatch: pytest.MonkeyPatch):
    class RedTransport:
        def post(self, url, headers, body, timeout):
            return (401, '{"error":"unauthorized"}')

    monkeypatch.setattr(server_mod, "_PROBE_TRANSPORT", RedTransport())
    return RedTransport


def test_models_liste_vide(tmp_home: Path):
    with _running_server() as url:
        status, body = _get(f"{url}/api/models")
        assert status == 200
        assert body == []


def test_add_cloud_green(tmp_home: Path, GREEN):
    key = "sk-TEST-XYZ"
    payload = {
        "name": "r1",
        "provenance": "openrouter",
        "model_id": "m",
        "api_key": key,
        "passphrase": "pp",
    }
    with _running_server() as url:
        status, body = _post(f"{url}/api/models", payload)
        assert status == 201
        route = body["route"]
        assert route["name"] == "r1"
        assert route["provenance"] == "openrouter"
        assert route["model_id"] == "m"
        assert route["key_fingerprint"].startswith("sha256:")
        assert key not in json.dumps(body)

        status2, list_body = _get(f"{url}/api/models")
        assert status2 == 200
        assert len(list_body) == 1
        assert list_body[0]["name"] == "r1"

    for path in tmp_home.rglob("*"):
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="ignore")
            assert key not in text, f"clé API trouvée dans {path}"

    reg = tmp_home / "r.jsonl"
    if reg.exists():
        assert key not in reg.read_text(encoding="utf-8", errors="ignore")


def test_add_cloud_red_rien_ecrit(tmp_home: Path, RED):
    key = "sk-TEST-RED"
    payload = {
        "name": "r1",
        "provenance": "openrouter",
        "model_id": "m",
        "api_key": key,
        "passphrase": "pp",
    }
    with _running_server() as url:
        status, body = _post(f"{url}/api/models", payload)
        assert status == 400
        status2, list_body = _get(f"{url}/api/models")
        assert list_body == []

    assert not (tmp_home / "models" / "routes.json").exists()


def test_add_cloud_champs_manquants(tmp_home: Path, GREEN):
    """Le 400 liste les champs manquants SANS refléter les valeurs soumises.
    (Valeurs DISTINCTIVES — une valeur d'un caractère rendrait l'assertion vide de sens.)"""
    payload = {
        "name": "route-distinctive-r1",
        "provenance": "openrouter",
        "model_id": "modele-distinctif-xyz",
        "passphrase": "passphrase-distinctive-pp",
    }
    with _running_server() as url:
        status, body = _post(f"{url}/api/models", payload)
        assert status == 400
        response_text = json.dumps(body)
        assert "api_key" in response_text
        assert "route-distinctive-r1" not in response_text
        assert "modele-distinctif-xyz" not in response_text
        assert "passphrase-distinctive-pp" not in response_text


def test_add_cloud_doublon(tmp_home: Path, GREEN):
    payload = {
        "name": "r1",
        "provenance": "openrouter",
        "model_id": "m",
        "api_key": "sk-1",
        "passphrase": "pp",
    }
    with _running_server() as url:
        status1, _ = _post(f"{url}/api/models", payload)
        assert status1 == 201
        status2, body2 = _post(f"{url}/api/models", payload)
        assert status2 == 400
        assert "existe" in str(body2.get("error", "")).lower()


def test_registre_journalise(tmp_home: Path, GREEN):
    key = "sk-REG-TEST"
    payload = {
        "name": "r1",
        "provenance": "openrouter",
        "model_id": "m",
        "api_key": key,
        "passphrase": "pp",
    }
    with _running_server() as url:
        status, body = _post(f"{url}/api/models", payload)
        assert status == 201
        fp = body["route"]["key_fingerprint"]

    reg = tmp_home / "r.jsonl"
    assert reg.exists()
    lines = [
        json.loads(line)
        for line in reg.read_text(encoding="utf-8").strip().split("\n")
        if line
    ]
    assert any(
        line.get("type") == "route_cloud_ajoutee"
        and line.get("payload", {}).get("key_fingerprint") == fp
        for line in lines
    )
    assert key not in reg.read_text(encoding="utf-8")


def test_post_inconnu(tmp_home: Path):
    with _running_server() as url:
        status, body = _post(f"{url}/api/nope", {"x": 1})
        assert status == 404
        assert "error" in body


def test_non_regression_get(tmp_home: Path):
    with _running_server() as url:
        status, body = _get(f"{url}/api/stacks")
        assert status == 200
        assert isinstance(body, list)

        status2, body2 = _get(f"{url}/api/bricks?sphere=S4")
        assert status2 == 200
        assert "bricks" in body2
