import subprocess
import sys
import tempfile

import pytest

PYTHON = sys.executable
CLI = [PYTHON, "-m", "forgeai.cli"]


def run(*args, stdin=None, env=None):
    return subprocess.run(
        CLI + list(args),
        stdin=stdin,
        capture_output=True,
        text=True,
        env=env,
    )


def test_no_gpu_flag_retire():
    res = run("template", "resolve", "--no-gpu", "agentique")
    assert res.returncode != 0
    assert "unrecognized arguments" in res.stderr

    res_ok = run("template", "resolve", "agentique")
    assert res_ok.returncode == 0


def test_wizard_stack_invalide_propre():
    with tempfile.TemporaryDirectory() as tmp:
        res = run(
            "wizard", "--ci", "--dry-run", "--stack", "zzz-inexistant", "--workdir", tmp
        )
    assert res.returncode == 8, res.stderr
    assert "ABORT [STACK]" in res.stderr
    assert "zzz-inexistant" in res.stderr
    assert "Traceback" not in res.stderr


def test_add_cloud_sans_tty_propre():
    with tempfile.TemporaryDirectory() as tmp:
        res = run(
            "model",
            "add-cloud",
            "--name",
            "r",
            "--provenance",
            "direct",
            "--model-id",
            "m",
            "--base-url",
            "http://x",
            "--home",
            tmp,
            stdin=subprocess.DEVNULL,
        )
    assert res.returncode == 9, res.stderr
    output = res.stdout + res.stderr
    assert "ECHEC ROUTE" in output or "aucune source disponible" in output
    assert "Traceback" not in output


def test_non_regression_resolve():
    res = run("template", "resolve", "dev-agentic")
    assert res.returncode == 0, res.stderr
    stdout = res.stdout.lower()
    assert "briques" in stdout
    assert "déployées" in stdout or "deployees" in stdout or "déploiement" in stdout
