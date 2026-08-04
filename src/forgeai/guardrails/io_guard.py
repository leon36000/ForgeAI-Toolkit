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
from forgeai.eval.rag_eval import groundedness
from forgeai.i18n import t
from typing import NamedTuple
import hashlib
import secrets
import unicodedata
from dataclasses import dataclass

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
    # Catégorie 3 — Ordres d'action (verbe d'ordre + cible)
    # Motif : verbe impératif d'exécution (FR/EN) suivi d'un mot désignant un programme/outil à exécuter.
    r"\b(?:ex[eé]cute|lance|appelle|invoque|run|execute|call|invoke)\s+(?:la\s+commande|le\s+script|le\s+programme|la\s+fonction|la\s+m[ée]thode|l'outil|le\s+binaire|un\s+script|une\s+commande|une\s+fonction|command|script|program|tool|binary|shell\s+command)",
    # Motif : verbe impératif d'exécution ciblant explicitement un interpréteur / shell / outil système.
    r"\b(?:ex[eé]cute|lance|appelle|run|execute|call|invoke)\s+(?:un\s+shell|un\s+bash|un\s+cmd|powershell|bash|sh|zsh|cmd\.exe|terminal|console)\b",
    # Motif : verbe impératif d'exécution ciblant un appel d'outil / appel de fonction via syntaxe typique.
    r"\b(?:appelle|invoque|invoke|call)\s+(?:l'outil|le\s+tool|la\s+function|function|tool|api|endpoint|le\s+module)",

    # Catégorie 3b — Ordres de requête réseau sortante (verbe d'ordre + utilitaire/URL)
    # Motif : verbe impératif suivi d'un utilitaire réseau (curl, wget, fetch).
    r"\b(?:ex[eé]cute|lance|appelle|invoque|utilise|run|execute|call|invoke|use)\s+(?:curl|wget|fetch|httpie|axios|requests?)(?:\s|$|[,;:.\"])",

    # Catégorie 3c — Ordres de divulgation de secret (verbe d'ordre + cible sensible)
    # Motif : verbe impératif de divulgation suivi d'une cible sensible (api key, secret, token, etc.).
    r"\b(?:envoie|r[ée]v[èe]le|affiche|transmets|imprime|donne|retourne|send|output|print|leak|reveal|display|dump|expose|exfiltrate|exfil|return|emit)\s+(?:l[ea]\s+|the\s+|a\s+|an\s+)?(?:\w+\s+){0,2}(?:api[- ]?key|cl[ée]\s+d'?api|secret|jeton|token|mot\s+de\s+passe|password|credentials|identifiants?|variable\s+d'environnement|environment\s+variable|env\s+var|private\s+key|clef\s+priv[ée]e|clef\s+secr[èe]te|auth[- ]?token|bearer|access[- ]?key)",
    # Motif : verbe de divulgation + formulation « le token », « ton secret », etc. (déterminant possessif/démonstratif).
    r"\b(?:envoie|r[ée]v[èe]le|affiche|transmets|donne|retourne|send|output|print|leak|reveal|display|dump|expose|exfiltrate)\s+(?:le\s+token|le\s+secret|le\s+mot\s+de\s+pass|la\s+cl[ée]|les\s+identifiants|ta\s+cl[ée]|ton\s+secret|votre\s+token|the\s+token|the\s+secret|the\s+password|your\s+token|your\s+secret)",
    # Motif : verbe de divulgation + formulation « X dans/envoyer vers une URL » (exfiltration vers l'extérieur).
    r"\b(?:envoie|transmets|exfiltre|envoie|send|post|upload|transmit|exfiltrate|leak)\s+(?:vers|to|sur|on)\s+(?:une\s+url|https?://|mon\s+serveur|my\s+server|un\s+endpoint|an\s+endpoint)",
))


class GuardrailBlocked(RuntimeError):
    """Entrée/sortie bloquée par un guardrail. Le message nomme le motif, pas le prompt."""


def scan_input(text: str, max_chars: int = MAX_INPUT_CHARS) -> None:
    """Valide une question utilisateur. Lève GuardrailBlocked si vide, trop longue, ou injection."""
    if text is None or not text.strip():
        raise GuardrailBlocked(t("guardrails.io_guard.scan_input.entree_vide"))
    if len(text) > max_chars:
        raise GuardrailBlocked(t("guardrails.io_guard.scan_input.entree_trop_longue",
                                  longueur=len(text), max_chars=max_chars))
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(text):
            # on ne recopie PAS le texte hostile ; on nomme le motif déclencheur (borné).
            raise GuardrailBlocked(t("guardrails.io_guard.scan_input.pattern_detecte",
                                      pattern=pattern.pattern[:60]))


def scan_output(answer: str, context_used: bool) -> None:
    """Valide une réponse générée. Lève GuardrailBlocked si vide ou non ancrée au contexte."""
    if answer is None or not answer.strip():
        raise GuardrailBlocked(t("guardrails.io_guard.scan_output.sortie_vide"))
    if not context_used:
        raise GuardrailBlocked(t("guardrails.io_guard.scan_output.sortie_non_ancree"))


@dataclass(frozen=True)
class ChunkReport:
    """Rapport d'analyse d'un chunk : spans, motifs déclencheurs, et indicateur de détection post-normalisation."""
    directive_spans: tuple[tuple[int, int], ...]
    motifs: tuple[str, ...]
    detecte_apres_normalisation: bool


def _tronquer_motif(motif: str, max_len: int = 60) -> str:
    """Tronque un motif à la longueur maximale autorisée pour le journal."""
    return motif[:max_len]


def _normaliser_avec_table(texte: str) -> tuple[str, list[int]]:
    """Construit une copie NFKC du texte, sans caractères Cf, et conserve la table originale -> normalisé."""
    caracteres_norm: list[str] = []
    table_indices: list[int] = []
    for index_orig, caractere in enumerate(texte):
        normalise = unicodedata.normalize("NFKC", caractere)
        for c in normalise:
            if unicodedata.category(c) == "Cf":
                continue
            caracteres_norm.append(c)
            table_indices.append(index_orig)
    return "".join(caracteres_norm), table_indices


def make_delimiter() -> str:
    """Génère une balise de délimitation imprévisible par requête.
    Un délimiteur fixe peut être reproduit dans un document empoisonné et ainsi
    annuler la séparation entre contexte et instruction ; un nonce aléatoire
    ne peut pas être anticipé par l'attaquant.
    """
    return f"<<<DONNEES-{secrets.token_hex(8)}>>>"


def scan_chunk(text: str) -> ChunkReport:
    """Détecte les directives d'injection dans un chunk, y compris après normalisation NFKC."""
    spans: set[tuple[int, int]] = set()
    motifs: set[str] = set()
    matched_original: set[int] = set()
    matched_normalized: set[int] = set()

    try:
        # Passage sur le texte original
        for idx, pattern in enumerate(_INJECTION_PATTERNS):
            for match in pattern.finditer(text):
                spans.add(match.span())
                motifs.add(_tronquer_motif(pattern.pattern))
                matched_original.add(idx)

        # Passage sur la copie normalisée, mappée vers les offsets originaux
        normalized, table = _normaliser_avec_table(text)
        if normalized:
            for idx, pattern in enumerate(_INJECTION_PATTERNS):
                for match in pattern.finditer(normalized):
                    a, b = match.span()
                    if b <= a:
                        continue
                    orig_start = table[a]
                    orig_end = table[b - 1] + 1
                    spans.add((orig_start, orig_end))
                    motifs.add(_tronquer_motif(pattern.pattern))
                    matched_normalized.add(idx)
    except Exception:
        # Garantie : aucun chunk ne doit faire échouer le pipeline
        return ChunkReport((), (), False)

    detecte_apres = bool(matched_normalized - matched_original)

    return ChunkReport(
        directive_spans=tuple(sorted(spans)),
        motifs=tuple(sorted(motifs)),
        detecte_apres_normalisation=detecte_apres,
    )


def neutralize_chunk(text: str, report: ChunkReport) -> str:
    """Neutralise les segments suspects d'un chunk tout en préservant le reste du signal utile."""
    if not report.directive_spans:
        return text

    # Fusion des spans qui se chevauchent ou se touchent
    sorted_spans = sorted(report.directive_spans)
    merged: list[list[int]] = []
    for start, end in sorted_spans:
        if not merged:
            merged.append([start, end])
        else:
            last_start, last_end = merged[-1]
            if start <= last_end:
                merged[-1][1] = max(last_end, end)
            else:
                merged.append([start, end])

    # Remplacement du dernier au premier pour garder les offsets valides
    result = text
    replacement = "[SEGMENT NEUTRALISÉ : directive]"
    for start, end in reversed(merged):
        result = result[:start] + replacement + result[end:]

    return result


def scan_assembled(context: str, delimiter: str) -> None:
    """Vérifie l'assemblé complet envoyé au LLM.

    Une directive peut être morcelée sur plusieurs chunks et échapper aux scans
    par chunk ; l'assemblé est la chaîne exacte transmise au modèle, donc le
    dernier endroit où bloquer une injection avant génération.
    """
    if delimiter in context:
        raise GuardrailBlocked(
            t("guardrails.io_guard.scan_assembled.forge_balise")
        )

    report = scan_chunk(context)
    if report.directive_spans:
        motifs = ", ".join(report.motifs)
        raise GuardrailBlocked(
            t("guardrails.io_guard.scan_assembled.directive_detectee", motifs=motifs)
        )


# Seuils de couverture et d'entailment — voir ADR-RAG-004A §3.2 et §3.3.2.
# I1 « pas de preuve, pas d'ancrage » et I3 « fail-closed » exigent des valeurs
# conservatives : un span n'est soutenu qu'au-dessus d'un score élevé, et la
# majorité qualifiée des spans doit l'être pour déclarer l'ensemble grounded.
SEUIL_COUVERTURE_S = 0.8
SEUIL_ENTAILMENT_T = 0.6


class Passage(NamedTuple):
    """Unité de contexte minimale passée au vérificateur d'ancrage.

    L'identifiant dérive du TEXTE seul (cf. `depuis_texte`), jamais de la
    source : deux sources distinctes portant le même passage partagent le même
    `passage_id`, ce qui garantit la stabilité inter-appels et inter-sources.
    """

    passage_id: str
    source: str
    text: str

    @staticmethod
    def depuis_texte(text: str, source: str) -> "Passage":
        """Construit un Passage en dérivant `passage_id` du texte normalisé.

        Normalisation : mise en minuscules, réduction des espaces multiples à
        un seul, suppression des espaces de bord. Identifiant = préfixe SHA-256
        hexadécimal de 16 caractères. Déterministe par construction.
        """
        texte_normalise = re.sub(r"\s+", " ", text.lower()).strip()
        passage_id = hashlib.sha256(texte_normalise.encode("utf-8")).hexdigest()[:16]
        return Passage(passage_id=passage_id, source=source, text=text)


class Citation(NamedTuple):
    """Résultat de la mise en correspondance d'un span avec son meilleur passage."""

    span: str
    passage_id: str
    supported: bool
    score: float
    reason: str = ""


@dataclass(frozen=True)
class GroundingVerdict:
    """Verdict d'ancrage : état, couverture, citations, motif.

    `state` ∈ {"grounded", "ungrounded", "unknown"}. `unknown` est un état de
    premier rang (contexte vide ou réponse non segmentable) et n'est jamais
    assimilé à `grounded` : un ancrage non prouvable n'est pas un ancrage
    (invariant I1).
    """

    state: str
    coverage: float
    citations: tuple[Citation, ...]
    reason: str = ""


_SEPARATEURS_SPANS = re.compile(r"[.!?;\n]")


def decouper_en_spans(answer: str) -> list[str]:
    """Découpe déterministe d'une réponse en phrases/propositions.

    Unité = phrase ou proposition (ADR §3.1). Segmentation sur les
    délimiteurs `.`, `!`, `?`, `;` et sauts de ligne ; segments vides ou
    réduits aux espaces éliminés ; ordre d'origine conservé.
    """
    segments = _SEPARATEURS_SPANS.split(answer)
    return [segment.strip() for segment in segments if segment.strip()]


def verify_grounding(answer: str, passages: list[Passage]) -> GroundingVerdict:
    """Calcule le verdict d'ancrage d'une réponse contre un ensemble de passages.

    POURQUOI : attester un soutien réel (chaque span couvert par un passage)
    plutôt que la simple présence d'un retrieval — c'est précisément le défaut
    que corrige l'ADR-RAG-004A, le booléen pré-cuit de l'appelant étant
    remplacé par un calcul local et reproductible.

    Invariants respectés :
      - I1 « pas de preuve, pas d'ancrage » : sans contexte ou sans span
        segmentable, l'état est `unknown`, jamais `grounded`.
      - I3 « fail-closed » : en cas de couverture insuffisante, l'état est
        `ungrounded`, l'appelant (pipeline RAG) devant refuser la réponse.

    Pureté : aucune E/S, aucun réseau, aucun appel LLM, aucun aléa. À entrées
    égales, verdict strictement identique, ordre des citations inclus
    (parcours des spans dans l'ordre du découpage ; à score égal entre
    passages, le premier de la liste est retenu, jamais `max()` sur ensemble
    non ordonné).
    """
    spans = decouper_en_spans(answer)

    if not passages:
        return GroundingVerdict(
            state="unknown",
            coverage=0.0,
            citations=(),
            reason="contexte vide",
        )
    if not spans:
        return GroundingVerdict(
            state="unknown",
            coverage=0.0,
            citations=(),
            reason="réponse non segmentable",
        )

    citations: list[Citation] = []
    nb_supportes = 0

    for span in spans:
        meilleur_score = -1.0
        meilleur_passage: Passage | None = None
        for passage in passages:
            score = groundedness(span, passage.text)
            if score > meilleur_score:
                meilleur_score = score
                meilleur_passage = passage

        # Invariant de déterminisme : à score strictement égal, le premier
        # passage rencontré reste retenu (pas de remplacement par égalité).
        supported = meilleur_score >= SEUIL_ENTAILMENT_T
        if supported:
            nb_supportes += 1
            citation = Citation(
                span=span,
                passage_id=meilleur_passage.passage_id,
                supported=True,
                score=meilleur_score,
            )
        else:
            citation = Citation(
                span=span,
                passage_id=meilleur_passage.passage_id,
                supported=False,
                score=meilleur_score,
                reason="entailment insuffisant",
            )
        citations.append(citation)

    coverage = round(nb_supportes / len(spans), 4)

    if coverage >= SEUIL_COUVERTURE_S:
        return GroundingVerdict(
            state="grounded",
            coverage=coverage,
            citations=tuple(citations),
            reason="",
        )

    return GroundingVerdict(
        state="ungrounded",
        coverage=coverage,
        citations=tuple(citations),
        reason=(
            f"couverture {coverage:.4f} inférieure au seuil "
            f"{SEUIL_COUVERTURE_S:.2f}"
        ),
    )
