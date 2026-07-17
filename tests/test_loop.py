"""Tests for the governed loop module."""
import pytest
from src.forgeai.loop import (
    LoopError,
    LoopResult,
    run_loop,
    make_command_step,
    make_command_check,
)


def test_complete_avant_budget():
    counter = 0

    def step(i: int):
        nonlocal counter
        counter += 1

    def is_complete() -> bool:
        return counter >= 3

    result = run_loop(step, is_complete, max_iterations=10)
    assert result == LoopResult(completed=True, iterations=3, reason="completion")
    assert counter == 3


def test_budget_epuise():
    call_count = 0

    def step(i: int):
        nonlocal call_count
        call_count += 1

    def is_complete() -> bool:
        return False

    result = run_loop(step, is_complete, max_iterations=4)
    assert result == LoopResult(completed=False, iterations=4, reason="budget")
    assert call_count == 4


def test_max_iterations_invalide_leve():
    with pytest.raises(LoopError, match="max_iterations doit être >= 1"):
        run_loop(lambda i: None, lambda: False, max_iterations=0)


def test_on_iteration_appele_chaque_fois():
    calls = []
    counter = 0

    def step(i: int):
        nonlocal counter
        counter += 1

    def is_complete() -> bool:
        return counter >= 2

    def on_iteration(i: int, done: bool):
        calls.append((i, done))

    result = run_loop(step, is_complete, max_iterations=5, on_iteration=on_iteration)
    assert result == LoopResult(completed=True, iterations=2, reason="completion")
    assert calls == [(1, False), (2, True)]


def test_make_command_step():
    executed_cmds = []

    def runner(cmd: str) -> int:
        executed_cmds.append(cmd)
        return 0  # success code, irrelevant for step

    step_fn = make_command_step("echo hello", runner)

    step_fn(1)
    assert executed_cmds == ["echo hello"]

    step_fn(2)
    assert executed_cmds == ["echo hello", "echo hello"]


def test_make_command_check():
    def runner(cmd: str) -> int:
        runner.calls.append(cmd)
        return 0 if cmd == "check_ready" else 1

    runner.calls = []

    check_ok = make_command_check("check_ready", runner)
    assert check_ok() is True
    assert runner.calls == ["check_ready"]

    check_fail = make_command_check("not_ready", runner)
    assert check_fail() is False
    assert runner.calls == ["check_ready", "not_ready"]


def test_cli_loop_run_completion_et_budget(tmp_path):
    """Chemin CLI : --until true => complétion (rc 0) ; --until false => budget épuisé (rc 13)."""
    from forgeai.cli import main
    reg = tmp_path / "r.jsonl"
    rc = main(["loop", "run", "--max-iter", "5", "--step", "true", "--until", "true",
               "--registre", str(reg)])
    assert rc == 0
    rc2 = main(["loop", "run", "--max-iter", "3", "--step", "true", "--until", "false",
                "--registre", str(reg)])
    assert rc2 == 13
