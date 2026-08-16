#!/usr/bin/env python3
"""Valide la cohérence des fichiers de coordination.

Vérifie:
- Schémas et structure des fichiers JSON.
- Cohérence claims actifs ↔ work-packages (lane, statut, deps).
- Absence de double claim sur la même lane.
- Packages completed réellement listés dans work-packages.
- Aucun claim actif sur un package aux dépendances non completées.

Exit 0 si tout passe (PASS). Exit 1 en cas d'erreur (FAIL).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
COORD_DIR = REPO_ROOT / "archive" / "coordination"


def load(path: Path) -> dict | list:
    if not path.exists():
        raise FileNotFoundError(f"Fichier manquant: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    errors: list[str] = []

    # --- Chargement ---
    try:
        wp_data = load(COORD_DIR / "work-packages.json")
        claims_data = load(COORD_DIR / "active-claims.json")
        completed_data = load(COORD_DIR / "completed.json")
    except FileNotFoundError as exc:
        print(f"FAIL — {exc}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as exc:
        print(f"FAIL — JSON invalide: {exc}", file=sys.stderr)
        return 1

    # --- Validation work-packages.json ---
    if "_schema" not in wp_data:
        errors.append("work-packages.json: clé '_schema' manquante")
    packages: list[dict] = wp_data.get("packages", [])
    if not isinstance(packages, list):
        errors.append("work-packages.json: 'packages' doit être une liste")
        packages = []

    pkg_by_id: dict[str, dict] = {}
    for pkg in packages:
        pid = pkg.get("id")
        if not pid:
            errors.append(f"Package sans 'id': {pkg}")
            continue
        if pid in pkg_by_id:
            errors.append(f"Package dupliqué: {pid}")
        pkg_by_id[pid] = pkg

    # Vérifier les dépendances référencent des packages connus
    for pkg in packages:
        for dep in pkg.get("dependencies", []):
            if dep not in pkg_by_id:
                errors.append(
                    f"Package {pkg['id']}: dépendance inconnue '{dep}' (pas dans work-packages)"
                )

    # --- Validation active-claims.json ---
    if "_schema" not in claims_data:
        errors.append("active-claims.json: clé '_schema' manquante")
    claims: list[dict] = claims_data.get("claims", [])
    if not isinstance(claims, list):
        errors.append("active-claims.json: 'claims' doit être une liste")
        claims = []

    # Unicité des lanes actives
    active_lanes: dict[str, str] = {}  # lane → package_id
    active_pkgs: set[str] = set()
    for claim in claims:
        pid = claim.get("package")
        lane = claim.get("lane")
        if not pid:
            errors.append(f"Claim sans 'package': {claim}")
            continue
        if pid in active_pkgs:
            errors.append(f"Double claim actif pour le package: {pid}")
        active_pkgs.add(pid)
        if lane:
            if lane in active_lanes:
                errors.append(
                    f"Collision de lane '{lane}': {active_lanes[lane]} et {pid} actifs simultanément"
                )
            else:
                active_lanes[lane] = pid

        # Le package doit exister dans work-packages
        if pid not in pkg_by_id:
            errors.append(f"Claim actif pour package inconnu: {pid}")
            continue

        pkg = pkg_by_id[pid]

        # La lane du claim doit correspondre à celle du package
        if lane and pkg.get("exclusive_lane") and lane != pkg["exclusive_lane"]:
            errors.append(
                f"Claim {pid}: lane '{lane}' ≠ lane du package '{pkg['exclusive_lane']}'"
            )

    # --- Validation completed.json ---
    if "_schema" not in completed_data:
        errors.append("completed.json: clé '_schema' manquante")
    completed_raw: list = completed_data.get("completed", [])
    if not isinstance(completed_raw, list):
        errors.append("completed.json: 'completed' doit être une liste")
        completed_raw = []

    completed_set: set[str] = set()
    for item in completed_raw:
        pid = item if isinstance(item, str) else item.get("package") or item.get("id")
        if not pid:
            errors.append(f"Entrée completed sans 'package'/'id': {item}")
            continue
        if pid not in pkg_by_id:
            errors.append(f"Completed référence un package inconnu: {pid}")
        completed_set.add(pid)

    # --- Cohérence claims actifs ↔ deps complétées ---
    for claim in claims:
        pid = claim.get("package")
        if not pid or pid not in pkg_by_id:
            continue
        pkg = pkg_by_id[pid]
        for dep in pkg.get("dependencies", []):
            if dep not in completed_set:
                errors.append(
                    f"Claim actif {pid}: dépendance '{dep}' non complétée"
                )

    # --- Résultat ---
    if errors:
        print("FAIL — validate_coordination: erreurs détectées:", file=sys.stderr)
        for e in errors:
            print(f"  • {e}", file=sys.stderr)
        return 1

    print(
        f"PASS — validate_coordination: {len(packages)} packages, "
        f"{len(claims)} claims actifs, {len(completed_set)} complétés, zéro erreur."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
