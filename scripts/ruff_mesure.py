#!/usr/bin/env python3
"""Invocation Ruff partagée entre `ruff_report.py` (#450 incrément 1) et `ruff_ratchet.py`
(#450 incrément 2) — extrait pour éliminer une duplication de ~45 lignes (Quality Gate
SonarCloud, densité de duplication sur code neuf, PR #572).

Ni `ruff_report.py` ni `ruff_ratchet.py` ne s'importent l'un l'autre : les deux restent
indépendants l'un de l'autre (comme conçu), en dépendant chacun de ce module d'infrastructure
commune — même principe que `gate_git_ref.py`, déjà partagé entre `mypy_gate.py` et
`ruff_ratchet.py` sans coupler les gates entre eux.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any


def mesurer_violations(racine: Path, regles: list[str]) -> list[dict[str, Any]]:
    """Exécute `ruff check --no-cache --output-format=json --select <regles> src scripts`
    (cwd=`racine`) et retourne les violations détectées.

    Gestion d'erreurs : ruff absent → RuntimeError ; code de sortie hors {0, 1} → RuntimeError ;
    sortie JSON invalide → RuntimeError ; sortie JSON valide mais pas une liste de dicts →
    RuntimeError. Les chemins absolus renvoyés par ruff (dépendants de la machine) sont
    normalisés en relatif POSIX à `racine` (`.as_posix()`, jamais de séparateur `\\` même sous
    Windows), pour une comparaison stable et portable entre appelants."""
    commande = [
        "ruff",
        "check",
        "--no-cache",
        "--output-format=json",
        "--select",
        ",".join(regles),
        "src",
        "scripts",
    ]

    try:
        resultat = subprocess.run(
            commande,
            cwd=str(racine),
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as erreur:
        raise RuntimeError(
            "ruff est indisponible : vérifiez son installation et le PATH"
        ) from erreur
    except OSError as erreur:
        raise RuntimeError(f"impossible d'exécuter ruff : {erreur}") from erreur

    if resultat.returncode not in (0, 1):
        details = resultat.stderr.strip()
        suffixe = f" : {details}" if details else ""
        raise RuntimeError(
            f"ruff a échoué avec le code {resultat.returncode}{suffixe}"
        )

    try:
        violations = json.loads(resultat.stdout)
    except json.JSONDecodeError as erreur:
        details = resultat.stderr.strip()
        suffixe = f" ({details})" if details else ""
        raise RuntimeError(
            f"la sortie JSON de ruff est invalide{suffixe} : {erreur}"
        ) from erreur

    if not isinstance(violations, list) or not all(
        isinstance(violation, dict) for violation in violations
    ):
        raise RuntimeError("la sortie JSON de ruff doit être une liste de violations")

    racine_resolue = Path(racine).resolve()
    for violation in violations:
        chemin = violation.get("filename")
        if isinstance(chemin, str):
            try:
                violation["filename"] = (
                    Path(chemin).resolve().relative_to(racine_resolue).as_posix()
                )
            except ValueError:
                pass  # hors de racine (improbable) : conserve le chemin absolu tel quel

    return violations
