"""Story E2a — B7 : preuve e2e RÉELLE du RAG durci (déploiement Docker).

Opt-in : ne s'exécute QUE si `FORGEAI_E2E=1` (skip par défaut, y compris en CI, pour ne pas
télécharger ~2,5 Go d'images/poids ni allonger la suite). Reproductible manuellement :

    FORGEAI_E2E=1 python3 -m pytest tests/test_rag_durci_e2e.py -s

Déploie le socle durci (ollama + qdrant v1.18.3 + TEI/bge-m3 + LiteLLM), puis prouve :
  - CONTRÔLE NÉGATIF : collection vide -> aucune fabrication (context_used=false, réponse vide).
  - ANCRAGE OOD : le fait fictif « Vornak-9 » (hors connaissance paramétrique) ingéré -> la réponse
    le contient ET cite le document -> l'ancrage vient du retrieval, pas des poids.
"""
from __future__ import annotations

import os
import subprocess
import time
import urllib.error
import urllib.request
from importlib.resources import files
from pathlib import Path

import pytest

from forgeai.planner.assemble import assemble_plan
from forgeai.rag.hardened import HardenedRagClient
from forgeai.renderers.compose import render_compose
from forgeai.renderers.litellm_config import render_litellm_config

pytestmark = pytest.mark.skipif(
    os.environ.get("FORGEAI_E2E") != "1",
    reason=(
        "preuve e2e Docker lourde (images/poids ~2,5 Go) — skip par défaut ; "
        "preuve d'exécution RÉELLE journalisée au registre Registres/mission.jsonl "
        "(événement tdad_green E2a) ; rejouable avec FORGEAI_E2E=1"
    ),
)

MASTER_KEY = "forgeai-e2a-e2e-runkey"  # clé de run éphémère (jamais un secret réel)


def _http_ok(url: str, timeout_s: float = 3.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout_s) as resp:
            return 200 <= resp.status < 300
    except (urllib.error.URLError, OSError, ValueError):
        return False


def _wait(checks: dict[str, str], timeout_s: float = 600.0) -> dict[str, str]:
    status = {k: "waiting" for k in checks}
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        for name, url in checks.items():
            if status[name] != "healthy" and _http_ok(url):
                status[name] = "healthy"
        if all(v == "healthy" for v in status.values()):
            return status
        time.sleep(3.0)
    raise AssertionError(f"socle durci non sain après {timeout_s}s : {status}")


def test_rag_durci_ancrage_ood_e2e(tmp_path: Path):
    overlay = Path(str(files("forgeai.data") / "deploy-hardened.json"))
    doc = (files("forgeai.data") / "smoke" / "verification-durci.md").read_text(encoding="utf-8")
    plan = assemble_plan(profile="hardened", deploy_overlay=overlay,
                         extra_bricks=("text-embeddings-inference-tei", "litellm"))
    (tmp_path / "docker-compose.yaml").write_text(render_compose(plan), encoding="utf-8")
    (tmp_path / "litellm-config.yaml").write_text(render_litellm_config(plan), encoding="utf-8")
    (tmp_path / ".env").write_text(
        f"FORGEAI_LITELLM_KEY={MASTER_KEY}\nFORGEAI_BAO_TOKEN=x\n", encoding="utf-8")
    ports = {s.name: s.host_port for s in plan.services}

    def compose(*args):
        return subprocess.run(["docker", "compose", *args], cwd=tmp_path,
                              capture_output=True, text=True, timeout=900)

    try:
        up = compose("up", "-d")
        assert up.returncode == 0, f"compose up : {up.stderr[-500:]}"
        _wait({
            "ollama": f"http://127.0.0.1:{ports['ollama']}/api/tags",
            "vector-store": f"http://127.0.0.1:{ports['vector-store']}/readyz",
            "tei": f"http://127.0.0.1:{ports['text-embeddings-inference-tei']}/health",
            "litellm": f"http://127.0.0.1:{ports['litellm']}/health/liveliness",
        })
        compose("exec", "-T", "ollama", "ollama", "pull", "qwen2.5:0.5b")

        client = HardenedRagClient(
            ollama_url=f"http://127.0.0.1:{ports['ollama']}",
            qdrant_url=f"http://127.0.0.1:{ports['vector-store']}",
            tei_url=f"http://127.0.0.1:{ports['text-embeddings-inference-tei']}",
            gateway_url=f"http://127.0.0.1:{ports['litellm']}",
            gateway_key=MASTER_KEY, llm_model="qwen2.5:0.5b", embed_model="bge-m3",
            collection="forgeai-rag-durci")
        client.pull_models()

        question = "Comment s'appelle le protocole de synchronisation interne de ForgeAI Toolkit ?"
        # CONTRÔLE NÉGATIF : collection vide -> aucune fabrication
        client.ensure_collection(dim=1024)
        neg = client.ask(question)
        assert neg["context_used"] is False and neg["answer"] == "", \
            "sans corpus, le RAG durci ne doit RIEN fabriquer"

        # ANCRAGE OOD : le fait fictif ne peut venir que du retrieval
        assert client.ingest(doc, source="verification-durci.md") >= 1
        pos = client.ask(question)
        assert "Vornak-9" in pos["answer"], f"ancrage OOD attendu, obtenu : {pos}"
        assert pos["sources"] == ["verification-durci.md"]
        assert pos["context_used"] is True
    finally:
        compose("down", "-v")
