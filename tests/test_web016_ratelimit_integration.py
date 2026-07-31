"""Tests d'intégration rate limiting / anti-bruteforce avec un serveur live (WEB-016)."""

import json
import threading
import urllib.error
import urllib.request

import pytest

import forgeai.web.server as web_server
from forgeai.web.ratelimit import RateLimiter
from forgeai.web.server import build_server


def _get(base_url: str, path: str = "/api/health"):
    req = urllib.request.Request(base_url + path)
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, resp.read(), dict(resp.headers)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), dict(exc.headers)


def _post(base_url: str, path: str, headers: dict, body: dict | None = None):
    data = json.dumps(body or {}).encode("utf-8")
    req = urllib.request.Request(
        base_url + path, data=data, method="POST",
        headers={"Content-Type": "application/json", **headers},
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, resp.read(), dict(resp.headers)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), dict(exc.headers)


@pytest.fixture()
def live_non_loopback():
    srv = build_server("0.0.0.0", 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    yield base, srv
    srv.shutdown()
    srv.server_close()


@pytest.fixture()
def live_loopback():
    srv = build_server("127.0.0.1", 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    yield base, srv
    srv.shutdown()
    srv.server_close()


def test_rate_limit_429_hors_loopback(live_non_loopback, monkeypatch):
    """Au-delà de rate_max requêtes depuis une IP NON-loopback → 429 + Retry-After.

    Le client de test se connecte via 127.0.0.1 (loopback) : on force `_is_loopback_host` à False
    pour simuler un vrai client réseau, sinon le bucket global l'exempterait.
    """
    base, srv = live_non_loopback
    monkeypatch.setattr(web_server, "_is_loopback_host", lambda ip: False)
    srv.forgeai_rate_limiter = RateLimiter(rate_max=2, rate_window_s=60.0)

    for _ in range(2):
        code, _, _ = _get(base)
        assert code == 200
    code, body, headers = _get(base)
    assert code == 429
    assert "rate_limited" in body.decode()
    assert "Retry-After" in headers


def test_loopback_non_limite(live_loopback):
    """En loopback, le bucket global ne bloque jamais, même à haut volume."""
    base, srv = live_loopback
    srv.forgeai_rate_limiter = RateLimiter(rate_max=1, rate_window_s=60.0)
    for _ in range(5):
        code, _, _ = _get(base)
        assert code == 200


def test_bruteforce_lockout(live_non_loopback):
    """auth_max échecs 401 depuis une IP → lockout : le bon jeton ensuite reçoit 429.

    L'anti-bruteforce s'applique même en loopback (le client de test est 127.0.0.1), ce qui couvre
    le déploiement derrière un proxy local.
    """
    base, srv = live_non_loopback
    token = "jeton-de-test-proof"  # proof:allow
    srv.forgeai_auth_value = token
    srv.forgeai_rate_limiter = RateLimiter(rate_max=100, auth_max=2, auth_window_s=600.0, lockout_s=900.0)

    for _ in range(2):
        code, _, _ = _post(base, "/api/deploy", {"Authorization": "Bearer mauvais-jeton"})  # proof:allow
        assert code == 401
    code, body, headers = _post(base, "/api/deploy", {"Authorization": f"Bearer {token}"})
    assert code == 429
    assert "rate_limited" in body.decode()
    assert "Retry-After" in headers


def test_non_regression_health_ok(live_non_loopback):
    """Trafic normal : une requête /api/health → 200 (rate limiter par défaut n'impacte pas)."""
    base, srv = live_non_loopback
    code, _, _ = _get(base, "/api/health")
    assert code == 200
