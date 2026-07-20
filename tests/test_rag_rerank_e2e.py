"""Story E2b — B7 : preuve e2e RÉELLE du rerank (déploiement Docker, effet mesurable).

Opt-in : ne s'exécute QUE si `FORGEAI_E2E=1` (skip par défaut, y compris CI — déploie 5 services
dont 2 modèles TEI ~2 Go). Reproductible :

    FORGEAI_E2E=1 python3 -m pytest tests/test_rag_rerank_e2e.py -s

Preuve d'exécution RÉELLE journalisée au registre Registres/mission.jsonl (événement tdad_green E2b).
Déploie le socle durci + 2e instance TEI (bge-reranker-v2-m3), puis prouve :
  - DISCRIMINATION mesurable : sur des candidats à pertinence tranchée, le reranker écrase le bruit
    (écart pertinent/hors-sujet ~0.9999) là où le cosine de l'embedding tasse les scores (~0.5) ;
  - ANCRAGE préservé : le RAG durci + rerank répond toujours de façon ancrée (fait OOD Vornak-9).
"""
from __future__ import annotations

import math
import os
import subprocess
import time
import urllib.error
import urllib.request
from importlib.resources import files
from pathlib import Path

import pytest

from forgeai.planner.assemble import assemble_plan
from forgeai.rag import hardened as H
from forgeai.rag.hardened import HardenedRagClient
from forgeai.renderers.compose import render_compose
from forgeai.renderers.litellm_config import render_litellm_config

pytestmark = pytest.mark.skipif(
    os.environ.get("FORGEAI_E2E") != "1",
    reason=(
        "preuve e2e Docker lourde (5 services, 2 modèles TEI ~2 Go) — skip par défaut ; preuve "
        "d'exécution RÉELLE journalisée au registre Registres/mission.jsonl (tdad_green E2b) ; "
        "rejouable avec FORGEAI_E2E=1"
    ),
)

KEY = "forgeai-e2b-e2e-runkey"  # gitleaks:allow — clé de run éphémère de test, jamais un secret


def _ok(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=3) as r:
            return 200 <= r.status < 300
    except (urllib.error.URLError, OSError, ValueError):
        return False


def _cos(a, b):
    d = sum(x * y for x, y in zip(a, b))
    return d / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)) + 1e-9)


def test_rerank_discrimination_et_ancrage_e2e(tmp_path: Path):
    overlay = Path(str(files("forgeai.data") / "deploy-hardened.json"))
    doc = (files("forgeai.data") / "smoke" / "verification-durci.md").read_text(encoding="utf-8")
    plan = assemble_plan(profile="hardened", deploy_overlay=overlay, extra_bricks=(
        "text-embeddings-inference-tei", "text-embeddings-inference-reranker", "litellm"))
    (tmp_path / "docker-compose.yaml").write_text(render_compose(plan), encoding="utf-8")
    (tmp_path / "litellm-config.yaml").write_text(render_litellm_config(plan), encoding="utf-8")
    (tmp_path / ".env").write_text(f"FORGEAI_LITELLM_KEY={KEY}\nFORGEAI_BAO_TOKEN=x\n", encoding="utf-8")
    ports = {s.name: s.host_port for s in plan.services}

    def compose(*a):
        return subprocess.run(["docker", "compose", *a], cwd=tmp_path,
                              capture_output=True, text=True, timeout=1800)

    def u(n):
        return f"http://127.0.0.1:{ports[n]}"

    try:
        assert compose("up", "-d").returncode == 0
        checks = {
            "ollama": u("ollama") + "/api/tags",
            "vector-store": u("vector-store") + "/readyz",
            "tei": u("text-embeddings-inference-tei") + "/health",
            "reranker": u("text-embeddings-inference-reranker") + "/health",
            "litellm": u("litellm") + "/health/liveliness",
        }
        deadline = time.monotonic() + 900
        while time.monotonic() < deadline and not all(_ok(v) for v in checks.values()):
            time.sleep(4)
        assert all(_ok(v) for v in checks.values()), "socle durci + reranker non sain"
        compose("exec", "-T", "ollama", "ollama", "pull", "qwen2.5:0.5b")

        client = HardenedRagClient(
            ollama_url=u("ollama"), qdrant_url=u("vector-store"),
            tei_url=u("text-embeddings-inference-tei"), gateway_url=u("litellm"), gateway_key=KEY,
            reranker_url=u("text-embeddings-inference-reranker"),
            llm_model="qwen2.5:0.5b", embed_model="bge-m3", collection="forgeai-rerank-e2e")

        # --- EFFET MESURABLE : discrimination fine du reranker vs cosine de l'embedding ---
        q = "Quelle est la capitale de la France ?"
        cands = [
            {"payload": {"text": "La choucroute garnie est une specialite alsacienne.", "source": "hs.md"}},
            {"payload": {"text": "Berlin est la capitale de l'Allemagne.", "source": "de.md"}},
            {"payload": {"text": "Paris est la capitale de la France.", "source": "fr.md"}},
        ]
        qv = client._embed([q])[0]
        ev = client._embed([c["payload"]["text"] for c in cands])
        emb = {c["payload"]["source"]: _cos(qv, e) for c, e in zip(cands, ev)}
        ranked = H._post(u("text-embeddings-inference-reranker") + "/rerank",
                         {"query": q, "texts": [c["payload"]["text"] for c in cands]})
        rr = {cands[it["index"]]["payload"]["source"]: it["score"] for it in ranked}
        # le reranker classe le pertinent 1er ET écrase le bruit bien plus nettement que l'embedding
        assert client._rerank(q, cands)[0]["payload"]["source"] == "fr.md"
        ecart_emb = emb["fr.md"] - emb["hs.md"]
        ecart_rr = rr["fr.md"] - rr["hs.md"]
        assert ecart_rr > ecart_emb, f"le rerank doit discriminer plus finement (rr={ecart_rr} vs emb={ecart_emb})"
        assert ecart_rr > 0.5, f"écart pertinent/bruit net attendu, obtenu {ecart_rr}"

        # --- ANCRAGE préservé : le RAG durci + rerank répond de façon ancrée (OOD) ---
        client.ensure_collection(dim=1024)
        neg = client.ask("Quel est le nom du protocole ?")
        assert neg["context_used"] is False and neg["answer"] == "", "négatif préservé sous rerank"
        client.ingest(doc, source="verification-durci.md")
        pos = client.ask("Comment s'appelle le protocole de synchronisation interne de ForgeAI Toolkit ?")
        assert "Vornak-9" in pos["answer"], f"ancrage OOD préservé, obtenu {pos}"
        assert pos["sources"] == ["verification-durci.md"]
    finally:
        compose("down", "-v")
