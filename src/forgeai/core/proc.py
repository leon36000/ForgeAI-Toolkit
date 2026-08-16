"""Gestion des processus avec timeout, annulation et kill d'arbre.

Module stdlib pur, portable POSIX/Windows.
"""
import os
import signal
import shlex
import subprocess
import sys
import threading
import time
from collections.abc import Callable

# NOTE i18n : PAS d'import de forgeai.i18n ici (délibéré, gardé par test_proc_no_forgeai_import
# dans tests/test_proc.py) — les 2 messages français ci-dessous restent non traduits,
# hors périmètre I18N-042.


class RunnerTimeoutError(RuntimeError):
    """Timeout dépassé pour une commande du runner."""


class RunnerCancelledError(RuntimeError):
    """Exécution annulée suite à un signal d'interruption (SIGINT)."""


def timed_runner(
    timeout_seconds: float | None,
    grace_seconds: float = 5.0,
) -> Callable[[str], int]:
    """Fabrique un runner qui exécute une commande avec timeout et annulation.

    Args:
        timeout_seconds: délai maximum avant kill d'arbre ; ``None`` = illimité.
        grace_seconds: délai entre SIGTERM et SIGKILL (POSIX uniquement).

    Returns:
        Un callable prenant une commande (str) et retournant le code de sortie.

    Raises:
        RunnerTimeoutError: si le timeout est atteint.
        RunnerCancelledError: si SIGINT est reçu.
    """

    def runner(cmd: str) -> int:
        argv = shlex.split(cmd)
        popen_kwargs: dict = {"args": argv}
        if os.name == "posix":
            popen_kwargs["start_new_session"] = True
        else:
            popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

        cancel_event = threading.Event()
        original_handler = signal.getsignal(signal.SIGINT)

        def handle_sigint(signum, frame):  # type: ignore
            cancel_event.set()

        signal.signal(signal.SIGINT, handle_sigint)

        try:
            p = subprocess.Popen(**popen_kwargs)
        except Exception:
            signal.signal(signal.SIGINT, original_handler)
            raise

        deadline = None
        if timeout_seconds is not None:
            deadline = time.monotonic() + timeout_seconds

        try:
            while p.poll() is None:
                if deadline is not None and time.monotonic() >= deadline:
                    break
                if cancel_event.is_set():
                    break
                if deadline is not None:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    wait_time = min(0.1, remaining)
                else:
                    wait_time = 0.1
                try:
                    p.wait(timeout=wait_time)
                except subprocess.TimeoutExpired:
                    continue

            if p.poll() is None:
                if deadline is not None and time.monotonic() >= deadline:
                    _kill_tree(p, grace_seconds)
                    raise RunnerTimeoutError(
                        f"Timeout après {timeout_seconds}s pour la commande : {cmd}"
                    )
                else:
                    _kill_tree(p, grace_seconds)
                    raise RunnerCancelledError(
                        f"Commande annulée par signal pour : {cmd}"
                    )
            return p.returncode
        finally:
            signal.signal(signal.SIGINT, original_handler)

    return runner


def kill_tree(proc, grace_seconds: float = 5.0) -> None:  # type: ignore
    """REL-038C : API PUBLIQUE — termine le groupe de processus de *proc* (grâce puis SIGKILL).

    Mince enveloppe autour de `_kill_tree` (CLI-036) : additive, elle ne modifie aucun appelant
    existant. Permet au serveur web de réutiliser la sémantique déjà éprouvée plutôt que de la
    ré-implémenter.
    """
    _kill_tree(proc, grace_seconds)


def _kill_tree(proc, grace_seconds: float) -> None:  # type: ignore
    """Tue récursivement le groupe de processus de *proc*, avec grâce.

    Args:
        proc: objet ``subprocess.Popen``.
        grace_seconds: délai d'attente entre SIGTERM et SIGKILL (POSIX).
    """
    if os.name == "posix":
        try:
            pgrp = os.getpgid(proc.pid)  # type: ignore
        except ProcessLookupError:
            return
        try:
            os.killpg(pgrp, signal.SIGTERM)  # type: ignore
        except ProcessLookupError:
            return
        time.sleep(grace_seconds)
        try:
            os.killpg(pgrp, 0)  # type: ignore
        except ProcessLookupError:
            try:
                proc.wait(timeout=5)  # type: ignore
            except (subprocess.TimeoutExpired, OSError):
                pass
            return
        try:
            os.killpg(pgrp, signal.SIGKILL)  # type: ignore
        except ProcessLookupError:
            pass
        try:
            proc.wait(timeout=5)  # type: ignore
        except subprocess.TimeoutExpired:
            message = (
                f"[kill_tree] process {proc.pid} n'a pas été réapé 5s après SIGKILL "
                "(possible D-state)"
            )
            try:
                print(message, file=sys.stderr)
            except UnicodeEncodeError:
                print(message.encode("ascii", "backslashreplace").decode("ascii"), file=sys.stderr)
    else:  # Windows
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],  # type: ignore
            capture_output=True,
            check=False,
        )
