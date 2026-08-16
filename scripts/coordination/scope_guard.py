#!/usr/bin/env python3
"""Scope-guard : vérifie que les fichiers modifiés par CETTE PR respectent le
périmètre (allowed_paths/forbidden_paths) du SEUL claim actif associé à sa branche.

Correctif (revue aveugle scellée ORCH-001-civ, verdict REJECT de Gemini-3.1-Pro,
objection majeure) : la version initiale (inline dans scope-guard.yml) itérait sur
TOUS les claims actifs et exigeait la conformité aux allowed_paths de CHAQUE claim.
Avec jusqu'à 6 claims concurrents autorisés (cf. AGENTS.md), toute PR valide pour
son propre package échouait dès qu'un second claim était actif, car ses fichiers
n'étaient pas dans les allowed_paths de CET AUTRE claim. La correction identifie le
claim propriétaire de la PR via le champ 'branch' et n'applique que SES règles.
"""
from __future__ import annotations

import fnmatch
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
COORD_DIR = REPO_ROOT / "archive" / "coordination"


def matches_any(path: str, patterns: list[str]) -> bool:
    return any(
        fnmatch.fnmatch(path, p.rstrip("*") + "*") if p.endswith("**") else fnmatch.fnmatch(path, p)
        for p in patterns
    )


def find_claim_for_branch(claims: list[dict], branch: str) -> dict | None:
    """Retourne le claim dont le champ 'branch' correspond exactement à `branch`.

    Si aucun claim n'a de champ 'branch' renseigné correspondant, retourne None
    (le guard SKIP alors — une PR non enregistrée dans un claim n'est pas jugée
    contre les règles d'un claim qui n'est pas le sien)."""
    for claim in claims:
        if claim.get("branch") == branch:
            return claim
    return None


def check_scope(changed_files: list[str], claim: dict, pkg_by_id: dict[str, dict]) -> list[str]:
    """Vérifie changed_files contre le SEUL claim déjà résolu pour la branche courante.

    Retourne la liste des erreurs (vide = OK). Ne regarde JAMAIS les autres claims :
    c'est précisément ce qui corrige le défaut rapporté en revue."""
    pid = claim.get("package")
    pkg = pkg_by_id.get(pid)
    if pkg is None:
        return [f"Claim référence un package inconnu: {pid}"]

    allowed = pkg.get("allowed_paths", [])
    forbidden = pkg.get("forbidden_paths", [])

    errors: list[str] = []
    for f in changed_files:
        if matches_any(f, forbidden):
            errors.append(f"INTERDIT: {f} est dans forbidden_paths de {pid}")
        elif allowed and not matches_any(f, allowed):
            errors.append(f"HORS SCOPE: {f} n'est pas dans allowed_paths de {pid}")
    return errors


def get_changed_files(base_ref: str = "origin/main") -> list[str]:
    res = subprocess.run(
        ["git", "diff", "--name-only", f"{base_ref}...HEAD"],
        capture_output=True,
        text=True,
        check=True,
    )
    return [line for line in res.stdout.splitlines() if line]


def current_branch() -> str:
    """Résout la branche de la PR : `GITHUB_HEAD_REF` (contexte GitHub Actions
    `pull_request`, où HEAD est détaché) en priorité, sinon `git branch --show-current`
    (exécution locale / autres contextes)."""
    branch = os.environ.get("GITHUB_HEAD_REF")
    if branch:
        return branch
    res = subprocess.run(["git", "branch", "--show-current"], capture_output=True, text=True)
    return res.stdout.strip()


def load(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Fichier manquant: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    claims_path = COORD_DIR / "active-claims.json"
    wp_path = COORD_DIR / "work-packages.json"

    if not claims_path.exists() or not wp_path.exists():
        print("SKIP — fichiers de coordination absents (bootstrap initial)")
        return 0

    claims_data = load(claims_path)
    claims: list[dict] = claims_data.get("claims", [])
    if not claims:
        print("SKIP — aucun claim actif")
        return 0

    wp_data = load(wp_path)
    pkg_by_id = {p["id"]: p for p in wp_data.get("packages", [])}

    try:
        changed = get_changed_files()
    except subprocess.CalledProcessError as exc:
        print(f"FAIL — git diff impossible: {exc}", file=sys.stderr)
        return 1
    if not changed:
        print("SKIP — aucun fichier modifié")
        return 0

    branch = current_branch()
    claim = find_claim_for_branch(claims, branch)
    if claim is None:
        print(
            f"SKIP — aucun claim actif ne correspond à la branche '{branch}' "
            "(PR hors coordination ou claim non enregistré)"
        )
        return 0

    errors = check_scope(changed, claim, pkg_by_id)
    if errors:
        print("FAIL — violations de périmètre:", file=sys.stderr)
        for e in errors:
            print(f"  • {e}", file=sys.stderr)
        return 1

    print(
        f"PASS — {len(changed)} fichier(s) modifié(s) dans le périmètre de "
        f"{claim.get('package')} (branche '{branch}')."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
