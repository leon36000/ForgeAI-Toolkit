"""Tests du dépouillement déterministe des revues aveugles."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import tally


def _verdict(dossier, nom, verdict, objections=None):
    (dossier / f"{nom}.verdict.json").write_text(
        json.dumps({"verdict": verdict, "objections": objections or []}),
        encoding="utf-8",
    )


def test_consensus_atteint(tmp_path):
    for i in range(7):
        _verdict(tmp_path, f"m{i}", "APPROVE")
    _verdict(tmp_path, "m7", "REJECT")
    verdicts = tally.lire_verdicts(tmp_path)
    consensus, rapport = tally.depouiller(verdicts, approve_min=7)
    assert consensus
    assert "CONSENSUS" in rapport


def test_consensus_refuse_sous_le_seuil(tmp_path):
    for i in range(6):
        _verdict(tmp_path, f"m{i}", "APPROVE")
    _verdict(tmp_path, "m6", "REJECT")
    consensus, _ = tally.depouiller(tally.lire_verdicts(tmp_path), approve_min=7)
    assert not consensus


def test_objection_critique_bloque_meme_avec_seuil(tmp_path):
    for i in range(8):
        _verdict(tmp_path, f"m{i}", "APPROVE")
    _verdict(tmp_path, "m8", "REJECT",
             [{"severite": "critique", "description": "faille X", "preuve": "y"}])
    consensus, rapport = tally.depouiller(tally.lire_verdicts(tmp_path), approve_min=7)
    assert not consensus
    assert "faille X" in rapport


def test_objection_critique_resolue_ne_bloque_pas(tmp_path):
    for i in range(7):
        _verdict(tmp_path, f"m{i}", "APPROVE")
    _verdict(tmp_path, "m7", "REJECT",
             [{"severite": "critique", "description": "réglée", "preuve": "z", "resolu": True}])
    consensus, _ = tally.depouiller(tally.lire_verdicts(tmp_path), approve_min=7)
    assert consensus


def test_verdict_invalide_rejete(tmp_path):
    (tmp_path / "m0.verdict.json").write_text('{"verdict": "PEUT-ETRE"}', encoding="utf-8")
    with pytest.raises(SystemExit):
        tally.lire_verdicts(tmp_path)
