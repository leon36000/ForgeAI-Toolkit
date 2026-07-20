"""Story E5 — preuve e2e RÉELLE : langfuse branché comme observabilité (LiteLLM → traces).

Opt-in : ne s'exécute QUE si `FORGEAI_E2E=1` (skip par défaut — déploie postgres + langfuse + ollama
+ litellm réels). Reproductible :

    FORGEAI_E2E=1 python3 -m pytest tests/test_langfuse_e2e.py -s

Prouve, via le CODE RÉEL `forgeai.observability.langfuse` (le chemin exact du wizard --rag-durci) :
  1. LiteLLM configuré avec `success_callback: ["langfuse"]` ÉMET une trace pour chaque génération ;
  2. la trace ATTERRIT dans langfuse (postgres) et est relisible par l'API publique (Basic auth) ;
  3. avant toute génération, aucune trace (contrôle négatif).

Preuve d'exécution RÉELLE journalisée au registre Registres/mission.jsonl (événement tdad_green E5).
"""
from __future__ import annotations

import json
import os
import secrets as pysecrets
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest
from forgeai.observability.langfuse import count_traces, wait_for_trace

pytestmark = pytest.mark.skipif(
    os.environ.get("FORGEAI_E2E") != "1",
    reason=(
        "preuve e2e Docker (postgres + langfuse + ollama + litellm réels) — skip par défaut ; "
        "d'exécution RÉELLE journalisée au registre Registres/mission.jsonl (tdad_green E5) ; "
        "rejouable avec FORGEAI_E2E=1"
    ),
)


def _ok(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=2) as r:
            return 200 <= r.status < 300
    except (urllib.error.URLError, OSError, ValueError):
        return False


def test_langfuse_observabilite_e2e(tmp_path: Path):
    pk = "pk-lf-" + pysecrets.token_hex(8)
    sk = "sk-lf-" + pysecrets.token_hex(8)
    mk = "sk-" + pysecrets.token_hex(12)  # gitleaks:allow — clé de run éphémère
    cfg = tmp_path / "litellm-config.yaml"
    cfg.write_text(
        'model_list:\n  - model_name: "qwen2.5:0.5b"\n    litellm_params:\n'
        '      model: "ollama_chat/qwen2.5:0.5b"\n      api_base: "http://e5t-ollama:11434"\n'
        'litellm_settings:\n  success_callback: ["langfuse"]\n'
        'general_settings:\n  master_key: "os.environ/LITELLM_MASTER_KEY"\n',
        encoding="utf-8")
    names = ["e5t-pg", "e5t-lf", "e5t-ollama", "e5t-litellm"]

    def d(*a):
        return subprocess.run(["docker", *a], capture_output=True, text=True, timeout=300)

    d("rm", "-f", *names)
    d("network", "create", "e5t-net")
    try:
        d("run", "-d", "--name", "e5t-pg", "--network", "e5t-net",
          "-e", "POSTGRES_PASSWORD=pg",  # proof:allow — mdp postgres de run éphémère
          "-e", "POSTGRES_DB=langfuse", "postgres:15-alpine")
        time.sleep(6)
        d("run", "-d", "--name", "e5t-lf", "--network", "e5t-net", "-p", "13100:3000",
          "-e", "DATABASE_URL=postgresql://postgres:pg@e5t-pg:5432/langfuse",
          "-e", "NEXTAUTH_URL=http://localhost:13100",
          "-e", f"NEXTAUTH_SECRET={pysecrets.token_hex(16)}",  # proof:allow — token de run éphémère
          "-e", f"SALT={pysecrets.token_hex(16)}",
          "-e", f"ENCRYPTION_KEY={pysecrets.token_hex(32)}",
          "-e", "TELEMETRY_ENABLED=false",
          "-e", "LANGFUSE_INIT_ORG_ID=forgeai", "-e", "LANGFUSE_INIT_PROJECT_ID=forgeai-rag",
          "-e", f"LANGFUSE_INIT_PROJECT_PUBLIC_KEY={pk}",
          "-e", f"LANGFUSE_INIT_PROJECT_SECRET_KEY={sk}",
          "-e", "LANGFUSE_INIT_USER_EMAIL=a@a.co", "-e", "LANGFUSE_INIT_USER_NAME=a",
          "-e", "LANGFUSE_INIT_USER_PASSWORD=pwpwpwpw",  # proof:allow — mdp UI factice headless
          "langfuse/langfuse:2")
        d("run", "-d", "--name", "e5t-ollama", "--network", "e5t-net", "ollama/ollama:latest")
        d("run", "-d", "--name", "e5t-litellm", "--network", "e5t-net", "-p", "14200:4000",
          "-e", f"LITELLM_MASTER_KEY={mk}", "-e", f"LANGFUSE_PUBLIC_KEY={pk}",
          "-e", f"LANGFUSE_SECRET_KEY={sk}", "-e", "LANGFUSE_HOST=http://e5t-lf:3000",
          "-v", f"{cfg}:/app/litellm-config.yaml:ro",
          "ghcr.io/berriai/litellm:main-stable",
          "--config", "/app/litellm-config.yaml", "--port", "4000")

        deadline = time.monotonic() + 180
        while time.monotonic() < deadline and not (
                _ok("http://127.0.0.1:13100/api/public/health")
                and _ok("http://127.0.0.1:14200/health/liveliness")):
            time.sleep(3)
        assert _ok("http://127.0.0.1:13100/api/public/health"), "langfuse doit être en santé"
        assert _ok("http://127.0.0.1:14200/health/liveliness"), "litellm doit être en santé"

        base = "http://127.0.0.1:13100"
        # 3) contrôle négatif : aucune trace avant génération
        assert count_traces(base, pk, sk) == 0

        # pull modèle + génération via LiteLLM (émet une trace langfuse)
        d("exec", "e5t-ollama", "ollama", "pull", "qwen2.5:0.5b")
        req = urllib.request.Request(
            "http://127.0.0.1:14200/v1/chat/completions",
            data=json.dumps({"model": "qwen2.5:0.5b",
                             "messages": [{"role": "user", "content": "Dis bonjour."}]}).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {mk}"},
            method="POST")
        with urllib.request.urlopen(req, timeout=120) as r:
            assert json.loads(r.read())["choices"][0]["message"]["content"]

        # 1+2) la trace atterrit et est relisible via le client forgeai
        trace = wait_for_trace(base, pk, sk, timeout=90, interval=3)
        assert trace is not None, "la génération LiteLLM doit produire une trace langfuse"
        assert trace.get("name")  # ex. litellm-acompletion
        assert count_traces(base, pk, sk) >= 1
    finally:
        d("rm", "-f", *names)
        d("network", "rm", "e5t-net")
