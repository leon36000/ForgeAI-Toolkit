"""Tests unitaires déterministes de RateLimiter (horloge factice, sans sleep)."""

import threading
import time

import pytest

from forgeai.web.ratelimit import RateLimiter


class MockClock:
    """Horloge contrôlable pour les tests."""

    def __init__(self, start: float = 0.0) -> None:
        self.t = start

    def __call__(self) -> float:
        return self.t


def test_constructeur_expose_ses_valeurs_par_defaut():
    rl = RateLimiter()

    assert rl.rate_max == 100
    assert rl.rate_window_s == 60.0
    assert rl.auth_max == 5
    assert rl.auth_window_s == 600.0
    assert rl.lockout_s == 900.0
    assert rl._evict_threshold == 4096


def test_bucket_autorise_sous_seuil():
    """Trois requêtes passent, la quatrième est bloquée par le bucket."""
    rl = RateLimiter(rate_max=3, rate_window_s=10.0, clock=MockClock())
    ip = "192.0.2.1"
    for _ in range(3):
        assert rl.check(ip, is_loopback=False) is None
    retry = rl.check(ip, is_loopback=False)
    assert isinstance(retry, float) and retry > 0


def test_bucket_recharge_apres_fenetre():
    """Après épuisement, un délai de rate_window_s rend un jeton disponible."""
    clock = MockClock()
    rl = RateLimiter(rate_max=1, rate_window_s=2.0, clock=clock)
    assert rl.check("192.0.2.1", is_loopback=False) is None
    assert rl.check("192.0.2.1", is_loopback=False) is not None
    clock.t += 2.0
    assert rl.check("192.0.2.1", is_loopback=False) is None


def test_bucket_recharge_partielle_est_calculable():
    """Une recharge partielle ne doit ni saturer ni autoriser trop tôt le bucket."""
    clock = MockClock()
    rl = RateLimiter(rate_max=2, rate_window_s=4.0, clock=clock)
    ip = "192.0.2.2"

    assert rl.check(ip, is_loopback=False) is None
    assert rl.check(ip, is_loopback=False) is None
    clock.t = 1.0
    assert rl.check(ip, is_loopback=False) == pytest.approx(1.0)
    assert rl._state[ip]["last_seen"] == 1.0


def test_recharge_repart_de_la_derniere_date_de_recharge():
    clock = MockClock()
    rl = RateLimiter(rate_max=2, rate_window_s=4.0, clock=clock)
    ip = "192.0.2.3"

    assert rl.check(ip, is_loopback=False) is None
    assert rl.check(ip, is_loopback=False) is None
    clock.t = 1.0
    assert rl.check(ip, is_loopback=False) is not None
    clock.t = 2.0
    assert rl.check(ip, is_loopback=False) is None
    clock.t = 3.0
    assert rl.check(ip, is_loopback=False) == pytest.approx(1.0)


def test_fenetre_de_recharge_unitaire_reste_active():
    clock = MockClock()
    rl = RateLimiter(rate_max=2, rate_window_s=1.0, clock=clock)
    ip = "192.0.2.4"

    assert rl.check(ip, is_loopback=False) is None
    assert rl.check(ip, is_loopback=False) is None
    clock.t = 0.25
    assert rl.check(ip, is_loopback=False) == pytest.approx(0.25)


def test_loopback_exempt_du_bucket():
    """Les requêtes loopback ne sont jamais freinées par le bucket."""
    rl = RateLimiter(rate_max=1, clock=MockClock())
    for _ in range(100):
        assert rl.check("127.0.0.1", is_loopback=True) is None


def test_auth_lockout_apres_seuil():
    """Après auth_max échecs, le lockout bloque MÊME en loopback."""
    rl = RateLimiter(auth_max=3, auth_window_s=600.0, lockout_s=900.0, clock=MockClock())
    ip = "10.0.0.5"
    for _ in range(3):
        rl.record_auth_failure(ip)
    retry = rl.check(ip, is_loopback=False)
    assert isinstance(retry, float) and retry > 0
    retry_lb = rl.check(ip, is_loopback=True)
    assert isinstance(retry_lb, float) and retry_lb > 0


def test_lockout_expire():
    """Après expiration du lockout, la requête redevient None."""
    clock = MockClock()
    rl = RateLimiter(auth_max=1, auth_window_s=60.0, lockout_s=10.0, clock=clock)
    ip = "10.1.0.2"
    rl.record_auth_failure(ip)
    assert rl.check(ip, is_loopback=False) is not None
    clock.t += 10.0
    assert rl.check(ip, is_loopback=False) is None


def test_rate_max_unitaire_recharge_partielle_ne_contourne_pas_la_garde():
    clock = MockClock()
    rl = RateLimiter(rate_max=1, rate_window_s=2.0, clock=clock)
    ip = "10.1.0.3"

    assert rl.check(ip, is_loopback=False) is None
    clock.t = 1.0
    assert rl.check(ip, is_loopback=False) == pytest.approx(1.0)


def test_echecs_hors_fenetre_ne_lockout_pas():
    """Des échecs espacés au-delà de la fenêtre glissante ne déclenchent pas de lockout."""
    clock = MockClock()
    rl = RateLimiter(auth_max=3, auth_window_s=30.0, lockout_s=60.0, clock=clock)
    ip = "10.2.0.3"
    for _ in range(2):
        rl.record_auth_failure(ip)
    clock.t += 31.0
    for _ in range(2):
        rl.record_auth_failure(ip)
    assert rl.check(ip, is_loopback=False) is None


def test_echec_exactement_a_la_limite_est_hors_fenetre():
    clock = MockClock()
    rl = RateLimiter(auth_max=2, auth_window_s=30.0, lockout_s=60.0, clock=clock)
    ip = "10.2.0.4"

    rl.record_auth_failure(ip)
    clock.t = 30.0
    rl.record_auth_failure(ip)

    assert rl.check(ip, is_loopback=False) is None


def test_lockout_ne_reset_pas_sur_succes():
    """Bloqué pendant le lockout ; après expiration, relâchement définitif sans réarmement."""
    clock = MockClock()
    rl = RateLimiter(auth_max=1, auth_window_s=30.0, lockout_s=5.0, clock=clock)
    ip = "10.3.0.4"
    rl.record_auth_failure(ip)
    assert rl.check(ip, is_loopback=False) is not None
    clock.t += 3.0
    assert rl.check(ip, is_loopback=False) is not None
    clock.t += 2.0  # total = 5.0
    assert rl.check(ip, is_loopback=False) is None
    clock.t += 1.0
    assert rl.check(ip, is_loopback=False) is None


def test_echec_rafraichit_last_seen_avant_toute_requete():
    clock = MockClock()
    rl = RateLimiter(auth_max=3, clock=clock)
    ip = "10.3.0.5"

    rl.check(ip, is_loopback=True)
    clock.t = 4.0
    rl.record_auth_failure(ip)

    assert rl._state[ip]["last_seen"] == 4.0


def test_rate_max_zero_retourne_la_fenetre_de_reessai_exacte():
    rl = RateLimiter(rate_max=0, rate_window_s=0.5, clock=MockClock())

    assert rl.check("203.0.113.8", is_loopback=False) == pytest.approx(0.5)


def test_thread_safety():
    """Appels concurrents massifs (dict partagé) : aucune exception, limites par IP respectées."""
    rate_max = 10
    rl = RateLimiter(rate_max=rate_max, rate_window_s=3600.0, clock=time.monotonic)
    results: dict = {}
    results_lock = threading.Lock()

    def stress(ip: str):
        local = [rl.check(ip, is_loopback=False) for _ in range(rate_max * 2)]
        with results_lock:
            results[ip] = local

    threads = [threading.Thread(target=stress, args=(f"192.0.2.{i}",)) for i in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    for ip, rets in results.items():
        none_count = sum(1 for r in rets if r is None)
        assert none_count <= rate_max, f"{ip}: {none_count} None > max {rate_max}"
        assert any(r is not None for r in rets), f"{ip}: aucun rejet alors que bucket saturé"


def test_eviction_preserve_lockout():
    """Une IP en lockout ACTIF n'est jamais purgée par l'éviction, même devenue inactive.

    Détecteur réel : le seuil d'inactivité (max(rate_window, auth_window)=100) est distinct et plus
    court que lockout_s (1000). On avance l'horloge à 150 : l'IP verrouillée est inactive depuis
    150 s (> 100) MAIS son lockout court jusqu'à 1000. Sans la garde `locked_until > now`, elle serait
    purgée et son bannissement perdu → le test tomberait.
    """
    clock = MockClock()
    rl = RateLimiter(
        rate_max=10, auth_max=2, auth_window_s=100.0, rate_window_s=60.0,
        lockout_s=1000.0, clock=clock,
    )
    rl._evict_threshold = 3  # seuil bas pour forcer l'éviction

    ip_lock = "10.99.99.99"
    for _ in range(2):
        rl.record_auth_failure(ip_lock)  # locked_until = 1000, last_seen = 0

    clock.t = 150.0  # > idle (100) mais < lockout (1000)
    # Sature la table pour déclencher l'éviction (chaque check purge les entrées périmées non verrouillées).
    for i in range(6):
        rl.check(f"203.0.113.{i}", is_loopback=False)

    retry = rl.check(ip_lock, is_loopback=False)
    assert isinstance(retry, float) and retry > 0, "lockout actif indûment purgé par l'éviction"


# ---------------------------------------------------------------------------
# Bug hunt (issue #531) : rate_max=0 ou rate_window_s=0 -> ZeroDivisionError sur toute
# requête distante (le token-bucket divise par ces valeurs sans garde).
# ---------------------------------------------------------------------------

def test_rate_max_zero_ne_leve_pas_zerodivisionerror():
    """rate_max=0 (constructeur direct) ne doit jamais faire planter check() — 429 propre."""
    rl = RateLimiter(rate_max=0, rate_window_s=60.0, clock=MockClock())
    retry = rl.check("203.0.113.5", is_loopback=False)
    assert isinstance(retry, float) and retry > 0, (
        "rate_max=0 doit rejeter proprement (retry > 0), pas planter"
    )


def test_rate_window_s_zero_ne_leve_pas_zerodivisionerror():
    """rate_window_s=0.0 ne doit jamais faire planter check() non plus (2e division, ligne 92)."""
    rl = RateLimiter(rate_max=5, rate_window_s=0.0, clock=MockClock())
    ip = "203.0.113.6"
    # Épuise le bucket initial pour retomber sur la branche de recharge (ligne 92).
    for _ in range(5):
        rl.check(ip, is_loopback=False)
    retry = rl.check(ip, is_loopback=False)
    assert isinstance(retry, float) and retry > 0


def test_from_env_rate_max_zero_ne_leve_pas(monkeypatch):
    """FORGEAI_RATE_MAX=0 (variable documentée, geste d'opérateur plausible) ne doit jamais
    faire planter une requête distante — même défaut atteint par la voie réellement utilisée
    en production (RateLimiter.from_env(), pas seulement le constructeur direct)."""
    monkeypatch.setenv("FORGEAI_RATE_MAX", "0")
    rl = RateLimiter.from_env()
    retry = rl.check("203.0.113.7", is_loopback=False)
    assert isinstance(retry, float) and retry > 0


def test_from_env_charge_tous_les_parametres(monkeypatch):
    valeurs = {
        "FORGEAI_RATE_MAX": "7",
        "FORGEAI_RATE_WINDOW_S": "12.5",
        "FORGEAI_AUTH_MAX": "4",
        "FORGEAI_AUTH_WINDOW_S": "33.5",
        "FORGEAI_LOCKOUT_S": "44.5",
    }
    for cle, valeur in valeurs.items():
        monkeypatch.setenv(cle, valeur)

    rl = RateLimiter.from_env()

    assert rl.rate_max == 7
    assert rl.rate_window_s == 12.5
    assert rl.auth_max == 4
    assert rl.auth_window_s == 33.5
    assert rl.lockout_s == 44.5


def test_from_env_valeurs_invalides_reprennent_les_defauts(monkeypatch):
    for cle in (
        "FORGEAI_RATE_MAX",
        "FORGEAI_RATE_WINDOW_S",
        "FORGEAI_AUTH_MAX",
        "FORGEAI_AUTH_WINDOW_S",
        "FORGEAI_LOCKOUT_S",
    ):
        monkeypatch.setenv(cle, "pas-un-nombre")

    rl = RateLimiter.from_env()

    assert rl.rate_max == 100
    assert rl.rate_window_s == 60.0
    assert rl.auth_max == 5
    assert rl.auth_window_s == 600.0
    assert rl.lockout_s == 900.0


def test_lockout_retourne_le_temps_restant_exact_et_rafraichit_l_activite():
    clock = MockClock()
    rl = RateLimiter(auth_max=1, lockout_s=10.0, clock=clock)
    ip = "10.4.0.1"
    rl.record_auth_failure(ip)

    clock.t = 3.0
    assert rl.check(ip, is_loopback=True) == pytest.approx(7.0)
    assert rl._state[ip]["last_seen"] == 3.0


def test_loopback_cree_et_rafraichit_l_etat():
    clock = MockClock()
    rl = RateLimiter(clock=clock)
    ip = "127.0.0.2"

    assert rl.check(ip, is_loopback=True) is None
    assert rl._state[ip]["last_seen"] == 0.0
    clock.t = 8.0
    assert rl.check(ip, is_loopback=True) is None
    assert rl._state[ip]["last_seen"] == 8.0


def test_eviction_ne_se_declenche_pas_au_seuil_exact():
    clock = MockClock(start=10.0)
    rl = RateLimiter(rate_window_s=1.0, auth_window_s=1.0, clock=clock)
    rl._evict_threshold = 2
    rl.check("203.0.113.10", is_loopback=True)
    rl.check("203.0.113.11", is_loopback=True)
    clock.t = 200.0

    rl._maybe_evict()

    assert len(rl._state) == 2


def test_eviction_respecte_exactement_la_duree_d_inactivite():
    clock = MockClock(start=10.0)
    rl = RateLimiter(rate_window_s=100.0, auth_window_s=100.0, clock=clock)
    rl._evict_threshold = 0
    rl.check("203.0.113.12", is_loopback=True)
    clock.t = 110.0

    rl._maybe_evict()

    assert "203.0.113.12" in rl._state


def test_eviction_supprime_un_lockout_arrive_a_echeance():
    clock = MockClock(start=0.0)
    rl = RateLimiter(rate_window_s=1.0, auth_window_s=1.0, clock=clock)
    rl._evict_threshold = 0
    rl.record_auth_failure("203.0.113.13")
    rl._state["203.0.113.13"]["locked_until"] = 10.0
    rl._state["203.0.113.13"]["last_seen"] = 0.0
    clock.t = 10.0

    rl._maybe_evict()

    assert "203.0.113.13" not in rl._state
