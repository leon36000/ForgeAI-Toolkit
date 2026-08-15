#!/usr/bin/env python3
"""Produit et vérifie l'état courant déterministe du dépôt."""

from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any

# INVARIANT DE POLITIQUE fixée par AGENTS.md : revue aveugle scellée 3/3.
# Ce n'est pas une donnée mesurée qui dérive d'une source externe.
_REVIEW_QUORUM = "3/3"

_SCHEMA = "state-current-v1"
_CATALOGUE = Path("src/forgeai/data/catalogue.json")
_CANONICAL_CATALOGUE_SIDECAR = Path("src/forgeai/data/catalogue.sha256")
_LEGACY_CATALOGUE_SIDECAR = Path("src/forgeai/data/catalogue.json.sha256")
_STATE_JSON = Path("governance/STATE-CURRENT.json")
_STATE_MARKDOWN = Path("governance/STATE-CURRENT.md")
_OBSERVATIONS = Path("governance/state-observations.json")
_OPEN_MARKER_RE = re.compile(r"<!-- state:([A-Za-z0-9_.-]+) -->")
_CLOSE_MARKER = "<!-- /state -->"
_PROJECT_SECTION_RE = re.compile(
    r"(?ms)^\[project\][ \t]*\r?$\n?(.*?)(?=^\[[^\]]+\][ \t]*\r?$|\Z)"
)
_VERSION_RE = re.compile(r'(?m)^[ \t]*version[ \t]*=[ \t]*["\']([^"\']+)["\'][ \t]*$')


def _within_repo(repo_root: Path, candidate: Path) -> Path:
    """Résout un chemin et garantit qu'il reste dans la racine du dépôt."""
    resolved_root = repo_root.resolve()
    resolved_candidate = candidate.resolve()
    if not resolved_candidate.is_relative_to(resolved_root):
        raise ValueError(f"chemin hors du dépôt: {candidate}")
    return resolved_candidate


def _path(repo_root: Path, relative: Path) -> Path:
    return _within_repo(repo_root, repo_root / relative)


def _read_bytes(repo_root: Path, relative: Path) -> bytes:
    path = _path(repo_root, relative)
    try:
        return path.read_bytes()
    except OSError as exc:
        raise ValueError(f"fichier inaccessible: {relative}: {exc}") from exc


def _read_text(repo_root: Path, relative: Path) -> str:
    try:
        return _read_bytes(repo_root, relative).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"fichier non UTF-8: {relative}: {exc}") from exc


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content.replace(b"\r\n", b"\n")).hexdigest()


def _relative(repo_root: Path, path: Path) -> str:
    return path.resolve().relative_to(repo_root.resolve()).as_posix()


def _load_json(repo_root: Path, relative: Path) -> Any:
    try:
        return json.loads(_read_text(repo_root, relative))
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON invalide: {relative}: {exc}") from exc


def _pyproject_version(text: str) -> str:
    section = _PROJECT_SECTION_RE.search(text)
    if section is None:
        raise ValueError("pyproject.toml: table [project] absente")
    version = _VERSION_RE.search(section.group(1))
    if version is None:
        raise ValueError("pyproject.toml: version absente de la table [project]")
    return version.group(1)


def _init_version(text: str) -> str:
    try:
        tree = ast.parse(text, filename="src/forgeai/__init__.py")
    except SyntaxError as exc:
        raise ValueError(f"src/forgeai/__init__.py invalide: {exc}") from exc

    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(target, ast.Name) and target.id == "__version__"
            for target in node.targets
        ):
            continue
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            return node.value.value
        raise ValueError("src/forgeai/__init__.py: __version__ doit être une chaîne")
    raise ValueError("src/forgeai/__init__.py: __version__ absent")


def _catalogue_sidecar(repo_root: Path) -> Path:
    canonical = _path(repo_root, _CANONICAL_CATALOGUE_SIDECAR)
    if canonical.is_file():
        return canonical
    legacy = _path(repo_root, _LEGACY_CATALOGUE_SIDECAR)
    if legacy.is_file():
        return legacy
    raise ValueError(
        "sidecar catalogue absent: "
        f"{_CANONICAL_CATALOGUE_SIDECAR.as_posix()}"
    )


def _test_files(repo_root: Path) -> list[Path]:
    tests_dir = _path(repo_root, Path("tests"))
    if not tests_dir.exists():
        return []
    if not tests_dir.is_dir():
        raise ValueError("tests n'est pas un répertoire")
    return sorted(
        (
            path
            for path in tests_dir.rglob("*.py")
            if path.is_file()
        ),
        key=lambda path: _relative(repo_root, path),
    )


def _js_test_files(repo_root: Path) -> list[Path]:
    tests_dir = _path(repo_root, Path("tests"))
    if not tests_dir.exists():
        return []
    if not tests_dir.is_dir():
        raise ValueError("tests n'est pas un répertoire")
    return sorted(
        (
            path
            for path in tests_dir.rglob("*.cjs")
            if path.is_file()
        ),
        key=lambda path: _relative(repo_root, path),
    )


def _count_tests(repo_root: Path, paths: list[Path]) -> int:
    total = 0
    for path in paths:
        relative = Path(_relative(repo_root, path))
        try:
            tree = ast.parse(_read_text(repo_root, relative), filename=str(relative))
        except SyntaxError as exc:
            raise ValueError(f"test Python invalide: {relative}: {exc}") from exc
        total += sum(
            isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
            for node in ast.walk(tree)
        )
    return total


def _workflow_files(repo_root: Path) -> list[Path]:
    workflows = _path(repo_root, Path(".github/workflows"))
    if not workflows.exists():
        return []
    if not workflows.is_dir():
        raise ValueError(".github/workflows n'est pas un répertoire")
    return sorted(
        (path for path in workflows.glob("*.yml") if path.is_file()),
        key=lambda path: _relative(repo_root, path),
    )


def _workflow_jobs(relative: str, text: str) -> int:
    lines = text.replace("\r\n", "\n").splitlines()
    jobs_indexes = [
        index for index, line in enumerate(lines)
        if line == "jobs:"
    ]
    if len(jobs_indexes) != 1:
        raise ValueError(
            f"workflow {relative}: exactement une clé top-level jobs: est requise"
        )

    jobs_index = jobs_indexes[0]
    jobs = 0
    found_child = False
    for line in lines[jobs_index + 1:]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line[0] not in " ":
            break
        if line.startswith("  ") and not line.startswith("   "):
            if re.fullmatch(r"  [A-Za-z0-9_.-]+:[ \t]*(?:#.*)?", line):
                jobs += 1
                found_child = True
                continue
            raise ValueError(
                f"workflow {relative}: structure jobs inattendue à deux espaces: {line!r}"
            )
        if not found_child:
            raise ValueError(
                f"workflow {relative}: aucun job indenté à deux espaces sous jobs:"
            )
    if not found_child:
        raise ValueError(f"workflow {relative}: jobs: ne contient aucun job")
    return jobs


def _cli_commands(repo_root: Path) -> list[str]:
    cli_path = _path(repo_root, Path("src/forgeai/cli.py"))
    if not cli_path.is_file():
        return []

    gate_path = _path(repo_root, Path("scripts/gate_docs.py"))
    if not gate_path.is_file():
        raise ValueError("scripts/gate_docs.py absent pour l'extraction de la CLI")
    spec = importlib.util.spec_from_file_location("_state_current_gate_docs", gate_path)
    if spec is None or spec.loader is None:
        raise ValueError(f"chargement impossible: {gate_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    first_level = set(module.sous_commandes(cli_path))

    try:
        tree = ast.parse(cli_path.read_text(encoding="utf-8"), filename=str(cli_path))
    except (OSError, UnicodeError, SyntaxError) as exc:
        raise ValueError(f"CLI illisible ou invalide {cli_path}: {exc}") from exc

    first_carrier: str | None = None
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Call):
            continue
        function = node.value.func
        if isinstance(function, ast.Attribute) and function.attr == "add_subparsers":
            if node.targets and isinstance(node.targets[0], ast.Name):
                first_carrier = node.targets[0].id
                break

    parser_names: dict[str, str] = {}
    if first_carrier is not None:
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Call):
                continue
            function = node.value.func
            if (
                isinstance(function, ast.Attribute)
                and function.attr == "add_parser"
                and isinstance(function.value, ast.Name)
                and function.value.id == first_carrier
                and node.value.args
                and isinstance(node.value.args[0], ast.Constant)
                and isinstance(node.value.args[0].value, str)
                and node.targets
                and isinstance(node.targets[0], ast.Name)
            ):
                parser_names[node.targets[0].id] = node.value.args[0].value

    second_level: set[str] = set()
    subparser_carriers: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Call):
            continue
        function = node.value.func
        if (
            isinstance(function, ast.Attribute)
            and function.attr == "add_subparsers"
            and isinstance(function.value, ast.Name)
            and function.value.id in parser_names
            and node.targets
            and isinstance(node.targets[0], ast.Name)
        ):
            subparser_carriers[node.targets[0].id] = parser_names[function.value.id]

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        function = node.func
        if (
            not isinstance(function, ast.Attribute)
            or function.attr != "add_parser"
            or not isinstance(function.value, ast.Name)
            or function.value.id not in subparser_carriers
            or not node.args
            or not isinstance(node.args[0], ast.Constant)
            or not isinstance(node.args[0].value, str)
        ):
            continue
        second_level.add(
            f"{subparser_carriers[function.value.id]} {node.args[0].value}"
        )
    return sorted(first_level | second_level)


def _commands_by_group(commands: list[str]) -> dict[str, int]:
    groups: dict[str, int] = {}
    for command in commands:
        parts = command.split(" ")
        if len(parts) == 2:
            groups[parts[0]] = groups.get(parts[0], 0) + 1
    return dict(sorted(groups.items()))


def _coordination_entries(value: Any, relative: str) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        for key in ("entries", "work_packages", "packages", "claims"):
            entries = value.get(key)
            if isinstance(entries, list):
                return entries
    raise ValueError(f"{relative}: liste d'entrées introuvable")


def _coordination_total(value: Any, claims: list[Any]) -> int:
    if isinstance(value, dict):
        limits = value.get("concurrency_limits")
        if isinstance(limits, dict):
            total = limits.get("total")
            if isinstance(total, int) and not isinstance(total, bool) and total >= 0:
                return total
            if total is not None:
                raise ValueError(
                    "coordination/work-packages.json: concurrency_limits.total invalide"
                )
    return sum(
        isinstance(claim, dict)
        and isinstance(claim.get("concurrency"), str)
        and bool(claim["concurrency"])
        for claim in claims
    )


def collect(repo_root: Path) -> dict:
    """Collecte exclusivement des informations locales, déterministes et traçables."""
    repo_root = repo_root.resolve()
    inputs: dict[str, str] = {}

    def source(relative: Path) -> bytes:
        content = _read_bytes(repo_root, relative)
        inputs[relative.as_posix()] = _sha256(content)
        return content

    pyproject_relative = Path("pyproject.toml")
    init_relative = Path("src/forgeai/__init__.py")
    catalogue_relative = _CATALOGUE
    pyproject_text = source(pyproject_relative).decode("utf-8")
    init_text = source(init_relative).decode("utf-8")
    catalogue_bytes = source(catalogue_relative)

    sidecar_path = _catalogue_sidecar(repo_root)
    sidecar_relative = Path(_relative(repo_root, sidecar_path))
    sidecar_bytes = source(sidecar_relative)

    try:
        pyproject_version = _pyproject_version(pyproject_text)
        init_version = _init_version(init_text)
    except UnicodeDecodeError as exc:
        raise ValueError(f"fichier de version non UTF-8: {exc}") from exc
    if pyproject_version != init_version:
        raise ValueError(
            "versions divergentes entre pyproject.toml "
            f"({pyproject_version!r}) et src/forgeai/__init__.py ({init_version!r})"
        )

    try:
        project_section = _PROJECT_SECTION_RE.search(pyproject_text)
        if project_section is None:
            raise ValueError("pyproject.toml: table [project] absente")
        name_match = re.search(
            r'(?m)^[ \t]*name[ \t]*=[ \t]*["\']([^"\']+)["\'][ \t]*$',
            project_section.group(1),
        )
        requires_match = re.search(
            r'(?m)^[ \t]*requires-python[ \t]*=[ \t]*["\']([^"\']+)["\'][ \t]*$',
            project_section.group(1),
        )
        dependencies_match = re.search(
            r"(?ms)^[ \t]*dependencies[ \t]*=[ \t]*\[(.*?)\]",
            project_section.group(1),
        )
        dependencies = (
            re.findall(r'["\']([^"\']+)["\']', dependencies_match.group(1))
            if dependencies_match is not None
            else []
        )
    except ValueError:
        raise
    package_name = name_match.group(1) if name_match is not None else ""
    requires_python = requires_match.group(1) if requires_match is not None else ""

    try:
        catalogue = json.loads(catalogue_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"catalogue JSON invalide: {exc}") from exc
    if not isinstance(catalogue, dict) or not isinstance(catalogue.get("entries"), list):
        raise ValueError("catalogue.json: clé entries doit être une liste")
    entries = catalogue["entries"]
    if not all(isinstance(entry, dict) for entry in entries):
        raise ValueError("catalogue.json: chaque entrée doit être un objet")
    expected_catalogue_digest = _sha256(catalogue_bytes)
    try:
        sidecar_digest = sidecar_bytes.decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise ValueError(f"sidecar catalogue non UTF-8: {exc}") from exc

    test_paths = _test_files(repo_root)
    for test_path in test_paths:
        source(Path(_relative(repo_root, test_path)))
    js_test_paths = _js_test_files(repo_root)
    for js_test_path in js_test_paths:
        source(Path(_relative(repo_root, js_test_path)))
    test_functions = _count_tests(repo_root, test_paths)

    workflow_paths = _workflow_files(repo_root)
    jobs_total = 0
    for workflow_path in workflow_paths:
        relative = Path(_relative(repo_root, workflow_path))
        workflow_text = source(relative).decode("utf-8")
        jobs_total += _workflow_jobs(relative.as_posix(), workflow_text)

    packages_relative = Path("coordination/work-packages.json")
    claims_relative = Path("coordination/active-claims.json")
    packages_value = json.loads(source(packages_relative).decode("utf-8"))
    claims_value = json.loads(source(claims_relative).decode("utf-8"))
    packages = _coordination_entries(packages_value, packages_relative.as_posix())
    claims = _coordination_entries(claims_value, claims_relative.as_posix())

    commands = _cli_commands(repo_root)
    input_list = [
        {"path": path, "sha256": digest}
        for path, digest in sorted(inputs.items())
    ]
    categories = {
        entry.get("category")
        for entry in entries
        if isinstance(entry.get("category"), str) and entry["category"]
    }

    return {
        "_schema": _SCHEMA,
        "package": {
            "name": package_name,
            "version": init_version,
            "version_pyproject": pyproject_version,
            "requires_python": requires_python,
            "runtime_dependencies": dependencies,
        },
        "catalogue": {
            "entries_total": len(entries),
            "sha256_recomputed_ok": sidecar_digest == expected_catalogue_digest,
            "descriptions_en_missing": sum(
                not isinstance(entry.get("description_en"), str)
                or not entry["description_en"].strip()
                for entry in entries
            ),
            "categories_total": len(categories),
        },
        "cli": {
            "subcommands_total": len(commands),
            "subcommands": commands,
            "subcommands_by_group": _commands_by_group(commands),
        },
        "tests": {
            "python_files": len(test_paths),
            "python_functions_declared": test_functions,
            "js_files": len(js_test_paths),
        },
        "ci": {
            "workflows": len(workflow_paths),
            "jobs_total": jobs_total,
        },
        "coordination": {
            "work_packages_total": len(packages),
            "active_claims_total": len(claims),
            "concurrency_total": _coordination_total(packages_value, claims),
        },
        "governance": {
            "review_quorum": _REVIEW_QUORUM,
        },
        "inputs": input_list,
    }


def load_observations(path: Path) -> list[dict]:
    """Charge les observations horodatées sans les confondre avec l'état scellé."""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"observations inaccessibles: {path}: {exc}") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"observations invalides: {path}: {exc}") from exc

    if not isinstance(value, list):
        raise ValueError("observations: une liste est requise")
    required = (
        "id",
        "value",
        "display",
        "observed_at",
        "source",
        "evidence",
        "sealed",
        "command",
    )
    observations: list[dict] = []
    for index, observation in enumerate(value, start=1):
        if not isinstance(observation, dict):
            raise ValueError(f"observation {index}: objet requis")
        for field in required:
            if field not in observation:
                raise ValueError(f"observation {index}: champ manquant {field}")
        if not isinstance(observation["sealed"], bool):
            raise ValueError(f"observation {index}: sealed doit être bool")
        source = observation["source"]
        if not isinstance(source, str):
            raise ValueError(f"observation {index}: source doit être une chaîne")
        if re.search(r"gh api|github|http", source, re.IGNORECASE) and observation["sealed"]:
            raise ValueError(
                f"observation {index}: une observation réseau ne peut pas être scellée"
            )
        observations.append(observation)
    return observations


def build_state(repo_root: Path) -> dict:
    """Assemble le bloc déterministe et les observations explicitement non scellées."""
    repo_root = repo_root.resolve()
    observations_path = _path(repo_root, _OBSERVATIONS)
    return {
        "deterministe": collect(repo_root),
        "observations": load_observations(observations_path),
    }


def render(state: dict) -> str:
    """Rend un état stable destiné à la lecture humaine."""
    deterministic = state.get("deterministe")
    observations = state.get("observations")
    if not isinstance(deterministic, dict) or not isinstance(observations, list):
        raise ValueError("état invalide pour le rendu")

    lines = [
        "<!-- NE PAS ÉDITER À LA MAIN — généré par scripts/governance/state_current.py --render -->",
        "",
        "# État courant du dépôt",
        "",
        "## Bloc déterministe",
        "",
        "```json",
        json.dumps(deterministic, ensure_ascii=False, indent=2, sort_keys=True),
        "```",
        "",
        "## Observations",
        "",
    ]
    if not observations:
        lines.append("- Aucune observation.")
    for observation in observations:
        if not isinstance(observation, dict):
            raise ValueError("observation invalide pour le rendu")
        display = observation.get("display")
        if not isinstance(display, str):
            raise ValueError("observation sans display pour le rendu")
        lines.append(
            f"- {display} — observation horodatée, non scellée — "
            "hors chaîne de preuve du dépôt"
        )
    return "\n".join(lines) + "\n"


def format_value(value: Any) -> str:
    """Formate les seules valeurs autorisées dans un marqueur documentaire."""
    if isinstance(value, bool):
        raise TypeError("type reçu non pris en charge: bool")
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return value
    raise TypeError(f"type reçu non pris en charge: {type(value).__name__}")


def _marker_value(state: dict, dotted_path: str) -> str:
    if dotted_path.startswith("observations."):
        observation_id = dotted_path[len("observations."):]
        for observation in state.get("observations", []):
            if isinstance(observation, dict) and observation.get("id") == observation_id:
                return format_value(observation.get("display"))
        raise KeyError(dotted_path)

    current: Any = state.get("deterministe")
    for segment in dotted_path.split("."):
        if not isinstance(current, dict) or segment not in current:
            raise KeyError(dotted_path)
        current = current[segment]
    return format_value(current)


def inject(text: str, state: dict, path_label: str) -> tuple[str, list[str]]:
    """Injecte les marqueurs d'état sans modifier les caractères hors valeurs."""
    del path_label
    openings = list(_OPEN_MARKER_RE.finditer(text))
    close_positions = [
        match.start() for match in re.finditer(re.escape(_CLOSE_MARKER), text)
    ]
    if len(openings) != len(close_positions):
        raise ValueError("marqueurs state déséquilibrés")

    cursor = 0
    parts: list[str] = []
    replacements: list[str] = []
    for opening in openings:
        close_start = text.find(_CLOSE_MARKER, opening.end())
        if close_start < 0:
            raise ValueError("marqueur state sans fermeture")
        nested = _OPEN_MARKER_RE.search(text, opening.end(), close_start)
        if nested is not None:
            raise ValueError("marqueurs state imbriqués")
        if close_start < cursor:
            raise ValueError("marqueurs state déséquilibrés")
        dotted_path = opening.group(1)
        old_value = text[opening.end():close_start]
        new_value = _marker_value(state, dotted_path)
        parts.extend((text[cursor:opening.end()], new_value))
        cursor = close_start
        replacements.append(f"{dotted_path} : {old_value} -> {new_value}")
    parts.append(text[cursor:])

    reconstructed = "".join(parts)
    if not openings and _CLOSE_MARKER in text:
        raise ValueError("marqueur state de fermeture sans ouverture")
    return reconstructed, replacements


def _compare_values(
    disk: Any,
    current: Any,
    dotted_path: str,
    errors: list[str],
) -> None:
    if isinstance(disk, dict) and isinstance(current, dict):
        for key in sorted(set(disk) | set(current)):
            child = f"{dotted_path}.{key}" if dotted_path else str(key)
            if key not in disk:
                errors.append(f"{child}: valeur disque absente, recalculée {current[key]!r}")
            elif key not in current:
                errors.append(f"{child}: valeur disque {disk[key]!r}, recalculée absente")
            else:
                _compare_values(disk[key], current[key], child, errors)
        return
    if isinstance(disk, list) and isinstance(current, list):
        if disk != current:
            errors.append(f"{dotted_path}: valeur disque {disk!r}, recalculée {current!r}")
        return
    if disk != current:
        errors.append(f"{dotted_path}: valeur disque {disk!r}, recalculée {current!r}")


def check(repo_root: Path, docs: list[Path] | None = None) -> tuple[bool, list[str]]:
    """Vérifie les fichiers d'état générés et les marqueurs documentaires."""
    repo_root = repo_root.resolve()
    errors: list[str] = []
    current = build_state(repo_root)

    disk_json_path = _path(repo_root, _STATE_JSON)
    disk_markdown_path = _path(repo_root, _STATE_MARKDOWN)
    try:
        disk_state = json.loads(disk_json_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"STATE-CURRENT.json inaccessible: {exc}") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"STATE-CURRENT.json invalide: {exc}") from exc
    if not isinstance(disk_state, dict):
        raise ValueError("STATE-CURRENT.json doit être un objet JSON")

    _compare_values(disk_state, current, "", errors)

    try:
        disk_markdown = disk_markdown_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"STATE-CURRENT.md inaccessible: {exc}") from exc
    expected_markdown = render(current)
    if disk_markdown != expected_markdown:
        errors.append("STATE-CURRENT.md: rendu désynchronisé")

    for document in docs or []:
        candidate = document if document.is_absolute() else repo_root / document
        document_path = _within_repo(repo_root, candidate)
        try:
            content = document_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ValueError(f"document inaccessible: {document_path}: {exc}") from exc
        rendered, replacements = inject(
            content,
            current,
            _relative(repo_root, document_path),
        )
        if rendered != content:
            labels = [
                replacement.split(" : ", 1)[0]
                for replacement in replacements
                if " : " in replacement
            ]
            suffix = ", ".join(labels) if labels else "marqueur state"
            errors.append(
                f"{_relative(repo_root, document_path)}: chemin pointé périmé: {suffix}"
            )

    if errors:
        errors.append(
            "corriger par : python3 scripts/governance/state_current.py --render"
        )
        return False, errors
    return True, []


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    """Exécute la génération ou la vérification de l'état courant."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--render", action="store_true")
    parser.add_argument("--docs", type=Path, action="append", default=None)
    args = parser.parse_args(argv)

    repo_root = args.repo_root.resolve()
    try:
        if args.render:
            state = build_state(repo_root)
            _write_json(_path(repo_root, _STATE_JSON), state)
            markdown_path = _path(repo_root, _STATE_MARKDOWN)
            markdown_path.parent.mkdir(parents=True, exist_ok=True)
            markdown_path.write_text(render(state), encoding="utf-8")
            for document in args.docs or []:
                candidate = document if document.is_absolute() else repo_root / document
                document_path = _within_repo(repo_root, candidate)
                try:
                    content = document_path.read_text(encoding="utf-8")
                except OSError as exc:
                    raise ValueError(
                        f"document inaccessible: {document_path}: {exc}"
                    ) from exc
                rendered, _ = inject(content, state, str(document_path))
                if rendered != content:
                    document_path.write_text(rendered, encoding="utf-8")
            return 0
        ok, errors = check(repo_root, args.docs)
    except (OSError, UnicodeError, ValueError, TypeError, KeyError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if not ok:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
