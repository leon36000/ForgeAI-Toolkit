#!/usr/bin/env python3
"""Sentinelle Qualité — sweep de complétion (pattern Sourcegraph, déviation D4 de l'audit).

Quand une story dit « fini », la Sentinelle cherche toute autre utilisation des symboles
touchés : si un symbole modifié est utilisé dans un fichier que le codeur n'a PAS ouvert,
c'est une surface non vérifiée (signal de réouverture). Elle repère aussi les symboles
publics définis dans le changeset SANS aucune référence de test (couverture incomplète).

Déterministe (AST + regex, aucun LLM). Produit un RAPPORT de santé (non bloquant par défaut ;
`--strict` sort en code ≠ 0 s'il reste des surfaces non vérifiées) — revu comme tout artefact.

Usage :
  sentinelle_sweep.py <fichier.py> [...]        # changeset explicite
  sentinelle_sweep.py --since main              # git diff --name-only main...HEAD
  [--src src] [--tests tests] [--strict]
"""
from __future__ import annotations

import argparse
import ast
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _rel(p: Path) -> str:
    """Chemin lisible : relatif au dépôt si possible, sinon absolu (robuste hors REPO)."""
    try:
        return str(p.relative_to(REPO))
    except ValueError:
        return str(p)


def defined_symbols(pyfile: Path) -> set[str]:
    """Symboles PUBLICS de haut niveau (def/class, hors _privés) définis dans le fichier."""
    try:
        tree = ast.parse(pyfile.read_text(encoding="utf-8"))
    except (SyntaxError, OSError):
        return set()
    names = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if not node.name.startswith("_"):
                names.add(node.name)
    return names


def _py_files(root: Path):
    return [p for p in root.rglob("*.py") if "__pycache__" not in p.parts]


def find_usages(symbol: str, roots: list[Path], exclude: set[Path]) -> list[Path]:
    pat = re.compile(r"\b" + re.escape(symbol) + r"\b")
    hits = []
    for root in roots:
        for py in _py_files(root):
            if py.resolve() in exclude:
                continue
            try:
                if pat.search(py.read_text(encoding="utf-8")):
                    hits.append(py)
            except OSError:
                continue
    return hits


def sweep(changed: list[Path], src_roots: list[Path], test_root: Path) -> dict:
    changed_res = {p.resolve() for p in changed}
    surfaces: dict[str, list[str]] = {}      # symbole → fichiers externes (non ouverts) qui l'utilisent
    untested: list[str] = []                 # symboles publics du changeset sans réf. de test
    for f in changed:
        if f.suffix != ".py" or "tests" in f.parts:
            continue
        for sym in defined_symbols(f):
            ext = find_usages(sym, src_roots, changed_res)
            if ext:
                surfaces[sym] = [_rel(p) for p in ext]
            if not find_usages(sym, [test_root], set()):
                untested.append(f"{sym} ({_rel(f)})")
    return {"surfaces_non_verifiees": surfaces, "symboles_publics_sans_test": untested}


def _changed_since(ref: str) -> list[Path]:
    out = subprocess.run(["git", "diff", "--name-only", f"{ref}...HEAD"],
                         capture_output=True, text=True, cwd=REPO).stdout
    return [REPO / line for line in out.splitlines() if line.strip()]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*")
    ap.add_argument("--since", default=None, help="ref git (ex. main) — sinon fichiers explicites")
    ap.add_argument("--src", default="src")
    ap.add_argument("--tests", default="tests")
    ap.add_argument("--strict", action="store_true", help="exit ≠ 0 si surfaces non vérifiées")
    a = ap.parse_args()

    changed = _changed_since(a.since) if a.since else [Path(f) for f in a.files]
    changed = [c if c.is_absolute() else REPO / c for c in changed]
    res = sweep(changed, [REPO / a.src], REPO / a.tests)

    print("SENTINELLE — sweep de complétion (D4)")
    surfaces = res["surfaces_non_verifiees"]
    if surfaces:
        print("  Surfaces à vérifier (symbole touché utilisé dans un fichier non ouvert) :")
        for sym, files in surfaces.items():
            print(f"    · {sym} → {', '.join(files)}")
    else:
        print("  Aucune surface externe non vérifiée.")
    if res["symboles_publics_sans_test"]:
        print("  Symboles publics du changeset SANS référence de test :")
        for s in res["symboles_publics_sans_test"]:
            print(f"    · {s}")
    if a.strict and surfaces:
        print("REOUVERTURE : surfaces non vérifiées présentes (--strict).")
        sys.exit(1)


if __name__ == "__main__":
    main()
