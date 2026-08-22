# Mode autonome Luna/Sol — design validé

## Décision

L’issue #603 autorise un mode d’exécution où GPT-5.6 Luna conduit et écrit les changements, avec un plafond strict de deux lanes d’écriture simultanées. GPT-5.6 Sol intervient comme reviewer frais, aveugle et en lecture seule pour les livraisons soumises à ce mode. Cette séparation de modèle, de contexte et de rôle ne constitue pas une attestation d’indépendance multi-vendor.

## Contrat observable

Le dépôt conserve la compatibilité de ses reçus historiques multi-vendor. Pour
une PR courante, la politique active exige le mode `sol_blind`, accepté
uniquement lorsqu’un reçu contient une preuve fraîche et liée au changement
examiné : base commit, head commit et head tree examinés, empreinte canonique du
diff, empreinte du prompt et `template_sha256` recopiée dans le receipt, provider ID Sol exact `GPT-5.6-Sol`, contexte frais,
revue aveugle, lecture seule, verdict `APPROVE` et liste d’objections
bloquantes vide. La fenêtre de fraîcheur est plafonnée à 24 heures. Le codeur
ne peut pas être Sol.

Le reçu conserve `story`, qui doit être exactement
`stories/ORCH-LUNA-SOL-603.md`, l’identifiant immuable employé pour reconstruire
le prompt, séparément de `dossier`, le répertoire des artefacts. Les deux
valeurs ne sont pas interchangeables; le dossier déclaré doit correspondre au
répertoire effectivement chargé par le vérificateur. Une preuve fraîche doit
également résoudre son codeur vers l'identité active `luna_writer` et lier le
`template_sha256` du template versionné.
Cette identité est validée comme l'unique entrée canonique du roster: modèle
`GPT-5.6 Luna`, vendor `openai`, provider ID `GPT-5.6-Luna-Writer` et statut
`actif`; une entrée absente, dupliquée ou modifiée échoue fermé.

Le reçu reste un claim que le gate réfute contre l’état Git courant. Le digest canonique continue d’exclure les artefacts de revue et les vues générées afin d’éviter l’auto-référence; la base et le digest lient donc la preuve au diff qui sera fusionné. Les commits `head_commit` et `reviewed_head_commit` doivent résoudre vers leurs arbres déclarés et appartenir à la lignée ancestrale du head courant; les commits de scellement restent permis sans comparaison circulaire exacte avec le commit qui ajoute le reçu.

## Composants

- `governance/autonomy-policy.json` porte la décision, les identités, le plafond `2`, les états terminaux et les limites T3.
- `manifests/roles.yaml` rend Luna writer et Sol reviewer résolubles, sans retirer les identités historiques nécessaires aux anciens reçus.
- `scripts/revue.py` ajoute `tally_sol_blind`, la génération de prompt liée au diff exact et le dispatch de `verifier_recu` selon `mode`; `tally()` reste inchangé pour les reçus historiques.
- `scripts/reviews_gate.py` choisit le tally correspondant au mode déclaré et
  exige que le reçu couvrant une PR courante utilise le mode par défaut de la
  politique (`sol_blind`); `multi_vendor` reste historique/archive.
- Les documents d’autorité, de méthode et de reprise décrivent le merge proportionnel, la recherche autonome, la reprise depuis GitHub et les deux verdicts terminaux `DONE_WITH_EVIDENCE` / `BLOCKED_WITH_REASON`.

## Sécurité et non-objectifs

Aucun workflow GitHub ne s’auto-modifie, ne force une branche, ne décode un payload embarqué ou ne reçoit `contents: write`. Cette livraison n’installe pas de daemon, ne promet pas une exécution hors session et ne modifie pas les règles externes de protection du dépôt. Les frontières T3 restent celles de Nathan.

## Preuves exigées

Les tests couvrent le chemin positif, le contexte historique/non frais, l’auto-review, le diff modifié, le plafond de deux writers et la compatibilité du tally multi-vendor. Les gates authority, state-current, path-classification, registres, no-stub, suite Python et `reviews-sealed` doivent être verts. La preuve finale `sol_blind` doit examiner le diff exact de la PR dans un contexte neuf avant le merge.
