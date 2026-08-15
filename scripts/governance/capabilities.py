#!/usr/bin/env python3
"""Diagnostic stdlib des capacités de construction et de gouvernance du dépôt."""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_PIN_RE = re.compile(r"^\s*rev:\s*(\S+)")


def _run_available(command: list[str]) -> bool:
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def _pinned_versions() -> str:
    config = REPO / ".pre-commit-config.yaml"
    try:
        revisions = _PIN_RE.findall(config.read_text(encoding="utf-8"))
    except OSError:
        return ""
    labels = ("ggshield", "ruff")
    found = [
        f"{label} {revision}"
        for label, revision in zip(labels, revisions[:2], strict=False)
    ]
    return f" épinglé : {', '.join(found)} — voir .pre-commit-config.yaml." if found else ""


def _capability(name: str, status: str, enables: str, howto: str) -> dict:
    return {
        "name": name,
        "status": status,
        "enables": enables,
        "howto": howto,
    }


def probe_capabilities(env: dict | None = None) -> list[dict]:
    """Retourne les capacités de gouvernance dans leur ordre canonique."""
    environment = os.environ if env is None else env
    capabilities = []

    python_ok = sys.version_info >= (3, 10)
    capabilities.append(
        _capability(
            "python3",
            "AVAILABLE" if python_ok else "BLOCKED",
            "tous les gates déterministes (no-stub-scan, registres, authority-map, docs, catalogue, metering-sites, tests, reviews-sealed)",
            "installez et utilisez python3 >= 3.10." if not python_ok else "aucune action requise.",
        )
    )

    git_ok = shutil.which("git") is not None and _run_available(["git", "--version"])
    capabilities.append(
        _capability(
            "git",
            "AVAILABLE" if git_ok else "BLOCKED",
            "opérations dépôt (branches, ancrage du registre `registre.py ancrage`, PR)",
            "installez git et rendez-le accessible dans PATH." if not git_ok else "aucune action requise.",
        )
    )

    pytest_ok = _run_available([sys.executable, "-m", "pytest", "--version"])
    capabilities.append(
        _capability(
            "pytest",
            "AVAILABLE" if pytest_ok else "OPTIONAL",
            "UNIQUEMENT le gate `tests` (pytest + couverture)",
            (
                "seul le gate `tests` est affecté ; installez les dépendances de développement "
                "pour exécuter pytest localement."
                if not pytest_ok
                else "aucune action requise."
            ),
        )
    )

    missing_tools = [
        tool for tool in ("ggshield", "ruff") if shutil.which(tool) is None
    ]
    local_hooks_ok = not missing_tools
    missing_text = ", ".join(missing_tools)
    capabilities.append(
        _capability(
            "pre-commit local (ggshield+ruff)",
            "AVAILABLE" if local_hooks_ok else "OPTIONAL",
            "hook pre-commit LOCAL (secrets + lint avant commit) — PAS le gate CI faisant autorité (`gitleaks`, toujours actif en CI indépendamment de cette capacité).",
            (
                "pip install -e '.[dev]' && pre-commit install ; ggshield nécessite ensuite "
                "une authentification locale (compte GitGuardian) — jamais une valeur en clair "
                f"au dépôt. Outil(s) absent(s) : {missing_text}.{_pinned_versions()}"
                if not local_hooks_ok
                else f"aucune action requise.{_pinned_versions()}"
            ),
        )
    )

    proof_script = Path.home() / "proof-method" / "scripts" / "civ_review.py"
    has_proof_method = proof_script.exists()
    has_api_key = environment.get("LITELLM_API_KEY") is not None  # proof:allow — présence, pas la valeur
    has_base_url = environment.get("LITELLM_BASE_URL") is not None
    missing_signals = []
    if not has_proof_method:
        missing_signals.append("~/proof-method/scripts/civ_review.py")
    if not has_api_key:  # proof:allow — booléen de présence, pas un secret en clair
        missing_signals.append("LITELLM_API_KEY")
    if not has_base_url:
        missing_signals.append("LITELLM_BASE_URL")
    review_ok = not missing_signals
    capabilities.append(
        _capability(
            "revue aveugle scellée (outillage externe)",
            "AVAILABLE" if review_ok else "OPTIONAL",
            "flux `civ_review.py` (revue aveugle scellée automatisée, 3 vendors distincts)",
            (
                "signaux absents : "
                + ", ".join(missing_signals)
                + ". Exportez LITELLM_BASE_URL et LITELLM_API_KEY depuis votre propre gestion "
                "de secrets avant d'invoquer civ_review.py ; sans ~/proof-method, la revue "
                "scellée doit être produite ailleurs (autre machine/session) puis versionnée "
                "dans reviews/ — les gates déterministes restent, eux, exécutables ici."
                if not review_ok
                else "aucune action requise."
            ),
        )
    )

    hooks_value = ""
    try:
        result = subprocess.run(
            ["git", "config", "--get", "core.hooksPath"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if result.returncode == 0:
            hooks_value = result.stdout.strip()
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        hooks_value = ""
    capabilities.append(
        _capability(
            "hooks git globaux",
            "AVAILABLE" if hooks_value else "OPTIONAL",
            "application locale de conventions non vérifiées par CI (ex. `.docs-exempt`, un journal en prose libre à la racine — actuellement lu par AUCUN script ni gate de ce dépôt ; sans hook global configuré, rien ne le fait respecter)",
            "aucune action requise — capacité purement informationnelle, ne bloque aucun gate.",
        )
    )

    return capabilities


def render_report(capabilities: list[dict]) -> str:
    """Rend un rapport texte stable, sans couleur ni donnée d'environnement."""
    lines = []
    for capability in capabilities:
        lines.extend(
            [
                f"{capability['name']} | {capability['status']}",
                f"  active : {capability['enables']}",
                f"  action : {capability['howto']}",
            ]
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(prog="capabilities.py")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()
    capabilities = probe_capabilities()
    if args.as_json:
        print(json.dumps(capabilities, ensure_ascii=False, indent=2))
    else:
        print(render_report(capabilities))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
