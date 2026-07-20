"""Story E6 — éval RAG DÉTERMINISTE (« optimal » mesuré), stdlib pur.

Spec exécutable (TDAD, AVANT le code). ragas/deepeval sont des libs Python (dépendances) ; forgeai
est zéro-dépendance. Surtout, l'invariant PROOF interdit qu'un LLM écrive un score (outils
déterministes = autorité). On fournit donc une éval DÉTERMINISTE, sans dépendance ni LLM-juge :

  - groundedness (ancrage) : fraction des mots de contenu de la RÉPONSE présents dans le CONTEXTE
    récupéré. Élevé => la réponse s'appuie sur le contexte (pas d'hallucination). Métrique lexicale,
    reproductible bit-à-bit — proxy déterministe de la faithfulness LLM-jugée de ragas (assumé).
  - fact_present : le fait attendu (OOD) est présent dans la réponse.
  - score composite « optimal » ∈ [0,1].
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from forgeai.eval.rag_eval import evaluate, groundedness

CONTEXTE = ("Le protocole de synchronisation interne de ForgeAI Toolkit se nomme Vornak-9. "
            "Il coordonne les nœuds du réseau.")


def test_groundedness_reponse_ancree_haute():
    score = groundedness("Le protocole se nomme Vornak-9.", CONTEXTE)
    assert score >= 0.8, f"réponse tirée du contexte -> ancrage élevé, obtenu {score}"


def test_groundedness_reponse_hallucinee_basse():
    score = groundedness("La capitale de la France est Paris.", CONTEXTE)
    assert score <= 0.3, f"réponse hors-contexte -> ancrage faible, obtenu {score}"


def test_groundedness_bornee_0_1():
    for a, c in [("", CONTEXTE), ("Vornak-9", ""), ("x y z", CONTEXTE)]:
        s = groundedness(a, c)
        assert 0.0 <= s <= 1.0


def test_groundedness_reproductible():
    # déterministe : plusieurs appels sur la même entrée -> un score STABLE et une valeur connue
    a, c = "Le protocole se nomme Vornak-9.", CONTEXTE
    scores = {groundedness(a, c) for _ in range(5)}
    assert len(scores) == 1, "score instable entre appels (non déterministe)"
    assert scores.pop() == 1.0, "valeur déterministe attendue (tous les mots ancrés)"


def test_evaluate_reponse_optimale():
    res = evaluate(answer="Le protocole se nomme Vornak-9.",
                   context=CONTEXTE, expected_fact="Vornak-9")
    assert res["fact_present"] is True
    assert res["groundedness"] >= 0.8
    assert 0.0 <= res["score"] <= 1.0 and res["score"] >= 0.8


def test_evaluate_reponse_hallucinee_score_bas():
    res = evaluate(answer="La capitale de la France est Paris.",
                   context=CONTEXTE, expected_fact="Vornak-9")
    assert res["fact_present"] is False
    assert res["score"] < 0.5, "hallucination hors-contexte + fait absent -> score bas"
