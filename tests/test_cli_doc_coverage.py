from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
SRC_DIR = REPO_ROOT / "src"
DOC_PATH = REPO_ROOT / "Docs" / "reference" / "cli.md"
BASELINE_PATH = REPO_ROOT / "Docs" / "BASELINE-CLI-DOC.json"
CLI_PATH = SRC_DIR / "forgeai" / "cli.py"

sys.path.insert(0, str(SCRIPTS_DIR))
import gate_docs  # noqa: E402


def test_baseline_vide() -> None:
    data = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))

    assert isinstance(data.get("commandes"), list)
    assert data["commandes"] == []


def test_toutes_commandes_premier_niveau_documentees() -> None:
    commandes = set(gate_docs.sous_commandes(CLI_PATH))
    documentees = set(gate_docs.commandes_documentees(REPO_ROOT))

    assert commandes
    assert commandes <= documentees


def test_gate_docs_exit_0_sur_vrai_depot() -> None:
    assert gate_docs.main([]) == 0


def test_report_mode_liste_zero_manquante(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert gate_docs.main(["--report"]) == 0

    sortie = capsys.readouterr().out.lower()
    assert "0" in sortie
    assert "non document" in sortie


def _safe_cli_invocations() -> dict[tuple[str, ...], list[str]]:
    wanted = {
        ("forgeai", "catalogue"),
        ("forgeai", "hardware"),
        ("forgeai", "ide", "list"),
        ("forgeai", "model", "list"),
        ("forgeai", "strategy", "show"),
        ("forgeai", "template", "list"),
        ("forgeai", "operators"),
    }
    found: dict[tuple[str, ...], list[str]] = {}
    in_shell_block = False

    for line in DOC_PATH.read_text(encoding="utf-8").splitlines():
        fence = re.match(r"^\s*```([A-Za-z0-9_-]*)\s*$", line)
        if fence:
            if in_shell_block:
                in_shell_block = False
            elif fence.group(1).lower() == "shell":
                in_shell_block = True
            continue

        if not in_shell_block:
            continue

        command_line = line.strip()
        if command_line.startswith("$"):
            command_line = command_line[1:].lstrip()
        if not command_line or command_line.startswith("#"):
            continue

        try:
            tokens = shlex.split(command_line)
        except ValueError:
            continue

        for prefix in wanted:
            if tuple(tokens[: len(prefix)]) == prefix:
                found.setdefault(prefix, tokens)
                break

    return found


def test_exemples_surs_du_cli_md_sont_executables() -> None:
    invocations = _safe_cli_invocations()
    expected = {
        ("forgeai", "catalogue"),
        ("forgeai", "hardware"),
        ("forgeai", "ide", "list"),
        ("forgeai", "model", "list"),
        ("forgeai", "strategy", "show"),
        ("forgeai", "template", "list"),
        ("forgeai", "operators"),
    }

    assert expected <= set(invocations)

    environment = os.environ.copy()
    existing_pythonpath = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = (
        str(SRC_DIR)
        if not existing_pythonpath
        else os.pathsep.join((str(SRC_DIR), existing_pythonpath))
    )

    for prefix in sorted(expected):
        invocation = [
            sys.executable,
            "-m",
            "forgeai",
            *invocations[prefix][1:],
        ]
        result = subprocess.run(
            invocation,
            cwd=REPO_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        assert result.returncode == 0, (
            f"Échec de {' '.join(invocation)} "
            f"(code {result.returncode})\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
