"""Tests réels du déploiement : aucun mock de _DEPLOY_CMD."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from forgeai.planner.assemble import assemble_plan
from forgeai.resources import deploy_overlay_path
from forgeai.stacks import load_stack
from forgeai.web.server import build_server


def _pythonpath_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC)
    return env


def _run_wizard(args: list[str], tmp: Path) -> subprocess.CompletedProcess:
    cmd = [
        sys.executable,
        "-m",
        "forgeai",
        "wizard",
        "--ci",
        "--workdir",
        str(tmp),
    ] + args
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=_pythonpath_env(),
        timeout=120,
    )


def test_wizard_dry_run_reel(tmp_path: Path) -> None:
    workdir = tmp_path / "wd"
    result = _run_wizard(
        ["--backend", "compose", "--stack", "agentique", "--dry-run"],
        workdir,
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "DRY-RUN OK" in result.stdout
    compose = workdir / "docker-compose.yaml"
    assert compose.exists()
    text = compose.read_text(encoding="utf-8")
    assert "litellm" in text
    assert "redis" in text


def test_wizard_dry_run_sans_stack(tmp_path: Path) -> None:
    workdir = tmp_path / "wd"
    result = _run_wizard(["--backend", "compose", "--dry-run"], workdir)
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "DRY-RUN OK" in result.stdout
    compose = workdir / "docker-compose.yaml"
    assert compose.exists()
    text = compose.read_text(encoding="utf-8")
    assert "litellm" not in text
    assert "redis" not in text


def test_assemble_plan_stack() -> None:
    overlay = deploy_overlay_path()
    stack = load_stack("agentique")
    plan = assemble_plan("minimal-cpu", overlay, stack=stack)
    names = {s.name for s in plan.services}
    assert "litellm" in names
    assert "redis" in names
    ports = [s.host_port for s in plan.services]
    assert len(ports) == len(set(ports))
    # Les services de l'overlay minimal sont conservés
    assert "ollama" in names


def test_defauts_embarques(tmp_path: Path) -> None:
    workdir = tmp_path / "wd"
    result = _run_wizard(["--backend", "compose", "--dry-run"], workdir)
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "DRY-RUN OK" in result.stdout


def test_web_deploy_dry_run_e2e(tmp_path: Path) -> None:
    os.environ["PYTHONPATH"] = str(SRC)
    server = build_server("127.0.0.1", 0)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    base = f"http://127.0.0.1:{port}"
    body = json.dumps(
        {
            "stack": "agentique",
            "backend": "compose",
            "confirm": "FORCER",
            "dry_run": True,
        },
        ensure_ascii=False,
    ).encode("utf-8")

    try:
        req = urllib.request.Request(
            f"{base}/api/deploy",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            assert resp.status == 202
            start_resp = json.loads(resp.read().decode("utf-8"))
            assert start_resp.get("started") is True

        # Attente que le sous-process wizard ait démarré avant de lire les events
        time.sleep(0.5)

        events_url = f"{base}/api/deploy/events"
        with urllib.request.urlopen(events_url, timeout=30) as resp:
            payload = resp.read().decode("utf-8")

        # Format SSE réel : `event: end` PRÉCÈDE sa ligne `data: {"exit_code": N}`
        dry_ok = False
        exit_code = None
        current_event = "message"
        for line in payload.splitlines():
            if line.startswith("event: "):
                current_event = line[7:]
            elif line.startswith("data: "):
                data = line[6:]
                if "DRY-RUN OK" in data:
                    dry_ok = True
                if current_event == "end":
                    try:
                        exit_code = json.loads(data).get("exit_code")
                    except json.JSONDecodeError:
                        pass
            elif not line:
                current_event = "message"

        assert dry_ok, "Le flux SSE ne contient pas 'DRY-RUN OK'"
        assert exit_code == 0, f"exit_code inattendu : {exit_code}"
    finally:
        server.shutdown()
        server.server_close()
