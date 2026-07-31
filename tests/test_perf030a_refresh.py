"""PERF-030A — invalidation matérielle atteignable en production.

Le cache matériel TTL (OPT-001) existe déjà mais sa purge `_hardware_cache_clear()` n'avait aucun
appelant de production. `POST /api/detect/refresh` la rend atteignable : ces tests prouvent que le
refresh force une re-sonde, qu'il renvoie le rapport frais, et qu'il hérite bien des gardes de
mutation (aucune re-sonde n'est déclenchée par une requête refusée = pas d'amplification).
"""

import json
import threading
import urllib.error
import urllib.request

import pytest

import forgeai.web.server as server


def _get(base, path, headers=None):
    req = urllib.request.Request(base + path, method="GET", headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def _post(base, path, headers=None, body=None):
    data = json.dumps(body or {}).encode()
    req = urllib.request.Request(
        base + path, data=data, method="POST",
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


class FakeReport:
    """Objet imitant le rapport matériel, avec .to_json()."""

    def to_json(self):
        return '{"cpu": "fake"}'


class FakeDetector:
    """Détecteur qui incrémente un compteur à chaque full_report() (observe les re-sondes)."""

    call_count = 0

    def __init__(self, runner):
        del runner  # injection ignorée

    def full_report(self):
        FakeDetector.call_count += 1
        return FakeReport()


@pytest.fixture(autouse=True)
def _purge_cache_materiel():
    """Le cache matériel est un état MODULE : le purger avant/après isole chaque test."""
    server._hardware_cache_clear()
    yield
    server._hardware_cache_clear()


@pytest.fixture(autouse=True)
def _reset_compteur():
    FakeDetector.call_count = 0
    yield


@pytest.fixture()
def live(monkeypatch):
    """Serveur loopback sans jeton, détecteur factice."""
    monkeypatch.setattr(server, "HardwareDetector", FakeDetector)
    srv = server.build_server("127.0.0.1", 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()
    srv.server_close()


@pytest.fixture()
def live_non_loopback(monkeypatch):
    """Serveur lié 0.0.0.0 AVEC jeton configuré (l'autorisation est donc exigée)."""
    jeton = "jeton-de-test-perf030a"  # proof:allow
    monkeypatch.setattr(server, "_WEB_TOKEN", jeton)
    monkeypatch.setattr(server, "HardwareDetector", FakeDetector)
    srv = server.build_server("0.0.0.0", 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}", jeton
    srv.shutdown()
    srv.server_close()


def test_refresh_force_une_nouvelle_sonde(live):
    """CA1/CA2 : le cache sert le 2e GET, puis le refresh purge → une re-sonde a lieu."""
    base = live

    status, _ = _get(base, "/api/detect")
    assert status == 200
    assert FakeDetector.call_count == 1

    status2, _ = _get(base, "/api/detect")
    assert status2 == 200
    assert FakeDetector.call_count == 1, (
        f"cache OPT-001 non utilisé : compteur={FakeDetector.call_count} au lieu de 1"
    )

    status_r, body_r = _post(base, "/api/detect/refresh")
    assert status_r == 200
    assert FakeDetector.call_count == 2, (
        f"le refresh n'a pas forcé de re-sonde : compteur={FakeDetector.call_count} au lieu de 2"
    )
    assert isinstance(json.loads(body_r), dict)


def test_refresh_renvoie_le_rapport(live):
    """CA1 : le corps du refresh est bien le rapport frais (identique au GET qui suit)."""
    base = live
    status_r, body_r = _post(base, "/api/detect/refresh")
    assert status_r == 200
    status_g, body_g = _get(base, "/api/detect")
    assert status_g == 200
    assert body_r == body_g, "le rapport du refresh diffère du GET /api/detect"


def test_refresh_exige_le_jeton_hors_loopback(live_non_loopback):
    """CA3 : sans jeton (jeton configuré) → 401, et AUCUNE sonde (pas d'amplification)."""
    base, _jeton = live_non_loopback
    avant = FakeDetector.call_count

    status, _ = _post(base, "/api/detect/refresh")
    assert status == 401, f"attendu 401 sans jeton, reçu {status}"
    assert FakeDetector.call_count == avant, (
        "une sonde a été déclenchée alors que le refresh était refusé"
    )


def test_refresh_refuse_cross_site(live):
    """CA3 : la route hérite de l'anti-CSRF (Sec-Fetch-Site: cross-site → 403), sans sonde."""
    base = live
    avant = FakeDetector.call_count

    status, _ = _post(base, "/api/detect/refresh", headers={"Sec-Fetch-Site": "cross-site"})
    assert status == 403, f"attendu 403 pour cross-site, reçu {status}"
    assert FakeDetector.call_count == avant, "sonde déclenchée malgré le rejet cross-site"


def test_detect_get_inchange(live):
    """CA4 : GET /api/detect reste 200 (non-régression OPT-001)."""
    base = live
    status, body = _get(base, "/api/detect")
    assert status == 200
    assert isinstance(json.loads(body), dict)
