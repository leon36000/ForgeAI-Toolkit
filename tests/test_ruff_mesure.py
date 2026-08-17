from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import ruff_mesure  # noqa: E402


# ---------------------------------------------------------------------------
# mesurer_violations — chemins d'erreur (mock subprocess.run)
# ---------------------------------------------------------------------------

def test_mesurer_violations_ruff_absent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ruff absent (FileNotFoundError) -> RuntimeError explicite."""

    def ruff_absent(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError("ruff")

    monkeypatch.setattr(ruff_mesure.subprocess, "run", ruff_absent)

    with pytest.raises(RuntimeError, match="ruff est indisponible"):
        ruff_mesure.mesurer_violations(tmp_path, ["ARG001"])


def test_mesurer_violations_code_retour_inattendu(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Code de retour hors {0, 1} -> RuntimeError mentionnant le code."""
    resultat = subprocess.CompletedProcess(
        args=["ruff"], returncode=2, stdout="", stderr="erreur ruff",
    )
    monkeypatch.setattr(ruff_mesure.subprocess, "run", lambda *a, **k: resultat)

    with pytest.raises(RuntimeError, match="code 2"):
        ruff_mesure.mesurer_violations(tmp_path, ["ARG001"])


def test_mesurer_violations_sortie_json_invalide(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sortie non-JSON -> RuntimeError."""
    resultat = subprocess.CompletedProcess(
        args=["ruff"], returncode=0, stdout="pas du json", stderr="",
    )
    monkeypatch.setattr(ruff_mesure.subprocess, "run", lambda *a, **k: resultat)

    with pytest.raises(RuntimeError, match="sortie JSON de ruff est invalide"):
        ruff_mesure.mesurer_violations(tmp_path, ["ARG001"])


def test_mesurer_violations_sortie_json_pas_une_liste(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """JSON valide mais pas une liste de dicts -> RuntimeError."""
    resultat = subprocess.CompletedProcess(
        args=["ruff"], returncode=0, stdout=json.dumps({"pas": "une liste"}), stderr="",
    )
    monkeypatch.setattr(ruff_mesure.subprocess, "run", lambda *a, **k: resultat)

    with pytest.raises(RuntimeError, match="doit être une liste de violations"):
        ruff_mesure.mesurer_violations(tmp_path, ["ARG001"])


def test_mesurer_violations_normalise_les_chemins_en_posix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Chemin absolu interne -> relatif POSIX (.as_posix(), jamais de '\\\\')."""
    chemin_interne = tmp_path / "src" / "module.py"
    chemin_interne.parent.mkdir()
    chemin_interne.write_text("", encoding="utf-8")
    chemin_externe = Path("/tmp/fichier-externe.py")

    resultat = subprocess.CompletedProcess(
        args=["ruff"],
        returncode=0,
        stdout=json.dumps(
            [
                {"code": "ARG001", "filename": str(chemin_interne)},
                {"code": "S101", "filename": str(chemin_externe)},
            ]
        ),
        stderr="",
    )
    monkeypatch.setattr(ruff_mesure.subprocess, "run", lambda *a, **k: resultat)

    violations = ruff_mesure.mesurer_violations(tmp_path, ["ARG001", "S101"])

    assert violations[0]["filename"] == "src/module.py"
    assert "\\" not in violations[0]["filename"]
    # Chemin externe (hors racine) : conservé tel quel, pas d'exception.
    assert violations[1]["filename"] == str(chemin_externe)


# ---------------------------------------------------------------------------
# mesurer_violations — bout en bout avec ruff réel sur un mini-projet jetable
# ---------------------------------------------------------------------------

def test_mesurer_violations_sur_mini_projet_reel(tmp_path: Path) -> None:
    """ruff réel sur un projet jetable : ARG001 détecté, chemin relatif POSIX."""
    (tmp_path / "src" / "pkg").mkdir(parents=True)
    (tmp_path / "scripts").mkdir()
    (tmp_path / "src" / "pkg" / "mod.py").write_text(
        "def f(x, y):\n    return x\n", encoding="utf-8"
    )

    violations = ruff_mesure.mesurer_violations(tmp_path, ["ARG001"])

    assert any(
        violation.get("code") == "ARG001"
        and violation.get("filename") == "src/pkg/mod.py"
        for violation in violations
    )
