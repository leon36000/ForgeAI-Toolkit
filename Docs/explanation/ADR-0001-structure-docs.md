# ADR-0001 — Un dossier de documentation unique : `Docs/` (Diátaxis)

- **Statut** : accepté (2026-07-23)
- **Contexte** : issue d'audit #123 (FAI-0017)

## Problème

Le dépôt portait **deux** dossiers de documentation : `Docs/` (majuscule, mandaté par le plan maître
CANON, structure Diátaxis) qui ne contenait qu'un squelette vide, et `docs/` (minuscule) qui contenait
les notes réelles (gates, preuves). Cette duplication est :

- **trompeuse** (deux emplacements pour « la doc ») ;
- un **bug de portabilité** pour la vocation universelle du Toolkit : sur un système de fichiers
  **insensible à la casse** (macOS, Windows), `Docs/` et `docs/` **entrent en collision** (même chemin),
  ce qui casse le checkout git.

## Décision

**Un seul dossier : `Docs/`** (majuscule), conforme au CANON. Le contenu de `docs/` (minuscule) y est
consolidé dans le quadrant Diátaxis approprié (`Docs/reference/`). Le dossier minuscule est supprimé.

## Conséquences

- Les 4 notes (`catalogue-gate`, `plugin-gate`, `reeval-defaults`, `proof-ubuntu-vierge`) vivent sous
  `Docs/reference/`. Aucune référence de code ne pointait vers `docs/` (vérifié) — pas de lien cassé.
- `.coderabbit.yaml` ne filtre plus que `Docs/**` (le filtre `docs/**` est retiré).
- Aucun amendement du CANON n'est nécessaire : la décision **aligne** la réalité sur le CANON (qui
  mandatait déjà `Docs/`).
- Question connexe traitée dans la même issue : `stories/` était ignoré par `.gitignore` alors qu'une
  spec de story (`stories/BC-models-remediation.md`, référencée au registre seq 92-93) était suivie →
  exception `!stories/*.md` ajoutée (les specs de story sont des artefacts de gouvernance versionnés,
  le reste du dossier reste éphémère).
