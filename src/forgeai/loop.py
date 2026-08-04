"""Loop utilities for governed agent loops."""
from dataclasses import dataclass
from typing import Callable, Optional

from forgeai.i18n import t


class LoopError(Exception):
    """Raised when loop parameters are invalid."""


@dataclass(frozen=True)
class LoopResult:
    completed: bool
    iterations: int
    reason: str  # "completion" or "budget"

    def __post_init__(self):
        if self.reason not in ("completion", "budget"):
            raise ValueError("reason must be 'completion' or 'budget'")


def run_loop(
    step: Callable[[int], None],
    is_complete: Callable[[], bool],
    max_iterations: int,
    *,
    on_iteration: Optional[Callable[[int, bool], None]] = None,
) -> LoopResult:
    """Run a governed loop.

    Args:
        step: Called for each iteration with the 1-based index.
        is_complete: Checked after each step; if True, the loop completes.
        max_iterations: Maximum number of iterations; must be >= 1.
        on_iteration: Called after each iteration with (index, completed_bool).

    Returns:
        LoopResult indicating completion status, iterations run, and reason.

    Raises:
        LoopError: If max_iterations < 1.
    """
    if max_iterations < 1:
        raise LoopError(t("loop.run_loop.max_iterations_invalide"))

    for i in range(1, max_iterations + 1):
        step(i)
        done = bool(is_complete())
        if on_iteration:
            on_iteration(i, done)
        if done:
            return LoopResult(completed=True, iterations=i, reason="completion")

    return LoopResult(completed=False, iterations=max_iterations, reason="budget")


def make_command_step(step_cmd: str, runner: Callable[[str], int]) -> Callable[[int], None]:
    """Return a step function that executes a command via runner.

    The returned step ignores the iteration number.
    """
    def _step(iteration: int) -> None:
        runner(step_cmd)
    return _step


def make_command_check(until_cmd: str, runner: Callable[[str], int]) -> Callable[[], bool]:
    """Return a completion check that runs a command; exit 0 means complete."""
    def _check() -> bool:
        return runner(until_cmd) == 0
    return _check
