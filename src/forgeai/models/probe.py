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

from forgeai.models.budget import BudgetTracker, extraire_tokens


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

        from forgeai.core.validation import valider_schema_url
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        valider_schema_url(url)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.status, resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", "replace")
        except (urllib.error.URLError, TimeoutError, OSError):
            return 0, ""


class MeteredTransport:
    """Décorateur de `Transport` qui mesure la consommation (ADR B-20 §1 chemin A).

    Porte pré-dispatch : `tracker.check(agent)` AVANT toute émission — sur COUPURE,
    `QuotaAtteint` remonte et `inner.post` n'est jamais appelé (zéro émission réseau).
    Transparent sur le fil : retourne le `(status, text)` de `inner` inchangé. La
    comptabilisation se fait APRÈS, à partir de la réponse effectivement reçue :
    échec réseau (status 0) → journal `motif="timeout"` ; sinon `extraire_tokens`
    sur le corps parsé (réponse d'erreur ou sans `usage` → `exact=False`,
    `motif="usage_absent"`). L'injection est opt-in via le paramètre `transport`
    existant : un appelant qui ne fournit pas de `MeteredTransport` n'est pas mesuré.
    """

    def __init__(self, inner: "Transport", tracker: BudgetTracker, agent: str = "probe") -> None:
        self._inner = inner
        self._tracker = tracker
        self._agent = agent

    def post(self, url: str, headers: dict[str, str], body: bytes, timeout: float
             ) -> tuple[int, str]:
        # Porte pré-dispatch : lève QuotaAtteint sur COUPURE AVANT toute émission.
        self._tracker.check(self._agent)
        status, text = self._inner.post(url, headers, body, timeout)
        if status == 0:
            # Pas de réponse consommée : journal timeout, jamais d'estimation (§7.1).
            self._tracker.record(self._agent, 0, exact=False, motif="timeout")
        else:
            try:
                reponse = json.loads(text)
            except (ValueError, TypeError):
                reponse = {}
            tokens, exact = extraire_tokens(reponse)
            self._tracker.record(
                self._agent, tokens, exact=exact,
                motif=None if exact else "usage_absent",
            )
        return status, text


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
    if not isinstance(data, dict):
        return ""
    for choice in data.get("choices", []) or []:
        if not isinstance(choice, dict):
            continue
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
