"""Story E2b — rerank (bge-reranker-v2-m3 via TEI) branché au RAG durci.

Spec exécutable (TDAD, AVANT le code). Faux socle HTTP unifié étendant celui d'E2a avec un endpoint
`/rerank` qui SCORE réellement les textes reçus (marqueur lexical) et renvoie la liste TRIÉE desc
[{index,score}] — simulation du service externe, jamais notre code. Contrat /rerank vérifié sur le
conteneur réel (TEI cpu-1.9, MODEL_ID=BAAI/bge-reranker-v2-m3).
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from forgeai.rag.hardened import HardenedRagClient

DIM = 1024
CIBLE = "CHUNK-CIBLE"  # marqueur : le faux reranker score haut les textes qui le contiennent


class _Socle(BaseHTTPRequestHandler):
    requests: list = []
    search_hits: list = []
    chat_answer: str = "réponse"

    def _read(self):
        n = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(n) if n else b""
        try:
            return json.loads(raw.decode()) if raw else {}
        except json.JSONDecodeError:
            return {}

    def _send(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_PUT(self):  # noqa: N802
        self.requests.append(("PUT", self.path, self._read()))
        self._send(200, {"result": True})

    def do_POST(self):  # noqa: N802
        payload = self._read()
        type(self).requests.append(("POST", self.path, payload))
        if self.path.startswith("/embed"):
            inputs = payload.get("inputs")
            k = len(inputs) if isinstance(inputs, list) else 1
            self._send(200, [[0.01] * DIM for _ in range(k)])
        elif "/points/search" in self.path:
            self._send(200, {"result": list(type(self).search_hits)})
        elif self.path.endswith("/rerank"):
            texts = payload.get("texts", [])
            scored = [{"index": i, "score": 1.0 if CIBLE in t else 0.0}
                      for i, t in enumerate(texts)]
            scored.sort(key=lambda x: x["score"], reverse=True)
            self._send(200, scored)
        elif self.path.endswith("/v1/chat/completions"):
            self._send(200, {"choices": [{"message": {"content": type(self).chat_answer}}]})
        elif self.path.endswith("/api/pull"):
            self._send(200, {"status": "ok"})
        else:
            self._send(200, {})

    def log_message(self, *a):  # noqa: ARG002
        return


@pytest.fixture()
def socle():
    _Socle.requests = []
    _Socle.search_hits = []
    _Socle.chat_answer = "réponse"
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Socle)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()
    srv.server_close()


def _client(base, reranker=True):
    return HardenedRagClient(
        ollama_url=base, qdrant_url=base, llm_model="qwen2.5:0.5b", embed_model="bge-m3",
        tei_url=base, gateway_url=base, gateway_key="k",
        reranker_url=(base if reranker else ""), collection="c")


def _posts(suffix):
    return [r for r in _Socle.requests if r[0] == "POST" and r[1].endswith(suffix)]


def _hit(text, source):
    return {"payload": {"text": text, "source": source}}


# B1 : _rerank POST /rerank {query, texts} et réordonne les hits ORIGINAUX
def test_rerank_reordonne_les_hits(socle):
    hits = [_hit("distracteur", "d.md"), _hit(f"{CIBLE} pertinent", "bon.md")]
    ordered = _client(socle)._rerank("q", hits)
    assert ordered[0]["payload"]["source"] == "bon.md", "le chunk CIBLE remonte en tête"
    rr = _posts("/rerank")
    assert rr and rr[0][2] == {"query": "q", "texts": ["distracteur", f"{CIBLE} pertinent"]}


# B2 : ask avec reranker élargit puis rerank puis top_k puis génère
def test_ask_avec_reranker_branche_le_flux(socle):
    _Socle.search_hits = [_hit("distracteur", "d.md"), _hit(f"{CIBLE} bon", "bon.md")]
    res = _client(socle, reranker=True).ask("q", top_k=1)
    assert res["context_used"] is True
    assert res["sources"] == ["bon.md"], "après rerank+top_k=1, seul le bon chunk reste"
    assert _posts("/rerank"), "le rerank doit être appelé"


# B3 (HAUTE) : reranker actif + collection vide -> négatif, AUCUN POST /rerank
def test_negatif_preserve_sous_rerank_actif(socle):
    _Socle.search_hits = []
    res = _client(socle, reranker=True).ask("q")
    assert res == {"answer": "", "sources": [], "context_used": False}
    assert not _posts("/rerank"), "jamais POST /rerank sur un retrieval vide"


# B4 (BASSE) : rerank actif -> limit==candidates ; inactif -> limit==top_k
def test_elargissement_du_retrieval(socle):
    _Socle.search_hits = [_hit(f"{CIBLE} x", "b.md")]
    _client(socle, reranker=True).ask("q", top_k=3, candidates=20)
    search = _posts("/points/search")
    assert search and search[-1][2].get("limit") == 20, "rerank actif -> limit élargi"
    _Socle.requests = []
    _client(socle, reranker=False).ask("q", top_k=3)
    search = _posts("/points/search")
    assert search and search[-1][2].get("limit") == 3, "sans rerank -> limit==top_k (E2a intact)"


# B5 (bornes) : rerank renvoie un index hors plage -> pas d'IndexError
def test_rerank_index_hors_plage_ne_casse_pas(socle, monkeypatch):
    from forgeai.rag import hardened
    monkeypatch.setattr(hardened, "_post", lambda url, payload, **k: [{"index": 99, "score": 1.0}])
    hits = [_hit("a", "a.md")]
    ordered = _client(socle)._rerank("q", hits)  # ne doit pas lever
    assert isinstance(ordered, list)


# B6 (A/B plomberie) : le prompt de génération contient le BON chunk après rerank
def test_ab_le_rerank_change_le_prompt(socle):
    _Socle.search_hits = [_hit("mauvais contexte", "d.md"), _hit(f"{CIBLE} vraie réponse", "bon.md")]
    _client(socle, reranker=True).ask("q", top_k=1)
    chat = _posts("/v1/chat/completions")
    prompt = chat[-1][2]["messages"][0]["content"]
    assert CIBLE in prompt and "mauvais contexte" not in prompt, "le rerank a changé le contexte généré"


# non-régression : sans reranker_url, aucun POST /rerank (chemin E2a)
def test_sans_reranker_aucun_appel(socle):
    _Socle.search_hits = [_hit("x", "x.md")]
    _client(socle, reranker=False).ask("q")
    assert not _posts("/rerank")


# verrou de spec : le 2e service TEI reranker est déployable (image/port/health/MODEL_ID)
def test_reranker_spec_verrouille():
    from forgeai.planner.assemble import _load_deploy_specs
    spec = _load_deploy_specs()["text-embeddings-inference-reranker"]
    assert "text-embeddings-inference" in spec["image"] and ":" in spec["image"]
    assert spec["container_port"] == 80
    assert spec["health_path"] == "/health"
    assert spec["env"]["MODEL_ID"] == "BAAI/bge-reranker-v2-m3"
