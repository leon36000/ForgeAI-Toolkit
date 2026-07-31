"""OPS-031A — agrégat d'état d'exécution, source UNIQUE partagée par la CLI et l'API web.

`doctor` répond à « ce que la machine PEUT faire » (capacités, préflight). Ce module répond à
« où en est le système MAINTENANT » : backends disponibles, cluster, dernier déploiement.

Toutes les dépendances sont INJECTÉES (fournisseurs sans argument) : l'agrégat est donc testable
sans aucune sonde réelle, et la CLI comme la route web appellent la même fonction — aucune logique
d'état dupliquée entre les deux surfaces.
"""

from __future__ import annotations

from typing import Any, Callable

from forgeai import __version__
from forgeai.core.redaction import redact_text

# Une sonde en échec ne doit pas faire échouer l'agrégat entier : sa section porte cet état, les
# autres restent renseignées (dégradation gracieuse — un `status` qui refuse de répondre quand une
# brique est en panne est précisément inutile au moment où on en a le plus besoin).
INDISPONIBLE = "indisponible"


def _sonder(fournisseur: Callable[[], Any]) -> dict:
    """Exécute un fournisseur et emballe son résultat, ou l'échec RÉDIGÉ.

    Le message d'un outil (kubectl, docker…) peut porter un chemin ou un fragment sensible : il est
    rédigé avant d'entrer dans l'agrégat, qui est exposé par l'API et imprimé par la CLI.
    """
    try:
        return {"etat": "ok", "valeur": fournisseur()}
    except Exception as exc:  # noqa: BLE001 — dégradation gracieuse, jamais de propagation
        return {"etat": INDISPONIBLE, "detail": redact_text(f"{type(exc).__name__}: {exc}")}


def collect_status(
    *,
    backends: Callable[[], Any],
    cluster: Callable[[], Any],
    deploiement: Callable[[], Any],
    materiel: Callable[[], Any],
) -> dict:
    """Agrège l'état d'exécution. Ne lève JAMAIS : chaque section échoue indépendamment."""
    return {
        "version": __version__,
        "backends": _sonder(backends),
        "cluster": _sonder(cluster),
        "deploiement": _sonder(deploiement),
        "materiel": _sonder(materiel),
    }


def format_status_humain(etat: dict) -> str:
    """Rendu lisible pour `forgeai status` (la sortie machine reste `--json`)."""
    lignes = [f"ForgeAI {etat.get('version', '?')}"]
    for section in ("backends", "cluster", "deploiement", "materiel"):
        bloc = etat.get(section) or {}
        if bloc.get("etat") == "ok":
            lignes.append(f"  {section:<12} ok       {bloc.get('valeur')}")
        else:
            lignes.append(f"  {section:<12} {INDISPONIBLE}  {bloc.get('detail', '')}")
    return "\n".join(lignes)
