"""Story E3c — client ledger immudb (API document v2), stdlib pur.

Spec exécutable (TDAD, AVANT le code). Un faux serveur immudb document-API (http.server) valide le
contrat HTTP réel observé sur immudb 1.11 : ouverture de session, création de collection idempotente,
insertion (→ transactionId + documentId), et piste d'audit d'un document (révisions inviolables).
Le comportement contre un immudb RÉEL est prouvé par l'e2e journalisé au registre. Invariant secrets :
ni les identifiants ni le token de session ne doivent apparaître dans une exception.
"""

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import ClassVar

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from forgeai.audit import immudb as _immudb_module
from forgeai.audit.immudb import (
    LedgerError,
    ensure_collection,
    history,
    open_session,
    record,
)

TOKEN = "sess-e3c"


class _ImmudbHandler(BaseHTTPRequestHandler):
    """immudb document-API minimal : session + collection + insert + audit, exige le sessionid."""

    collections: ClassVar[dict] = {}
    docs: ClassVar[dict] = {}
    tx: ClassVar[list[int]] = [1]

    def log_message(self, *args):
        return

    def _read(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length) or b"{}")

    def _send(self, code: int, obj: dict):
        payload = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _auth(self) -> bool:
        return self.headers.get("grpc-metadata-sessionid") == TOKEN

    def do_GET(self):
        if self.path == "/api/v2/collections":
            if not self._auth():
                return self._send(401, {"error": "not logged in"})
            cols = [{"name": n} for n in _ImmudbHandler.collections]
            return self._send(200, {"collections": cols})
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        p = self.path
        if p == "/api/v2/authorization/session/open":
            body = self._read()
            if body.get("username") and body.get("password"):
                return self._send(200, {"sessionID": TOKEN})
            return self._send(401, {"error": "bad creds"})
        if not self._auth():
            return self._send(401, {"error": "not logged in"})
        parts = p.split("/")
        # /api/v2/collection/{name}
        if len(parts) == 5 and parts[3] == "collection":
            name = parts[4]
            if name in _ImmudbHandler.collections:
                return self._send(500, {"error": f"collection already exists ({name})"})
            _ImmudbHandler.collections[name] = self._read()
            return self._send(200, {})
        # /api/v2/collection/{name}/documents
        if len(parts) == 6 and parts[5] == "documents":
            name = parts[4]
            if name not in _ImmudbHandler.collections:
                return self._send(500, {"error": f"collection does not exist ({name})"})
            body = self._read()
            docs = body.get("documents")
            if not docs:
                return self._send(
                    500, {"error": "illegal arguments: no document specified"}
                )
            _ImmudbHandler.tx[0] += 1
            tx = _ImmudbHandler.tx[0]
            doc_id = f"doc{tx:032x}"
            stored = dict(docs[0], _id=doc_id)
            _ImmudbHandler.docs.setdefault(name, {})[doc_id] = (tx, stored)
            return self._send(200, {"transactionId": str(tx), "documentIds": [doc_id]})
        # /api/v2/collection/{name}/documents/search
        if len(parts) == 7 and parts[5] == "documents" and parts[6] == "search":
            name = parts[4]
            revs = [
                {"documentId": did, "document": d}
                for did, (tx, d) in _ImmudbHandler.docs.get(name, {}).items()
            ]
            return self._send(200, {"revisions": revs})
        # /api/v2/collection/{name}/document/{id}/audit
        if len(parts) == 8 and parts[5] == "document" and parts[7] == "audit":
            self._read()
            name, did = parts[4], parts[6]
            entry = _ImmudbHandler.docs.get(name, {}).get(did)
            if entry is None:
                return self._send(404, {"error": "not found"})
            tx, d = entry
            return self._send(
                200,
                {
                    "revisions": [
                        {
                            "transactionId": str(tx),
                            "documentId": did,
                            "revision": "1",
                            "document": d,
                            "username": "immudb",
                            "ts": "1784541026",
                        }
                    ]
                },
            )
        return self._send(404, {"error": "not found"})


@pytest.fixture
def immu():
    _ImmudbHandler.collections = {}
    _ImmudbHandler.docs = {}
    _ImmudbHandler.tx = [1]
    server = HTTPServer(("127.0.0.1", 0), _ImmudbHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
        assert not thread.is_alive(), "le faux serveur immudb doit être arrêté"


def test_open_session_retourne_token(immu):
    tok = open_session(immu, "immudb", "immudb", "defaultdb")
    assert tok == TOKEN


def test_record_puis_history_round_trip(immu):
    tok = open_session(immu, "immudb", "immudb", "defaultdb")
    ensure_collection(immu, tok, "audit", [{"name": "fact", "type": "STRING"}])
    res = record(immu, tok, "audit", {"fact": "Vornak-9", "story": "E3c"})
    assert res["transactionId"] and res["documentId"], "insertion -> tx + docId"
    revs = history(immu, tok, "audit", res["documentId"])
    assert revs and revs[0]["document"]["fact"] == "Vornak-9"
    assert (
        revs[0]["transactionId"] == res["transactionId"]
    )  # inscription au ledger prouvée


def test_ensure_collection_idempotent(immu):
    tok = open_session(immu, "immudb", "immudb", "defaultdb")
    ensure_collection(immu, tok, "audit", [{"name": "fact", "type": "STRING"}])
    # 2e appel : la collection existe déjà -> ne doit PAS lever (idempotent)
    ensure_collection(immu, tok, "audit", [{"name": "fact", "type": "STRING"}])


def test_tx_monotone_ledger_append_only(immu):
    tok = open_session(immu, "immudb", "immudb", "defaultdb")
    ensure_collection(immu, tok, "audit", [{"name": "fact", "type": "STRING"}])
    t1 = int(record(immu, tok, "audit", {"fact": "a"})["transactionId"])
    t2 = int(record(immu, tok, "audit", {"fact": "b"})["transactionId"])
    assert t2 > t1, "chaque écriture avance le transactionId (ledger append-only)"


def test_sans_session_leve_ledgererror(immu):
    with pytest.raises(LedgerError):
        record(immu, "mauvais-token", "audit", {"fact": "x"})


def test_exception_ne_fuit_pas_identifiants():
    try:
        open_session("http://127.0.0.1:1", "immudb", "MOTDEPASSE-SECRET", "defaultdb")
        raise AssertionError("aurait dû lever LedgerError")
    except LedgerError as exc:
        assert "MOTDEPASSE-SECRET" not in str(exc)


# --- CAND-008 (audit v7.1, P1_HIGH) ----------------------------------------
#
# La garde `if collection not in names: raise` de `ensure_collection` (ligne ~81 de
# src/forgeai/audit/immudb.py) n'était exercée par AUCUN test : le faux serveur HTTP de
# `immu` ne produit jamais l'état « échec réel + collection absente de la liste de
# secours », donc un mutant qui neutralise la garde (ex. `if False: raise`) fait passer
# toute la suite existante. Les deux tests ci-dessous ferment ce trou avec une double
# injectée pour `_request` (pas de réseau réel) et pinnent les DEUX branches.
#
# Cycle RED/GREEN exécuté manuellement pour `test_...leve_ledgererror` :
#   1. RED  : garde temporairement neutralisée en éditant immudb.py ligne 81
#             (`if collection not in names:` -> `if False:  # CAND-008 RED probe`),
#             `pytest tests/test_immudb.py -k relance_si_absente -q` -> 1 failed
#             (LedgerError attendue mais absorbée : pytest.raises n'a rien capturé).
#   2. GREEN : garde restaurée à l'identique (`git checkout -- ...immudb.py`),
#             même commande -> 1 passed.
# Preuve capturée dans le message de commit CAND-008 (sorties pytest complètes).


def test_ensure_collection_relance_si_absente_de_la_liste_secours(monkeypatch):
    """Pinning : POST échoue (LedgerError) ET la collection cible n'apparaît PAS dans le
    GET de secours -> l'exception doit remonter, jamais être avalée (ledger d'audit)."""
    appels = []

    def _request_double(method, url, token, payload, timeout):
        appels.append(method)
        if method == "POST":
            raise LedgerError("immudb POST ... -> HTTP 500")
        if method == "GET":
            # la collection ciblée ("audit") N'EST PAS dans la liste de secours
            return {"collections": [{"name": "autre-collection"}]}
        raise AssertionError(f"méthode inattendue: {method}")

    monkeypatch.setattr(_immudb_module, "_request", _request_double)

    with pytest.raises(LedgerError):
        ensure_collection(
            "http://fake-immudb.invalid", "tok", "audit",
            [{"name": "fact", "type": "STRING"}],
        )
    assert appels == ["POST", "GET"], "doit tenter la création puis relire la liste de secours"


def test_ensure_collection_absorbe_si_presente_dans_la_liste_secours(monkeypatch):
    """Contrôle négatif complémentaire : POST échoue MAIS la collection cible EST dans le
    GET de secours (2e appel sur collection déjà existante) -> aucune exception ne remonte
    (idempotence voulue). Pinne la branche `if collection not in names` == False."""
    appels = []

    def _request_double(method, url, token, payload, timeout):
        appels.append(method)
        if method == "POST":
            raise LedgerError("immudb POST ... -> HTTP 500 (collection already exists)")
        if method == "GET":
            # la collection ciblée ("audit") EST dans la liste de secours
            return {"collections": [{"name": "audit"}]}
        raise AssertionError(f"méthode inattendue: {method}")

    monkeypatch.setattr(_immudb_module, "_request", _request_double)

    ensure_collection(
        "http://fake-immudb.invalid", "tok", "audit",
        [{"name": "fact", "type": "STRING"}],
    )  # ne doit PAS lever
    assert appels == ["POST", "GET"]
