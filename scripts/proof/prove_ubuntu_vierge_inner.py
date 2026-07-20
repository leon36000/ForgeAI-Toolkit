"""Preuve exécutée DANS l'Ubuntu vierge : forgeai (installé depuis les sources) déploie le
socle durci from-scratch via le dockerd imbriqué, puis prouve un RAG ancré (fait OOD)."""
import json
import subprocess
import time
import urllib.error
import urllib.request
from importlib.resources import files
from pathlib import Path

from forgeai.planner.assemble import assemble_plan
from forgeai.rag.hardened import HardenedRagClient
from forgeai.renderers.compose import render_compose
from forgeai.renderers.litellm_config import render_litellm_config

KEY = "forgeai-vierge-runkey"
WORK = Path("/root/deploy")
WORK.mkdir(exist_ok=True)

overlay = Path(str(files("forgeai.data") / "deploy-hardened.json"))
doc = (files("forgeai.data") / "smoke" / "verification-durci.md").read_text(encoding="utf-8")
plan = assemble_plan(profile="hardened", deploy_overlay=overlay,
                     extra_bricks=("text-embeddings-inference-tei", "litellm"))
(WORK / "docker-compose.yaml").write_text(render_compose(plan), encoding="utf-8")
(WORK / "litellm-config.yaml").write_text(render_litellm_config(plan), encoding="utf-8")
(WORK / ".env").write_text(f"FORGEAI_LITELLM_KEY={KEY}\nFORGEAI_BAO_TOKEN=x\n", encoding="utf-8")
ports = {s.name: s.host_port for s in plan.services}
print("forgeai a généré le plan durci :", list(ports), flush=True)


def compose(*a):
    return subprocess.run(["docker", "compose", *a], cwd=WORK,
                          capture_output=True, text=True, timeout=1800)


def ok(u):
    try:
        with urllib.request.urlopen(u, timeout=3) as r:
            return 200 <= r.status < 300
    except (urllib.error.URLError, OSError, ValueError):
        return False


print("== docker compose up (déploiement DANS l'ubuntu vierge) ==", flush=True)
up = compose("up", "-d")
print(up.stdout[-400:], up.stderr[-400:], flush=True)
assert up.returncode == 0, "compose up a échoué"

print("== attente santé (bge-m3 cold-start) ==", flush=True)
checks = {
    "ollama": f"http://127.0.0.1:{ports['ollama']}/api/tags",
    "vector-store": f"http://127.0.0.1:{ports['vector-store']}/readyz",
    "tei": f"http://127.0.0.1:{ports['text-embeddings-inference-tei']}/health",
    "litellm": f"http://127.0.0.1:{ports['litellm']}/health/liveliness",
}
st = {k: "waiting" for k in checks}
deadline = time.monotonic() + 900
while time.monotonic() < deadline:
    for k, u in checks.items():
        if st[k] != "healthy" and ok(u):
            st[k] = "healthy"
    if all(v == "healthy" for v in st.values()):
        break
    time.sleep(4)
print("HEALTH:", json.dumps(st, ensure_ascii=False), flush=True)
assert all(v == "healthy" for v in st.values()), f"socle durci non sain : {st}"

print("== pull qwen2.5:0.5b ==", flush=True)
compose("exec", "-T", "ollama", "ollama", "pull", "qwen2.5:0.5b")

c = HardenedRagClient(
    ollama_url=f"http://127.0.0.1:{ports['ollama']}",
    qdrant_url=f"http://127.0.0.1:{ports['vector-store']}",
    tei_url=f"http://127.0.0.1:{ports['text-embeddings-inference-tei']}",
    gateway_url=f"http://127.0.0.1:{ports['litellm']}",
    gateway_key=KEY, llm_model="qwen2.5:0.5b", embed_model="bge-m3",
    collection="forgeai-rag-durci")
c.pull_models()
q = "Comment s'appelle le protocole de synchronisation interne de ForgeAI Toolkit ?"

c.ensure_collection(dim=1024)
neg = c.ask(q)
print("NEGATIF:", json.dumps(neg, ensure_ascii=False), flush=True)
assert neg["context_used"] is False and neg["answer"] == "", "négatif : ne doit rien fabriquer"

c.ingest(doc, source="verification-durci.md")
pos = c.ask(q)
print("POSITIF:", json.dumps(pos, ensure_ascii=False), flush=True)
assert "Vornak-9" in pos["answer"], "ancrage OOD attendu"
assert pos["sources"] == ["verification-durci.md"]
assert pos["context_used"] is True
print("UBUNTU_VIERGE_OK: infra IA durcie déployée FROM SCRATCH dans ubuntu:24.04 nu ; RAG ancré Vornak-9", flush=True)
