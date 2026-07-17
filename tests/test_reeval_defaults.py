import json
from pathlib import Path

import pytest

from scripts.reeval_defaults import main, reevaluate_defaults, current_defaults
from forgeai.resources import catalogue_path


def test_catalogue_reel_optimal():
    """Le catalogue réel possède déjà les défauts optimaux (posés par B‑01)."""
    data = json.loads(catalogue_path().read_text())
    entries = data["entries"] if isinstance(data, dict) else data
    assert reevaluate_defaults(entries) == []


def test_propose_changement_avec_preuve():
    """Une catégorie dont le défaut courant n'est pas le meilleur ★ doit proposer un changement."""
    entries = [
        {"category": "X", "name": "A", "popularity": "★ 10", "default": True},
        {"category": "X", "name": "B", "popularity": "★ 999", "default": None},
    ]
    changes = reevaluate_defaults(entries)
    assert len(changes) == 1
    ch = changes[0]
    assert ch["category"] == "X"
    assert ch["current"] == "A"
    assert ch["proposed"] == "B"
    assert ch["current_stars"] == 10
    assert ch["proposed_stars"] == 999


def test_sans_defaut_courant():
    """Si aucune entrée n'a default=True, current est None et current_stars == 0."""
    entries = [
        {"category": "Y", "name": "C", "popularity": "★ 5", "default": None},
        {"category": "Y", "name": "D", "popularity": "★ 5", "default": None},
    ]
    changes = reevaluate_defaults(entries)
    assert len(changes) == 1
    ch = changes[0]
    assert ch["category"] == "Y"
    assert ch["current"] is None
    assert ch["proposed"] == "C"          # même ★ → plus petit nom
    assert ch["current_stars"] == 0
    assert ch["proposed_stars"] == 5


def test_main_journalise_si_flag(tmp_path: Path):
    """Avec --journal, les changements sont journalisés dans le registre."""
    entries = [
        {"category": "X", "name": "A", "popularity": "★ 10", "default": True},
        {"category": "X", "name": "B", "popularity": "★ 999", "default": None},
    ]
    catalogue_file = tmp_path / "catalogue.json"
    catalogue_file.write_text(json.dumps(entries), encoding="utf-8")
    registre_file = tmp_path / "r.jsonl"

    # Lancement avec journal
    exit_code = main([
        "--catalogue", str(catalogue_file),
        "--registre", str(registre_file),
        "--journal",
    ])
    assert exit_code == 0

    # Vérification du registre
    assert registre_file.exists()
    lignes = registre_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lignes) == 1
    ligne = json.loads(lignes[0])
    assert ligne["type"] == "default_reeval"
    assert ligne["actor"] == "recherche"
    payload = ligne["payload"]
    assert payload["category"] == "X"
    assert payload["current"] == "A"
    assert payload["proposed"] == "B"
    assert payload["current_stars"] == 10
    assert payload["proposed_stars"] == 999


def test_main_sans_journal_ne_touche_pas_le_registre(tmp_path: Path):
    """Sans --journal, le registre n'est pas créé/modifié."""
    entries = [
        {"category": "X", "name": "A", "popularity": "★ 10", "default": True},
        {"category": "X", "name": "B", "popularity": "★ 999", "default": None},
    ]
    catalogue_file = tmp_path / "catalogue.json"
    catalogue_file.write_text(json.dumps(entries), encoding="utf-8")
    registre_file = tmp_path / "r.jsonl"
    # Le fichier ne doit pas exister
    assert not registre_file.exists()

    exit_code = main([
        "--catalogue", str(catalogue_file),
        "--registre", str(registre_file),
    ])
    assert exit_code == 0
    # Il ne doit pas avoir été créé
    assert not registre_file.exists()
