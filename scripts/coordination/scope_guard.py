#!/usr/bin/env python3
"""Scope-guard : périmètre historique + coupe-circuit quantitatif de branche.

Le contrôle historique vérifie les chemins d'une PR contre le claim JSON de sa
branche lorsqu'un tel claim existe encore. #578 ajoute un budget indépendant des
claims archivés afin qu'une branche ou une boucle de revue ne puisse plus croître
silencieusement jusqu'à des milliers de lignes/rounds.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
COORD_DIR = REPO_ROOT / "archive" / "coordination"

# Circuit breakers, jamais des objectifs à consommer. Une branche légitime qui les
# dépasse doit être replanifiée/découpée plutôt que faire augmenter le seuil.
SCOPE_LIMITS = {
    "ahead": 20,
    "behind": 30,
    "changed_files": 80,
    "substantive_churn": 6000,
    "max_file_churn": 2000,
    "tests_churn": 3000,
    "story_churn": 1500,
    "generated_churn": 50000,
}
GENERATED_PATHS = {
    "governance/path-classification.json",
    "governance/PATH-CLASSIFICATION.md",
    "governance/STATE-CURRENT.json",
    "governance/STATE-CURRENT.md",
}
GENERATED_PREFIXES = ("evidence/reviews/", "evidence/registres/")
GitRunner = Callable[[list[str]], str]


def matches_any(path: str, patterns: list[str]) -> bool:
    return any(
        fnmatch.fnmatch(path, p.rstrip("*") + "*") if p.endswith("**") else fnmatch.fnmatch(path, p)
        for p in patterns
    )


def find_claim_for_branch(claims: list[dict], branch: str) -> dict | None:
    """Retourne le claim historique dont `branch` correspond exactement."""
    for claim in claims:
        if claim.get("branch") == branch:
            return claim
    return None


def check_scope(changed_files: list[str], claim: dict, pkg_by_id: dict[str, dict]) -> list[str]:
    """Vérifie changed_files contre le SEUL claim déjà résolu pour la branche."""
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


def _run_git(command: list[str]) -> str:
    return subprocess.run(command, capture_output=True, text=True, check=True).stdout


def _is_generated(path: str) -> bool:
    return path in GENERATED_PATHS or path.startswith(GENERATED_PREFIXES)


def _numstat_churn(insertions: str, deletions: str) -> int:
    add = 0 if insertions == "-" else int(insertions)
    delete = 0 if deletions == "-" else int(deletions)
    return add + delete


def collect_scope_metrics(
    base_ref: str = "origin/main",
    head_ref: str = "HEAD",
    *,
    runner: GitRunner | None = None,
) -> dict[str, int]:
    """Mesure la divergence et le churn d'une branche depuis son merge-base."""
    run = runner or _run_git
    ahead = int(run(["git", "rev-list", "--count", f"{base_ref}..{head_ref}"]).strip())
    behind = int(run(["git", "rev-list", "--count", f"{head_ref}..{base_ref}"]).strip())
    raw = run(["git", "diff", "--numstat", "--no-renames", f"{base_ref}...{head_ref}"])

    substantive = 0
    generated = 0
    max_file = 0
    tests = 0
    story = 0
    changed = 0
    for line in raw.splitlines():
        if not line:
            continue
        parts = line.split("\t", 2)
        if len(parts) != 3:
            raise ValueError(f"numstat illisible: {line!r}")
        insertions, deletions, path = parts
        churn = _numstat_churn(insertions, deletions)
        changed += 1
        if _is_generated(path):
            generated += churn
            continue
        substantive += churn
        max_file = max(max_file, churn)
        if path.startswith("tests/") or path.startswith("scripts/coordination/test_"):
            tests += churn
        if path.startswith("stories/"):
            story += churn

    return {
        "ahead": ahead,
        "behind": behind,
        "changed_files": changed,
        "substantive_churn": substantive,
        "max_file_churn": max_file,
        "tests_churn": tests,
        "story_churn": story,
        "generated_churn": generated,
    }


def evaluate_scope(metrics: dict[str, int]) -> tuple[bool, list[str]]:
    """Applique les coupe-circuits quantitatifs sans bypass implicite."""
    labels = {
        "ahead": "ahead commits",
        "behind": "behind commits",
        "changed_files": "fichiers modifiés",
        "substantive_churn": "churn substantive",
        "max_file_churn": "churn max par fichier",
        "tests_churn": "churn tests",
        "story_churn": "churn story",
        "generated_churn": "churn généré/preuve",
    }
    failures: list[str] = []
    for key, limit in SCOPE_LIMITS.items():
        value = metrics.get(key, 0)
        if value > limit:
            failures.append(f"FAIL — {labels[key]}: {value} > limite {limit}")
    if failures:
        return False, failures
    summary = ", ".join(f"{key}={metrics.get(key, 0)}" for key in SCOPE_LIMITS)
    return True, [f"PASS — budget quantitatif: {summary}"]


def review_round_policy(round_number: int, *, replanned: bool = False) -> tuple[bool, str]:
    """Borne la revue : 2 rounds auto, un 3e après replan, jamais davantage."""
    if round_number <= 0:
        return False, "INVALID"
    if round_number <= 2:
        return True, "AUTO"
    if round_number == 3:
        return (True, "REPLAN") if replanned else (False, "REPLAN_REQUIRED")
    return False, "STOP"


def get_changed_files(base_ref: str = "origin/main") -> list[str]:
    res = subprocess.run(
        ["git", "diff", "--name-only", f"{base_ref}...HEAD"],
        capture_output=True,
        text=True,
        check=True,
    )
    return [line for line in res.stdout.splitlines() if line]


def current_branch() -> str:
    """Résout la branche de la PR, puis la branche Git locale en repli."""
    branch = os.environ.get("GITHUB_HEAD_REF")
    if branch:
        return branch
    res = subprocess.run(["git", "branch", "--show-current"], capture_output=True, text=True)
    return res.stdout.strip()


def load(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Fichier manquant: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Coupe-circuit de scope ForgeAI")
    parser.add_argument("--base-ref", default="origin/main")
    parser.add_argument("--head-ref", default="HEAD")
    parser.add_argument("--round", type=int, dest="review_round")
    parser.add_argument("--replanned", action="store_true")
    return parser.parse_args(argv)


def _quantitative_preflight(args: argparse.Namespace) -> bool:
    try:
        metrics = collect_scope_metrics(args.base_ref, args.head_ref)
    except (subprocess.CalledProcessError, ValueError) as exc:
        print(f"FAIL — mesure Git impossible: {exc}", file=sys.stderr)
        return False

    ok, report = evaluate_scope(metrics)
    if not ok:
        print("FAIL — budget quantitatif dépassé; STOP/SPLIT/REPLAN requis:", file=sys.stderr)
        for line in report:
            print(f"  • {line}", file=sys.stderr)
        return False
    for line in report:
        print(line)

    if args.review_round is not None:
        allowed, mode = review_round_policy(args.review_round, replanned=args.replanned)
        if not allowed:
            print(
                f"FAIL — round de revue {args.review_round} refusé ({mode}); "
                "STOP/SPLIT/REPLAN avant toute nouvelle dépense multi-vendor",
                file=sys.stderr,
            )
            return False
        print(f"PASS — round de revue {args.review_round}: {mode}")
    return True


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if not _quantitative_preflight(args):
        return 1

    claims_path = COORD_DIR / "active-claims.json"
    wp_path = COORD_DIR / "work-packages.json"

    if not claims_path.exists() or not wp_path.exists():
        print("SKIP legacy-claim — fichiers de coordination absents (budget déjà contrôlé)")
        return 0

    claims_data = load(claims_path)
    claims: list[dict] = claims_data.get("claims", [])
    if not claims:
        print("SKIP legacy-claim — aucun claim actif (budget déjà contrôlé)")
        return 0

    wp_data = load(wp_path)
    pkg_by_id = {p["id"]: p for p in wp_data.get("packages", [])}

    try:
        changed = get_changed_files(args.base_ref)
    except subprocess.CalledProcessError as exc:
        print(f"FAIL — git diff impossible: {exc}", file=sys.stderr)
        return 1
    if not changed:
        print("SKIP legacy-claim — aucun fichier modifié")
        return 0

    branch = current_branch()
    claim = find_claim_for_branch(claims, branch)
    if claim is None:
        print(
            f"SKIP legacy-claim — aucun claim actif ne correspond à la branche '{branch}' "
            "(budget quantitatif déjà contrôlé)"
        )
        return 0

    errors = check_scope(changed, claim, pkg_by_id)
    if errors:
        print("FAIL — violations de périmètre:", file=sys.stderr)
        for error in errors:
            print(f"  • {error}", file=sys.stderr)
        return 1

    print(
        f"PASS — {len(changed)} fichier(s) modifié(s) dans le périmètre de "
        f"{claim.get('package')} (branche '{branch}')."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
