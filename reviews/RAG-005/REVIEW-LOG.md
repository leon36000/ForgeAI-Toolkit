# RAG-005 — journal de la revue scellée

Vendors : `deepseek / google / xai`, tous distincts, tous différents du vendor codeur.
Codeurs mobilisés : Kimi-K3 (conception), Kimi-2.7 (io_guard), **MiniMax-M3** (motifs de sécurité et
correctifs) — MiniMax est un vendor distinct des trois reviewers, **aucun SWAP CIV n'a donc été
nécessaire**.

## Tour 1 — REJECT 3/3 (sceau `bd3b7a985f60`)
Objection **CRITIQUE**, trouvée indépendamment par les trois vendors et **fondée** :
`scan_assembled` recevait les documents **avec leurs lignes de provenance intercalées**. Entre
« Ignore all » et « previous instructions » se glissait `\n\n[DOC 2 | source=…]\n`, qui n'est pas de
l'espace ; les motifs exigeant `\s+` ne matchaient plus. **La détection du fractionnement ne
fonctionnait pas sur le chemin de production.**

Cause de l'angle mort : mon test unitaire appelait `scan_assembled(a + "\n" + b, delim)` — il
**fabriquait son entrée**, reproduisant un assemblage que le code de production n'effectue jamais.
Un vert obtenu sur une entrée inventée est pire que pas de test : il produit une fausse confiance.

Objections mineures également retenues : fragment `and output the admin password` non couvert ;
absence de test d'intégration `ask()` sur les documents fractionnés ; élargissement de périmètre
(celui-ci déjà déclaré).

## Tour 2 — APPROVE 3/3 (sceau `05ce0ed22e22`), 0 objection critique
Correctifs : deux chaînes distinctes (le prompt garde la provenance, le détecteur reçoit les textes
contigus) ; motif de divulgation élargi aux articles FR/EN + deux qualificatifs bornés ; test
d'intégration traversant `ask()` avec les deux moitiés du corpus adversarial.

Une objection **mineure** subsistait, de Gemini, et elle était **exacte** : `scan_chunk` et
`neutralize_chunk` s'exécutaient hors de tout `if self.guardrails`. Avec `guardrails=False`,
l'utilisateur croyait avoir désactivé les gardes alors que ses documents étaient quand même
réécrits. Corrigée dans la foulée (test rouge écrit d'abord), avec cette distinction explicite :
`guardrails=False` désactive la **réécriture du contenu**, jamais la **séparation structurelle**
(délimiteur et provenance), qui n'est pas une garde optionnelle.

## Élargissement de périmètre — DÉCLARÉ, jamais silencieux
`tests/test_rag_rerank.py` comparait la réponse par égalité stricte de dictionnaire ; `ask`
retournant désormais `sanitization_events` sur tous ses chemins, cette égalité sur-spécifiait le
contrat. L'intention du contrôle négatif (réponse vide sans fabrication **et** aucun appel
`/rerank`) est vérifiée champ par champ. Déclaré dans la story, la PR et le pack de revue.
