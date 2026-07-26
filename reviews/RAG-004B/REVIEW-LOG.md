# RAG-004B — journal de la revue scellée

**APPROVE 3/3 au premier tour, ZÉRO objection** à tous les niveaux de sévérité.
Vendors distincts `deepseek / google / xai`, sceau commun `fe2797b0166a`.
Codeurs : MiniMax-M3 (vérificateur d'ancrage et méthode `ask`) — vendor distinct des trois
reviewers, **aucun SWAP CIV nécessaire**. Le vendor codeur n'a évidemment pas relu son propre code.

## Pourquoi un tour a suffi, contrairement à RAG-005
Le contrat n'a pas été improvisé : **ADR-RAG-004A** (livré en amont dans la même série) fixait déjà
les états, les seuils S=0,8 et T=0,6, les invariants I1→I5 et la table d'oracles. Les tests ont été
dérivés directement de cette table, chacun **recalculant** l'état attendu depuis sa fixture au lieu
d'asséner une chaîne — c'est la règle d'oracle de l'ADR §4.

Surtout, la leçon de RAG-005 a été appliquée **d'emblée** : trois tests d'intégration traversent
`ask()`, le point d'entrée public réel, et non une entrée reconstituée à la main. C'est précisément
l'angle mort qui avait valu un REJECT 3/3 au package précédent.

## Deux défauts trouvés par ces tests pendant l'implémentation
1. **Régression du crew** : en réécrivant `ask`, il a perdu le `if self.guardrails` sur la boucle de
   neutralisation — correctif validé en RAG-005 sur objection de la revue. Restauré, commenté pour
   interdire la réintroduction.
2. **Fixtures irréalistes** : plusieurs tests historiques faisaient répondre le LLM factice sans
   aucun lien lexical avec leur contexte ; le vérificateur les refuse à juste titre. Elles ont été
   rendues réalistes **plutôt que d'abaisser les seuils** — le contrat n'a pas été assoupli pour
   faire passer des tests.

## Élargissement de périmètre — DÉCLARÉ
`tests/test_rag_rerank.py` (hors `allowed_paths`) assertait `context_used`, champ retiré par l'ADR
§8. Assertions migrées vers `grounding`, fixture rendue ancrée. Déclaré dans la story, la PR et ce
journal — jamais en silence.
