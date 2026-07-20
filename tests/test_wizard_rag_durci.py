"""Story E2c — le wizard déploie le RAG DURCI via le flag `--rag-durci`.

Spec exécutable (TDAD, AVANT le code). Frontières externes simulées (docker/ollama/qdrant/gateway
mockés) — le comportement réel est prouvé par l'e2e journalisé au registre. Vérifie que `--rag-durci`
bascule le wizard sur le chemin durci (overlay hardened + TEI + reranker + LiteLLM + HardenedRagClient
+ clé passerelle) sans casser le chemin par défaut (RagClient tout-Ollama).
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import forgeai.cli as cli
from forgeai.bootstrap.secrets import ENV_KEYS, bootstrap_secrets


class FakeDetector:
    def __init__(self, runner):
        self.runner = runner

    def full_report(self):
        from forgeai.core.models import Disk, HardwareProfile
        return HardwareProfile(cpu_model="ci", cpu_cores=4, cpu_arch="x86_64", ram_gb=32.0,
                               os_name="Linux CI",
                               disks=(Disk(path="/", total_gb=1000.0, free_gb=500.0),))


class FakeHardenedRag:
    last = None

    def __init__(self, **kwargs):
        FakeHardenedRag.last = kwargs

    def pull_models(self):
        return None

    def ingest(self, text, source):
        assert text.strip()
        return 2

    def ask(self, question):
        return {"answer": "Le protocole se nomme Vornak-9.",
                "sources": ["verification-durci.md"], "context_used": True}


class FakeRag(FakeHardenedRag):
    used = False

    def __init__(self, **kwargs):
        FakeRag.used = True
        super().__init__(**kwargs)


@pytest.fixture
def wired(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "HardwareDetector", FakeDetector)
    monkeypatch.setattr(cli, "compose_up", lambda f: None)
    monkeypatch.setattr(cli, "compose_down", lambda f, volumes=False: None)
    monkeypatch.setattr(cli, "wait_healthy",
                        lambda plan, timeout_s: {s.name: "healthy" for s in plan.services})
    monkeypatch.setattr(cli, "HardenedRagClient", FakeHardenedRag)
    monkeypatch.setattr(cli, "RagClient", FakeRag)
    FakeHardenedRag.last = None
    FakeRag.used = False
    return tmp_path, tmp_path / "reg.jsonl"


def _run(tmp_path, reg, *extra):
    return cli.main(["wizard", "--ci", "--workdir", str(tmp_path / "run"),
                     "--registre", str(reg), "--teardown", "--skip-preflight", *extra])


# B1 : --rag-durci instancie HardenedRagClient branché (TEI + passerelle + reranker + clé)
def test_rag_durci_instancie_hardened_client(wired):
    tmp_path, reg = wired
    assert _run(tmp_path, reg, "--rag-durci") == 0
    k = FakeHardenedRag.last
    assert k is not None, "--rag-durci doit instancier HardenedRagClient"
    assert k.get("reranker_url"), "reranker branché"
    assert k.get("tei_url") and k.get("gateway_url"), "embed TEI + passerelle branchés"
    assert k.get("gateway_key"), "clé passerelle lue depuis le .env"
    assert not FakeRag.used, "le RAG tout-Ollama NE doit PAS être utilisé en durci"


# B2 : le plan durci déploie les 5 services (ollama, vector-store, TEI, reranker, litellm)
def test_rag_durci_plan_cinq_services(wired):
    tmp_path, reg = wired
    assert _run(tmp_path, reg, "--rag-durci") == 0
    plan = (tmp_path / "run" / "plan.json").read_text(encoding="utf-8")
    for name in ("ollama", "vector-store", "text-embeddings-inference-tei",
                 "text-embeddings-inference-reranker", "litellm"):
        assert f'"{name}"' in plan, f"{name} doit être au plan durci"


# B3 : défauts OOD appliqués (doc + question + fait Vornak-9) si non surchargés
def test_rag_durci_defauts_ood(wired, capsys):
    tmp_path, reg = wired
    assert _run(tmp_path, reg, "--rag-durci") == 0  # fait attendu par défaut = Vornak-9, présent dans la réponse
    out = capsys.readouterr().out
    assert "Vornak-9" in out


# B4 : bootstrap génère FORGEAI_LITELLM_KEY, ligne 0 (FORGEAI_API_TOKEN) préservée
def test_bootstrap_genere_litellm_key(tmp_path):
    bootstrap_secrets(tmp_path)
    env = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "FORGEAI_LITELLM_KEY" in ENV_KEYS
    assert "FORGEAI_LITELLM_KEY=" in env
    assert env.splitlines()[0].startswith("FORGEAI_API_TOKEN="), "ligne 0 préservée (test permissions)"


# non-régression : sans --rag-durci, le wizard utilise RagClient (tout-Ollama)
def test_sans_rag_durci_utilise_ragclient(wired):
    tmp_path, reg = wired
    assert _run(tmp_path, reg, "--question", "Quelle version de Python ?",
                "--expected-fact", "Vornak-9", "--document",
                str(Path(cli.__file__).resolve().parent / "data" / "smoke" / "verification-durci.md")) == 0
    assert FakeRag.used, "sans --rag-durci, RagClient (tout-Ollama) est utilisé"
    assert FakeHardenedRag.last is None or not FakeHardenedRag.last.get("reranker_url")
