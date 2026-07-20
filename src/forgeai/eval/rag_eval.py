"""Évaluation DÉTERMINISTE du RAG (story E6) — stdlib pur, « optimal » mesuré.

ragas/deepeval sont des libs Python (dépendances) ; forgeai est zéro-dépendance. Surtout,
l'invariant PROOF interdit qu'un LLM écrive un score (outils déterministes = autorité). On mesure
donc la qualité par des métriques LEXICALES reproductibles bit-à-bit, sans LLM-juge :

  - `groundedness(answer, context)` : fraction des mots de contenu de la réponse présents dans le
    contexte récupéré (ancrage — proxy déterministe de la faithfulness LLM-jugée de ragas, assumé) ;
  - `evaluate(...)` : agrège groundedness + présence du fait attendu -> score composite ∈ [0,1].

Aucune dépendance (str/re de la stdlib). Les mots-outils (stopwords FR+EN) sont ignorés pour ne
compter que le contenu porteur de sens.
"""
from __future__ import annotations

import re

# Mots-outils FR + EN : ignorés pour ne mesurer que les mots de CONTENU (noms, verbes, entités).
_STOPWORDS = frozenset("""
le la les un une des du de d au aux et ou où mais donc or ni car ce cet cette ces se sa son ses
leur leurs à a en dans sur sous pour par avec sans que qui quoi dont est sont être il elle on nous
vous ils elles ne pas plus se s l n y
the a an of to in on for and or but is are was were be been it its this that these those with as at
by from he she they we you i not no
""".split())

_WORD = re.compile(r"[a-zà-ÿ0-9][a-zà-ÿ0-9\-]*", re.IGNORECASE)


def _content_words(text: str) -> list[str]:
    """Mots de contenu normalisés (minuscule, hors stopwords) d'un texte. Forme explicite."""
    words: list[str] = []
    if not text:
        return words
    for match in _WORD.finditer(text):
        word = match.group(0).lower()
        if word not in _STOPWORDS:
            words.append(word)
    return words


def groundedness(answer: str, context: str) -> float:
    """Fraction ∈ [0,1] des mots de contenu de `answer` présents dans `context`.

    1.0 = chaque mot porteur de la réponse figure dans le contexte (réponse ancrée) ;
    proche de 0 = la réponse invente hors-contexte. Réponse vide -> 0.0 (rien d'ancré à créditer).
    """
    answer_words = _content_words(answer)
    if not answer_words:
        return 0.0
    context_words = set(_content_words(context))
    matched = 0
    for word in answer_words:
        if word in context_words:
            matched += 1
    return matched / len(answer_words)


def evaluate(answer: str, context: str, expected_fact: str) -> dict:
    """Score composite déterministe du RAG : ancrage + présence du fait attendu.

    Retourne {groundedness, fact_present, score} avec score ∈ [0,1] = moyenne pondérée
    (ancrage 0.6, fait présent 0.4). Aucun LLM, aucun aléa : rejouable à l'identique.
    """
    g = groundedness(answer, context)
    answer_text = answer.lower() if answer else ""
    fact = expected_fact.lower() if expected_fact else ""
    fact_present = bool(fact) and fact in answer_text
    score = round(0.6 * g + 0.4 * (1.0 if fact_present else 0.0), 4)
    return {"groundedness": round(g, 4), "fact_present": fact_present, "score": score}
