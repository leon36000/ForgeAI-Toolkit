"""FAI-0002 (#107) — spécifications de concurrence du registre hash-chaîné.

Le registre append-only est la pièce d'auditabilité du Toolkit ; son intégrité doit tenir
sous accès concurrent (le serveur web est multi-thread et append depuis ses handlers, et
plusieurs process CLI peuvent viser le même fichier). Ces tests spécifient le COMPORTEMENT
attendu : N appends concurrents ⇒ chaîne intègre, aucune écriture perdue, seq unique.

RED avant correctif : sur `registre.append()` sans verrou, la course forke la chaîne
(seq/prev_hash dupliqués), perd des écritures et corrompt des lignes ⇒ ces tests échouent.
"""
import multiprocessing as mp
import os
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import registre


def _appende_lot(reg_path: str, n: int, actor: str) -> None:
    reg = Path(reg_path)
    for i in range(n):
        registre.append(reg, "charge", actor, {"i": i})


def _seqs_et_lignes(reg: Path) -> tuple[list[int], int]:
    entries = registre._read_entries(reg)
    return [e["seq"] for e in entries], len(entries)


def test_appends_multiprocessus_gardent_la_chaine_intacte(tmp_path):
    """Comportement : P process × K appends sur le même fichier ⇒ P*K entrées,
    seq 1..P*K uniques, chaîne vérifiée intègre, zéro écriture perdue."""
    reg = tmp_path / "r.jsonl"
    P, K = 8, 20
    # fork n'existe pas sur Windows ; spawn y expose la même course (les deux
    # process font lecture-intégrale puis append sur le même fichier).
    ctx = mp.get_context("fork" if os.name == "posix" else "spawn")
    barrier = ctx.Barrier(P)

    def worker(idx):
        barrier.wait()  # maximise la contention : tous démarrent ensemble
        _appende_lot(str(reg), K, f"p{idx}")

    procs = [ctx.Process(target=worker, args=(i,)) for i in range(P)]
    for p in procs:
        p.start()
    for p in procs:
        p.join()

    seqs, n = _seqs_et_lignes(reg)
    assert n == P * K, f"écritures perdues : {n}/{P*K}"
    assert sorted(seqs) == list(range(1, P * K + 1)), "seq dupliqués/manquants (fork de chaîne)"
    assert registre.verify(reg) is None, f"chaîne rompue : {registre.verify(reg)}"


def test_appends_multithreads_gardent_la_chaine_intacte(tmp_path):
    """Comportement : T threads × K appends (même process) ⇒ chaîne intègre.
    Le verrou doit sérialiser aussi les threads (descripteurs de fichier distincts)."""
    reg = tmp_path / "r.jsonl"
    T, K = 8, 20
    barrier = threading.Barrier(T)

    def worker(idx):
        barrier.wait()
        _appende_lot(str(reg), K, f"t{idx}")

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(T)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    seqs, n = _seqs_et_lignes(reg)
    assert n == T * K, f"écritures perdues : {n}/{T*K}"
    assert sorted(seqs) == list(range(1, T * K + 1)), "seq dupliqués/manquants (course thread)"
    assert registre.verify(reg) is None


def test_append_sequentiel_reste_intact(tmp_path):
    """Régression : le comportement séquentiel nominal est préservé."""
    reg = tmp_path / "r.jsonl"
    a = registre.append(reg, "t", "seq", {"n": 1})
    b = registre.append(reg, "t", "seq", {"n": 2})
    assert a["seq"] == 1 and a["prev_hash"] == registre.GENESIS
    assert b["seq"] == 2 and b["prev_hash"] == a["hash"]
    assert registre.verify(reg) is None


def test_append_refuse_un_fichier_corrompu(tmp_path):
    """Sous verrou, append lit le fichier existant ; une ligne JSON corrompue préexistante
    est signalée (SystemExit) au lieu d'être silencieusement écrasée."""
    reg = tmp_path / "r.jsonl"
    registre.append(reg, "t", "seq", {"n": 1})
    with reg.open("a", encoding="utf-8") as fh:
        fh.write("{ceci n'est pas du json}\n")
    with pytest.raises(SystemExit):
        registre.append(reg, "t", "seq", {"n": 2})

# ---------------------------------------------------------------------------
# C6 : la CLI officielle (wrapper scripts/registre.py) sérialise les appends
# concurrents multi-processus sur les trois OS.
# ---------------------------------------------------------------------------

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def _cli_worker(reg_path: str, actor: str, n: int) -> None:
    """Sous-processus : `n` appends via la CLI officielle (scripts/registre.py)."""
    import subprocess
    import sys as _sys

    for _ in range(n):
        cp = subprocess.run(
            [
                _sys.executable,
                str(SCRIPTS / "registre.py"),
                "append",
                reg_path,
                "--type",
                "t",
                "--actor",
                actor,
                "--payload-json",
                "{}",
            ],
            capture_output=True,
            text=True,
        )
        if cp.returncode != 0:
            raise AssertionError(
                f"CLI append a échoué (actor={actor}): rc={cp.returncode}\n"
                f"stdout={cp.stdout}\nstderr={cp.stderr}"
            )


def test_cli_serialize_appends_multi_processus(tmp_path):
    """4 sous-processus × 5 appends CLI concurrents ⇒ chaîne intègre, 20 entrées, seq 1..20."""
    import sys as _sys

    reg = tmp_path / "registre_cli.jsonl"
    reg_path = str(reg)

    n_workers = 4
    n_per_worker = 5
    total = n_workers * n_per_worker  # 20

    # Vagues concurrentes : 4 Popen vivants à la fois, 5 vagues.
    for wave in range(n_per_worker):
        procs = []
        for i in range(n_workers):
            actor = f"cli{wave * n_workers + i}"
            proc = mp.get_context("fork" if os.name == "posix" else "spawn").Process(
                target=_cli_worker, args=(reg_path, actor, 1)
            )
            proc.start()
            procs.append(proc)
        for proc in procs:
            proc.join()
            assert proc.exitcode == 0, (
                f"sous-processus CLI terminé en code {proc.exitcode}"
            )

    # Chaîne intègre, 20 entrées, seq 1..20 uniques.
    assert registre.verify(reg) is None, f"chaîne rompue : {registre.verify(reg)}"
    seqs, count = _seqs_et_lignes(reg)
    assert count == total, f"attendu {total} entrées, obtenu {count}"
    assert seqs == list(range(1, total + 1)), f"seq non consécutifs: {seqs}"
