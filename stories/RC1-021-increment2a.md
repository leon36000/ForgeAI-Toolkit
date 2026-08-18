# RC1-021 incrément 2a — seuils ciblés par catégorie + cliquet anti-régression (#451)

Suite de l'incrément 1 (PR #560, mergée `21df914`) qui a livré la MESURE informationnelle
(`scripts/branch_coverage_report.py`, job CI `branch-coverage-report`,
`governance/branch-coverage-baseline.json` avec un seuil global initial NON bloquant).

Couvre 2 des 5 critères restants de #451 :
- [x] seuils ciblés plus élevés pour orchestrateurs, sécurité, persistance et rollback ;
- [x] la baseline ne peut pas augmenter silencieusement ;

Les 3 autres critères (mutation ciblée, disposition des mutants survivants, tests négatifs de
garde) restent **hors périmètre** — incrément 2b distinct, nécessite l'introduction d'un outil
tiers de mutation testing.

## Livré

- `governance/branch-coverage-categories.json` (nouveau, committé) : mapping de 4 catégories
  (`orchestrateurs`, `securite`, `persistance`, `rollback`) → listes de globs de chemins,
  review-visible, jamais dérivé dynamiquement par mot-clé.
- `scripts/branch_coverage_ratchet.py` (nouveau) : réutilise le JSON déjà produit par
  `branch_coverage_report.py` (jamais de mesure séparée), calcule la couverture agrégée par
  catégorie (`pathlib.PurePath.match` / `fnmatch`, stdlib), compare à
  `governance/branch-coverage-baseline.json` (clé `seuils_par_categorie`) via le module partagé
  `gate_git_ref.py` (même pattern que `ruff_ratchet.py` / `mypy_gate.py`). Mode
  `--regenerer-baseline` explicite pour la maintenance (jamais automatique en CI).
- `.github/workflows/gates.yml` : nouveau job bloquant `branch-coverage-ratchet` (`fetch-depth:
  0`, distinct du job informationnel existant `branch-coverage-report`, inchangé), ajouté à
  `needs:` de l'agrégateur `tests` (#580).
- `tests/test_branch_coverage_ratchet.py` (nouveau, 41 tests) : logique pure + intégration
  `main()` (nominal, régression locale, incohérences de catégories dans les deux sens,
  régénération, amorçage) + test structurel anti-dérive lisant le vrai `gates.yml` via
  `yaml.safe_load()` (même motif que `tests/test_rc1580_tests_aggregate.py`).
- `governance/branch-coverage-baseline.json` : `seuils_par_categorie` rempli depuis une mesure
  fraîche réelle (orchestrateurs 85.97%, sécurité 86.47%, persistance 91.74%, rollback 84.12%) —
  aucune valeur inventée. `_but`/`_statut` mis à jour pour refléter l'état réel (incrément 2a
  livré, mécanisme désormais bloquant).

## Défauts trouvés et corrigés AVANT toute revue (exécution directe, jamais supposé correct)

1. **Amorçage `--regenerer-baseline` cassé** : la première implémentation validait la baseline
   EXISTANTE (stricte, exige `seuils_par_categorie` non vide) avant même de vérifier le flag de
   régénération — rendait impossible le tout premier amorçage (le fichier hérité de l'incrément 1
   n'a pas encore cette clé). Corrigé en suivant exactement le pattern de `ruff_ratchet.py` :
   chargement tolérant de l'ancienne baseline en mode régénération, validation stricte seulement
   avant écriture finale sur disque.
2. **Comparaison de référence git trop stricte** : `origin/main` (état réel du dépôt, confirmé
   par `git show origin/main:governance/branch-coverage-baseline.json`) n'a pas encore
   `seuils_par_categorie` — la validation stricte de la référence aurait fait échouer le tout
   premier run du nouveau job CI sur sa propre PR. Corrigé par une fonction de validation de
   référence séparée et tolérante (`_valider_baseline_reference`), distincte de la validation
   locale stricte inchangée.
3. **Logique de comparaison de catégories vides** : même après le correctif 2, la comparaison en
   aval traitait un ensemble de catégories de référence vide comme une « incohérence » plutôt que
   « rien à comparer » — détecté par mon propre test TDD avant tout commit. Corrigé : la
   comparaison de catégories/régression contre référence git est sautée entièrement quand la
   référence n'a pas encore de catégories (cas légitime d'ancien schéma).
4. Mineur : test structurel initial basé sur recherche de sous-chaînes/distances de caractères
   dans le texte brut du YAML (fragile) remplacé par `yaml.safe_load()` + navigation de structure
   (même motif que `test_rc1580_tests_aggregate.py`).

## Vérifié empiriquement (pas seulement lu la documentation)

- `python3 scripts/branch_coverage_ratchet.py --sortie-json branch-coverage.json --base-ref-git
  origin/main` exécuté en conditions réelles : `exit 0`, « Cliquet couverture de branches par
  catégorie : OK, aucune régression. » — confirme que le tout premier déploiement de ce job sur
  sa propre PR ne casse pas la CI.
- 41/41 tests verts, ruff/mypy propres sur les 2 nouveaux fichiers Python.
- YAML (`gates.yml`) et JSON (`branch-coverage-categories.json`,
  `branch-coverage-baseline.json`) valides.
- `no_stub_scan.py --all` : 390 fichiers, zéro violation.
- Suite complète du dépôt verte (`--ignore=tests/test_data002b_wal_idempotent.py`, exit 0).

## Hors périmètre (incrément 2b, story distincte)

Campagne de mutation ciblée sur les gardes/compensations, disposition de chaque mutant survivant,
tests négatifs prouvant qu'une garde retirée rend le job rouge — nécessite l'introduction d'un
outil tiers de mutation testing (mutmut/cosmic-ray/mutpy), non encore présent dans le dépôt.
