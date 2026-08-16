"""Rate limiting et protection anti-bruteforce pour le serveur HTTP ForgeAI (WEB-016).

Fournit la classe RateLimiter : token-bucket par IP (exemption loopback) et fenêtre glissante des
échecs 401 → lockout (actif même en loopback, pour couvrir un déploiement derrière un proxy local).
Les valeurs par défaut peuvent être surchargées via des variables d'environnement FORGEAI_RATE_*.
Horloge injectable → déterministe et testable sans sleep. Thread-safe (un seul threading.Lock ;
le serveur est ThreadingHTTPServer). Mémoire bornée par éviction paresseuse qui ne supprime JAMAIS
un lockout actif (sinon un attaquant réinitialiserait son bannissement en saturant la table).
"""

import os
import threading
import time
from typing import Optional


class RateLimiter:
    def __init__(
        self,
        *,
        rate_max: int = 100,
        rate_window_s: float = 60.0,
        auth_max: int = 5,
        auth_window_s: float = 600.0,
        lockout_s: float = 900.0,
        clock=time.monotonic,
    ) -> None:
        self.rate_max = rate_max
        self.rate_window_s = rate_window_s
        self.auth_max = auth_max
        self.auth_window_s = auth_window_s
        self.lockout_s = lockout_s
        self._clock = clock
        self._lock = threading.Lock()
        self._state: dict = {}  # ip → { tokens, last_refill, failures, locked_until, last_seen }
        self._evict_threshold = 4096
        # Seuil d'inactivité pour l'éviction : DISTINCT (plus court) que lockout_s, afin qu'une IP en
        # lockout actif mais silencieuse ne devienne "périmée" que par son inactivité SANS être
        # purgée — la garde `locked_until > now` est alors réellement porteuse (et testable).
        self._idle_evict_s = max(rate_window_s, auth_window_s)

    @classmethod
    def from_env(cls) -> "RateLimiter":
        def _int(key: str, default: int) -> int:
            try:
                return int(os.environ.get(key, ""))
            except (ValueError, TypeError):
                return default

        def _float(key: str, default: float) -> float:
            try:
                return float(os.environ.get(key, ""))
            except (ValueError, TypeError):
                return default

        return cls(
            rate_max=_int("FORGEAI_RATE_MAX", 100),
            rate_window_s=_float("FORGEAI_RATE_WINDOW_S", 60.0),
            auth_max=_int("FORGEAI_AUTH_MAX", 5),
            auth_window_s=_float("FORGEAI_AUTH_WINDOW_S", 600.0),
            lockout_s=_float("FORGEAI_LOCKOUT_S", 900.0),
        )

    def check(self, ip: str, *, is_loopback: bool) -> Optional[float]:
        """Retourne None si la requête est autorisée, sinon le délai (s, >0) avant réautorisation."""
        with self._lock:
            self._maybe_evict()
            now = self._clock()
            state = self._state.get(ip)

            # 1) lockout actif : prioritaire, MÊME en loopback.
            if state and state["locked_until"] > now:
                state["last_seen"] = now
                return state["locked_until"] - now

            # 2) loopback : exempt du bucket global (mais pas du lockout, traité ci-dessus).
            if is_loopback:
                if state is None:
                    self._state[ip] = self._init_state(now)
                else:
                    state["last_seen"] = now
                return None

            # 3) token-bucket par IP.
            if state is None:
                state = self._init_state(now)
                self._state[ip] = state
            elif self.rate_window_s > 0:
                # bug hunt (issue #531) : self.rate_window_s == 0 diviserait par zéro ici
                # (`FORGEAI_RATE_WINDOW_S=0`, variable documentée). Fenêtre nulle = pas de
                # recharge calculable proprement ; on ne fait juste rien avancer (les jetons
                # restent à leur valeur courante) plutôt que de planter.
                elapsed = now - state["last_refill"]
                state["tokens"] = min(
                    self.rate_max,
                    state["tokens"] + elapsed * (self.rate_max / self.rate_window_s),
                )
                state["last_refill"] = now
            state["last_seen"] = now

            if state["tokens"] >= 1.0:
                state["tokens"] -= 1.0
                return None
            if self.rate_max <= 0:
                # bug hunt (issue #531) : self.rate_max <= 0 diviserait par zéro ci-dessous.
                # rate_max <= 0 signifie littéralement « zéro requête autorisée » —
                # FORGEAI_RATE_MAX=0 est un geste d'opérateur plausible pour bloquer tout
                # trafic distant en urgence ; refuser systématiquement (retry fixe) est le
                # comportement qui honore cette intention, pas planter la connexion.
                return max(self.rate_window_s, 0.001)
            retry = (1.0 - state["tokens"]) * (self.rate_window_s / self.rate_max)
            return max(retry, 0.001)

    def record_auth_failure(self, ip: str) -> None:
        """Enregistre un échec d'authentification (401) ; arme un lockout au-delà du seuil."""
        with self._lock:
            self._maybe_evict()
            now = self._clock()
            state = self._state.get(ip)
            if state is None:
                state = self._init_state(now)
                self._state[ip] = state
            state["last_seen"] = now
            state["failures"].append(now)
            cutoff = now - self.auth_window_s
            state["failures"] = [t for t in state["failures"] if t > cutoff]
            if len(state["failures"]) >= self.auth_max:
                state["locked_until"] = now + self.lockout_s

    def _init_state(self, now: float) -> dict:
        return {
            "tokens": float(self.rate_max),  # bucket plein au départ
            "last_refill": now,
            "failures": [],
            "locked_until": 0.0,
            "last_seen": now,
        }

    def _maybe_evict(self) -> None:
        """Éviction paresseuse au-delà du seuil de taille ; ne purge jamais un lockout ACTIF."""
        if len(self._state) <= self._evict_threshold:
            return
        now = self._clock()
        stale = [
            ip
            for ip, st in self._state.items()
            if st["locked_until"] <= now and now - st["last_seen"] > self._idle_evict_s
        ]
        for ip in stale:
            del self._state[ip]
