# ADR-0002 — Portée et limites de la revue automatique (CodeRabbit)

- **Statut** : accepté (2026-08-16)
- **Contexte** : issue d'audit #444 (RC1-014, source EXT-017)

## Problème

`.coderabbit.yaml` excluait de la revue automatique `CANON/**`, `Docs/**` et `stories/**` — du
contenu normatif majoritairement rédigé/édité par des humains, pas des données générées — ainsi
que cinq chemins devenus **morts** après la migration RC1-010 (#440) : `Phase-A/`, `Rapports/`,
`Recherche/`, `Registres/`, `reviews/`. Une exclusion sur un chemin mort est un no-op silencieux :
elle ne protège plus rien, elle masque juste que la configuration n'a pas suivi la réorganisation
du dépôt.

## Décision

1. **Chemins corrigés** vers leurs équivalents post-migration (`Registres/` → `evidence/registres/`,
   `reviews/` → `evidence/reviews/`, `Phase-A/`/`Rapports/`/`Recherche/` → `archive/`).
2. **`CANON/**`, `Docs/**`, `stories/**` retirés de l'exclusion** : ce contenu reçoit désormais la
   revue automatique CodeRabbit, comme tout autre changement de PR.
3. **Exclusions bornées à une allowlist justifiée**, vérifiée par
   `scripts/governance/validate_coderabbit_config.py` (gate déterministe, même famille que
   `validate_sonar_suppressions.py`) : seuls des artefacts **générés** ayant leur propre
   validation déterministe séparée restent exclus — `evidence/**` (registres hash-chaînés,
   revues scellées, sorties d'audit), `archive/**` (historique gelé, RC1-010), les fichiers
   `governance/*.json`/`*.md` auto-référentiels (même ensemble que
   `classify_paths.py::self_referential_generated_paths`), `src/forgeai/data/**` (catalogue
   généré, gate `catalogue` dédié) et les répertoires de build (`build/`, `dist/`).

## Limites du contrôle automatique (ce que CodeRabbit NE remplace PAS)

CodeRabbit est une **heuristique LLM en profil `chill`**, non bloquante (`pre_merge_checks` en
mode `warning` uniquement) — elle **complète** les gates déterministes du dépôt, elle ne s'y
substitue jamais :

- **La revue aveugle scellée multi-vendor** (`~/proof-method/scripts/civ_review.py` +
  `scripts/revue.py tally`, AGENTS.md règle 3) reste la SEULE autorité de revue pour tout
  changement de code source — 3 vendors distincts, prompt identique scellé, dépouillement
  déterministe. Un avis CodeRabbit favorable ne dispense jamais de cette revue.
- **L'approbation T3 de Nathan** (AGENTS.md règle 5 : paiements, secrets de production,
  suppressions définitives, engagements externes) reste requise indépendamment de ce que
  CodeRabbit signale ou ne signale pas sur `CANON/` — l'inclure dans la revue automatique ajoute
  un signal supplémentaire, ça ne réduit ni ne remplace la frontière T3.
- **`.github/CODEOWNERS`** (signature humaine requise par la branch protection,
  `require_code_owner_reviews`) reste le mécanisme d'approbation humaine effective sur
  `CANON/`, `manifests/`, `evidence/registres/`, `evidence/reviews/`, `.github/` — CodeRabbit
  n'a aucune capacité d'approbation ou de blocage de merge.
- **La cohérence liens/identifiants/statuts avec l'authority map** (critère de l'audit #444)
  est déjà couverte, pour les sources ENREGISTRÉES, par
  `scripts/governance/validate_authority.py` (gate CI `authority-map`) — non dupliquée ici.

## Conséquences

- Toute future exclusion ajoutée à `.coderabbit.yaml` doit être répertoriée dans l'allowlist de
  `validate_coderabbit_config.py` (gate CI bloquant) — plus d'exclusion silencieuse non
  justifiée.
- `CANON/`, `Docs/`, `stories/` génèrent désormais des commentaires CodeRabbit sur toute PR qui
  les touche — signal supplémentaire, jamais une condition de merge (profil `chill`,
  `request_changes_workflow: false`).
