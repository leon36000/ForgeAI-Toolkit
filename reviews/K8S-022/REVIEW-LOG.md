# K8S-022 — journal de la revue scellée

**Verdict final : APPROVE 3/3**, vendors distincts `deepseek / google / xai`, 0 objection critique.
Sceau commun `prompt_sha256 = 4ef920f60166…` (prompt neutre identique pour les trois).
Vendor du codeur = Moonshot (Kimi-2.7 pour l'implémentation, Kimi-K3 pour la conception) : **exclu**
du trio de revue, aucune auto-relecture.

## Réassignations de route (journalisées, conformes à la règle du pool)
1. **Qwen3.6-40B — ROUTE INSTABLE** (tour 1) : aucun JSON dans la réponse. Réassigné.
2. **MiMo-V2.5-Pro — ROUTE INSTABLE** (tour 2) : JSON malformé (`Expecting ',' delimiter`). Réassigné.
3. **Grok-4.5 (xAI)** retenu comme troisième vendor : distinct de DeepSeek, de Google et du codeur.
   Composer (même vendor xAI) n'a donc pas été apparié, conformément à la règle.

## Objection reçue et traitée
**DeepSeek-V4-Pro, tour 1, sévérité MINEURE** (sceau `8aeb65d3027d`) : *« Pour les services GPU,
readOnlyRootFilesystem est désactivé sans justification documentée dans la story ni preuve de
nécessité… ce qui pourrait affaiblir le durcissement sans mesure de validation. »*

**Objection RECEVABLE — acceptée et corrigée** (commit dédié) : la justification manquait
effectivement. Ajoutée au docstring de `_security_block`, au commentaire émis dans le manifeste rendu
et à la story : les chemins d'écriture d'un moteur GPU (caches de modèles, cache de compilation du
runtime vendor) dépendent de l'image ET de l'hôte et n'ont pas pu être mesurés faute de matériel GPU
autorisé (`LAB-033*`, `BLOCKED_LAB`). La règle du package — « exceptions spécifiques et TESTÉES » —
interdit d'activer la racine en lecture seule à l'aveugle : cela casserait des déploiements réels.
`readOnlyRootFilesystem` n'est pas une exigence PSS restricted ; le pod GPU ne déroge à `restricted`
que par son identité root et son volume `hostPath`. Comportement inchangé, seule la preuve manquait.

Le tour 2 a été relancé sur le pack RECONSTRUIT après correction : les trois vendors ont donc jugé
l'artefact final, et non un diff supersédé. 0 objection au tour 2.
