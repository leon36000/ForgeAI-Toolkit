"""Client coffre openbao (KV v2) — stdlib pur (story E3b).

Branche la brique **openbao** du châssis comme coffre de secrets du déploiement RAG durci :
écrit puis relit un secret via l'API HTTP KV v2 (`/v1/secret/data/<path>`), authentifié par
l'en-tête `X-Vault-Token`. Aucune dépendance (urllib de la stdlib) — comme tout forgeai, pour
la portabilité « monde entier ».

Invariant secrets : ni le token ni les valeurs stockées n'apparaissent JAMAIS dans un message
d'erreur, un log ou un argv — seuls la méthode, l'URL et le code HTTP transitent en clair.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from forgeai.i18n import t

_KV_PREFIX = "/v1/secret/data/"
_RENEW_SELF = "/v1/auth/token/renew-self"


class VaultError(RuntimeError):
    """Échec d'écriture/lecture openbao. Le message ne contient ni token ni valeur secrète."""


def _kv_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}{_KV_PREFIX}{path.strip('/')}"


def _request(method: str, url: str, token: str, payload: dict | None, timeout: float) -> dict:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("X-Vault-Token", token)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — URL locale/LAN du socle
            body = resp.read().decode("utf-8")
        return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:  # 403/404/500… : le code seul, jamais le token/valeur
        raise VaultError(f"openbao {method} {url} -> HTTP {exc.code}") from None
    except urllib.error.URLError as exc:  # coffre injoignable : la raison réseau, pas de secret
        raise VaultError(t("secrets.vault.request.injoignable", method=method, url=url, reason=exc.reason)) from None
    except ValueError as exc:  # réponse non-JSON
        raise VaultError(t("secrets.vault.request.reponse_illisible", method=method, url=url, detail=exc)) from None


def store(base_url: str, token: str, path: str, data: dict, *, timeout: float = 10.0) -> None:
    """Écrit `data` (dict de secrets) au chemin KV v2 `path`. Lève VaultError en cas d'échec."""
    _request("POST", _kv_url(base_url, path), token, {"data": dict(data)}, timeout)


def read(base_url: str, token: str, path: str, *, timeout: float = 10.0) -> dict:
    """Lit et retourne le dict de secrets au chemin KV v2 `path`. Lève VaultError si absent."""
    doc = _request("GET", _kv_url(base_url, path), token, None, timeout)
    return doc.get("data", {}).get("data", {})


def renew_self(base_url: str, token: str, *, timeout: float = 10.0) -> int:
    """Renouvelle le token applicatif périodique (renew-self). Renvoie le TTL restant (secondes)
    après renouvellement. Lève VaultError si le renouvellement échoue (jamais le token dans le message).
    Un token périodique (period=720h) reste valide indéfiniment TANT QU'il est renouvelé dans sa période ;
    ce renouvellement proactif le garantit (un token non-root a toujours un TTL, seul le root n'expire pas)."""
    url = f"{base_url.rstrip('/')}{_RENEW_SELF}"
    doc = _request("POST", url, token, {}, timeout)
    return int(doc.get("auth", {}).get("lease_duration", 0))
