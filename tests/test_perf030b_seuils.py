"""PERF-030B — seuils de non-régression des performances de /api/detect.

Le détecteur PRIMAIRE est le TRAVAIL effectué (nombre de sondes matérielles), qui est déterministe :
avec cache, une rafale de N requêtes ne coûte qu'UNE sonde ; sans cache, elle en coûterait N.
Le temps n'est qu'un filet grossier SECONDAIRE (un seuil purement chronométrique flake sur des
runners CI partagés, et un test qui flake finit désactivé — donc ne protège plus rien).
Verrouille le cache TTL (OPT-001) et son invalidation ponctuelle (PERF-030A).
"""

import threading
import time
import urllib.request

import pytest

import forgeai.web.server as server

# ---------------------------------------------------------------------------
# Seuils de non-régression (constantes nommées, pas de nombres magiques)
# ---------------------------------------------------------------------------
N_REQUETES = 20             # taille de la rafale sur /api/detect
SONDES_MAX_RAFALE = 1       # SEUIL PRIMAIRE : une rafale entière ne coûte qu'une sonde (cache TTL)
SONDES_MAX_PAR_REFRESH = 1  # un refresh = exactement une re-sonde (pas d'amplification)
PLAFOND_P95_S = 1.0         # filet CHRONO généreux ; jamais la garde principale
PLAFOND_P95_MAX_S = 5.0     # borne HAUTE du filet : au-delà il ne mesurerait plus rien (cf. CA5)


class FakeReport:
    def to_json(self):
        return '{"cpu": "fake"}'


class FakeDetector:
    """Détecteur factice : compte les sondes et simule un coût (~20 ms) pour rendre le gain visible."""

    call_count = 0

    def __init__(self, *args, **kwargs):
        del args, kwargs  # injection du runner ignorée par le faux détecteur

    def full_report(self):
        FakeDetector.call_count += 1
        time.sleep(0.02)
        return FakeReport()


@pytest.fixture(autouse=True)
def _reset_et_purge():
    """Le cache matériel est un état MODULE : purger + remettre le compteur à zéro isole chaque test."""
    server._hardware_cache_clear()
    FakeDetector.call_count = 0
    yield
    server._hardware_cache_clear()
    FakeDetector.call_count = 0


@pytest.fixture()
def live(monkeypatch):
    """Serveur loopback (port dynamique) avec le faux détecteur injecté."""
    monkeypatch.setattr(server, "HardwareDetector", FakeDetector)
    srv = server.build_server("127.0.0.1", 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()
    srv.server_close()


def _get(url, path):
    with urllib.request.urlopen(f"{url}{path}", timeout=10) as resp:
        return resp.status, resp.read().decode("utf-8")


def _post(url, path):
    req = urllib.request.Request(f"{url}{path}", method="POST", data=b"")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.status, resp.read().decode("utf-8")


# ---------------------------------------------------------------------------
# Seuils PRIMAIRES (déterministes)
# ---------------------------------------------------------------------------

def test_rafale_ne_sonde_quune_fois(live):
    """CA1 : une rafale de N_REQUETES GET /api/detect ne coûte qu'UNE sonde matérielle."""
    for _ in range(N_REQUETES):
        code, _ = _get(live, "/api/detect")
        assert code == 200, f"GET /api/detect a échoué (code {code})"

    assert FakeDetector.call_count <= SONDES_MAX_RAFALE, (
        f"RÉGRESSION perf /api/detect : {FakeDetector.call_count} sondes pour {N_REQUETES} "
        f"requêtes, seuil {SONDES_MAX_RAFALE} (le cache TTL est-il cassé ?)"
    )


def test_refresh_coute_exactement_une_sonde(live):
    """CA2 : POST /api/detect/refresh ne déclenche qu'une seule re-sonde."""
    _get(live, "/api/detect")  # cache chaud → état déterministe
    avant = FakeDetector.call_count

    code, _ = _post(live, "/api/detect/refresh")
    assert code == 200, f"POST refresh a échoué (code {code})"

    assert FakeDetector.call_count - avant == SONDES_MAX_PAR_REFRESH, (
        f"RÉGRESSION perf refresh : {FakeDetector.call_count - avant} sondes, "
        f"seuil {SONDES_MAX_PAR_REFRESH}"
    )


def test_rafale_apres_refresh_reste_bornee(live):
    """CA2 : après un refresh, le cache est de nouveau chaud — aucune sonde supplémentaire."""
    _post(live, "/api/detect/refresh")
    apres_refresh = FakeDetector.call_count

    for _ in range(N_REQUETES):
        code, _ = _get(live, "/api/detect")
        assert code == 200

    assert FakeDetector.call_count == apres_refresh, (
        f"RÉGRESSION perf après refresh : +{FakeDetector.call_count - apres_refresh} sondes, "
        f"attendu 0 (le cache aurait dû absorber les {N_REQUETES} GET)"
    )


# ---------------------------------------------------------------------------
# Filet SECONDAIRE (chronométrique)
# ---------------------------------------------------------------------------

def test_p95_sous_plafond(live):
    """CA3 : le p95 des N_REQUETES GET reste sous PLAFOND_P95_S.

    Ce test NE remplace PAS les seuils déterministes ci-dessus : il n'existe que pour attraper une
    dégradation grossière SANS rapport avec le cache (boucle lente, parsing excessif). Son seuil est
    volontairement large (1 s) pour ne jamais flaker sur un runner CI chargé.
    """
    _get(live, "/api/detect")  # cache chaud avant mesure
    temps = []
    for _ in range(N_REQUETES):
        debut = time.perf_counter()
        code, _ = _get(live, "/api/detect")
        temps.append(time.perf_counter() - debut)
        assert code == 200

    ordonnes = sorted(temps)
    p95 = ordonnes[max(0, int(len(ordonnes) * 0.95) - 1)]
    assert p95 < PLAFOND_P95_S, (
        f"filet chrono : p95 des {N_REQUETES} requêtes = {p95:.3f} s ≥ {PLAFOND_P95_S} s"
    )


# ---------------------------------------------------------------------------
# Intégrité des seuils (empêche une neutralisation silencieuse)
# ---------------------------------------------------------------------------

def test_les_seuils_sont_coherents():
    """CA5 : les seuils existent et restent significatifs (on ne peut pas les vider en silence)."""
    assert SONDES_MAX_RAFALE >= 1, "seuil trop bas (un premier GET exige forcément 1 sonde)"
    assert N_REQUETES > SONDES_MAX_RAFALE, (
        f"N_REQUETES ({N_REQUETES}) doit dépasser le seuil ({SONDES_MAX_RAFALE}) "
        "pour que le test soit significatif"
    )
    assert SONDES_MAX_PAR_REFRESH >= 1
    # Bornes HAUTE et basse : sans plafond, un futur portage de PLAFOND_P95_S à une valeur absurde
    # (ex. 3600 s) neutraliserait le filet chrono en silence — ce que CA5 doit précisément empêcher.
    assert 0 < PLAFOND_P95_S <= PLAFOND_P95_MAX_S, (
        f"PLAFOND_P95_S ({PLAFOND_P95_S} s) hors bornes : doit rester dans ]0, {PLAFOND_P95_MAX_S}] "
        "pour que le filet chrono garde un sens"
    )
