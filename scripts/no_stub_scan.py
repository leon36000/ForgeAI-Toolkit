#!/usr/bin/env python3
"""Gate no-stub (§8bis du plan maître) — détection déterministe de stubs et de faux.

Détecte, dans les répertoires de code (src/, scripts/, tests/, .github/) :
  - marqueurs de travail inachevé (liste §8bis) dans tout fichier texte;
  - corps de fonction vides (pass / Ellipsis seuls), raise NotImplementedError,
    assert True, et skips pytest sans justification au registre — via AST Python.

Un seul hit ⇒ exit 1 (gate bloquant). Usage :
    no_stub_scan.py --all            # scanne les fichiers suivis par git
    no_stub_scan.py fichier [...]    # scanne des chemins explicites
"""
import argparse
import ast
import re
import subprocess
import sys
from pathlib import Path

CODE_DIRS = ("src", "scripts", "tests", ".github")

# Construits par concaténation pour que ce fichier ne se signale pas lui-même.
MARKERS = [
    "TO" + "DO",
    "FIX" + "ME",
    "XX" + "X",
    "HA" + "CK",
    "PLACE" + "HOLDER",
]
MARKER_RE = re.compile(r"\b(" + "|".join(MARKERS) + r")\b")
JUSTIFICATION_TOKEN = "Registres/"


def _tracked_files() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "--", *CODE_DIRS],
        capture_output=True, text=True, check=True,
    ).stdout
    return [Path(p) for p in out.splitlines() if p]


def scan_markers(path: Path, text: str) -> list[str]:
    violations = []
    for lineno, line in enumerate(text.splitlines(), 1):
        match = MARKER_RE.search(line)
        if match:
            violations.append(f"{path}:{lineno}: marqueur interdit '{match.group(1)}'")
    return violations


def _body_is_empty(body: list[ast.stmt]) -> bool:
    """Corps réduit à docstring + pass/Ellipsis = implémentation absente."""
    statements = list(body)
    if statements and isinstance(statements[0], ast.Expr) and isinstance(
        statements[0].value, ast.Constant
    ) and isinstance(statements[0].value.value, str):
        statements = statements[1:]  # docstring
    if not statements:
        return True
    return all(
        isinstance(stmt, ast.Pass)
        or (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant)
            and stmt.value.value is Ellipsis)
        for stmt in statements
    )


def _is_pytest_skip(node: ast.Call) -> bool:
    """pytest.skip / pytest.xfail / pytest.mark.skip / pytest.mark.xfail / skipif."""
    dotted = []
    obj = node.func
    while isinstance(obj, ast.Attribute):
        dotted.append(obj.attr)
        obj = obj.value
    if isinstance(obj, ast.Name):
        dotted.append(obj.id)
    dotted.reverse()
    return (
        len(dotted) >= 2
        and dotted[0] == "pytest"
        and dotted[-1] in ("skip", "xfail", "skipif")
    )


def _call_is_justified(node: ast.Call) -> bool:
    parts = [arg.value for arg in node.args if isinstance(arg, ast.Constant)]
    parts += [kw.value.value for kw in node.keywords
              if isinstance(kw.value, ast.Constant)]
    return any(isinstance(p, str) and JUSTIFICATION_TOKEN in p for p in parts)


def scan_python(path: Path, text: str) -> list[str]:
    violations = []
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        return [f"{path}:{exc.lineno}: fichier Python non analysable ({exc.msg})"]
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            decorated_abstract = any(
                (isinstance(d, ast.Name) and "abstract" in d.id)
                or (isinstance(d, ast.Attribute) and "abstract" in d.attr)
                for d in node.decorator_list
            )
            if not decorated_abstract and _body_is_empty(node.body):
                violations.append(
                    f"{path}:{node.lineno}: corps vide dans la fonction '{node.name}'"
                )
        elif isinstance(node, ast.Raise):
            target = node.exc
            if isinstance(target, ast.Call):
                target = target.func
            if isinstance(target, ast.Name) and target.id == "NotImplementedError":
                violations.append(f"{path}:{node.lineno}: raise NotImplementedError")
        elif isinstance(node, ast.Assert):
            if isinstance(node.test, ast.Constant) and node.test.value is True:
                violations.append(f"{path}:{node.lineno}: assert True (faux vert)")
        elif isinstance(node, ast.Call) and _is_pytest_skip(node):
            if not _call_is_justified(node):
                violations.append(
                    f"{path}:{node.lineno}: skip/xfail pytest sans justification "
                    f"'{JUSTIFICATION_TOKEN}...'"
                )
    return violations


def scan_file(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []  # binaire ou illisible : hors périmètre du scan texte
    violations = [] if path.name == Path(__file__).name else scan_markers(path, text)
    if path.suffix == ".py":
        violations += scan_python(path, text)
    return violations


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument("--all", action="store_true",
                        help="scanne tous les fichiers suivis des répertoires de code")
    args = parser.parse_args()

    files = _tracked_files() if args.all else args.paths
    if not files:
        parser.error("aucun fichier à scanner (utiliser --all ou passer des chemins)")

    violations = []
    for path in files:
        violations += scan_file(path)

    if violations:
        print(f"NO-STUB-SCAN : {len(violations)} violation(s) §8bis — PR bloquée")
        for v in violations:
            print(f"  {v}")
        sys.exit(1)
    print(f"NO-STUB-SCAN : OK ({len(files)} fichiers scannés, zéro violation)")


if __name__ == "__main__":
    main()
