"""Redaction centrale des secrets (ERR-041A) — erreurs, logs, états persistés.

Module FEUILLE : stdlib UNIQUEMENT, AUCUN import ``forgeai.*`` (vérifié par test
AST). Source de vérité unique pour empêcher toute fuite de secret dans un message
d'erreur, un log ou un état persisté.

Contrat (décision architecte, issue #237) :
- déterministe et sans état (fonctions pures, constantes gelées, ordre fixe) ;
- idempotent : ``redact(redact(x)) == redact(x)`` (le marqueur ne contient aucune
  forme secrète, il est point fixe des motifs) ;
- ne lève JAMAIS (une entrée bizarre ne doit pas casser le rendu d'une erreur) ;
- ne tronque JAMAIS (un fragment de valeur suffit à corréler) : la valeur reconnue
  est remplacée INTÉGRALEMENT par le marqueur ;
- frontière = la LISTE des tokens de clés et des motifs de valeurs ci-dessous ;
  en cas de doute on SUR-RÉDIGE (faux positif acceptable : le coût est du
  diagnostic, jamais de la confidentialité).

Anti-ReDoS : tous les motifs sont LINÉAIRES (classes de caractères à quantificateur
simple ; ni backreference, ni lookaround quantifié, ni alternance recouvrante
quantifiée).
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Final

REDACTED: Final[str] = "«REDACTED»"
"""Marqueur stable, greppable, diffable. Remplace INTÉGRALEMENT la valeur."""

SENSITIVE_KEY_TOKENS: Final[frozenset[str]] = frozenset(
    {
        "key",
        "apikey",
        "secret",
        "token",
        "password",
        "passphrase",
        "authorization",
        "bearer",
        "credentials",
    }
)
"""Jetons de NOM de clé sensibles. Une clé est sensible ssi sa forme normalisée
(minuscules, découpée sur tout caractère non alphanumérique) INTERSECTE cet
ensemble — jamais un test de sous-chaîne (« monkey » ≠ « key »)."""

MAX_DEPTH: Final[int] = 32
"""Borne de récursion de ``redact_mapping`` (structures cycliques/pathologiques)."""

# Séparateur de normalisation des noms de clés : tout ce qui n'est pas [a-z0-9].
_NORM_SPLIT: Final = re.compile(r"[^a-z0-9]+")

# --- Motifs de VALEURS secrètes, appliqués dans l'ordre (déterminisme) ---------
# M1 — schème d'autorisation : « Bearer » / « Authorization » + séparateur + valeur
#      non blanche (hors guillemets, « & », « ; »). Le label et le séparateur sont
#      CONSERVÉS ; seule la valeur est remplacée.
_M1_AUTH: Final = re.compile(
    r"(?i)\b(bearer|authorization)([ \t]*[:=]?[ \t]+)([^\s\"'&;]+)"
)
# M2 — « nom…(key|token|secret|password|passphrase|credentials)… » + « = »/« : » +
#      valeur (guillemets optionnels). Nom et séparateur (et guillemets) conservés,
#      valeur INTÉGRALEMENT remplacée. Le nom est une suite de [A-Za-z0-9_] contenant
#      l'un des jetons sensibles (bornée à gauche par un non-mot).
_M2_KV: Final = re.compile(
    r"(?i)(?<![A-Za-z0-9_])"
    r"([A-Za-z0-9_]*(?:key|token|secret|password|passphrase|credentials)[A-Za-z0-9_]*)"
    r"([ \t]*[:=][ \t]*)"
    r"(\"?)([^\s\"'&;]+)(\"?)"
)
# M3 — clé préfixée « sk- » + ≥8 caractères [A-Za-z0-9_-].
_M3_SK: Final = re.compile(r"(?i)\bsk-[A-Za-z0-9_-]{8,}")
# M4 — jeton opaque long : ≥32 caractères [A-Za-z0-9] bornés (superset de l'hex ;
#      sur-rédaction assumée d'un jeton opaque non préfixé, §3(d)).
_M4_LONG: Final = re.compile(r"(?<![A-Za-z0-9])[A-Za-z0-9]{32,}(?![A-Za-z0-9])")


def _sub_m1(m: "re.Match[str]") -> str:
    # Conserve « Bearer »/« Authorization » + séparateur ; rédige la valeur.
    return f"{m.group(1)}{m.group(2)}{REDACTED}"


def _sub_m2(m: "re.Match[str]") -> str:
    # Conserve nom + séparateur + guillemets ; rédige la valeur.
    return f"{m.group(1)}{m.group(2)}{m.group(3)}{REDACTED}{m.group(5)}"


def _sub_full(m: "re.Match[str]") -> str:
    # M3/M4 : la correspondance entière EST le secret → remplacement total.
    return REDACTED


# Table (motif, substitution) appliquée dans l'ordre par ``redact_text``. C'est la
# SOURCE unique de l'ordre ET de l'application : retirer une entrée retire réellement
# la protection correspondante (mutation détectable, pas de motif « décoratif »).
_REDACTION_RULES: Final = (
    (_M1_AUTH, _sub_m1),
    (_M2_KV, _sub_m2),
    (_M3_SK, _sub_full),
    (_M4_LONG, _sub_full),
)

SECRET_VALUE_PATTERNS: Final[tuple[re.Pattern[str], ...]] = tuple(
    pattern for pattern, _ in _REDACTION_RULES
)
"""Motifs de valeurs secrètes, dans l'ordre d'application (dérivé de la table)."""


def is_sensitive_key(key: object) -> bool:
    """True ssi le NOM de clé normalisé intersecte ``SENSITIVE_KEY_TOKENS``.

    Découpe sur tout caractère non alphanumérique (jamais de test de sous-chaîne) :
    ``FORGEAI_API_TOKEN`` → {forgeai, api, token} → True ; ``monkey`` → {monkey} →
    False. Entrée non-``str`` → False. Ne lève jamais.
    """
    if not isinstance(key, str):
        return False
    parts = {p for p in _NORM_SPLIT.split(key.lower()) if p}
    return not parts.isdisjoint(SENSITIVE_KEY_TOKENS)


def redact_text(s: str) -> str:
    """Rédige les secrets d'une chaîne. Applique M1..M4 dans l'ordre.

    Entrée non-``str`` : coercion gardée (``str()`` sous garde ; repli = nom de
    classe). Ne lève JAMAIS, ne tronque JAMAIS.
    """
    if not isinstance(s, str):
        try:
            s = str(s)
        except Exception:
            return f"<{type(s).__name__}>"
    # Application ordonnée de la table (source unique de l'ordre et de l'action).
    for pattern, replacement in _REDACTION_RULES:
        s = pattern.sub(replacement, s)
    return s


def redact_mapping(d: Mapping, _depth: int = 0) -> dict:
    """Rédige récursivement un mapping. NOUVEAU dict (entrée jamais mutée), structure
    préservée. Clé sensible → marqueur (quel que soit le type de valeur) ; valeur
    ``Mapping`` → récursion ; ``list``/``tuple`` → liste d'items rédigés ; ``str`` →
    ``redact_text`` (défense en profondeur) ; autre → inchangé. Au-delà de
    ``MAX_DEPTH`` : sous-arbre → marqueur (gère les cycles sans lever).
    """
    if _depth >= MAX_DEPTH:
        return REDACTED  # type: ignore[return-value]

    def _val(v: object) -> object:
        if isinstance(v, Mapping):
            return redact_mapping(v, _depth + 1)
        if isinstance(v, (list, tuple)):
            return [_val(x) for x in v]
        if isinstance(v, str):
            return redact_text(v)
        return v

    out: dict = {}
    try:
        items = list(d.items())
    except Exception:
        return out
    for k, v in items:
        if is_sensitive_key(k):
            out[k] = REDACTED
        else:
            out[k] = _val(v)
    return out


def redact_exception(exc: BaseException) -> str:
    """« {type}: {message rédigé} ». Si ``str(exc)`` lève → le seul nom de classe.
    Ne lève jamais, y compris sur exception exotique."""
    name = type(exc).__name__
    try:
        message = str(exc)
    except Exception:
        return name
    return f"{name}: {redact_text(message)}"
