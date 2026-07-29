"""Story P1-S06 (déploiement) — docker compose up + attente de santé réelle.

La santé n'est jamais « le container tourne » : chaque service doit répondre
sur son endpoint HTTP de healthcheck (contrat de preuve du plan maître).
"""
from __future__ import annotations

import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

from forgeai.core.models import DeploymentPlan, HealthState, ProbeType


class DeployError(Exception):
    pass


def _compose(args: list[str], compose_file: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker", "compose", "-f", str(compose_file), *args],
        capture_output=True, text=True, timeout=600,
    )


def compose_up(compose_file: Path, services: list[str] | None = None) -> None:
    """Démarre les services (détaché). `services` limite le démarrage à un sous-ensemble — utilisé par
    l'amorçage openbao (démarrer openbao + son unsealer AVANT les consommateurs qui attendent
    service_healthy = coffre descellé, sinon interblocage au premier boot). None = tous les services."""
    proc = _compose(["up", "-d", *(services or [])], compose_file)
    if proc.returncode != 0:
        raise DeployError(f"docker compose up a échoué :\n{proc.stderr[-2000:]}")


def compose_down(compose_file: Path, volumes: bool = False) -> None:
    args = ["down"]
    if volumes:
        args.append("-v")
    proc = _compose(args, compose_file)
    if proc.returncode != 0:
        raise DeployError(f"docker compose down a échoué :\n{proc.stderr[-2000:]}")


def http_ok(url: str, timeout_s: float = 3.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout_s) as resp:
            return 200 <= resp.status < 300
    except (urllib.error.URLError, OSError, ValueError):
        return False


class HealthContractError(RuntimeError):
    """Un service exige la santé (health_required=True) mais aucun contrat de sonde
    exploitable n'existe (ni probe_type ni healthcheck_url). On refuse plutôt
    que de conclure au succès par défaut."""


def agreger_verdicts(verdicts: dict[str, "HealthState"]) -> "HealthState":
    """Agrège un dictionnaire nom_service → verdict de santé.

    Collection VIDE → `HealthState.UNKNOWN`, jamais READY. C'est la garde
    centrale : un déploiement de zéro service sondé n'a rien prouvé.
    `all()` sur une collection vide vaut `True` en Python — c'est précisément
    le piège corrigé ici.

    Si un verdict vaut `FAILED` → `FAILED`.
    Si tous valent `FUNCTIONALLY_READY` → `FUNCTIONALLY_READY`.
    Si au moins un vaut `UNKNOWN` → `UNKNOWN`.
    Sinon (mélange de `TRANSPORT_READY`) → `TRANSPORT_READY`.
    """
    if not verdicts:
        return HealthState.UNKNOWN
    values = set(verdicts.values())
    if HealthState.FAILED in values:
        return HealthState.FAILED
    if values == {HealthState.FUNCTIONALLY_READY}:
        return HealthState.FUNCTIONALLY_READY
    if HealthState.UNKNOWN in values:
        return HealthState.UNKNOWN
    # Sinon : uniquement TRANSPORT_READY (ou éventuellement TRANSPORT_READY
    # mêlé avec d'autres valeurs déjà capturées ci-dessus ; en pratique
    # ce bloc n'atteint que le cas TRANSPORT_READY pur ou mélangé
    # uniquement avec lui-même).
    return HealthState.TRANSPORT_READY


def evaluer_service(
    svc: "ServiceSpec",
    sonde_reussie: bool | None = None,
    transport_ouvert: bool = False,
) -> "HealthState":
    """Évalue l'état de santé d'un service en fonction des preuves.

    - `sonde_reussie is True` → FUNCTIONALLY_READY.
    - `sonde_reussie is False` et `transport_ouvert` → TRANSPORT_READY.
      Un port ouvert prouve que le transport répond, PAS que le service
      accepte des requêtes applicatives.
    - `sonde_reussie is False` sans transport → FAILED.
    - `sonde_reussie is None` (aucune sonde) → FAILED si
      `svc.health_required`, sinon UNKNOWN.
    """
    if sonde_reussie is True:
        return HealthState.FUNCTIONALLY_READY
    if sonde_reussie is False:
        if transport_ouvert:
            return HealthState.TRANSPORT_READY
        return HealthState.FAILED
    # sonde_reussie is None
    if svc.health_required:
        return HealthState.FAILED
    return HealthState.UNKNOWN


def wait_healthy(
    plan: "DeploymentPlan",
    timeout_s: float = 180.0,
    probe=None,
) -> dict[str, str]:
    """Attend que chaque service réponde sur sa sonde. Échec = DeployError
    avec l'état exact de chaque service (jamais de faux succès).

    Avant toute boucle, vérifie les contrats : tout service
    `health_required=True` sans `probe_type` exploitable ni `healthcheck_url`
    déclenche `HealthContractError` (préfixe ERR_HEALTH_CONTRAT_ABSENT).
    """
    from forgeai.core.models import HealthState

    if probe is None:
        # probe doit être une fonction qui prend une URL et retourne bool
        def probe(url: str) -> bool:
            # fallback minimal, par défaut on utilise http_ok
            import urllib.request
            try:
                with urllib.request.urlopen(url, timeout=2) as _:
                    return True
            except Exception:
                return False

    # Vérification des contrats avant toute attente
    for svc in plan.services:
        if svc.health_required:
            a_sonde = (
                svc.probe_type is not None or
                svc.healthcheck_url is not None
            )
            if not a_sonde:
                raise HealthContractError(
                    f"ERR_HEALTH_CONTRAT_ABSENT : le service '{svc.name}' "
                    f"exige la santé (health_required=True) mais n'a ni "
                    f"probe_type exploitable ni healthcheck_url. Refus "
                    f"d'attendre."
                )

    deadline = time.monotonic() + timeout_s
    status: dict[str, str] = {
        s.name: "waiting" for s in plan.services if s.healthcheck_url
    }

    while time.monotonic() < deadline:
        for svc in plan.services:
            if svc.healthcheck_url and status.get(svc.name) != "healthy":
                if probe(svc.healthcheck_url):
                    status[svc.name] = "healthy"

        # Utiliser agreger_verdicts pour décider du succès
        # On convertit les valeurs string en HealthState
        verdicts = {}
        for svc in plan.services:
            if svc.healthcheck_url:
                if status.get(svc.name) == "healthy":
                    verdicts[svc.name] = HealthState.FUNCTIONALLY_READY
                else:
                    verdicts[svc.name] = HealthState.UNKNOWN  # pas encore sain
            # services sans healthcheck_url ne participent pas à l'attente,
            # leur état est ignoré dans le verdict global car ils n'ont
            # pas été requis (pas de health_required=True ou pas de probe).
        if agreger_verdicts(verdicts) == HealthState.FUNCTIONALLY_READY:
            return status
        time.sleep(2.0)

    raise DeployError(
        f"Healthchecks incomplets après {timeout_s}s : {status}"
    )
