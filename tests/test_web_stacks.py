import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from forgeai.resources import catalogue_path
from forgeai.web.server import build_server


def _get(base: str, path: str):
    try:
        with urllib.request.urlopen(base + path, timeout=30) as resp:
            return resp.status, resp.read().decode("utf-8"), dict(resp.headers)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8"), dict(exc.headers)


@pytest.fixture(scope="function")
def server_url():
    server = build_server(port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    base = f"http://{host}:{port}"
    yield base
    server.shutdown()
    thread.join(timeout=5)


def test_api_stacks_liste(server_url):
    status, body, _ = _get(server_url, "/api/stacks")
    assert status == 200
    data = json.loads(body)
    assert isinstance(data, list)
    assert len(data) == 6
    ids = [s["id"] for s in data]
    expected = [
        "agentique",
        "assistant-entreprise",
        "automatisation",
        "mlops",
        "support-conversationnel",
        "tout-en-un",
    ]
    assert ids == expected
    assert ids[-1] == "tout-en-un"
    for s in data:
        assert s["n_deploy"] > 0
        assert s["defaults"]["S4"] == "litellm"


def test_api_stack_detail(server_url):
    status, body, _ = _get(server_url, "/api/stacks/agentique")
    assert status == 200
    profile = json.loads(body)
    assert profile["id"] == "agentique"
    assert profile["deploy_by_sphere"]
    s5 = profile["deploy_by_sphere"]["S5"]
    assert "hermes-agent" in s5
    assert "superpowers" in s5
    assert profile["wiring"]


def test_api_stack_inconnu(server_url):
    status, _, _ = _get(server_url, "/api/stacks/xyz")
    assert status == 404


def test_api_spheres(server_url):
    status, body, _ = _get(server_url, "/api/spheres")
    assert status == 200
    spheres = json.loads(body)
    assert len(spheres) == 14
    nums = [s["num"] for s in spheres]
    assert nums == sorted(nums)
    total = sum(s["count"] for s in spheres)
    catalogue = json.loads(Path(catalogue_path()).read_text(encoding="utf-8"))
    entries = catalogue["entries"]
    assert total == len(entries)
    for s in spheres:
        assert s["count"] > 0


def test_accueil_contient_stacks(server_url):
    """Le HTML statique porte le conteneur ; les cartes sont rendues par app.js
    (données via /api/stacks) — on vérifie le contrat réel des deux côtés."""
    status, body, _ = _get(server_url, "/")
    assert status == 200
    assert 'id="stacks"' in body
    assert "stacks-grid" in body
    status_js, js, _ = _get(server_url, "/app.js")
    assert status_js == 200
    assert "stack-card" in js  # le renderer crée les cartes
    assert "/api/stacks" in js  # alimentées par l'API


def test_routes_b02a_intactes(server_url):
    status, body, _ = _get(server_url, "/api/detect")
    assert status == 200
    detect = json.loads(body)
    assert "cpu_model" in detect

    status, _, _ = _get(server_url, "/api/health")
    assert status == 200

    status, _, _ = _get(server_url, "/nope")
    assert status == 404


def test_auto_suffisance_assets():
    import forgeai.web.server as server_mod

    assets_dir = Path(server_mod.__file__).resolve().parent / "assets"
    for name in ("index.html", "app.css", "app.js"):
        text = (assets_dir / name).read_text(encoding="utf-8")
        assert "http://" not in text
        assert "https://" not in text
