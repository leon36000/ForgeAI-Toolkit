"""Régressions FIX-AUDIT-1 : le gate ne doit jamais réussir sans revue dépouillée."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
GATE = REPO / "scripts" / "reviews_gate.py"
MESSAGE_SUCCES = "GATE OK : toutes les revues liantes sont APPROVE 3/3."


def _execute_gate(manifest: Path, reviews_root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(GATE),
            "--manifest",
            str(manifest),
            "--reviews-root",
            str(reviews_root),
        ],
        capture_output=True,
        check=False,
        text=True,
    )


def test_defaut_fail_open_manifeste_vide_doit_echouer(tmp_path: Path) -> None:
    manifest = tmp_path / "BINDING.txt"
    manifest.write_text("", encoding="utf-8")
    reviews_root = tmp_path / "reviews"
    reviews_root.mkdir()

    result = _execute_gate(manifest, reviews_root)

    assert result.returncode != 0
    assert "manifeste" in result.stdout
    assert "vide ou absent" in result.stdout


def test_defaut_fail_open_manifeste_supprime_doit_echouer(tmp_path: Path) -> None:
    manifest = tmp_path / "BINDING.txt"
    manifest.write_text("S-1\n", encoding="utf-8")
    manifest.unlink()
    reviews_root = tmp_path / "reviews"
    reviews_root.mkdir()

    result = _execute_gate(manifest, reviews_root)

    assert result.returncode != 0
    assert "manifeste" in result.stdout
    assert "vide ou absent" in result.stdout


def test_defaut_fail_open_aucun_depouillement_n_imprime_pas_le_succes(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "BINDING.txt"
    manifest.write_text("", encoding="utf-8")
    reviews_root = tmp_path / "reviews"
    reviews_root.mkdir()

    result = _execute_gate(manifest, reviews_root)

    assert result.returncode != 0
    assert MESSAGE_SUCCES not in result.stdout
