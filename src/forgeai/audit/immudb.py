"""Client ledger immudb (API document v2) — stdlib pur (story E3c).

Branche la brique **immudb** du châssis comme ledger d'audit IMMUABLE du déploiement RAG durci :
enregistre un événement d'audit dans le ledger append-only d'immudb via l'API HTTP document v2,
puis en relit la piste de révisions (`transactionId` monotone + `revision` = preuve d'inscription
inviolable, horodatée côté serveur). Aucune dépendance (urllib) — comme tout forgeai.

Flux REST (observé sur immudb 1.11, port 8080) :
  1. POST /authorization/session/open  {username,password,database}  -> {sessionID}
  2. POST /collection/{name}           (header grpc-metadata-sessionid) -> crée la collection
  3. POST /collection/{name}/documents {documents:[{...}]}            -> {transactionId, docIds}
  4. POST /collection/{name}/document/{id}/audit                      -> {revisions:[...]}
(préfixe commun /api/v2 omis ci-dessus pour la lisibilité.)

Invariant secrets : ni les identifiants ni le token de session n'apparaissent dans un message
d'erreur, un log ou un argv — seuls la méthode, l'URL et le code HTTP transitent en clair.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from forgeai.core.validation import valider_schema_url
from forgeai.i18n import t

_API = "/api/v2"


class LedgerError(RuntimeError):
    """Échec d'une opération immudb. Le message ne contient ni identifiant ni token."""


def _request(method: str, url: str, token: str | None, payload: dict | None,
             timeout: float) -> dict:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("grpc-metadata-sessionid", token)
    # HORS du try : ValidationError hérite de ValueError, capturé plus bas.
    valider_schema_url(url)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — URL locale/LAN du socle
            body = resp.read().decode("utf-8")
        return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:  # code seul ; jamais le payload/creds
        raise LedgerError(f"immudb {method} {url} -> HTTP {exc.code}") from None
    except urllib.error.URLError as exc:
        raise LedgerError(t("audit.immudb.request.injoignable", method=method, url=url, reason=exc.reason)) from None
    except ValueError as exc:
        raise LedgerError(t("audit.immudb.request.reponse_illisible", method=method, url=url, detail=exc)) from None


def open_session(base_url: str, username: str,
                 password: str,  # proof:allow — paramètre, pas un secret
                 database: str = "defaultdb", *, timeout: float = 10.0) -> str:
    """Ouvre une session, retourne le token de session. Lève LedgerError si refusé."""
    doc = _request("POST", f"{base_url.rstrip('/')}{_API}/authorization/session/open", None,
                   {"username": username, "password": password, "database": database}, timeout)
    token = doc.get("sessionID")
    if not token:
        raise LedgerError(t("audit.immudb.open_session.sessionid_absent"))
    return token


def ensure_collection(base_url: str, token: str, collection: str, fields: list[dict],
                      *, timeout: float = 10.0) -> None:
    """Crée la collection si absente. Idempotent : une collection existante n'est pas une erreur.

    (Un 2e appel sur une collection existante est avalé après confirmation via la liste.)
    """
    url = f"{base_url.rstrip('/')}{_API}/collection/{collection}"
    try:
        _request("POST", url, token, {"fields": fields}, timeout)
    except LedgerError:
        # collection déjà existante -> confirmée par la liste ; sinon on relaie l'échec réel.
        listed = _request("GET", f"{base_url.rstrip('/')}{_API}/collections", token, None, timeout)
        names = {c.get("name") for c in listed.get("collections", [])}
        if collection not in names:
            raise


def record(base_url: str, token: str, collection: str, document: dict,
           *, timeout: float = 10.0) -> dict:
    """Écrit `document` au ledger. Retourne {transactionId, documentId}. Lève LedgerError si KO."""
    url = f"{base_url.rstrip('/')}{_API}/collection/{collection}/documents"
    doc = _request("POST", url, token, {"documents": [document]}, timeout)
    ids = doc.get("documentIds") or []
    if not doc.get("transactionId") or not ids:
        raise LedgerError(t("audit.immudb.record.transaction_absent"))
    return {"transactionId": doc["transactionId"], "documentId": ids[0]}


def history(base_url: str, token: str, collection: str, document_id: str,
            *, timeout: float = 10.0) -> list:
    """Retourne la piste d'audit (révisions inviolables) d'un document du ledger."""
    url = f"{base_url.rstrip('/')}{_API}/collection/{collection}/document/{document_id}/audit"
    doc = _request("POST", url, token, {"page": 1, "pageSize": 10}, timeout)
    return doc.get("revisions", [])
