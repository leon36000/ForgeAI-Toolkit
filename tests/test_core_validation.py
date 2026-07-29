"""Tests pour src/forgeai/core/validation.py."""
import os
from pathlib import Path

import pytest

from forgeai.core.validation import (
    NODE_NAME_RE,
    ValidationError,
    resolve_within,
    valider_nom_simple,
)


# --- valider_nom_simple ---


def test_valider_nom_simple_valide():
    assert valider_nom_simple("abc") is None
    assert valider_nom_simple("a-b") is None
    assert valider_nom_simple("a.b") is None
    assert valider_nom_simple("x") is None


def test_valider_nom_simple_slash():
    with pytest.raises(ValidationError):
        valider_nom_simple("a/b")


def test_valider_nom_simple_double_point():
    with pytest.raises(ValidationError):
        valider_nom_simple("..")


def test_valider_nom_simple_double_point_inclus():
    # "a..b" contient ".." donc rejeté par le prédicat `".." in name`.
    with pytest.raises(ValidationError):
        valider_nom_simple("a..b")


def test_valider_nom_simple_vide():
    with pytest.raises(ValidationError):
        valider_nom_simple("")


def test_valider_nom_simple_point():
    with pytest.raises(ValidationError):
        valider_nom_simple(".")


# --- resolve_within ---


def test_resolve_within_absolu_dans_racine(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    cible = root / "file"
    cible.write_text("x")
    result = resolve_within(cible, root)
    assert result == Path(os.path.realpath(cible))


def test_resolve_within_racine_ellememe(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    result = resolve_within(root, root)
    assert result == Path(os.path.realpath(root))


def test_resolve_within_relatif_avec_base(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    cible = root / "file"
    cible.write_text("x")
    result = resolve_within("file", root, base=root)
    assert result == Path(os.path.realpath(cible))


def test_resolve_within_double_point_sortant(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    cible = root / ".." / "other"
    with pytest.raises(ValidationError):
        resolve_within(cible, root)


def test_resolve_within_double_point_interne(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    cible = root / "a" / ".." / "b"
    result = resolve_within(cible, root)
    assert result == Path(os.path.realpath(root / "b"))


def test_resolve_within_symlink_sortant(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    dehors = tmp_path / "dehors"
    dehors.mkdir()
    lien = root / "lien"
    os.symlink(dehors, lien)
    with pytest.raises(ValidationError):
        resolve_within(lien, root)


def test_resolve_within_symlink_entrant(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    cible = root / "file"
    cible.write_text("x")
    lien_racine = tmp_path / "lien_racine"
    os.symlink(root, lien_racine)
    result = resolve_within(lien_racine / "file", lien_racine)
    assert result == Path(os.path.realpath(cible))


def test_resolve_within_cible_inexistante_dans_racine(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    cible = root / "future"
    result = resolve_within(cible, root)
    assert result == Path(os.path.realpath(cible))


def test_resolve_within_cible_inexistante_hors_racine(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    cible = tmp_path / "future"
    with pytest.raises(ValidationError):
        resolve_within(cible, root)


def test_resolve_within_message_erreur(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    cible = tmp_path / "dehors"
    with pytest.raises(ValidationError) as exc_info:
        resolve_within(cible, root)
    msg = str(exc_info.value)
    assert os.path.realpath(str(cible)) in msg
    assert os.path.realpath(str(root)) in msg


def test_resolve_within_rejette_repertoire_frere_prefixe_commun(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    repo_evil = tmp_path / "repo-evil"
    repo_evil.mkdir()
    cible_evil = repo_evil / "x.txt"
    cible_evil.write_text("x")
    with pytest.raises(ValidationError):
        resolve_within(cible_evil, repo)
    cible_ok = repo / "x.txt"
    cible_ok.write_text("x")
    result = resolve_within(cible_ok, repo)
    assert result == Path(os.path.realpath(cible_ok))
