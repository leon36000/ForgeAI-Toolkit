from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import gate_git_ref  # noqa: E402


class _Result:
    """Simule un résultat de subprocess.run avec stdout et returncode minimal."""

    def __init__(self, stdout: str = ""):
        self.stdout = stdout
        self.returncode = 0


# ---------------------------------------------------------------------------
# valider_ref_git
# ---------------------------------------------------------------------------

def test_valider_ref_git_refuse_vide():
    """Un ref vide est refusé."""
    with pytest.raises(ValueError):
        gate_git_ref.valider_ref_git("")


def test_valider_ref_git_refuse_prefixe_tiret():
    """Un ref commençant par '-' est refusé (injection d'option git)."""
    with pytest.raises(ValueError):
        gate_git_ref.valider_ref_git("-branche")


def test_valider_ref_git_accepte_ref_normal():
    """Un ref normal comme origin/main ne lève pas d'erreur."""
    assert gate_git_ref.valider_ref_git("origin/main") is None


# ---------------------------------------------------------------------------
# charger_base_reference_git — erreurs git et chemins
# ---------------------------------------------------------------------------

def test_charger_base_reference_git_git_absent_premier_appel(tmp_path, monkeypatch):
    """FileNotFoundError sur rev-parse lève RuntimeError avec fetch-depth: 0."""
    chemin_base = tmp_path / "base.json"
    chemin_base.write_text("{}", encoding="utf-8")

    def fake_run(args, **kwargs):
        raise FileNotFoundError

    monkeypatch.setattr(gate_git_ref.subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="fetch-depth: 0"):
        gate_git_ref.charger_base_reference_git(
            tmp_path, chemin_base, "origin/main", lambda c, l: c
        )


def test_charger_base_reference_git_chemin_hors_racine(tmp_path_factory, monkeypatch):
    """Un chemin de base hors de la racine git est refusé avant git show."""
    racine = tmp_path_factory.mktemp("racine")
    chemin_base = tmp_path_factory.mktemp("hors") / "base.json"
    chemin_base.write_text("{}", encoding="utf-8")

    def fake_run(args, **kwargs):
        if args[:2] == ["git", "rev-parse"]:
            return _Result()
        raise AssertionError("subprocess.run ne doit pas être appelé une seconde fois")

    monkeypatch.setattr(gate_git_ref.subprocess, "run", fake_run)

    with pytest.raises(ValueError, match="hors de la racine git"):
        gate_git_ref.charger_base_reference_git(
            racine, chemin_base, "origin/main", lambda c, l: c
        )


def test_charger_base_reference_git_git_absent_second_appel(tmp_path, monkeypatch):
    """FileNotFoundError sur git show lève RuntimeError avec fetch-depth: 0."""
    chemin_base = tmp_path / "base.json"
    chemin_base.write_text("{}", encoding="utf-8")

    def fake_run(args, **kwargs):
        if args[:2] == ["git", "rev-parse"]:
            return _Result()
        raise FileNotFoundError

    monkeypatch.setattr(gate_git_ref.subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="fetch-depth: 0"):
        gate_git_ref.charger_base_reference_git(
            tmp_path, chemin_base, "origin/main", lambda c, l: c
        )


# ---------------------------------------------------------------------------
# charger_base_reference_git — succès, JSON invalide, référence absente
# ---------------------------------------------------------------------------

def test_charger_base_reference_git_succes_complet(tmp_path, monkeypatch):
    """Le chemin complet charge le JSON, appelle valider_base et retourne (contenu, "")."""
    chemin_base = tmp_path / "base.json"
    chemin_base.write_text("{}", encoding="utf-8")

    contenu_attendu = {
        "version": 1,
        "borne": {"total_erreurs": 0},
        "fichiers_proteges": [],
        "dette": {},
    }
    json_attendu = json.dumps(contenu_attendu)

    appels_valider_base = []

    def fake_valider_base(contenu, libelle):
        appels_valider_base.append((contenu, libelle))
        return contenu

    def fake_run(args, **kwargs):
        if args[:2] == ["git", "rev-parse"]:
            return _Result()
        if args[:2] == ["git", "show"]:
            return _Result(stdout=json_attendu)
        raise AssertionError(f"Appel subprocess inattendu: {args}")

    monkeypatch.setattr(gate_git_ref.subprocess, "run", fake_run)

    resultat, message = gate_git_ref.charger_base_reference_git(
        tmp_path, chemin_base, "origin/main", fake_valider_base
    )

    assert resultat == contenu_attendu
    assert message == ""
    assert appels_valider_base == [(contenu_attendu, "base de reference git")]


def test_charger_base_reference_git_json_invalide(tmp_path, monkeypatch):
    """Un JSON invalide dans git show lève ValueError mentionnant JSON invalide."""
    chemin_base = tmp_path / "base.json"
    chemin_base.write_text("{}", encoding="utf-8")

    def fake_run(args, **kwargs):
        if args[:2] == ["git", "rev-parse"]:
            return _Result()
        if args[:2] == ["git", "show"]:
            return _Result(stdout="{invalide")
        raise AssertionError(f"Appel subprocess inattendu: {args}")

    monkeypatch.setattr(gate_git_ref.subprocess, "run", fake_run)

    with pytest.raises(ValueError, match="JSON invalide"):
        gate_git_ref.charger_base_reference_git(
            tmp_path, chemin_base, "origin/main", lambda c, l: c
        )


def test_charger_base_reference_git_reference_absente(tmp_path, monkeypatch):
    """Une référence absente retourne (None, message_non_vide)."""
    chemin_base = tmp_path / "base.json"
    chemin_base.write_text("{}", encoding="utf-8")

    def fake_run(args, **kwargs):
        if args[:2] == ["git", "rev-parse"]:
            return _Result()
        raise gate_git_ref.subprocess.CalledProcessError(1, args)

    monkeypatch.setattr(gate_git_ref.subprocess, "run", fake_run)

    resultat, message = gate_git_ref.charger_base_reference_git(
        tmp_path, chemin_base, "origin/main", lambda c, l: c
    )

    assert resultat is None
    assert message != ""
