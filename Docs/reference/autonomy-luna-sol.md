# Référence exécutable — autonomie Luna/Sol

Cette phase versionne le noyau du contrat de l’issue #603. La source de vérité
est `governance/autonomy-policy.json`; la décision associée est
`governance/decisions/D-2026-08-21-autonomie-luna-sol.md`.

Le writer actif est `luna_writer` / `GPT-5.6-Luna-Writer`, avec exactement deux
writer lanes. Le reviewer actif est `sol` / `GPT-5.6-Sol`, en contexte frais,
aveugle et strictement read-only. `multi_vendor` reste un mode historique
d’archive et conserve son quorum 3/3.

Le prompt Sol est reconstruit depuis le diff Git exact et les critères de la
story `stories/ORCH-LUNA-SOL-603.md`. Le reçu lie les commits, arbres, digest
du diff, prompt, template, journaux SDD et registre de mission; les digests
neutralisent les configurations Git globales qui pourraient modifier ou
ordonner la sortie. Le reviewer n’écrit jamais dans le dépôt.

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
Pour distinguer un reçu historique d’un reçu courant, le mode PR vérifie d’abord les dates
intrinsèques et les futures, classe la liaison via Git, puis applique la fenêtre actuelle au
reçu courant; l’historique est validé à l’heure de son scellement.

Les limites T3 restent humaines : paiements, secrets de production,
suppressions définitives et engagements externes. Les états terminaux sont
`DONE_WITH_EVIDENCE` et `BLOCKED_WITH_REASON`; cette phase ne prétend aucun
résultat runtime, matériel ou externe.

Vérifications de la phase :

```bash
python3 scripts/governance/validate_authority.py
python3 scripts/governance/state_current.py
python3 scripts/governance/classify_paths.py
python3 scripts/reviews_gate.py --exiger-recu-courant --base-ref origin/main --issue <pr>
python3 -m pytest -q
```

La preuve Sol et le dossier documentaire final sont ajoutés dans une phase
bornée ultérieure, avec les fichiers qu’ils déclarent réellement.
