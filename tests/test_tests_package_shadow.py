"""Regression test for deterministic imports from the repository test package."""

from __future__ import annotations

import pathlib
import os
import subprocess
import sys


def test_local_tests_package_resolves_before_installed_package() -> None:
    """A repository test sibling must remain importable in a polluted environment."""
    root = pathlib.Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    source_path = str(root / "src")
    environment["PYTHONPATH"] = os.pathsep.join(
        part for part in (source_path, environment.get("PYTHONPATH", "")) if part
    )
    probe = subprocess.run(
        [
            sys.executable,
            "-c",
            "import tests.test_routestore_concurrence as module; print(module.__file__)",
        ],
        cwd=root,
        check=False,
        capture_output=True,
        env=environment,
        text=True,
    )

    assert probe.returncode == 0, probe.stderr
    assert pathlib.Path(probe.stdout.strip()).resolve() == (
        root / "tests" / "test_routestore_concurrence.py"
    ).resolve()
