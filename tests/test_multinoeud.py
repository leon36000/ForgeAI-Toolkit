"""Tests P0.2 — ciblage nœud K3s et sondage distant.

Zéro mock de commande : wizard lancé en subprocess réel, serveur web démarré
en thread réelle. Python 3.11+ stdlib uniquement (hors pytest).
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from forgeai.core.models import DeploymentPlan, RenderTarget, ServiceSpec
from forgeai.renderers.k3s import render_k3s
from forgeai.web.server import build_server


def _minimal_plan() -> DeploymentPlan:
    return DeploymentPlan(
        plan_id="test-p0.2",
        profile="Minimal",
        target=RenderTarget.K3S,
        model="llama3",
        embed_model="nomic-embed-text",
        services=[
            ServiceSpec(
                name="ollama",
                image="ollama/ollama",
                container_port=11434,
                host_port=11434,
                gpu=False,
                volumes=[],
                healthcheck_url="http://localhost:11434/",
            ),
            ServiceSpec(
                name="vector-store",
                image="qdrant/qdrant",
                container_port=6333,
                host_port=6333,
                gpu=False,
                volumes=[],
                healthcheck_url="http://localhost:6333/health",
            ),
        ],
    )


def test_render_k3s_libre() -> None:
    yaml = render_k3s(_minimal_plan(), node=None)
    assert "nodeSelector" not in yaml


def test_render_k3s_cible() -> None:
    yaml = render_k3s(_minimal_plan(), node="worker-2")
    assert "kubernetes.io/hostname: worker-2" in yaml


def _run_wizard(*extra: str, workdir: Path) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["FORGEAI_HOME"] = str(workdir)
    return subprocess.run(
        [sys.executable, "-m", "forgeai", "wizard", "--ci", "--dry-run",
         "--backend", "k3s", "--workdir", str(workdir / "run"), *extra],
        capture_output=True,
        text=True,
        env=env,
    )


def test_wizard_node_auto_dry_run(tmp_path: Path) -> None:
    res = _run_wizard("--node", "auto", workdir=tmp_path)
    assert res.returncode == 0, res.stderr
    assert "scheduler libre" in res.stdout
    k3s_yaml = tmp_path / "run" / "k3s.yaml"
    assert k3s_yaml.exists()
    assert "nodeSelector" not in k3s_yaml.read_text(encoding="utf-8")


def test_wizard_node_cible_dry_run(tmp_path: Path) -> None:
    # Cible construite pour être GARANTIE différente du hostname local : le test
    # prouve le ciblage distant sur n'importe quelle machine, sans skip.
    cible = socket.gethostname().lower() + "-autre-noeud"
    res = _run_wizard("--node", cible, workdir=tmp_path)
    assert res.returncode == 0, res.stderr
    k3s_yaml = tmp_path / "run" / "k3s.yaml"
    assert k3s_yaml.exists()
    text = k3s_yaml.read_text(encoding="utf-8")
    assert f"kubernetes.io/hostname: {cible}" in text


def test_wizard_node_invalide(tmp_path: Path) -> None:
    res = _run_wizard("--node", "worker;rm", workdir=tmp_path)
    assert res.returncode != 0
    k3s_yaml = tmp_path / "run" / "k3s.yaml"
    if k3s_yaml.exists():
        assert "worker;rm" not in k3s_yaml.read_text(encoding="utf-8")


@pytest.fixture
def live_server(tmp_path: Path):
    """Serveur web réel sur port éphémère, isolé dans tmp_path via FORGEAI_HOME."""
    old_home = os.environ.get("FORGEAI_HOME")
    os.environ["FORGEAI_HOME"] = str(tmp_path)
    server = build_server("127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()
    if old_home is None:
        os.environ.pop("FORGEAI_HOME", None)
    else:
        os.environ["FORGEAI_HOME"] = old_home


def _post_json(server, path: str, payload: dict) -> tuple[int, dict]:
    host, port = server.server_address
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"http://{host}:{port}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    # 4xx = partie du contrat teste : retourner, pas lever
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.getcode(), json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def _get_json(server, path: str) -> tuple[int, dict]:
    host, port = server.server_address
    with urllib.request.urlopen(f"http://{host}:{port}{path}", timeout=10) as resp:
        return resp.getcode(), json.loads(resp.read().decode("utf-8"))


def _wait_deploy_end(server, timeout: float = 30.0) -> int | None:
    """Lit le flux SSE /api/deploy/events jusqu'à l'événement end et retourne exit_code."""
    host, port = server.server_address
    deadline = time.monotonic() + timeout
    with urllib.request.urlopen(
        f"http://{host}:{port}/api/deploy/events", timeout=timeout
    ) as resp:
        event_lines: list[str] = []
        while time.monotonic() < deadline:
            line = resp.readline()
            if not line:
                time.sleep(0.05)
                continue
            decoded = line.decode("utf-8").rstrip("\n")
            if decoded == "":
                event = "\n".join(event_lines)
                if event.startswith("event: end"):
                    data_part = event.split("data: ", 1)[1]
                    return json.loads(data_part).get("exit_code")
                event_lines = []
            else:
                event_lines.append(decoded)
    return None


def test_web_deploy_node_transmis(live_server) -> None:
    code, body = _post_json(
        live_server,
        "/api/deploy",
        {
            "stack": "agentique",
            "backend": "k3s",
            "confirm": "FORCER",
            "dry_run": True,
            "node": "worker-2",
        },
    )
    assert code == 202, body
    exit_code = _wait_deploy_end(live_server, timeout=30.0)
    assert exit_code == 0, f"wizard dry-run a échoué avec exit_code={exit_code}"
    k3s_yaml = Path(live_server.server_address[0])  # placeholder
    # Le workdir du wizard est FORGEAI_HOME/deploy.
    home = Path(os.environ["FORGEAI_HOME"])
    k3s_yaml = home / "deploy" / "k3s.yaml"
    assert k3s_yaml.exists()
    text = k3s_yaml.read_text(encoding="utf-8")
    assert "kubernetes.io/hostname: worker-2" in text


def test_web_deploy_node_invalide(live_server) -> None:
    code, body = _post_json(
        live_server,
        "/api/deploy",
        {
            "stack": "agentique",
            "backend": "k3s",
            "confirm": "FORCER",
            "dry_run": True,
            "node": "bad;inj",
        },
    )
    assert code == 400
    assert body.get("error") == "node invalide"


def test_summary_nodes(live_server) -> None:
    # Choisit un stack réellement présent pour éviter un 404.
    code, stacks = _get_json(live_server, "/api/stacks")
    assert code == 200 and stacks, "les 6 stacks embarqués doivent toujours être servis"
    stack_id = stacks[0]["id"]
    code, payload = _get_json(live_server, f"/api/summary?stack={stack_id}")
    assert code == 200
    assert "nodes" in payload
    assert isinstance(payload["nodes"], list)
