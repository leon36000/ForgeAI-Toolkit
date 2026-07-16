"""Tests du module de gestion des budgets de tokens."""

import pytest

from forgeai.models.budget import BudgetError, BudgetState, BudgetTracker


def test_set_puis_record_accumule(tmp_path):
    tracker = BudgetTracker(tmp_path)
    tracker.set_budget("a", 1000)
    assert tracker.record("a", 100) == "OK"
    assert tracker.record("a", 100) == "OK"
    assert tracker.status("a").used_tokens == 200


def test_alerte_au_seuil(tmp_path):
    tracker = BudgetTracker(tmp_path)
    tracker.set_budget("a", 100, 0.8)
    assert tracker.record("a", 80) == "ALERTE"


def test_coupure_au_quota(tmp_path):
    tracker = BudgetTracker(tmp_path)
    tracker.set_budget("a", 100)
    assert tracker.record("a", 100) == "COUPURE"
    assert tracker.record("a", 50) == "COUPURE"


def test_agent_inconnu(tmp_path):
    tracker = BudgetTracker(tmp_path)
    with pytest.raises(BudgetError):
        tracker.record("x", 1)
    with pytest.raises(BudgetError):
        tracker.status("x")


def test_validation(tmp_path):
    tracker = BudgetTracker(tmp_path)
    with pytest.raises(BudgetError):
        tracker.set_budget("a", -1)
    with pytest.raises(BudgetError):
        tracker.set_budget("a", 100, alert_ratio=1.5)

    tracker.set_budget("a", 100)
    with pytest.raises(BudgetError):
        tracker.record("a", -5)


def test_persistance(tmp_path):
    tracker = BudgetTracker(tmp_path)
    tracker.set_budget("a", 1000)
    tracker.record("a", 123)

    tracker2 = BudgetTracker(tmp_path)
    assert tracker2.status("a").used_tokens == 123


def test_report(tmp_path):
    tracker = BudgetTracker(tmp_path)
    tracker.set_budget("beta", 200)
    tracker.set_budget("alpha", 100)
    tracker.record("beta", 50)
    tracker.record("alpha", 10)

    report = tracker.report()
    assert len(report) == 2
    assert [state.agent for state in report] == ["alpha", "beta"]
    assert all(isinstance(state, BudgetState) for state in report)
    assert report[0].used_tokens == 10
    assert report[1].used_tokens == 50


from forgeai.cli import main


def test_cli_budget_set_status(tmp_path, capsys):
    home = tmp_path
    registre_path = tmp_path / "r.jsonl"
    assert main(["budget", "set", "--agent", "coder", "--quota", "1000",
                 "--home", str(home), "--registre", str(registre_path)]) == 0
    assert main(["budget", "status", "--agent", "coder",
                 "--home", str(home)]) == 0
    captured = capsys.readouterr()
    assert "coder" in captured.out


def test_budgets_json_corrompu_leve_budgeterror(tmp_path):
    from forgeai.models.budget import BudgetTracker, BudgetError
    (tmp_path / "budgets.json").write_text("{ pas du json valide", encoding="utf-8")
    with pytest.raises(BudgetError):
        BudgetTracker(tmp_path).status("x")
