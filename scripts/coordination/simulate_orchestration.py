#!/usr/bin/env python3
"""Simule dix scénarios anti-collision pour le plan de contrôle multi-IDE.

Chaque simulation teste une règle d'invariant du système de coordination.
Exit 0 si les 10/10 passent. Exit 1 à la première défaillance.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
COORD_DIR = REPO_ROOT / "coordination"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_wp() -> dict[str, dict]:
    data = json.loads((COORD_DIR / "work-packages.json").read_text(encoding="utf-8"))
    return {p["id"]: p for p in data.get("packages", [])}


def build_completed(ids: list[str]) -> set[str]:
    return set(ids)


def try_claim(
    pkg_id: str,
    packages: dict[str, dict],
    active_claims: dict[str, str],  # lane → pkg_id
    active_pkgs: set[str],
    completed: set[str],
    origin_main: str = "251f068",
    branch_base: str = "251f068",
) -> tuple[bool, str]:
    """Tente d'ouvrir un claim. Retourne (ok, raison)."""
    if pkg_id not in packages:
        return False, f"Package inconnu: {pkg_id}"
    pkg = packages[pkg_id]

    # Pas de double claim
    if pkg_id in active_pkgs:
        return False, f"Double claim sur {pkg_id}"

    # Lane exclusive libre
    lane = pkg.get("exclusive_lane")
    if lane and lane in active_claims:
        return False, f"Lane '{lane}' déjà détenue par {active_claims[lane]}"

    # Dépendances complétées
    for dep in pkg.get("dependencies", []):
        if dep not in completed:
            return False, f"Dépendance non complétée: {dep}"

    # Base commit = dernier origin/main
    if branch_base != origin_main:
        return False, f"Base périmée: {branch_base} ≠ {origin_main}"

    # Blocked_lab interdit
    if pkg.get("status") == "BLOCKED_LAB":
        return False, f"Package BLOCKED_LAB: {pkg_id}"

    return True, "OK"


# ---------------------------------------------------------------------------
# Scénarios
# ---------------------------------------------------------------------------

def run_simulations() -> list[tuple[str, bool, str]]:
    packages = load_wp()
    results: list[tuple[str, bool, str]] = []

    origin = "251f068"
    stale = "abc1234"

    # 1. Claim ORCH-001 sans dépendances manquantes
    ok, reason = try_claim("ORCH-001", packages, {}, set(), set(), origin, origin)
    results.append(("SIM-01: ORCH-001 claim sans deps — attendu OK", ok, reason))

    # 2. Double claim sur ORCH-001
    active_pkgs = {"ORCH-001"}
    ok, reason = try_claim("ORCH-001", packages, {}, active_pkgs, set(), origin, origin)
    results.append(("SIM-02: double claim ORCH-001 — attendu FAIL", not ok, reason))

    # 3. Claim UI-039 avant ORCH-001 complété
    ok, reason = try_claim("UI-039", packages, {}, set(), set(), origin, origin)
    results.append(("SIM-03: UI-039 avant ORCH-001 — attendu FAIL", not ok, reason))

    # 4. Claim UI-039 après ORCH-001 complété
    completed = build_completed(["ORCH-001"])
    ok, reason = try_claim("UI-039", packages, {}, set(), completed, origin, origin)
    results.append(("SIM-04: UI-039 après ORCH-001 — attendu OK", ok, reason))

    # 5. Collision de lane web-ui (UI-039 actif, UI-040 tenté)
    active_pkgs = {"UI-039"}
    active_lanes: dict[str, str] = {"web-ui": "UI-039"}
    completed = build_completed(["ORCH-001"])
    ok, reason = try_claim("UI-040", packages, active_lanes, active_pkgs, completed, origin, origin)
    results.append(("SIM-05: collision lane web-ui (UI-039 actif) — attendu FAIL", not ok, reason))

    # 6. UI-040 avec UI-039 complété, lane libre
    completed = build_completed(["ORCH-001", "UI-039"])
    ok, reason = try_claim("UI-040", packages, {}, set(), completed, origin, origin)
    results.append(("SIM-06: UI-040 après UI-039 complété — attendu OK", ok, reason))

    # 7. Base commit périmée
    ok, reason = try_claim("ORCH-001", packages, {}, set(), set(), origin, stale)
    results.append(("SIM-07: base périmée — attendu FAIL", not ok, reason))

    # 8. DOC-032 sans toutes ses deps
    completed = build_completed(["ORCH-001", "CAP-033A"])
    ok, reason = try_claim("DOC-032", packages, {}, set(), completed, origin, origin)
    results.append(("SIM-08: DOC-032 avec deps partielles — attendu FAIL", not ok, reason))

    # 9. DOC-032 avec toutes ses deps
    completed = build_completed(["ORCH-001", "CAP-033A", "OPS-031E", "UI-040"])
    ok, reason = try_claim("DOC-032", packages, {}, set(), completed, origin, origin)
    results.append(("SIM-09: DOC-032 avec toutes les deps — attendu OK", ok, reason))

    # 10. Package inexistant
    ok, reason = try_claim("GHOST-999", packages, {}, set(), set(), origin, origin)
    results.append(("SIM-10: package inconnu — attendu FAIL", not ok, reason))

    return results


def main() -> int:
    try:
        sims = run_simulations()
    except Exception as exc:
        print(f"FAIL — erreur inattendue: {exc}", file=sys.stderr)
        return 1

    passed = 0
    failed = 0
    for label, ok, detail in sims:
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {label} ({detail})")
        if ok:
            passed += 1
        else:
            failed += 1

    print(f"\nsimulate_orchestration: {passed}/{len(sims)} PASS")
    if failed:
        print(f"FAIL — {failed} simulation(s) ont échoué.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
