"""Tests du registre append-only hash-chaîné."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import registre


def test_append_cree_une_chaine_valide(tmp_path):
    reg = tmp_path / "r.jsonl"
    first = registre.append(reg, "test", "pytest", {"n": 1})
    second = registre.append(reg, "test", "pytest", {"n": 2})

    assert first["seq"] == 1
    assert first["prev_hash"] == registre.GENESIS
    assert second["seq"] == 2
    assert second["prev_hash"] == first["hash"]
    assert registre.verify(reg) is None


def test_verify_detecte_une_alteration(tmp_path):
    reg = tmp_path / "r.jsonl"
    registre.append(reg, "test", "pytest", {"n": 1})
    registre.append(reg, "test", "pytest", {"n": 2})

    lines = reg.read_text(encoding="utf-8").splitlines()
    entry = json.loads(lines[0])
    entry["payload"] = {"n": 999}  # falsification sans recalcul du hash
    lines[0] = json.dumps(entry, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    reg.write_text("\n".join(lines) + "\n", encoding="utf-8")

    erreur = registre.verify(reg)
    assert erreur is not None
    assert "seq 1" in erreur


def test_verify_detecte_une_entree_supprimee(tmp_path):
    reg = tmp_path / "r.jsonl"
    registre.append(reg, "test", "pytest", {"n": 1})
    registre.append(reg, "test", "pytest", {"n": 2})

    lines = reg.read_text(encoding="utf-8").splitlines()
    reg.write_text(lines[1] + "\n", encoding="utf-8")  # suppression de la genèse

    assert registre.verify(reg) is not None


def test_registre_vide_est_valide(tmp_path):
    assert registre.verify(tmp_path / "absent.jsonl") is None
