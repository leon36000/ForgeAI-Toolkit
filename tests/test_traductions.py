"""Tests du pipeline F23 (scripts/traductions.py) — garde-fous d'application."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import traductions


def test_parse_lot_format_inline(tmp_path):
    lot = tmp_path / "lot.yaml"
    lot.write_text('traductions:\n  - {nom: "Brique X", en: "Brick X does things."}\n',
                   encoding="utf-8")
    assert traductions.parse_lot(lot) == {"Brique X": "Brick X does things."}


def test_parse_lot_format_bloc(tmp_path):
    lot = tmp_path / "lot.yaml"
    lot.write_text('  - nom: "Brique Y"\n    en: "Brick Y."\n', encoding="utf-8")
    assert traductions.parse_lot(lot) == {"Brique Y": "Brick Y."}


def test_parse_lot_vide_echoue(tmp_path):
    lot = tmp_path / "vide.yaml"
    lot.write_text("rien: ici\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        traductions.parse_lot(lot)


def test_apply_refuse_nom_inconnu(tmp_path, monkeypatch, capsys):
    lot = tmp_path / "lot.yaml"
    lot.write_text('- {nom: "N Existe Pas", en: "x"}\n', encoding="utf-8")
    with pytest.raises(SystemExit):
        traductions.cmd_apply([lot])
    assert "nom inconnu" in capsys.readouterr().out


def test_apply_refuse_ecrasement(tmp_path, capsys):
    # Activepieces a été traduite au lot pilote — le ré-appliquer doit échouer.
    lot = tmp_path / "lot.yaml"
    lot.write_text('- {nom: "Activepieces", en: "overwrite attempt"}\n', encoding="utf-8")
    with pytest.raises(SystemExit):
        traductions.cmd_apply([lot])
    assert "déjà traduit" in capsys.readouterr().out
