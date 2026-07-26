# RAG-004B — Contrat d'ancrage appliqué (FAI-U-004)

## Cause racine
`HardenedRagClient.ask` **affirmait** l'ancrage au lieu de le mesurer :

```python
scan_output(answer, context_used=True)   # booléen codé en dur
...
"context_used": True,
```

La promesse « réponse ancrée » attestait donc la **présence d'un retrieval**, jamais un **soutien
réel**. Reproduit : contexte « Vornak-9 possede deux lunes. », réponse « La capitale de la France
est Paris. » → `context_used: True`, `sources: ['faq.md']`, aucun blocage.

## Changement — implémentation fidèle d'ADR-RAG-004A
L'ADR (livré en RAG-004A) prescrit le contrat ; ce package l'implémente **sans le réinventer**.

| Élément | Mise en œuvre |
|---|---|
| `Passage` | `passage_id = sha256(texte normalisé)[:16]` — dérive du **texte seul**, jamais de la source |
| `verify_grounding` | **pur** : aucune E/S, aucun LLM, déterministe (invariant I4) |
| Découpage | spans = propositions, segmentation déterministe documentée |
| Entailment | recouvrement lexical via `rag_eval.groundedness`, seuil T = 0,6 (§3.3.2) |
| Couverture | spans supportés / spans totaux, seuil S = 0,8 (§3.2) |
| États | `grounded` / `ungrounded` / `unknown` — ce dernier de **premier rang**, jamais assimilé à `grounded` (I3 fail-closed) |
| Liste close | citations restreintes aux passages réellement injectés (I2) |
| Sortie | `context_used` **retiré**, remplacé par `grounding` + `coverage` + `citations` (§8) |

Comportement vérifié :

| scénario | grounding | couverture | réponse |
|---|---|---|---|
| réponse soutenue | `grounded` | 1.0 | exposée, sources présentes |
| réponse hors-sujet (FAI-U-004) | `ungrounded` | 0.0 | **vidée**, aucune fabrication |
| contexte vide | `unknown` | — | **vidée** |

## Régression du crew, attrapée par les tests
En réécrivant `ask`, le crew a **perdu le `if self.guardrails`** sur la boucle de neutralisation —
le correctif validé en RAG-005 sur objection de la revue scellée. Mon test de non-régression l'a
signalé immédiatement ; le gating a été restauré, avec un commentaire qui interdit de le
réintroduire.

## Fixtures rendues réalistes plutôt que contrat affaibli
Plusieurs tests historiques faisaient répondre le LLM factice **sans aucun lien lexical** avec leur
contexte. Le nouveau vérificateur les refuse — **à juste titre**. Ces fixtures ont donc été rendues
réalistes (une réponse RAG ancrée reprend le contenu de son contexte), au lieu d'abaisser les
seuils : le contrat n'a pas été assoupli pour faire passer des tests.

## Élargissement de périmètre — DÉCLARÉ
`tests/test_rag_rerank.py` (hors `allowed_paths`) assertait `context_used`, champ retiré par l'ADR.
Assertions migrées vers `grounding` et fixture rendue ancrée. Signalé ici, dans la PR et le pack.

## Limites
L'entailment est **lexical**, borne inférieure assumée par l'ADR (§6) : il peut produire des faux
`ungrounded` sur des paraphrases lointaines — des **refus sûrs** — mais il borne les faux
`grounded`. Un vérificateur NLI pourra être substitué derrière la même interface si la contrainte
« zéro dépendance » est relâchée.

## Rollback
`git revert` → retour au booléen codé en dur (défaut FAI-U-004 connu) ; baseline verte.
