"""WEB-034A — en-têtes de sécurité + suppression de la bannière Python."""

from __future__ import annotations

import threading
import urllib.error
import urllib.request

import pytest

from forgeai.web.server import build_server


def _headers(base: str, path: str) -> dict:
    """GET *path* et retourne les en-têtes (capture aussi les 4xx/5xx : l'override
    end_headers doit injecter les en-têtes de sécurité sur toute réponse)."""
    url = f"{base}{path}"
    try:
        resp = urllib.request.urlopen(url, timeout=5)
    except urllib.error.HTTPError as e:
        return dict(e.headers)
    with resp:
        return dict(resp.headers)


@pytest.fixture()
def live():
    """Serveur live loopback (miroir de tests/test_web_auth.py)."""
    srv = build_server("127.0.0.1", 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]
    yield f"http://127.0.0.1:{port}", port
    srv.shutdown()
    srv.server_close()


def test_headers_securite_sur_html(live) -> None:
    """GET / → tous les en-têtes de sécurité présents."""
    base_url, _port = live
    headers = _headers(base_url, "/")
    assert headers.get("X-Content-Type-Options") == "nosniff"
    assert headers.get("X-Frame-Options") == "DENY"
    assert headers.get("Referrer-Policy") == "no-referrer"
    csp = headers.get("Content-Security-Policy", "")
    assert "default-src 'self'" in csp, f"default-src absent: {csp}"
    assert "script-src 'self'" in csp, f"script-src 'self' absent: {csp}"
    assert "frame-ancestors 'none'" in csp, f"frame-ancestors absent: {csp}"


def test_headers_securite_sur_json(live) -> None:
    """GET /api/health → mêmes en-têtes (override end_headers global, pas que le HTML)."""
    base_url, _port = live
    headers = _headers(base_url, "/api/health")
    assert headers.get("X-Content-Type-Options") == "nosniff"
    assert headers.get("X-Frame-Options") == "DENY"
    assert headers.get("Referrer-Policy") == "no-referrer"
    assert "Content-Security-Policy" in headers


def test_pas_de_banniere_python(live) -> None:
    """Le header Server ne contient PAS 'Python' et commence par 'ForgeAI'."""
    base_url, _port = live
    server = _headers(base_url, "/").get("Server", "")
    assert "Python" not in server, f"Bannière Python présente: {server}"
    assert server.startswith("ForgeAI"), f"Server inattendu: {server}"


def test_csp_compatible_ui(live) -> None:
    """La CSP n'autorise ni unsafe-eval globalement ni unsafe-inline dans script-src."""
    base_url, _port = live
    csp = _headers(base_url, "/").get("Content-Security-Policy", "")
    assert "unsafe-eval" not in csp, f"unsafe-eval présent: {csp}"
    start = csp.find("script-src ")
    assert start != -1, "script-src absent"
    directive = csp[start:].split(";", 1)[0]
    assert "unsafe-inline" not in directive, f"unsafe-inline dans script-src: {directive}"
    assert "'self'" in directive, f"'self' absent de script-src: {directive}"


def test_non_regression_ui_servie(live) -> None:
    """GET / → 200 et corps non vide (l'UI est toujours servie)."""
    base_url, _port = live
    with urllib.request.urlopen(f"{base_url}/", timeout=5) as resp:
        assert resp.status == 200
        assert len(resp.read()) > 0
