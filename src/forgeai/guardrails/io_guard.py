"""Guardrails I/O MAISON du RAG durci (story E4) — stdlib pur.

nemo-guardrails est une lib Python (dépendance) ; forgeai reste zéro-dépendance pour la
portabilité « monde entier ». On fournit donc une garde DÉTERMINISTE, sans dépendance :

  - ENTRÉE : rejette les questions vides, trop longues, ou portant un pattern d'injection de
    prompt (OWASP LLM01 — « ignore previous instructions », « reveal your system prompt », …).
    C'est une première ligne de défense rapide contre l'injection directe ; ce n'est PAS une
    garde sémantique LLM (les contournements sophistiqués restent possibles) — assumé et documenté.
  - SORTIE : exige l'ANCRAGE (la réponse doit s'appuyer sur le contexte récupéré) et non-vide.

Les gardes lèvent `GuardrailBlocked(reason)` ; la raison décrit le blocage sans recopier un
prompt hostile potentiellement volumineux.
"""
from __future__ import annotations

import re

MAX_INPUT_CHARS = 4000

# Patterns d'injection connus (OWASP LLM01), FR + EN, insensibles à la casse. Chaque motif vise
# une tournure d'écrasement d'instructions ou d'exfiltration du prompt système.
_INJECTION_PATTERNS: tuple[re.Pattern, ...] = tuple(re.compile(p, re.IGNORECASE) for p in (
    r"ignore\s+(all\s+|the\s+|any\s+)*(previous|above|prior|preceding)\s+(instructions|prompts?)",
    r"disregard\s+(all\s+|the\s+|your\s+|any\s+)*(previous|above|prior)?\s*(instructions|prompts?)",
    r"forget\s+(all\s+|the\s+|your\s+|any\s+)*(previous\s+)?(instructions|prompts?)",
    r"(oublie|ignore)[a-z]*\s+(les\s+|toutes\s+les\s+)?instructions\s+(pr[ée]c[ée]dentes|ci-dessus)",
    r"reveal\s+(your\s+|the\s+)?(system\s+)?(prompt|instructions)",
    r"print\s+(your\s+|the\s+)?(system\s+)?(prompt|instructions)",
    r"(what\s+(is|are)|show\s+me)\s+(your\s+)?(system\s+)?(prompt|instructions)",
    r"you\s+are\s+now\b",
    r"\bsystem\s+prompt\s*:",
    r"new\s+instructions\s*:",
    r"\bjailbreak\b",
    r"\bDAN\s+mode\b",
))


class GuardrailBlocked(RuntimeError):
    """Entrée/sortie bloquée par un guardrail. Le message nomme le motif, pas le prompt."""


def scan_input(text: str, max_chars: int = MAX_INPUT_CHARS) -> None:
    """Valide une question utilisateur. Lève GuardrailBlocked si vide, trop longue, ou injection."""
    if text is None or not text.strip():
        raise GuardrailBlocked("entrée vide")
    if len(text) > max_chars:
        raise GuardrailBlocked(f"entrée trop longue ({len(text)} > {max_chars} caractères)")
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(text):
            # on ne recopie PAS le texte hostile ; on nomme le motif déclencheur (borné).
            raise GuardrailBlocked(f"pattern d'injection détecté : {pattern.pattern[:60]}")


def scan_output(answer: str, context_used: bool) -> None:
    """Valide une réponse générée. Lève GuardrailBlocked si vide ou non ancrée au contexte."""
    if answer is None or not answer.strip():
        raise GuardrailBlocked("sortie vide")
    if not context_used:
        raise GuardrailBlocked("sortie non ancrée (aucun contexte récupéré)")
