"""WEB-017 : politique d'accès aux lectures sensibles (GET /api/* hors santé et i18n).
Les GET sensibles réutilisent la même garde que les mutations — jeton, anti-rebinding Host.
Tests RED avant implémentation, doivent tomber si la garde est absente de do_GET."""

import secrets
import threading
import urllib.error
import urllib.request

import pytest

import forgeai.web.server as web_server
from forgeai.web.server import build_server, _is_sensitive_read_path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get(base, path, headers=None):
    """GET HTTP avec urllib, retourne (status_code, body_bytes)."""
    req = urllib.request.Request(base + path, method="GET", headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


# ---------------------------------------------------------------------------
# Fixtures (miroir du style test_web_auth.py)
# ---------------------------------------------------------------------------

@pytest.fixture()
def live_loopback():
    """Serveur loopback sans jeton, port libre, thread daemon."""
    srv = build_server("127.0.0.1", 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]
    yield f"http://127.0.0.1:{port}", port
    srv.shutdown()
    srv.server_close()


@pytest.fixture()
def live_non_loopback():
    """Serveur bind 0.0.0.0, accédé via loopback pour le test. Sans jeton par défaut."""
    srv = build_server("0.0.0.0", 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    yield base, srv
    srv.shutdown()
    srv.server_close()


@pytest.fixture()
def live_non_loopback_with_token(monkeypatch):
    """Serveur bind 0.0.0.0 AVEC jeton configuré via monkeypatch._WEB_TOKEN."""
    configured_token = secrets.token_urlsafe(32)
    monkeypatch.setattr(web_server, "_WEB_TOKEN", configured_token)
    srv = build_server("0.0.0.0", 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    yield base, configured_token, srv
    srv.shutdown()
    srv.server_close()


# ---------------------------------------------------------------------------
# Tests de classification (unitaire, sans serveur)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path, expected", [
    ("/api/detect", True),
    ("/api/models", True),
    ("/api/models/local", True),
    ("/api/nodes/status", True),
    ("/api/stacks", True),
    ("/api/spheres", True),
    ("/", False),
    ("/index.html", False),
    ("/app.js", False),
    ("/app.css", False),
    ("/api/health", False),
    ("/api/i18n/fr", False),
])
def test_is_sensitive_read_path_classification(path, expected):
    assert _is_sensitive_read_path(path) == expected


# ---------------------------------------------------------------------------
# Tests de comportement (live)
# ---------------------------------------------------------------------------

def test_get_public_health_sans_jeton_200(live_loopback):
    """/api/health est public, accessible sans jeton en loopback."""
    base, _ = live_loopback
    code, _ = _get(base, "/api/health")
    assert code == 200, f"Santé doit être publique, reçu {code}"


def test_get_public_asset_sans_jeton_200(live_loopback):
    """Asset statique hors /api/ ne doit jamais être refusé."""
    base, _ = live_loopback
    code, _ = _get(base, "/app.css")
    # 200 si l'asset existe, 404 si absent — mais pas 401/403
    assert code not in (401, 403), f"Asset public ne doit pas être refusé, reçu {code}"


def test_get_public_i18n_sans_jeton_200(live_loopback):
    """Les traductions /api/i18n/* sont explicitement exclues de la garde."""
    base, _ = live_loopback
    code, _ = _get(base, "/api/i18n/fr")
    assert code == 200, f"i18n doit être public, reçu {code}"


def test_get_sensible_loopback_sans_jeton_200(live_loopback):
    """En loopback sans jeton configuré, un GET sensible doit passer (UI locale)."""
    base, _ = live_loopback
    code, _ = _get(base, "/api/detect")
    assert code == 200, f"GET sensible loopback sans jeton doit être autorisé, reçu {code}"


def test_get_sensible_hors_loopback_sans_jeton_401(live_non_loopback):
    """Bind non‑loopback sans jeton → 401 pour toute lecture sensible."""
    base, srv = live_non_loopback
    code, _ = _get(base, "/api/detect")
    assert code == 401, f"GET sensible hors loopback sans jeton doit être 401, reçu {code}"


def test_get_sensible_hors_loopback_bearer_valide_200(live_non_loopback_with_token):
    """Bind non‑loopback avec jeton → le Bearer valide autorise le GET sensible."""
    base, token, srv = live_non_loopback_with_token
    headers = {"Authorization": f"Bearer {token}"}
    code, _ = _get(base, "/api/detect", headers=headers)
    assert code == 200, f"GET sensible authentifié doit être 200, reçu {code}"


def test_get_rebinding_host_evil_403(live_loopback):
    """Même en loopback, un Host non autorisé sur un GET sensible → 403 (anti-DNS-rebinding)."""
    base, _ = live_loopback
    headers = {"Host": "evil.example"}
    code, _ = _get(base, "/api/detect", headers=headers)
    assert code == 403, f"Host de rebinding doit être refusé sur GET sensible, reçu {code}"


def test_garde_reellement_en_tete_do_GET_detection_vive():
    """Test LIVE : classification précise — /api/health reste 200 même avec un Host malveillant,
    alors que /api/detect avec le même Host → 403. Prouve que la garde est insérée avant les
    routes et discriminée par la classification, pas un rejet global."""
    srv = build_server("127.0.0.1", 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        headers = {"Host": "evil.example"}
        code_sensible, _ = _get(base, "/api/detect", headers=headers)
        code_public, _ = _get(base, "/api/health", headers=headers)
    finally:
        srv.shutdown()
        srv.server_close()

    assert code_sensible == 403, f"GET sensible avec Host evil → 403, reçu {code_sensible}"
    assert code_public == 200, f"GET public /api/health avec Host evil reste 200, reçu {code_public}"


# ---------------------------------------------------------------------------
# Non-régression : les GET publics ne sont jamais affectés
# ---------------------------------------------------------------------------

def test_get_root_sans_jeton_200(live_loopback):
    base, _ = live_loopback
    code, _ = _get(base, "/")
    assert code == 200


def test_get_index_html_sans_jeton_200(live_loopback):
    base, _ = live_loopback
    code, _ = _get(base, "/index.html")
    assert code == 200
