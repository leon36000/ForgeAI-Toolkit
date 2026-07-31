"""Tests unitaires déterministes de RateLimiter (horloge factice, sans sleep)."""

import threading
import time

from forgeai.web.ratelimit import RateLimiter


class MockClock:
    """Horloge contrôlable pour les tests."""

    def __init__(self, start: float = 0.0) -> None:
        self.t = start

    def __call__(self) -> float:
        return self.t


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
