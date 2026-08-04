"""Story P1-S06 (déploiement) — docker compose up + attente de santé réelle.

La santé n'est jamais « le container tourne » : chaque service doit répondre
sur son endpoint HTTP de healthcheck (contrat de preuve du plan maître).
"""
from __future__ import annotations

import json
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

from forgeai.core.models import HealthState, ProbeType, ServiceSpec
from forgeai.core.redaction import redact_text
from forgeai.i18n import t


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
        raise DeployError(t("deploy.compose.compose_up.echec", detail=redact_text(proc.stderr[-2000:])))


def compose_down(compose_file: Path, volumes: bool = False) -> None:
    args = ["down"]
    if volumes:
        args.append("-v")
    proc = _compose(args, compose_file)
    if proc.returncode != 0:
        raise DeployError(t("deploy.compose.compose_down.echec", detail=redact_text(proc.stderr[-2000:])))


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


# HEALTH-028B : une sonde INTERNE (healthcheck Compose) est exécutée par Docker, pas
# depuis l'hôte. Sa preuve existe donc — dans Docker. La lire est la SEULE preuve
# fonctionnelle disponible pour ces services ; conclure sans elle bloquerait tout plan
# contenant un postgres ou un redis. Ne lève jamais : un diagnostic qui plante ne
# diagnostique rien, l'appelant traite le dictionnaire vide comme une absence d'info.
def _etats_docker(plan) -> dict:
    try:
        r = subprocess.run(
            ["docker", "compose", "-p", str(plan.plan_id), "ps", "--format", "json"],
            capture_output=True, text=True, timeout=10, check=False
        )
        if r.returncode != 0:
            return {}
        stdout = r.stdout.strip()
        if not stdout:
            return {}
        if stdout.startswith('['):
            services = json.loads(stdout)
        else:
            services = []
            for line in stdout.split('\n'):
                line = line.strip()
                if line:
                    services.append(json.loads(line))
        result = {}
        for s in services:
            name = s.get("Service") or s.get("Name") or "unknown"
            state = s.get("Health") or s.get("State") or "unknown"
            result[name] = state
        return result
    except Exception:
        return {}


def _etiquette_publique(etat: HealthState) -> str:
    """Traduit un `HealthState` vers le vocabulaire historique de `wait_healthy`.

    Le CLI compare ces valeurs à "healthy" en dur : rompre ce contrat casserait le produit.
    Seul `FUNCTIONALLY_READY` vaut "healthy" — un transport joignable dont l'applicatif n'est
    pas prouvé reste en attente, jamais sain.
    """
    if etat is HealthState.FUNCTIONALLY_READY:
        return "healthy"
    # Tout le reste est "waiting", y compris FAILED. Ce n'est PAS masquer un échec : les
    # violations de contrat sont rejetées AVANT la boucle (HealthContractError, étape 1).
    # Passé ce filtre, un FAILED en cours d'attente signifie « la sonde n'a pas encore
    # répondu », pas « preuve d'échec » — un service qui démarre lentement n'est pas en panne.
    # L'état interne exact reste rendu dans le champ `détail` du message d'erreur.
    return "waiting"


def wait_healthy(plan, timeout_s: float = 180.0, probe=None) -> dict:
    """Attend la santé du plan avec contrat non-vacu. Lève DeployError si timeout ou contrat manquant."""
    from urllib.request import urlopen

    def _default_probe(url: str) -> bool:
        try:
            urlopen(url, timeout=2)
            return True
        except Exception:
            return False

    if probe is None:
        probe = _default_probe

    # --- Étape 1 : contrôle des contrats (AVANT toute attente) ---
    for svc in plan.services:
        if not getattr(svc, "health_required", False):
            continue
        probe_type = getattr(svc, "probe_type", None)
        exploitable = (
            getattr(svc, "healthcheck_url", None) is not None
            or probe_type in (ProbeType.HTTP, ProbeType.TCP, ProbeType.EXEC)
        )
        if not exploitable:
            raise HealthContractError(
                t("deploy.compose.wait_healthy.contrat_absent", name=svc.name,
                  probe_type=probe_type, healthcheck_url=getattr(svc, 'healthcheck_url', None))
            )

    deadline = time.monotonic() + timeout_s
    # --- Étape 2 et 3 : sondage itératif avec agrégation ---
    while True:
        verdicts: dict = {}
        etats_docker = _etats_docker(plan)
        for svc in plan.services:
            healthcheck_url = getattr(svc, "healthcheck_url", None)
            probe_type = getattr(svc, "probe_type", None)
            requis = bool(getattr(svc, "health_required", False))
            sondable = bool(healthcheck_url) or probe_type in (
                ProbeType.HTTP, ProbeType.TCP, ProbeType.EXEC)
            # Un service NI requis NI sondable n'apporte aucune information : l'inclure le
            # ferait peser UNKNOWN sur l'agrégat pour toujours. En revanche, un service
            # sondable DOIT être évalué même s'il n'est pas `health_required` — sinon un plan
            # de services simplement sondés produirait un ensemble VIDE, et la garde
            # anti-vacuité conclurait UNKNOWN alors qu'une preuve était disponible.
            if not requis and not sondable:
                continue
            if healthcheck_url:
                sonde_reussie = bool(probe(healthcheck_url))
                transport_ouvert = sonde_reussie
            elif probe_type in (ProbeType.HTTP, ProbeType.TCP, ProbeType.EXEC):
                # Sonde INTERNE : exécutée par Docker, pas depuis l'hôte. Sa preuve existe
                # néanmoins — on la LIT. Conclure sans elle bloquerait éternellement tout plan
                # contenant un postgres ou un redis (défaut mesuré : timeout systématique).
                etat_docker = etats_docker.get(svc.name, "unknown")
                if etat_docker == "healthy":
                    sonde_reussie = True
                elif etat_docker in ("unhealthy", "exited", "dead"):
                    sonde_reussie = False
                else:
                    sonde_reussie = None   # starting / unknown : pas encore de preuve
                transport_ouvert = False
            else:
                # Service non sondable : doit quand même figurer dans verdicts pour que
                # evaluer_service le déclare FAILED (garde anti-vacuité).
                verdicts[svc.name] = evaluer_service(svc, sonde_reussie=None, transport_ouvert=False)
                continue
            verdicts[svc.name] = evaluer_service(
                svc, sonde_reussie=sonde_reussie, transport_ouvert=transport_ouvert
            )

        global_verdict = agreger_verdicts(verdicts)
        if global_verdict == HealthState.FUNCTIONALLY_READY:
            # CONTRAT DE SORTIE PRÉSERVÉ : `cli.py` compare ces valeurs à "healthy" en dur.
            # Changer ce vocabulaire casserait le produit sans rien apporter — la distinction
            # fine (TRANSPORT_READY / UNKNOWN / FAILED) vit dans `HealthState`, en interne,
            # et c'est elle qui porte la garde anti-vacuité.
            return {nom: _etiquette_publique(etat) for nom, etat in verdicts.items()}

        if time.monotonic() >= deadline:
            details = ", ".join(f"{n}={v.value}" for n, v in verdicts.items()) or t("deploy.compose.wait_healthy.details_vide")
            etats = {nom: _etiquette_publique(etat) for nom, etat in verdicts.items()}
            raise DeployError(
                t("deploy.compose.wait_healthy.non_ready", verdict=global_verdict.value,
                  timeout_s=timeout_s, etats=etats, details=details)
            )

        time.sleep(2)
