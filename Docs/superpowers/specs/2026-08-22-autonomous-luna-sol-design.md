# Mode autonome Luna/Sol — design validé

## Décision

L’issue #603 autorise un mode d’exécution où GPT-5.6 Luna conduit et écrit les changements, avec un plafond strict de deux lanes d’écriture simultanées. GPT-5.6 Sol intervient comme reviewer frais, aveugle et en lecture seule pour les livraisons soumises à ce mode. Cette séparation de modèle, de contexte et de rôle ne constitue pas une attestation d’indépendance multi-vendor.

## Contrat observable

Le dépôt conserve son mode historique multi-vendor par défaut. Un nouveau mode explicite `sol_blind` est accepté uniquement lorsqu’un reçu contient une preuve fraîche et liée au changement examiné : base commit, head commit et head tree examinés, empreinte canonique du diff, empreinte du prompt, provider ID Sol exact `GPT-5.6-Sol`, contexte frais, revue aveugle, lecture seule, verdict `APPROVE` et liste d’objections bloquantes vide. La fenêtre de fraîcheur est plafonnée à 24 heures. Le codeur ne peut pas être Sol.

Le reçu conserve `story`, l’identifiant immuable employé pour reconstruire le
prompt, séparément de `dossier`, le répertoire des artefacts. Les deux valeurs
ne sont pas interchangeables; le dossier déclaré doit correspondre au répertoire
effectivement chargé par le vérificateur.

Le reçu reste un claim que le gate réfute contre l’état Git courant. Le digest canonique continue d’exclure les artefacts de revue et les vues générées afin d’éviter l’auto-référence; la base et le digest lient donc la preuve au diff qui sera fusionné. Le head commit et le head tree examinés sont conservés pour la traçabilité, sans comparaison circulaire avec le commit qui ajoute le reçu.

## Composants

- `governance/autonomy-policy.json` porte la décision, les identités, le plafond `2`, les états terminaux et les limites T3.
- `manifests/roles.yaml` rend Luna writer et Sol reviewer résolubles, sans retirer les identités historiques nécessaires aux anciens reçus.
- `scripts/revue.py` ajoute `tally_sol_blind`, la génération de prompt liée au diff exact et le dispatch de `verifier_recu` selon `mode`; `tally()` reste inchangé pour les reçus historiques.
- `scripts/reviews_gate.py` choisit le tally correspondant au mode déclaré et applique la même vérification fraîche pour les PR courantes.
- Les documents d’autorité, de méthode et de reprise décrivent le merge proportionnel, la recherche autonome, la reprise depuis GitHub et les deux verdicts terminaux `DONE_WITH_EVIDENCE` / `BLOCKED_WITH_REASON`.

## Sécurité et non-objectifs

Aucun workflow GitHub ne s’auto-modifie, ne force une branche, ne décode un payload embarqué ou ne reçoit `contents: write`. Cette livraison n’installe pas de daemon, ne promet pas une exécution hors session et ne modifie pas les règles externes de protection du dépôt. Les frontières T3 restent celles de Nathan.

## Preuves exigées

Les tests couvrent le chemin positif, le contexte historique/non frais, l’auto-review, le diff modifié, le plafond de deux writers et la compatibilité du tally multi-vendor. Les gates authority, state-current, path-classification, registres, no-stub, suite Python et `reviews-sealed` doivent être verts. La preuve finale `sol_blind` doit examiner le diff exact de la PR dans un contexte neuf avant le merge.
