"""P0.3b — la sélection utilisateur (briques cochées + modèles choisis) atteint le déploiement.

Zéro mock de commande : wizard en subprocess réel, serveur web réel (règle post-audit)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from forgeai.web.server import _DEPLOY_STATE, build_server


def _run_wizard(*extra: str, workdir: Path) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env.setdefault("PYTHONPATH", str(Path(__file__).parent.parent / "src"))
    return subprocess.run(
        [sys.executable, "-m", "forgeai", "wizard", "--ci", "--dry-run",
         "--workdir", str(workdir / "run"), "--stack", "agentique", *extra],
        capture_output=True, text=True, timeout=120, env=env,
    )


def _selection_file(tmp_path: Path, bricks: list[str], models: list[str]) -> Path:
    f = tmp_path / "sel.json"
    f.write_text(json.dumps({"bricks": bricks, "models": models}), encoding="utf-8")
    return f


def test_wizard_selection_dry_run(tmp_path: Path) -> None:
    sel = _selection_file(tmp_path, ["qdrant", "litellm"], ["Qwen/Qwen3.6-27B"])
    res = _run_wizard("--selection", str(sel), workdir=tmp_path)
    assert res.returncode == 0, res.stdout + res.stderr
    assert "selection=2+1" in res.stdout
    manifest = json.loads((tmp_path / "run" / "selection.json").read_text(encoding="utf-8"))
    assert manifest["bricks"] == ["qdrant", "litellm"]
    assert manifest["models"] == [
        {"hf_id": "Qwen/Qwen3.6-27B", "node": "auto", "engine": "vllm"}]  # v2 normalisé
    assert "litellm" in manifest["deployables"]


def test_wizard_selection_brique_inconnue(tmp_path: Path) -> None:
    sel = _selection_file(tmp_path, ["brique-inexistante-xyz"], [])
    res = _run_wizard("--selection", str(sel), workdir=tmp_path)
    assert res.returncode == 8
    assert "brique-inexistante-xyz" in res.stderr
    assert not (tmp_path / "run" / "selection.json").exists()


def test_wizard_selection_modele_inconnu(tmp_path: Path) -> None:
    sel = _selection_file(tmp_path, [], ["fake/NExiste-Pas"])
    res = _run_wizard("--selection", str(sel), workdir=tmp_path)
    assert res.returncode == 8
    assert "fake/NExiste-Pas" in res.stderr


@pytest.fixture()
def live(tmp_path, monkeypatch):
    monkeypatch.setenv("FORGEAI_HOME", str(tmp_path))
    with _DEPLOY_STATE["lock"]:
        _DEPLOY_STATE["proc"] = None
        _DEPLOY_STATE["lines"].clear()
        _DEPLOY_STATE["done"] = False
        _DEPLOY_STATE["exit_code"] = None
    srv = build_server("127.0.0.1", 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}", tmp_path
    with _DEPLOY_STATE["lock"]:
        proc = _DEPLOY_STATE["proc"]
    if proc is not None and proc.poll() is None:
        proc.terminate()
        proc.wait()
    srv.shutdown()
    srv.server_close()


def _post(base: str, payload: dict) -> tuple[int, dict]:
    req = urllib.request.Request(
        f"{base}/api/deploy", data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def _attendre_fin(timeout_s: float = 120.0) -> int | None:
    limite = time.monotonic() + timeout_s
    while time.monotonic() < limite:
        with _DEPLOY_STATE["lock"]:
            if _DEPLOY_STATE["done"]:
                return _DEPLOY_STATE["exit_code"]
        time.sleep(0.5)
    return None


def test_web_deploy_selection_e2e(live) -> None:
    base, home = live
    code, body = _post(base, {"stack": "agentique", "backend": "compose",
                              "confirm": "FORCER", "dry_run": True,
                              "bricks": ["qdrant"], "models": ["Qwen/Qwen3.6-27B"]})
    assert code == 202 and body["started"] is True
    assert _attendre_fin() == 0
    manifest = json.loads((home / "deploy" / "selection.json").read_text(encoding="utf-8"))
    assert manifest["bricks"] == ["qdrant"]
    assert manifest["models"] == [
        {"hf_id": "Qwen/Qwen3.6-27B", "node": "auto", "engine": "vllm"}]  # v2 normalisé


def test_web_deploy_selection_invalide(live) -> None:
    base, _ = live
    code, body = _post(base, {"stack": "agentique", "backend": "compose",
                              "confirm": "FORCER", "dry_run": True,
                              "bricks": ["a;b"]})
    assert code == 400
    assert "a;b" not in json.dumps(body)


def test_sans_selection_inchange(live) -> None:
    base, _ = live
    code, _ = _post(base, {"stack": "agentique", "backend": "compose",
                           "confirm": "FORCER", "dry_run": True})
    assert code == 202
    assert _attendre_fin() == 0
