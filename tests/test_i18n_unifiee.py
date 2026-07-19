import importlib.resources
import json
import threading
import urllib.error
import urllib.request

import pytest

from forgeai.web.server import build_server


@pytest.fixture
def server_url():
    server = build_server("127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _get_json(url):
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        # 4xx = contrat testé : retourner, pas lever
        return exc.code, json.loads(exc.read().decode("utf-8"))


def test_api_i18n_fr_en(server_url):
    fr_status, fr_body = _get_json(f"{server_url}/api/i18n/fr")
    en_status, en_body = _get_json(f"{server_url}/api/i18n/en")

    assert fr_status == 200
    assert en_status == 200
    assert isinstance(fr_body, dict)
    assert isinstance(en_body, dict)

    assert len(fr_body) >= 90
    assert len(en_body) >= 90

    fr_keys = set(fr_body.keys())
    en_keys = set(en_body.keys())
    assert fr_keys == en_keys

    assert all(isinstance(v, str) and v for v in fr_body.values())
    assert all(isinstance(v, str) and v for v in en_body.values())


def test_api_i18n_inconnu(server_url):
    status, body = _get_json(f"{server_url}/api/i18n/de")
    assert status == 404
    assert isinstance(body, dict)
    assert "error" in body


def test_source_unique(server_url):
    for lang in ("fr", "en"):
        _, api_body = _get_json(f"{server_url}/api/i18n/{lang}")
        raw = importlib.resources.files("forgeai.data") / "locales" / f"{lang}.json"
        data = json.loads(raw.read_text(encoding="utf-8"))
        web = data["web"]

        assert set(api_body.keys()) == set(web.keys())
        for key in web:
            assert api_body[key] == web[key]


def test_cles_cli_intactes():
    raw = importlib.resources.files("forgeai.data") / "locales" / "fr.json"
    data = json.loads(raw.read_text(encoding="utf-8"))

    assert any(k.startswith("wizard.") for k in data.keys())
    assert isinstance(data.get("web"), dict)
