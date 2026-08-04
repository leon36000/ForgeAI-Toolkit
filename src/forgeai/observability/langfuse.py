"""Client observabilité langfuse (API publique) — stdlib pur (story E5).

Branche la brique **langfuse** du châssis comme observabilité du RAG durci : LiteLLM émet ses traces
via `success_callback: ["langfuse"]` (dans litellm-config.yaml quand langfuse est au plan),
et ce module VÉRIFIE côté déploiement que les traces atterrissent — `GET /api/public/traces`,
authentifié en Basic (public_key:secret_key). Aucune dépendance (urllib) — comme tout forgeai.

Invariant secrets : les clés d'API (pk-lf-…/sk-lf-…) n'apparaissent jamais dans un message d'erreur.
"""
from __future__ import annotations

import base64
import json
import time
import urllib.error
import urllib.request

from forgeai.i18n import t

_TRACES = "/api/public/traces"


class ObservabilityError(RuntimeError):
    """Échec d'interrogation langfuse. Le message ne contient pas les clés d'API."""


def _get(base_url: str, public_key: str, secret_key: str, path: str, timeout: float) -> dict:
    token = base64.b64encode(f"{public_key}:{secret_key}".encode()).decode()
    req = urllib.request.Request(f"{base_url.rstrip('/')}{path}")
    req.add_header("Authorization", f"Basic {token}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — URL locale/LAN
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise ObservabilityError(f"langfuse GET {path} -> HTTP {exc.code}") from None
    except urllib.error.URLError as exc:
        raise ObservabilityError(t("observability.langfuse.get.injoignable", path=path, reason=exc.reason)) from None
    except ValueError as exc:
        raise ObservabilityError(t("observability.langfuse.get.reponse_illisible", path=path, detail=exc)) from None


def count_traces(base_url: str, public_key: str, secret_key: str, *, timeout: float = 10.0) -> int:
    """Nombre de traces visibles dans le projet langfuse (via ses clés d'ingestion)."""
    doc = _get(base_url, public_key, secret_key, f"{_TRACES}?limit=50", timeout)
    return len(doc.get("data", []))


def wait_for_trace(base_url: str, public_key: str, secret_key: str, *,
                   timeout: float = 60.0, interval: float = 3.0) -> dict | None:
    """Attend qu'AU MOINS une trace apparaisse (le callback LiteLLM flush en asynchrone).

    Retourne la trace la plus récente, ou None si le délai expire. Utilise time.monotonic (pas
    de génération aléatoire). Une erreur transitoire d'interrogation est retentée jusqu'au délai.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            doc = _get(base_url, public_key, secret_key, f"{_TRACES}?limit=1",
                       timeout=min(interval + 2, 10))
            data = doc.get("data", [])
            if data:
                return data[0]
        except ObservabilityError:
            pass  # langfuse pas encore prêt / trace pas encore flushée -> on retente
        time.sleep(interval)
    return None
