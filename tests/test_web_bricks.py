from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request

import pytest

from forgeai.stacks import deploy_ids, list_stacks, load_stack
from forgeai.web.server import build_server, chassis_ids


@pytest.fixture(scope="module")
def base_url():
    server = build_server("127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    yield f"http://{host}:{port}"
    server.shutdown()
    server.server_close()


def _get(base_url: str, path: str):
    with urllib.request.urlopen(base_url + path, timeout=30) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))


def _get_status(base_url: str, path: str):
    try:
        with urllib.request.urlopen(base_url + path, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            data = body
        return exc.code, data


def test_bricks_sphere_seule(base_url):
    status, data = _get(base_url, "/api/bricks?sphere=S6")
    assert status == 200
    assert data["sphere"] == "S6"
    assert data["stack"] is None
    assert data["total"] > 30

    required_keys = {
        "id",
        "name",
        "description_fr",
        "description_en",
        "stars",
        "installed",
        "locked",
    }
    for brick in data["bricks"]:
        assert required_keys.issubset(brick.keys())
        assert brick["installed"] is False
        assert brick["locked"] is False

    order_keys = [(-brick["stars"], brick["id"]) for brick in data["bricks"]]
    assert order_keys == sorted(order_keys)


def test_bricks_avec_stack(base_url):
    status, data = _get(base_url, "/api/bricks?sphere=S6&stack=agentique")
    assert status == 200
    bricks = data["bricks"]
    assert any(brick["installed"] for brick in bricks)

    qdrant = next((b for b in bricks if b["id"] == "qdrant"), None)
    assert qdrant is not None
    assert qdrant["installed"] is True

    first_not_installed = next(
        (i for i, b in enumerate(bricks) if not b["installed"]), None
    )
    if first_not_installed is not None:
        assert all(b["installed"] for b in bricks[:first_not_installed])
    else:
        assert all(b["installed"] for b in bricks)


def test_bricks_chassis_verrouille(base_url):
    status, data = _get(base_url, "/api/bricks?sphere=S4&stack=agentique")
    assert status == 200
    litellm = next(b for b in data["bricks"] if b["id"] == "litellm")
    assert litellm["installed"] is True
    assert litellm["locked"] is True


def test_bricks_hors_deploy_decochables(base_url):
    status, data = _get(base_url, "/api/bricks?sphere=S6&stack=agentique")
    assert status == 200
    for brick in data["bricks"]:
        if not brick["installed"]:
            assert brick["locked"] is False


def test_bricks_sphere_invalide(base_url):
    status, data = _get_status(base_url, "/api/bricks?sphere=S99")
    assert status == 404

    status, data = _get_status(base_url, "/api/bricks")
    assert status == 400

    status, data = _get_status(base_url, "/api/bricks?sphere=S6&stack=xyz")
    assert status == 404


def test_chassis_intersection():
    chassis = chassis_ids()
    assert "litellm" in chassis
    assert len(chassis) >= 20

    profiles = [sid for sid in list_stacks() if sid != "tout-en-un"]
    assert len(profiles) >= 5
    for brick_id in chassis:
        for sid in profiles:
            assert brick_id in deploy_ids(load_stack(sid))


def test_non_regression(base_url):
    status, data = _get(base_url, "/api/stacks")
    assert status == 200
    assert len(data) == 6

    status, _ = _get(base_url, "/api/detect")
    assert status == 200

    status, _ = _get_status(base_url, "/nope")
    assert status == 404
