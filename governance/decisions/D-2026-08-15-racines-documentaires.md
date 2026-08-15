# Décision — racines documentaires

Date : 2026-08-15

Référence : issue GitHub [#439 — Consolidation des racines documentaires](https://github.com/leon36000/ForgeAI-Toolkit/issues/439).

## Décision

`Docs/`, avec majuscule, est confirmée comme racine unique de la documentation
active du dépôt. Cette décision confirme, sans la superseder, la décision déjà
actée dans [`Docs/explanation/ADR-0001-structure-docs.md`](../../Docs/explanation/ADR-0001-structure-docs.md).

`governance/` porte le canon, les décisions, la méthode et les artefacts de
gouvernance, notamment les schémas, les manifestes générés et le journal de
vision. Il est distinct de la documentation produit et utilisateur, qui vit
sous `Docs/`.

La formulation « docs/ » dans l'énoncé de l'issue #439 était descriptive et
non normative sur la casse.

L'écart `docs/politique-versions-python.md`, créé par erreur par RC1-447/PR495,
est fermé par cette story au moyen du déplacement versionné
`git mv docs/politique-versions-python.md Docs/reference/politique-versions-python.md`.

## Portée

Cette décision fixe les racines documentaires actives du dépôt.

Ce fichier matérialise cette décision comme entrée versionnée de
`governance/authority.json`, sous l'identifiant
`gov.decision-racines-documentaires`.
