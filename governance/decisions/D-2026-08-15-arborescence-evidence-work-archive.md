# Décision — arborescence evidence/ work/ archive/ (RC1-010)

Date : 2026-08-15

Référence : issue GitHub [#440 — Séparer evidence/, work/ et archive/ avec traçabilité complète](https://github.com/leon36000/ForgeAI-Toolkit/issues/440).

Cette décision précède tout déplacement de fichier (lot 0 de #440). Elle tranche deux conflits
de gouvernance découverts en reconnaissance, avant que le code ne les matérialise.

## Décision A — `coordination/work-packages.json` passe `active` → `superseded`

`governance/authority.json` marquait `coord.work-packages` `active` (`decision.vision_log_seq:
null` — jamais tranché), en contradiction avec `AGENTS.md` (§Modèle de coordination, issue
#481) qui affirme que `coordination/*.json` est archivé/historique et remplacé par ce modèle.
Cette entrée passe `superseded_by: gov.decision-mission-lead`, `retention:
historical_record`, comme son pair `coord.active-claims` (déjà superseded depuis #431).

Cette bascule de statut de gouvernance **ne dispense d'aucune obligation fonctionnelle** :
`coordination/work-packages.json` reste lu par `scripts/coordination/validate_coordination.py`
et `scripts/governance/state_current.py` — le lot 1 de #440 (déplacement physique vers
`archive/coordination/`) devra mettre à jour ces lecteurs dans le même commit que le `git mv`,
exactement comme `coord.active-claims` reste fonctionnellement lu depuis #433 malgré son statut
`superseded`.

## Décision B — `stories/` reste en place, `work/` n'est pas créé

La formulation de l'issue #440 (« `work/` : stories et coordination actives ») est descriptive,
pas normative — même lecture que la formulation « docs/ » de #439
([D-2026-08-15-racines-documentaires.md](D-2026-08-15-racines-documentaires.md)). La règle
`governance-stories` de `governance/path-classification-rules.json` (#438, déjà mergée,
`target_kind: keep`) fait autorité : `stories/` contient des artefacts de gouvernance
(comptes-rendus datés, dont `stories/ORCH-001.md` est une source d'autorité empreintée dans
`governance/authority.json`) et reste en place. `work/` n'est créé par aucun lot de #440.

## Décision C — `completed.json` migre avec ses deux pairs

`coordination/completed.json` n'a pas d'entrée propre dans `governance/authority.json` (ce
n'est pas une source normative, c'est une donnée) mais il est chargé par
`scripts/coordination/validate_coordination.py` au même titre que `work-packages.json` et
`active-claims.json` — les trois fichiers migrent ensemble, dans le même lot (lot 1), leur
lecteur commun étant adapté dans le même commit.

## Règles de destination ajoutées (lot 0, préparatoire)

`governance/path-classification-rules.json` reçoit, en fin de tableau (aucune règle existante
n'est réordonnée ni modifiée — aucune classification actuelle ne change), des règles `keep`
pour les préfixes de destination `evidence/reviews/`, `evidence/registres/`,
`evidence/audit-output/`, `archive/` — nécessaires pour que `classify_paths.py` ne lève pas
« chemin non classé » dès le premier fichier déplacé par les lots suivants.

## Portée

Cette décision fixe l'ordre et les règles de la migration `evidence/`/`archive/` (#440), sans
déplacer aucun fichier. Elle est matérialisée comme entrée versionnée de
`governance/authority.json` sous l'identifiant `gov.decision-arborescence-evidence-work-archive`.
