"""Tests P2-F22 — CLI `forgeai node status` (kubectl simulé par fixture réelle)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import forgeai.cli as cli
from forgeai.core.runner import FixtureRunner

FIXTURES = Path(__file__).parent / "fixtures" / "k3s"


def _wire(monkeypatch):
    fixture = (FIXTURES / "get_nodes_real.json").read_text(encoding="utf-8")
    monkeypatch.setattr(cli, "SubprocessRunner", lambda: FixtureRunner({"kubectl": fixture}))


def test_node_status_affiche_et_scelle(monkeypatch, tmp_path, capsys):
    _wire(monkeypatch)
    reg = tmp_path / "reg.jsonl"
    code = cli.main(["node", "status", "--registre", str(reg), "--witness"])
    out = capsys.readouterr().out
    assert code == 0
    assert "2/4 nœuds Ready" in out
    assert "NODE_WITNESS=" in out
    entry = json.loads(reg.read_text(encoding="utf-8").splitlines()[-1])
    assert entry["type"] == "jonction_prouvee"
    assert entry["payload"]["ready"] == 2


def test_node_status_sans_witness_ne_scelle_pas(monkeypatch, tmp_path, capsys):
    _wire(monkeypatch)
    reg = tmp_path / "reg.jsonl"
    assert cli.main(["node", "status", "--registre", str(reg)]) == 0
    assert not reg.exists()


def test_node_status_cluster_injoignable(monkeypatch, capsys):
    monkeypatch.setattr(cli, "SubprocessRunner", lambda: FixtureRunner({}))
    assert cli.main(["node", "status"]) == 8
