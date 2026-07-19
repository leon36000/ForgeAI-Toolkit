"""Corrective #49 — ensure_collection idempotente (409 = collection existante, pas une erreur).

Trouvée au premier déploiement UI réel (2026-07-19) : re-run du wizard sur une machine
ayant déjà déployé → HTTPError 409 → échec S08. Le double HTTP ci-dessous simule le
COMPORTEMENT RÉEL de Qdrant (PUT collection : 200 la première fois, 409 ensuite) —
c'est le service externe qui est simulé, jamais nos commandes."""
from __future__ import annotations

import json
import threading
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from forgeai.rag.client import RagClient


class _QdrantLike(BaseHTTPRequestHandler):
    """PUT /collections/<name> : 200 au premier appel, 409 (déjà existante) ensuite."""

    seen: set[str] = set()

    def do_PUT(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)
        if self.path.startswith("/collections/") and "/points" not in self.path:
            code = 409 if self.path in self.seen else 200
            self.seen.add(self.path)
        else:
            code = 200
        body = json.dumps({"result": True, "status": "ok"}).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # noqa: ARG002
        return


@pytest.fixture()
def qdrant_double():
    _QdrantLike.seen = set()
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _QdrantLike)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()
    srv.server_close()


def _client(url: str) -> RagClient:
    return RagClient(ollama_url="http://127.0.0.1:1", qdrant_url=url,
                     collection="preuve", llm_model="m", embed_model="e")


def test_ensure_collection_premier_appel(qdrant_double):
    _client(qdrant_double).ensure_collection(dim=4)  # 200 : ne lève pas
    # assertion réelle : le double a bien reçu le PUT de création
    assert any(path.endswith("/collections/preuve") for path in _QdrantLike.seen)


def test_ensure_collection_idempotente_409(qdrant_double):
    c = _client(qdrant_double)
    c.ensure_collection(dim=4)   # 200 — créée
    c.ensure_collection(dim=4)   # 409 — existante : NE DOIT PAS lever (le bug d'origine)
    c.ensure_collection(dim=4)   # toujours idempotent


def test_autres_erreurs_toujours_levees(qdrant_double):
    """Seul 409 est toléré : un vrai problème HTTP doit continuer d'échouer fort."""
    c = _client(qdrant_double)
    c.qdrant_url = "http://127.0.0.1:1"  # port fermé → URLError, jamais avalée
    with pytest.raises(urllib.error.URLError):
        c.ensure_collection(dim=4)
