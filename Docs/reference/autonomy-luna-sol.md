# Référence exécutable — autonomie Luna/Sol

Cette référence décrit l’implémentation finale et son protocole de scellement
pour l’issue #603. La source de vérité est `governance/autonomy-policy.json`; la décision associée est
`governance/decisions/D-2026-08-21-autonomie-luna-sol.md`.

La règle d’absence d’écriture distante s’applique aux workflows du contrat
Luna/Sol. Les automatisations indépendantes du dépôt, comme
`.github/workflows/ci-deps-update.yml`, restent hors de son périmètre et suivent
leur propre politique de permissions.

Le writer actif est `luna_writer` / `GPT-5.6-Luna-Writer`, avec exactement deux
writer lanes. Le reviewer actif est `sol` / `GPT-5.6-Sol`, en contexte frais,
aveugle et strictement read-only. `multi_vendor` reste un mode historique
d’archive et conserve son quorum 3/3.

Le prompt Sol est reconstruit depuis le diff Git exact et les critères de la
story `stories/ORCH-LUNA-SOL-603.md`. Après approbation de l’implémentation,
le reçu final courant est
`evidence/reviews/ORCH-LUNA-SOL-603-final-seal-r3/RECU.json`; il lie les commits,
arbres, digest du diff, prompt, template, journaux SDD et registre de mission.
Le champ `candidate_diff_digest` reste le digest canonique des entrées Git brutes;
`artifact_sha256` scelle séparément les octets exacts du diff texte présenté à Sol.
Les digests neutralisent les configurations Git globales qui pourraient
modifier ou ordonner la sortie. Le reviewer n’écrit jamais dans le dépôt.

Le gate sans drapeau conserve le dépouillement historique, vérifie la forme/cohérence interne
du reçu et le hash du prompt, mais ne recharge pas ses objets Git; cela reste compatible avec
les checkouts CI peu profonds. Le mode PR
`--exiger-recu-courant --base-ref ...` vérifie la liaison complète au changement courant,
les métadonnées du prompt contre le reçu et le verdict, puis les objets Git; le mode
`--mode archive` applique la même cohérence avant de vérifier les objets après fusion.
La fenêtre de fraîcheur est vérifiée entre la revue et le scellement; le mode PR ajoute
l’horloge courante, tandis que l’archive ne fait pas expirer un reçu ancien déjà scellé.
Une prétention de scellement future est refusée contre l’horloge de validation, et le mode PR
ne résout l’état Git qu’après la validation locale du triplet reçu/prompt/verdict.
Cette validation locale compare aussi les métadonnées d’empreinte répétées dans le verdict Sol
au reçu avant toute résolution d’objet Git.
Elle impose également l’identité canonique `GPT-5.6-Sol` et les trois marqueurs de revue
fraîche/aveugle/read-only avant cette résolution.
Le schéma de réponse exige aussi ses champs `verdict`, `blocking_findings`, `reviewed_at` et
`prompt_sha256` exacts; la date du verdict ne peut pas dépasser celle du scellement.
Le digest canonique exclut uniquement les fichiers générés nommés exactement et les répertoires
de preuve par préfixe; un chemin ressemblant à un manifeste reste donc couvert.
Pour distinguer un reçu historique d’un reçu courant, le mode PR vérifie d’abord les dates
intrinsèques et les futures, classe la liaison via Git, puis applique la fenêtre actuelle au
reçu courant; l’historique est validé à l’heure de son scellement.

Le mode archive exige en plus que chaque reçu encore présent dans
`evidence/reviews/BINDING.txt` pointe vers un commit ancêtre de `main`. Les
quatorze reçus historiques qui ne satisfaisaient plus cette preuve ont été
retirés du manifeste actif, sans supprimer leurs dossiers; leurs identités et
commits sont consignés dans `evidence/reviews/ARCHIVE-UNMERGED.txt`. Ils restent
consultables mais ne sont pas réintroduits comme preuve liante sans nouvelle
revue.

Les limites T3 restent humaines : paiements, secrets de production,
suppressions définitives et engagements externes. Les états terminaux sont
`DONE_WITH_EVIDENCE` et `BLOCKED_WITH_REASON`; cette livraison ne prétend aucun
résultat runtime, matériel ou externe.

Vérifications de la phase :

```bash
python3 scripts/governance/validate_authority.py
python3 scripts/governance/state_current.py
python3 scripts/governance/classify_paths.py
python3 scripts/reviews_gate.py --exiger-recu-courant --base-ref origin/main --issue <pr>
python3 scripts/reviews_gate.py --mode archive
python3 -m pytest -q
```

Le statut `DONE_WITH_EVIDENCE` de la story n’est recevable que lorsque ces
commandes passent, que `BINDING.txt` contient le reçu final et que le mode
archive réussit sur l’arbre fusionné. Une preuve non retrouvée reste
`BLOCKED_WITH_REASON`; aucun transcript ou état runtime ne la remplace.
