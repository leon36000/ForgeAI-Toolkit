"""Initialisation / déscellement idempotent d'openbao en mode production.

Toute la logique déterministe et testable (ne tourne PAS dans l'image openbao).
Stdlib pure, transport injectable, jamais de fuite de secret dans les erreurs.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

from forgeai.i18n import t

# ---------------------------------------------------------------------------
# Exception
# ---------------------------------------------------------------------------

class OpenBaoInitError(RuntimeError):
    """Échec d'init/unseal openbao. Le message ne contient **jamais** de token/clé."""

# ---------------------------------------------------------------------------
# Politique applicative (HCL)
# ---------------------------------------------------------------------------

_POLICY_HCL = (
    'path "secret/data/forgeai/*" { capabilities = ["create","read","update","delete"] }\n'
    'path "secret/metadata/forgeai/*" { capabilities = ["read","list","delete"] }\n'
    # Le token applicatif est émis `no_default_policy` (scopé) : il doit porter EXPLICITEMENT ses
    # capacités d'AUTO-GESTION, sinon lookup-self/renew-self échouent en 403 — le renouvellement
    # périodique (720h) serait alors IMPOSSIBLE => expiration silencieuse du token (l'impasse même que
    # le design met en garde). Prouvé par la preuve e2e S6 (403 sans ces lignes). revoke-self inutile :
    # la rotation est faite par le root (openbao_init), pas par le token lui-même.
    'path "auth/token/lookup-self" { capabilities = ["read"] }\n'
    'path "auth/token/renew-self" { capabilities = ["update"] }\n'
)

# ---------------------------------------------------------------------------
# Transport par défaut (stdlib, injectable pour les tests)
# ---------------------------------------------------------------------------

def http_transport(base_url: str, timeout: float = 10.0):
    """Fabrique un transport basé sur urllib.

    Retourne une fonction ``request(method, path, *, token=None, payload=None)``
    qui renvoie ``(status_code: int, body: dict)``.
    **Aucun** secret n'apparaît dans les messages d'erreur.
    """
    base = base_url.rstrip("/")

    def request(
        method: str,
        path: str,
        *,
        token: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> tuple[int, dict]:
        url = f"{base}{path}"
        data_bytes = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(url, data=data_bytes, method=method)
        if token is not None:
            req.add_header("X-Vault-Token", token)
        if data_bytes is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode("utf-8")
            return (resp.status, json.loads(body) if body else {})
        except urllib.error.HTTPError as exc:
            # Ne jamais inclure le token ni la charge utile dans le message
            raise OpenBaoInitError(
                f"openbao {method} {path} -> HTTP {exc.code}"
            ) from None
        except urllib.error.URLError as exc:
            raise OpenBaoInitError(
                t("secrets.openbao_init.http_transport.injoignable", method=method, path=path, reason=exc.reason)
            ) from None
        except ValueError as exc:
            raise OpenBaoInitError(
                t("secrets.openbao_init.http_transport.reponse_illisible", method=method, path=path, detail=exc)
            ) from None

    return request

# ---------------------------------------------------------------------------
# Logique principale
# ---------------------------------------------------------------------------

def ensure_openbao_ready(
    request: Callable[..., tuple[int, dict]],
    key_store: Any,  # doit posséder .read() -> dict|None et .write(data: dict) -> None
    secret_store: Any,  # idem
    *,
    key_shares: int = 1,
    key_threshold: int = 1,
    token_period: str = "720h",
) -> str:
    """Rend openbao **prêt** et renvoie un token applicatif **scopé** (jamais le root).

    Idempotent : réconcilie par état désiré.
    """
    # ── 1. seal-status ────────────────────────────────────────────────
    status, body = request("GET", "/v1/sys/seal-status")
    initialized = body.get("initialized", False)
    sealed = body.get("sealed", False)

    root_token: str | None = None
    unseal_key: str | None = None

    # ── 2. Init si nécessaire ─────────────────────────────────────────
    if not initialized:
        status_init, init_resp = request(
            "PUT",
            "/v1/sys/init",
            payload={"secret_shares": key_shares, "secret_threshold": key_threshold},
        )
        keys = init_resp.get("keys", [])
        root = init_resp.get("root_token", "")
        if not keys or not root:
            raise OpenBaoInitError(t("secrets.openbao_init.ensure_openbao_ready.init_reponse_incomplete"))
        unseal_key = keys[0]
        root_token = root
        # Écriture atomique + read-back
        key_store.write({"unseal_key": unseal_key, "root_token": root_token})
        stored = key_store.read()
        if (not stored or stored.get("unseal_key") != unseal_key
                or stored.get("root_token") != root_token):
            # NOTE i18n : PAS de t() ici (délibéré) — tests/test_openbao_init.py::
            # TestReadBackInitFails::test_detects_readback_failure vérifie
            # `"read-back" in str(exc_info.value).lower()` sur ce texte anglais
            # d'origine (déjà un cas particulier : seul message anglais du fichier).
            # Convertir casserait ce test existant (CA5) — hors périmètre I18N-042.
            raise OpenBaoInitError(
                "openbao init succeeded but key store read-back failed - "
                "the key material is irrecoverable"
            )
        initialized = True
        sealed = True  # après init le coffre est toujours scellé

    # ── 3. Récupérer les clés depuis le store ────────────────────────
    keys_data = key_store.read()
    if initialized and (not keys_data or not keys_data.get("root_token")
                        or not keys_data.get("unseal_key")):
        raise OpenBaoInitError(
            t("secrets.openbao_init.ensure_openbao_ready.coffre_sans_cles")
        )
    root_token = keys_data["root_token"]
    unseal_key = keys_data["unseal_key"]

    # ── 4. Unseal si scellé ───────────────────────────────────────────
    if sealed:
        status_unseal, unseal_resp = request(
            "PUT",
            "/v1/sys/unseal",
            payload={"key": unseal_key},
        )
        if unseal_resp.get("sealed") is not False:
            raise OpenBaoInitError(
                t("secrets.openbao_init.ensure_openbao_ready.unseal_echec")
            )

    # ── 5. Monter KV v2 sur secret/ ──────────────────────────────────
    status_mounts, mounts_body = request(
        "GET", "/v1/sys/mounts", token=root_token
    )
    existing_mounts = mounts_body.get("data", mounts_body)
    if "secret/" not in existing_mounts:
        try:
            request(
                "POST",
                "/v1/sys/mounts/secret",
                token=root_token,
                payload={"type": "kv", "options": {"version": "2"}},
            )
        except OpenBaoInitError as exc:
            # Un 400 « path already in use » est acceptable si la vérif a raté
            if "HTTP 400" not in str(exc):
                raise

    # ── 6. Policy forgeai-app ────────────────────────────────────────
    request(
        "PUT",
        "/v1/sys/policies/acl/forgeai-app",
        token=root_token,
        payload={"policy": _POLICY_HCL},
    )

    # ── 7. Token applicatif ──────────────────────────────────────────
    stored_token_doc = secret_store.read()
    current_token = stored_token_doc.get("token") if stored_token_doc else None

    if current_token:
        try:
            lookup_status, lookup = request(
                "GET", "/v1/auth/token/lookup-self", token=current_token
            )
            if (
                lookup_status == 200
                and "forgeai-app" in lookup.get("data", {}).get("policies", [])
            ):
                return current_token
        except OpenBaoInitError:
            # token invalide -> on en crée un nouveau
            pass

    # Créer un nouveau token
    new_token_resp = request(
        "POST",
        "/v1/auth/token/create",
        token=root_token,
        payload={
            "policies": ["forgeai-app"],
            "period": token_period,
            "no_default_policy": True,
            "no_parent": True,
        },
    )
    new_token = new_token_resp[1].get("auth", {}).get("client_token", "")
    if not new_token:
        raise OpenBaoInitError(
            t("secrets.openbao_init.ensure_openbao_ready.token_create_sans_client_token")
        )

    # Persister le nouveau token
    secret_store.write({"token": new_token})

    # Révoquer l'ancien (best effort)
    if current_token and current_token != new_token:
        try:
            request(
                "POST",
                "/v1/auth/token/revoke",
                token=root_token,
                payload={"token": current_token},
            )
        except OpenBaoInitError:
            pass

    return new_token
