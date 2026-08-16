#!/usr/bin/env python3
"""Valide les exclusions de .coderabbit.yaml (aucun chemin mort, exclusions bornées à une allowlist justifiée)."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import yaml

# build et dist sont des répertoires d'artefacts de release jamais trackés par git ;
# leur absence est normale et ne doit jamais être signalée comme un chemin mort.
_ABSENCE_TOLEREE = frozenset({"build", "dist"})

# RC1-014 (#444) : seuls les artefacts GÉNÉRÉS ayant leur propre validation déterministe
# séparée restent exclus (CANON/, Docs/, stories/ délibérément retirés car contenu normatif humain).
_ALLOWLIST = frozenset({
    "!src/forgeai/data/**",
    "src/forgeai/data/__init__.py",
    "!archive/**",
    "!evidence/registres/**",
    "!evidence/reviews/**",
    "!evidence/audit-output/**",
    "!evidence/dedup/**",
    "!governance/STATE-CURRENT.json",
    "!governance/STATE-CURRENT.md",
    "!governance/path-classification.json",
    "!governance/PATH-CLASSIFICATION.md",
    "!governance/AUTHORITY-MAP.md",
    "!build/**",
    "!dist/**",
})


def _charger_config(root: Path) -> dict:
    fichier = root / ".coderabbit.yaml"
    contenu = yaml.safe_load(fichier.read_text(encoding="utf-8"))
    return contenu if isinstance(contenu, dict) else {}


def _filtres(config: dict) -> list[str]:
    return config.get("reviews", {}).get("path_filters", []) or []


def _repertoire_exclu(motif: str) -> str | None:
    if motif.startswith("!") and motif.endswith("/**"):
        return motif[1:-3]
    return None


def _fichiers_trackes(root: Path, sous_chemin: str) -> list[str]:
    resultat = subprocess.run(
        ["git", "-C", str(root), "ls-files", "--", sous_chemin],
        capture_output=True,
        text=True,
    )
    if resultat.returncode != 0:
        return []
    return [ligne for ligne in resultat.stdout.splitlines() if ligne.strip()]


def _chemin_mort(root: Path, repertoire: str) -> bool:
    if repertoire in _ABSENCE_TOLEREE:
        return False
    return len(_fichiers_trackes(root, repertoire)) == 0


def erreurs(root: Path) -> list[str]:
    config = _charger_config(root)
    problemes: list[str] = []
    for motif in _filtres(config):
        if motif not in _ALLOWLIST:
            problemes.append(
                f"exclusion non inventoriée dans l'allowlist du validateur : {motif!r} — "
                f"ajoutez-la avec justification à _ALLOWLIST (validate_coderabbit_config.py) "
                f"ou retirez-la de .coderabbit.yaml"
            )
        repertoire = _repertoire_exclu(motif)
        if repertoire is not None and _chemin_mort(root, repertoire):
            problemes.append(
                f"chemin mort exclu dans .coderabbit.yaml : {motif!r} — "
                f"le répertoire {repertoire!r} n'a aucun fichier tracké dans le dépôt ; "
                f"corrigez ou retirez cette entrée"
            )
    return problemes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    root = args.root.resolve()
    problemes = erreurs(root)
    if problemes:
        for probleme in problemes:
            print(f"ERREUR: {probleme}", file=sys.stderr)
        return 1
    print("OK: .coderabbit.yaml valide (aucun chemin mort, exclusions bornées à l'allowlist)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
