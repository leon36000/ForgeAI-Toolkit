#!/usr/bin/env python3
"""Vérifie que tous les gates release-critical agrégés par le job CI ``tests``
ont réussi (RC1-580, #580).

Pourquoi ce script plutôt qu'une expression GitHub Actions inline : deux
défauts mesurés empiriquement rendaient une expression ``if:``/``run: python3
-c '...'`` peu fiable ici — (1) un job avec ``needs:`` sans ``if: always()``
est SILENCIEUSEMENT ``skipped`` dès qu'une dépendance échoue, et un check
``skipped`` compte comme RÉUSSI pour la protection de branche GitHub (succès/
skipped/neutral sont tous des statuts positifs) ; (2) l'expression
``contains(needs.*.result, 'failure')`` a un bug documenté avec le filtre
étoile sur des jobs conditionnels. Ce script reçoit le contexte ``needs``
sérialisé en JSON (``toJSON(needs)``, transmis par variable d'environnement
pour éviter tout problème d'échappement shell) et vérifie EXPLICITEMENT que
CHAQUE dépendance a le résultat ``success`` — aucune ambiguïté d'expression,
et testable unitairement (contrairement à un bloc YAML inline).
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any


def gates_en_echec(resultats_needs: dict[str, Any]) -> dict[str, Any]:
    """Retourne ``{nom_job: resultat}`` pour chaque dépendance dont le
    résultat n'est PAS ``success`` (échec, annulation, skip, etc.).

    Pourquoi vérifier l'égalité à ``success`` plutôt que l'inégalité à
    ``failure`` : un statut ``skipped``/``cancelled``/``neutral`` n'est ni
    l'un ni l'autre littéralement, mais ne doit JAMAIS être traité comme un
    succès ici — c'est précisément le défaut que ce script corrige (un job
    skip silencieusement compte comme succès pour GitHub, jamais pour cet
    agrégateur).

    Pourquoi ``isinstance(info, dict)`` (round 1 de revue scellée, #580,
    objection mineure) : le contexte ``needs`` de GitHub Actions produit
    toujours un objet par job, mais un appelant qui construirait ce JSON
    autrement (test, script tiers) pourrait fournir une valeur scalaire —
    ``.get()`` lèverait alors une ``AttributeError`` brute au lieu d'un
    diagnostic clair. Une entrée non conforme est elle-même un échec.
    """
    return {
        nom: (info.get("result") if isinstance(info, dict) else info)
        for nom, info in resultats_needs.items()
        if not isinstance(info, dict) or info.get("result") != "success"
    }


def main(argv: list[str] | None = None) -> int:
    del argv  # aucun argument CLI : tout vient de la variable d'environnement
    brut = os.environ.get("RESULTATS_NEEDS")
    if not brut:
        print(
            "RESULTATS_NEEDS absent ou vide — ce script doit être invoqué "
            "avec ${{ toJSON(needs) }} dans la variable d'environnement.",
            file=sys.stderr,
        )
        return 1

    try:
        resultats_needs = json.loads(brut)
    except json.JSONDecodeError as erreur:
        print(f"RESULTATS_NEEDS n'est pas un JSON valide : {erreur}", file=sys.stderr)
        return 1

    if not isinstance(resultats_needs, dict) or not resultats_needs:
        print(
            "RESULTATS_NEEDS doit être un objet JSON non vide (contexte "
            "needs sérialisé) — reçu : "
            f"{resultats_needs!r}",
            file=sys.stderr,
        )
        return 1

    echecs = gates_en_echec(resultats_needs)
    if echecs:
        print(
            f"{len(echecs)} gate(s) release-critical n'ont PAS réussi : {echecs}",
            file=sys.stderr,
        )
        return 1

    print(f"OK : les {len(resultats_needs)} gates release-critical ont tous réussi.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
