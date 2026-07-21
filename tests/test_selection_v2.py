"""N1b — sélection v2 : {modèle, nœud, moteur} + embeddings par famille + placement du RAG.

Zéro mock de commande : wizard en subprocess réel, serveur web réel."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from importlib import resources
from pathlib import Path

import pytest

from forgeai.web.server import _DEPLOY_STATE, build_server


def _un_embedding_reel() -> str:
    reg = json.loads((resources.files("forgeai.data") / "modeles-locaux.json")
                     .read_text(encoding="utf-8"))
    return next(m["hf_id"] for m in reg["modeles"] if m["famille"] == "embeddings-rerank")


def _run_wizard(sel: dict, tmp_path: Path, *extra: str) -> subprocess.CompletedProcess:
    f = tmp_path / "sel.json"
    f.write_text(json.dumps(sel), encoding="utf-8")
    env = os.environ.copy()
    env.setdefault("PYTHONPATH", str(Path(__file__).parent.parent / "src"))
    return subprocess.run(
        [sys.executable, "-m", "forgeai", "wizard", "--ci", "--dry-run",
         "--workdir", str(tmp_path / "run"), "--stack", "agentique",
         "--selection", str(f), *extra],
        capture_output=True, text=True, timeout=120, env=env,
    )


def test_v2_normalise_et_trace(tmp_path: Path) -> None:
    emb = _un_embedding_reel()
    sel = {"models": [{"hf_id": "Qwen/Qwen3.6-27B", "node": "worker-x", "engine": "vllm"},
                      "zai-org/GLM-5.2"],
           "embeddings": [{"hf_id": emb, "node": "auto", "engine": "llama-cpp"}],
           "rag_node": "local"}
    res = _run_wizard(sel, tmp_path, "--backend", "k3s")
    assert res.returncode == 0, res.stdout + res.stderr
    assert "RAG -> local" in res.stdout
    man = json.loads((tmp_path / "run" / "selection.json").read_text(encoding="utf-8"))
    glm = next(m for m in man["models"] if m["hf_id"] == "zai-org/GLM-5.2")
    assert glm["node"] == "auto" and glm["engine"] == "vllm"  # string nue normalisée
    qwen = next(m for m in man["models"] if m["hf_id"] == "Qwen/Qwen3.6-27B")
    assert qwen["node"] == "worker-x" and qwen["engine"] == "vllm"
    assert man["embeddings"][0]["hf_id"] == emb
    assert man["rag_node"] == "local"


def test_v2_moteur_inconnu(tmp_path: Path) -> None:
    sel = {"models": [{"hf_id": "Qwen/Qwen3.6-27B", "node": "auto", "engine": "moteur-fantome"}]}
    res = _run_wizard(sel, tmp_path)
    assert res.returncode == 8
    assert "moteur-fantome" in res.stderr


def test_v2_moteur_incompatible_vendor(tmp_path: Path) -> None:
    # S4 : moteur nvidia-only (tensorrt-llm) assigné à un nœud AMD => ABORT [SEL] (choix filtré).
    sel = {"models": [{"hf_id": "Qwen/Qwen3.6-27B", "node": "worker-amd",
                       "engine": "tensorrt-llm", "vendor": "amd"}]}
    res = _run_wizard(sel, tmp_path)
    assert res.returncode == 8, res.stdout + res.stderr
    assert "incompatible avec le vendor" in res.stderr


def test_v2_embedding_mauvaise_famille(tmp_path: Path) -> None:
    sel = {"embeddings": [{"hf_id": "Qwen/Qwen3.6-27B", "node": "auto", "engine": "llama-cpp"}]}
    res = _run_wizard(sel, tmp_path)
    assert res.returncode == 8
    assert "embeddings-rerank" in res.stderr


def test_v2_rag_node_compose_refuse(tmp_path: Path) -> None:
    sel = {"rag_node": "worker-x"}
    res = _run_wizard(sel, tmp_path, "--backend", "compose")
    assert res.returncode == 9
    assert "mono-machine" in res.stderr


def test_v2_rag_node_auto_compose_accepte(tmp_path: Path) -> None:
    """Objection revue N1b : auto == la seule machine en compose — jamais rejeté."""
    sel = {"rag_node": "auto", "models": None}  # null JSON toléré aussi
    res = _run_wizard(sel, tmp_path, "--backend", "compose")
    assert res.returncode == 0, res.stdout + res.stderr


def test_v2_rag_node_k3s_place(tmp_path: Path) -> None:
    sel = {"rag_node": "worker-x"}
    res = _run_wizard(sel, tmp_path, "--backend", "k3s")
    assert res.returncode == 0, res.stdout + res.stderr
    yaml = (tmp_path / "run" / "k3s.yaml").read_text(encoding="utf-8")
    assert "kubernetes.io/hostname: worker-x" in yaml
    assert "rag=worker-x" in res.stdout


def test_retrocompat_v1(tmp_path: Path) -> None:
    sel = {"bricks": ["qdrant"], "models": ["Qwen/Qwen3.6-27B"]}
    res = _run_wizard(sel, tmp_path)
    assert res.returncode == 0, res.stdout + res.stderr
    man = json.loads((tmp_path / "run" / "selection.json").read_text(encoding="utf-8"))
    assert man["models"][0] == {"hf_id": "Qwen/Qwen3.6-27B", "node": "auto", "engine": "vllm"}


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


def _attendre_fin(timeout_s: float = 120.0):
    limite = time.monotonic() + timeout_s
    while time.monotonic() < limite:
        with _DEPLOY_STATE["lock"]:
            if _DEPLOY_STATE["done"]:
                return _DEPLOY_STATE["exit_code"]
        time.sleep(0.5)
    return None


def test_web_v2_e2e(live) -> None:
    base, home = live
    emb = _un_embedding_reel()
    code, body = _post(base, {
        "stack": "agentique", "backend": "k3s", "confirm": "FORCER", "dry_run": True,
        "models": [{"hf_id": "Qwen/Qwen3.6-27B", "node": "worker-x", "engine": "vllm"}],
        "embeddings": [{"hf_id": emb, "node": "auto", "engine": "llama-cpp"}],
        "rag_node": "auto"})
    assert code == 202 and body["started"] is True
    assert _attendre_fin() == 0
    man = json.loads((home / "deploy" / "selection.json").read_text(encoding="utf-8"))
    assert man["models"][0]["node"] == "worker-x"
    assert man["embeddings"][0]["hf_id"] == emb
    assert man["rag_node"] == "auto"


def test_web_v2_forme_invalide(live) -> None:
    base, _ = live
    code, body = _post(base, {"stack": "agentique", "backend": "k3s", "confirm": "FORCER",
                              "dry_run": True, "models": [{"hf_id": "a;b"}]})
    assert code == 400 and "a;b" not in json.dumps(body)
    code2, _ = _post(base, {"stack": "agentique", "backend": "k3s", "confirm": "FORCER",
                            "dry_run": True, "rag_node": "x;y"})
    assert code2 == 400
