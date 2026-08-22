# Contrat exécutable d'autonomie Luna/Sol (#603)

Ce document décrit le contrat que les scripts et les gates peuvent vérifier.
Il ne constitue pas une preuve de revue, d'exécution runtime, de matériel ou
d'un service externe. Explicitly, no runtime evidence and no external evidence
are claimed here. La politique versionnée est la source de vérité :
[`governance/autonomy-policy.json`](../../governance/autonomy-policy.json).
Le design de référence est
[`Docs/superpowers/specs/2026-08-22-autonomous-luna-sol-design.md`](../superpowers/specs/2026-08-22-autonomous-luna-sol-design.md).

## Roster et lanes

Le roster actif de `manifests/roles.yaml` contient :

- `luna_writer` — provider identity `GPT-5.6-Luna-Writer`, writer primaire
  `GPT-5.6 Luna`;
- `sol` — provider identity `GPT-5.6-Sol`, reviewer `GPT-5.6 Sol`.

`luna` / `GPT-5.6-Luna-Pro` est une identité historique retirée, conservée
pour résoudre les anciens reçus. Le contrat autorise exactement
`max_active_writer_lanes = 2`. Une lane d'écriture est possédée par un seul
writer; les reviewers ne sont pas des writers et restent read-only.
Issue tracking may cover at most four disjoint issues, but it is subordinate to the policy: never
more than two active writer lanes.

## Mode `sol_blind`

Le mode historique multi-vendor reste compatible pour les anciennes preuves.
Le mode explicite `sol_blind` exige un seul verdict Sol, dans un contexte fresh,
blind et read-only. Sol ne reçoit ni verdict attendu ni verdict d'un autre
reviewer. Le codeur ne peut pas résoudre vers Sol, même si Luna et Sol ont le
même vendor.

Le verdict doit contenir exactement les éléments de liaison utiles suivants :

- `fresh_context: true`, `blind: true`, `reviewer_read_only: true`;
- `reviewer_model: GPT-5.6-Sol` comme provider ID canonique exact, reconnu par le roster;
- `candidate_diff_digest` égal au digest canonique du diff Git examiné;
- `base_commit`, `reviewed_head_commit` et `reviewed_head_tree` égaux aux
  métadonnées Git attendues;
- `prompt_sha256` égal au hash du prompt canonique livré à Sol;
- `reviewed_at` avec un fuseau et dans la fenêtre de fraîcheur, plafonnée à 24 heures;
- `verdict: APPROVE` et `blocking_findings: []`.

Le reçu conserve ces liaisons avec `mode: sol_blind`. Le gate traite le reçu
comme un claim et le compare à la PR ou au diff courant; le head conservé sert
à la traçabilité sans comparaison circulaire avec le commit qui ajoute le
reçu. Les artefacts de revue et les vues générées restent hors du digest
canonique.

Le reçu porte aussi `story`, l’identifiant immuable utilisé pour reconstruire le
prompt, séparément de `dossier`, qui désigne le répertoire des artefacts sous
`evidence/reviews/`. La commande `recu --mode sol_blind` exige donc
`--story <story-id>` afin que le prompt produit et le prompt vérifié utilisent
exactement la même valeur; le gate vérifie aussi que `dossier` correspond au
répertoire effectivement chargé.

In `reviews_gate.py`, receipt-mode dispatch preserves `multi_vendor`'s historical 3/3 tally;
active `sol_blind` requires exactly one `GPT-5.6-Sol` verdict.

## Boucle, reprise et source de vérité

La boucle sûre est : lire la politique et le plan, inspecter l'issue et le diff,
écrire seulement dans les deux lanes autorisées, tester après chaque tranche,
faire livrer à Sol un prompt blind exact, puis contrôler les registres, les
vues et les hooks avant de demander le merge. La recherche autonome peut
continuer dans le dépôt, mais aucun workflow ne peut recevoir `contents: write`,
faire un `force-push`, décoder du code source embarqué ou être `self-writing`.

Après interruption, la reprise repart de la politique versionnée, de l'issue/PR
GitHub, de `git status`/`git diff`, de l'historique Git et des registres vérifiés.
Ce sont la source de vérité de reprise; un transcript, une mémoire de session
ou une affirmation runtime précédente ne l'est pas. En cas de contexte Sol
expiré, de diff changé ou de preuve incomplète, il faut générer un nouveau
contexte et un nouveau binding, jamais réutiliser un verdict périmé.

## Chemin de merge et garde-fous

Le chemin repository-native, dans cet ordre, est :

1. Lire `governance/autonomy-policy.json`, la story et le diff Git courant.
2. Respecter les deux writer lanes et conserver les décisions T3 pour Nathan.
3. Exécuter les tests ciblés et les checks proportionnés; ne pas transformer un
   claim en preuve.
4. Prolonger les registres avec `scripts/registre.py append`, puis les vérifier
   avec `python3 scripts/registre.py verify governance/vision-log.jsonl evidence/registres/mission.jsonl`.
5. Régénérer les vues, sans éditer leurs hashes ou leur contenu à la main :

   ```text
   python3 scripts/governance/validate_authority.py --render
   python3 scripts/governance/state_current.py --render --docs README.md --docs AGENTS.md
   python3 scripts/governance/classify_paths.py --render
   ```

6. Inspecter le diff complet, passer `git diff --check` et les hooks normaux,
   puis ne fusionner qu'avec un head courant, les checks requis réussis et un
   reçu `sol_blind` mécaniquement valide.

Les workflows ne doivent jamais utiliser `contents: write`, `force-push`,
`decode` de source embarquée ou une logique `self-writing`. Le contrat ne
modifie pas les règles externes de protection du dépôt.

## T3 et états terminaux

Les frontières T3 restent : paiements, secrets de production, suppressions
définitives et engagements externes. Elles appartiennent à Nathan; la revue
Sol recommande et le gate vérifie, mais ne lève pas une frontière T3.

Les seuls états terminaux sont :

- `DONE_WITH_EVIDENCE` — tous les artefacts et checks exigés sont présents et
  vérifiables;
- `BLOCKED_WITH_REASON` — une condition concrète manque ou échoue, avec sa
  raison consignée et sans preuve inventée.

Task 4 est `DONE_WITH_EVIDENCE` pour cette tranche documentaire et déterministe.
Task 5 reste `PENDING` : final fresh Sol evidence remains pending, et aucune
preuve runtime ou externe finale n'est prétendue ici.

## Vérifier

Les tests ciblés sont `python3 -m pytest -q tests/test_autonomy_docs.py
tests/test_autonomy_policy.py tests/test_revue_sol_blind.py
tests/test_reviews_gate.py`. Les checks de gouvernance et de registre sont
ceux des commandes ci-dessus; les vues doivent rester synchronisées et les
registres append-only. La story
[`stories/ORCH-LUNA-SOL-603.md`](../../stories/ORCH-LUNA-SOL-603.md) conserve le
statut et le checkpoint de la tranche en cours.
