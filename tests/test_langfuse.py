"""Story E5 — client observabilité langfuse (API publique traces), stdlib pur.

Spec exécutable (TDAD, AVANT le code). Un faux serveur langfuse (http.server) valide le contrat
réel : `GET /api/public/traces` authentifié en Basic (public_key:secret_key) -> {"data":[...]}.
Le comportement contre un langfuse RÉEL est prouvé par l'e2e journalisé au registre. Les clés
d'API ne doivent pas apparaître dans une exception.
"""
import base64
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from forgeai.observability.langfuse import ObservabilityError, count_traces, wait_for_trace

PK, SK = "pk-lf-test", "sk-lf-test"


class _LangfuseHandler(BaseHTTPRequestHandler):
    traces: list = []

    def log_message(self, *a):
        return

    def _auth_ok(self) -> bool:
        hdr = self.headers.get("Authorization", "")
        if not hdr.startswith("Basic "):
            return False
        raw = base64.b64decode(hdr[6:]).decode()
        return raw == f"{PK}:{SK}"

    def do_GET(self):
        if self.path.startswith("/api/public/traces"):
            if not self._auth_ok():
                self.send_response(401)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"data": _LangfuseHandler.traces}).encode())
            return
        self.send_response(404)
        self.end_headers()


@pytest.fixture
def lf():
    _LangfuseHandler.traces = []
    server = HTTPServer(("127.0.0.1", 0), _LangfuseHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}", _LangfuseHandler
    finally:
        server.shutdown()


def test_count_traces_vide(lf):
    base, _ = lf
    assert count_traces(base, PK, SK) == 0


def test_count_traces_apres_ingestion(lf):
    base, H = lf
    H.traces = [{"id": "t1", "name": "litellm-acompletion"}]
    assert count_traces(base, PK, SK) == 1


def test_wait_for_trace_present(lf):
    base, H = lf
    H.traces = [{"id": "t1", "name": "litellm-acompletion"}]
    tr = wait_for_trace(base, PK, SK, timeout=2.0, interval=0.1)
    assert tr and tr["name"] == "litellm-acompletion"


def test_wait_for_trace_timeout_retourne_none(lf):
    base, _ = lf
    assert wait_for_trace(base, PK, SK, timeout=0.5, interval=0.1) is None


def test_mauvaise_cle_leve_erreur(lf):
    base, _ = lf
    with pytest.raises(ObservabilityError):
        count_traces(base, "pk-mauvais", "sk-mauvais")


def test_exception_ne_fuit_pas_les_cles():
    try:
        count_traces("http://127.0.0.1:1", "pk-CONFIDENTIEL", "sk-CONFIDENTIEL")
        raise AssertionError("aurait dû lever")
    except ObservabilityError as exc:
        assert "CONFIDENTIEL" not in str(exc)
