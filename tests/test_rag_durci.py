"""Story E2a — RAG durci : embed via TEI, génération via la passerelle LiteLLM.

Spec exécutable (TDAD, écrite AVANT le code de production). Un faux socle HTTP unifié
simule le COMPORTEMENT RÉEL des services externes (jamais notre code) :
  - TEI      POST /embed          {"inputs":[...]}  -> liste BRUTE de vecteurs (bge-m3, 1024-dim)
  - Qdrant   PUT/POST /collections/... (idempotent + search configurable)
  - Passerelle POST /v1/chat/completions (exige Authorization: Bearer, forme OpenAI)
  - Ollama   POST /api/pull        (pull des modèles)
Faits TEI vérifiés sur le conteneur réel (ghcr.io/huggingface/text-embeddings-inference:cpu-1.9,
MODEL_ID=BAAI/bge-m3) : /embed {"inputs":"x"} -> [[float x1024]], dimension 1024.
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from forgeai.rag.hardened import HardenedRagClient

DIM = 1024


class _SocleDurci(BaseHTTPRequestHandler):
    """Faux socle : TEI /embed, Qdrant, passerelle /v1/chat/completions, Ollama /api/pull."""

    requests: list = []          # (method, path, payload, headers) reçus
    search_hits: list = []       # hits renvoyés par /points/search (configurable par test)
    chat_answer: str = "Réponse durcie ancrée."

    def _read(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b""
        try:
            return json.loads(raw.decode("utf-8")) if raw else {}
        except json.JSONDecodeError:
            return {}

    def _send(self, code: int, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_PUT(self):  # noqa: N802
        payload = self._read()
        type(self).requests.append(("PUT", self.path, payload, dict(self.headers)))
        self._send(200, {"result": True, "status": "ok"})

    def do_POST(self):  # noqa: N802
        payload = self._read()
        type(self).requests.append(("POST", self.path, payload, dict(self.headers)))
        if self.path.startswith("/embed"):
            # TEI : une entrée string OU liste -> liste BRUTE de vecteurs (un par entrée)
            inputs = payload.get("inputs")
            n = len(inputs) if isinstance(inputs, list) else 1
            self._send(200, [[0.01 * (j + 1)] * DIM for j in range(n)])
        elif self.path.endswith("/points/search") or "/points/search" in self.path:
            self._send(200, {"result": list(type(self).search_hits)})
        elif self.path.endswith("/v1/chat/completions"):
            self._send(200, {"choices": [{"message": {"content": type(self).chat_answer}}]})
        elif self.path.endswith("/api/pull"):
            self._send(200, {"status": "success"})
        else:
            self._send(200, {})

    def log_message(self, *args):  # noqa: ARG002
        return


@pytest.fixture()
def socle():
    _SocleDurci.requests = []
    _SocleDurci.search_hits = []
    _SocleDurci.chat_answer = "Réponse durcie ancrée."
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _SocleDurci)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    yield base
    srv.shutdown()
    srv.server_close()


def _client(base: str) -> HardenedRagClient:
    return HardenedRagClient(
        ollama_url=base, qdrant_url=base, llm_model="qwen2.5:0.5b",
        embed_model="bge-m3", tei_url=base, gateway_url=base,
        gateway_key="forgeai-bearer-test-token-DO-NOT-LEAK",
        collection="forgeai-rag-durci-test",
    )


def _posts_to(base, suffix):
    return [r for r in _SocleDurci.requests if r[0] == "POST" and r[1].endswith(suffix)]


# --- B1 : embed via TEI (format brut, PAS le format Ollama {'embeddings':...}) ---
def test_embed_passe_par_tei_format_brut(socle):
    vecs = _client(socle)._embed(["alpha", "beta"])
    assert len(vecs) == 2 and len(vecs[0]) == DIM, "un vecteur 1024-dim par texte"
    embed_posts = _posts_to(socle, "/embed")
    assert embed_posts, "l'embed doit POST sur TEI /embed"
    assert embed_posts[0][2] == {"inputs": ["alpha", "beta"]}, "corps TEI {'inputs':[...]}"


# --- B2 : génération via la passerelle avec Bearer ---
def test_ask_genere_via_passerelle_bearer(socle):
    _SocleDurci.search_hits = [{"payload": {"text": "contexte durci", "source": "doc.md"}}]
    res = _client(socle).ask("question ?")
    assert res["answer"] == "Réponse durcie ancrée."
    assert res["context_used"] is True
    chat = _posts_to(socle, "/v1/chat/completions")
    assert chat, "la génération doit passer par la passerelle /v1/chat/completions"
    assert chat[0][3].get("Authorization") == "Bearer forgeai-bearer-test-token-DO-NOT-LEAK"
    # forme OpenAI : messages présents
    assert "messages" in chat[0][2]


# --- B3 : contrôle négatif — sans hit, pas de génération, context_used=false ---
def test_ask_sans_hit_pas_de_generation(socle):
    _SocleDurci.search_hits = []
    res = _client(socle).ask("hors corpus ?")
    assert res["answer"] == "" and res["sources"] == [] and res["context_used"] is False
    assert not _posts_to(socle, "/v1/chat/completions"), "aucune génération sans contexte"


# --- B4 : sources triées + dédupliquées ---
def test_ask_retourne_sources_triees_dedupliquees(socle):
    _SocleDurci.search_hits = [
        {"payload": {"text": "a", "source": "z.md"}},
        {"payload": {"text": "b", "source": "a.md"}},
        {"payload": {"text": "c", "source": "z.md"}},
    ]
    res = _client(socle).ask("q ?")
    assert res["sources"] == ["a.md", "z.md"]


# --- B5 : la clé Bearer n'est JAMAIS journalisée ---
def test_cle_jamais_journalisee(socle, capsys):
    _SocleDurci.search_hits = [{"payload": {"text": "x", "source": "s.md"}}]
    c = _client(socle)
    c.ask("q ?")
    c.pull_models()
    out = capsys.readouterr()
    assert "forgeai-bearer-test-token-DO-NOT-LEAK" not in (out.out + out.err)


# --- B6 : pull_models durci ne tire QUE le LLM (embed servi par TEI) ---
def test_pull_models_tire_uniquement_le_llm(socle):
    _client(socle).pull_models()
    pulls = _posts_to(socle, "/api/pull")
    modeles = [p[2].get("model") for p in pulls]
    assert "qwen2.5:0.5b" in modeles, "le LLM doit être tiré"
    assert "bge-m3" not in modeles, "l'embed (TEI) ne se tire PAS via Ollama /api/pull"


# --- non-régression : ingest/_search hériter route l'embed via TEI (polymorphisme) ---
def test_ingest_route_embed_via_tei(socle):
    n = _client(socle).ingest("Paragraphe un.\n\nParagraphe deux.", source="doc.md")
    assert n >= 1
    assert _posts_to(socle, "/embed"), "ingest doit embarquer via TEI (self._embed surchargé)"
