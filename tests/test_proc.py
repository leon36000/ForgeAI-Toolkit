import ast
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from forgeai.core.proc import (
    RunnerCancelledError,
    RunnerTimeoutError,
    _kill_tree,
    timed_runner,
)

posix_only = pytest.mark.skipif(
    os.name != "posix",
    reason="mécanisme de groupe de process POSIX (os.killpg / start_new_session) : la branche "
    "Windows (taskkill /F /T) est couverte de façon déterministe par le mock G5 "
    "(test_windows_kill_branch, os.name monkeypatché) ; proc.py est stdlib pur donc importable "
    "partout. La portabilité de l'analyse de commande (shlex.split, POSIX) est un défaut "
    "pré-existant du runner loop, hors périmètre CLI-036, écart consigné au Registres/mission.jsonl.",
)


def _wait_dead(pid: int, timeout: float = 5.0) -> bool:
    """True dès que ``pid`` n'existe plus (tolère le bref état zombie avant reap)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except (ProcessLookupError, OSError):
            return True
        time.sleep(0.05)
    return False


# ---------------------------------------------------------------------------
# G1 – kill d'arbre réel (POSIX) : le petit-enfant, enfant NORMAL du step (donc
#      dans le même groupe de session), est bien tué avec le step au timeout.
# ---------------------------------------------------------------------------
@posix_only
def test_kill_tree_real(tmp_path: Path) -> None:
    orphan_pid_file = tmp_path / "orphan.pid"
    script = tmp_path / "make_orphan.py"
    # NB : le petit-enfant NE prend PAS start_new_session -> il reste dans le
    # groupe du step et doit donc être atteint par le kill d'arbre (killpg).
    script.write_text(
        "import subprocess, sys, time\n"
        "grandchild = subprocess.Popen(\n"
        "    [sys.executable, '-c', 'import time; time.sleep(999)'],\n"
        ")\n"
        "with open(sys.argv[1], 'w') as f:\n"
        "    f.write(str(grandchild.pid))\n"
        "time.sleep(999)\n"
    )
    cmd = f"{sys.executable} {script} {orphan_pid_file}"
    runner = timed_runner(timeout_seconds=1.0, grace_seconds=0.5)
    with pytest.raises(RunnerTimeoutError):
        runner(cmd)

    pid = int(orphan_pid_file.read_text().strip())
    assert _wait_dead(pid), f"le petit-enfant {pid} a survécu au kill d'arbre"


# ---------------------------------------------------------------------------
# G2 – chemin heureux
# ---------------------------------------------------------------------------
def test_happy_path() -> None:
    runner = timed_runner(None)
    ret = runner(f'{sys.executable} -c "exit(0)"')
    assert ret == 0


# ---------------------------------------------------------------------------
# G3 – timeout dépassé
# ---------------------------------------------------------------------------
def test_timeout() -> None:
    runner = timed_runner(timeout_seconds=0.5, grace_seconds=0.3)
    start = time.monotonic()
    with pytest.raises(RunnerTimeoutError):
        runner(f'{sys.executable} -c "import time; time.sleep(999)"')
    elapsed = time.monotonic() - start
    assert elapsed < 0.5 + 0.3 + 1.0  # large tolérance


# ---------------------------------------------------------------------------
# G4 – annulation via SIGINT (POSIX)
# ---------------------------------------------------------------------------
@posix_only
def test_cancellation() -> None:
    def send_signal() -> None:
        time.sleep(0.3)
        os.kill(os.getpid(), signal.SIGINT)

    thread = threading.Thread(target=send_signal)
    thread.start()
    runner = timed_runner(None)
    with pytest.raises(RunnerCancelledError):
        runner(f'{sys.executable} -c "import time; time.sleep(10)"')
    thread.join()


# ---------------------------------------------------------------------------
# G5 – branche Windows kill (mock)
# ---------------------------------------------------------------------------
def test_windows_kill_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force os.name → 'nt' pour valider l'appel à taskkill."""
    monkeypatch.setattr(os, "name", "nt")
    fake_proc = subprocess.Popen([sys.executable, "-c", "exit(0)"])
    calls = []

    def mock_run(args, **kwargs):  # type: ignore
        calls.append(args)
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(subprocess, "run", mock_run)
    try:
        _kill_tree(fake_proc, 5.0)
    finally:
        fake_proc.wait()

    assert len(calls) == 1
    cmd = calls[0]
    assert cmd[:3] == ["taskkill", "/F", "/T"]
    assert "/PID" in cmd
    assert str(fake_proc.pid) in cmd


# ---------------------------------------------------------------------------
# G6 – idempotence de _kill_tree et timeout=None sur step court
# ---------------------------------------------------------------------------
def test_idempotence_kill_tree_dead_process() -> None:
    proc = subprocess.Popen([sys.executable, "-c", "exit(0)"])
    proc.wait()
    # Ne doit rien lever
    _kill_tree(proc, 0.1)


def test_timeout_none_short_step() -> None:
    runner = timed_runner(None)
    ret = runner(f'{sys.executable} -c "exit(42)"')
    assert ret == 42


# ---------------------------------------------------------------------------
# G9 – escalade SIGKILL (POSIX) : un process qui IGNORE SIGTERM ne meurt que par
#      SIGKILL ; prouve que l'escalade après la grâce est PORTEUSE (sans elle le
#      process survivrait). Teste _kill_tree directement pour cibler l'escalade.
# ---------------------------------------------------------------------------
@posix_only
def test_kill_tree_escalates_to_sigkill(tmp_path: Path) -> None:
    ready = tmp_path / "ready"
    # Le process installe SIG_IGN sur SIGTERM PUIS signale sa disponibilité :
    # sans ce handshake, le SIGTERM de _kill_tree gagnerait la course de démarrage
    # et tuerait le process avant l'installation du handler (l'escalade ne serait
    # jamais exercée — le test deviendrait non détectant).
    code = (
        "import signal, time, sys\n"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        "open(sys.argv[1], 'w').close()\n"
        "time.sleep(999)\n"
    )
    proc = subprocess.Popen(
        [sys.executable, "-c", code, str(ready)],
        start_new_session=True,
    )
    try:
        deadline = time.monotonic() + 5.0
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert ready.exists(), "le process n'a pas signalé l'installation du handler"
        _kill_tree(proc, grace_seconds=0.4)
        assert _wait_dead(proc.pid), (
            "le process ignorant SIGTERM a survécu : escalade SIGKILL absente"
        )
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()


# ---------------------------------------------------------------------------
# G7 – AST : proc.py ne contient aucun import forgeai.*
# ---------------------------------------------------------------------------
def test_proc_no_forgeai_import() -> None:
    proc_file = (
        Path(__file__).resolve().parent.parent / "src" / "forgeai" / "core" / "proc.py"
    )
    tree = ast.parse(proc_file.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith("forgeai"), (
                    f"Import interdit trouvé : import {alias.name}"
                )
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.startswith("forgeai"):
                pytest.fail(f"Import interdit trouvé : from {node.module} ...")


# ---------------------------------------------------------------------------
# G8 – CLI loop run --timeout : _loop_run RETOURNE 14 (cli.main renvoie l'int,
#      seul sys.exit(main()) au __main__ lèverait SystemExit).
# ---------------------------------------------------------------------------
def test_cli_loop_timeout(tmp_path: Path) -> None:
    import forgeai.cli as cli

    registre_path = tmp_path / "registre.jsonl"
    step_cmd = f'{sys.executable} -c "import time; time.sleep(999)"'
    until_cmd = f'{sys.executable} -c "exit(0)"'
    args = [
        "loop",
        "run",
        "--max-iter",
        "1",
        "--step",
        step_cmd,
        "--until",
        until_cmd,
        "--timeout",
        "0.5",
        "--registre",
        str(registre_path),
    ]
    assert cli.main(args) == 14


# ---------------------------------------------------------------------------
# G10 – mapping CLI de RunnerCancelledError -> code 15 (via cli.main). G4 ne prouve
#       que la levée au niveau runner ; ici on exerce le `except` de _loop_run.
# ---------------------------------------------------------------------------
def test_cli_loop_cancel_maps_to_15(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import forgeai.core.proc as proc
    import forgeai.cli as cli

    def fake_timed_runner(timeout_seconds, grace_seconds=5.0):
        def _r(cmd: str) -> int:
            raise proc.RunnerCancelledError("annulation simulée")
        return _r

    # _loop_run fait `from forgeai.core.proc import timed_runner` à l'exécution :
    # patcher l'attribut du module suffit à intercepter le dispatch.
    monkeypatch.setattr(proc, "timed_runner", fake_timed_runner)
    registre_path = tmp_path / "registre.jsonl"
    args = [
        "loop", "run", "--max-iter", "1",
        "--step", "true", "--until", "true",
        "--registre", str(registre_path),
    ]
    assert cli.main(args) == 15
