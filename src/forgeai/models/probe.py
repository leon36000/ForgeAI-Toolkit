"""Test de connexion réel d'une route modèle — transport injectable (comme CommandRunner).

Critère B-09 : « test de connexion réel obligatoire avant validation de la route ;
échec = message clair, pas de route cassée ajoutée ». Le probe envoie une requête de
complétion minimale (schéma compatible OpenAI, adopté par OpenRouter/DeepInfra/NIM et la
plupart des fournisseurs directs) et exige une réponse NON VIDE = GREEN.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol


class Transport(Protocol):
    def post(self, url: str, headers: dict[str, str], body: bytes, timeout: float
             ) -> tuple[int, str]:
        """POST -> (code_http, corps_texte). code 0 = échec réseau/transport."""


class UrllibTransport:
    """Transport de production — stdlib urllib, aucune dépendance externe."""

    def post(self, url: str, headers: dict[str, str], body: bytes, timeout: float
             ) -> tuple[int, str]:
        import urllib.error
        import urllib.request
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.status, resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", "replace")
        except (urllib.error.URLError, TimeoutError, OSError):
            return 0, ""


@dataclass(frozen=True)
class ProbeResult:
    ok: bool
    status: int
    detail: str  # message clair (jamais la clé)

    @property
    def light(self) -> str:
        return "GREEN" if self.ok else "RED"


def _extract_text(payload: str) -> str:
    """Extrait le texte de complétion d'une réponse compatible OpenAI (souple)."""
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return ""
    for choice in data.get("choices", []) or []:
        msg = choice.get("message") or {}
        content = msg.get("content") or choice.get("text") or ""
        if isinstance(content, str) and content.strip():
            return content.strip()
    return ""


def probe_route(base_url: str, model_id: str, api_key: str,
                transport: Transport | None = None, timeout: float = 30.0) -> ProbeResult:
    """Appelle <base_url>/chat/completions avec un prompt trivial. Ne journalise JAMAIS la clé."""
    transport = transport or UrllibTransport()
    url = base_url.rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    body = json.dumps({
        "model": model_id,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 8,
    }).encode("utf-8")
    status, payload = transport.post(url, headers, body, timeout)
    if status == 0:
        return ProbeResult(False, 0, f"connexion impossible à {base_url} (réseau/URL)")
    if status == 401 or status == 403:
        return ProbeResult(False, status, "clé API refusée (401/403) — vérifier la clé")
    if status >= 400:
        return ProbeResult(False, status, f"fournisseur a répondu HTTP {status}")
    text = _extract_text(payload)
    if not text:
        return ProbeResult(False, status, "réponse vide/illisible — route non validée")
    return ProbeResult(True, status, "réponse non vide reçue")
