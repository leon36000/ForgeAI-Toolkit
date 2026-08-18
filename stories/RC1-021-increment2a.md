# RC1-021 incrément 2a — seuils ciblés par catégorie + cliquet anti-régression (#451)

Suite de l'incrément 1 (PR #560, mergée `21df914`) qui a livré la MESURE informationnelle
(`scripts/branch_coverage_report.py`, job CI `branch-coverage-report`,
`governance/branch-coverage-baseline.json` avec un seuil global initial NON bloquant).

Couvre 1 des 5 critères restants de #451, plus un mécanisme de cliquet anti-régression sur les
seuils par catégorie (non explicitement listé comme critère séparé, mais nécessaire pour rendre
le premier critère réellement bloquant plutôt que déclaratif) :
- [x] seuils ciblés plus élevés pour orchestrateurs, sécurité, persistance et rollback ;
- [x] (complément) un seuil de couverture par catégorie ne peut pas **baisser** silencieusement
  (comparaison locale ET contre `origin/main` via `gate_git_ref.py`) — voir précision ci-dessous
  sur la formulation exacte de l'issue.

**Précision importante (round 1 de revue, voir plus bas)** : le critère de l'issue original
formulé « la baseline ne peut pas augmenter silencieusement » (ligne 17 du corps de #451) est
positionné dans le bloc mutation testing de l'issue (entre « chaque mutant survivant reçoit une
disposition » et « tests négatifs prouvant que retirer une garde importante rend le job rouge »)
— il porte sur la baseline du NOMBRE DE MUTANTS SURVIVANTS TOLÉRÉS (une dette, comme pour
`ruff_ratchet.py`/`mypy_gate.py` : plus de dette ne doit jamais passer silencieusement), PAS sur
les seuils de couverture par catégorie de cet incrément. Une version antérieure de cette story
citait ce critère par erreur comme couvert ici — corrigé.

Les 3 autres critères (mutation ciblée, disposition des mutants survivants, la vraie baseline de
mutants « ne peut pas augmenter silencieusement », tests négatifs de garde) restent **hors
périmètre** — incrément 2b distinct, nécessite l'introduction d'un outil tiers de mutation
testing.

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

## Round 1 de revue scellée — REJECT 1/3 (Qwen3.8-2.4T APPROVE ; DeepSeek-V4-Pro-0813 et
GPT-5.6-Terra-Pro REJECT, 2 objections majeures identiques)

**Objection majeure (réfutée avec preuve textuelle, code inchangé)** : « le critère dit "la
baseline ne peut pas augmenter silencieusement", l'implémentation ne bloque que les baisses de
seuil ». Vérifié directement sur le corps de l'issue #451 (`gh issue view 451 --json body`,
lignes numérotées) : le critère cité est la ligne 17, entourée des lignes 15-16 (« campagne de
mutation ciblée », « chaque mutant survivant reçoit une disposition ») et 18 (« tests négatifs
prouvant que retirer une garde importante rend le job rouge ») — un bloc cohérent sur la
MUTATION TESTING, hors périmètre explicite de cet incrément 2a. « La baseline » de ce critère est la baseline de mutants
survivants tolérés (une dette, croissante = mauvais signe, symétrique à `ruff_ratchet.py`), pas
mon `seuils_par_categorie` (un pourcentage de couverture, où c'est l'inverse qui est vrai :
empêcher une BAISSE protège la qualité, bloquer une HAUSSE bloquerait au contraire toute
amélioration légitime de couverture — contraire à l'esprit d'un cliquet). Story corrigée
ci-dessus pour ne plus citer ce critère comme couvert ici ; code non modifié (déjà correct).

**Objections mineures — vérifiées, non retenues (documentées, pas de changement de code)** :
- « seuils par catégorie parfois < seuil global (90.21%) » : attendu et voulu — chaque seuil est
  la mesure fraîche réelle de SA catégorie (ex. `rollback` 84.12%, structurellement plus complexe
  — `cli.py`/`deploy/`), pas une valeur artificiellement forcée au-dessus d'une moyenne globale
  (violerait le principe déjà établi dans le fichier baseline lui-même : « aucune marge ajoutée
  arbitrairement »).
- « catégorie sans fichier matché = 100%, permet une suppression de fichiers de passer le
  cliquet » : angle mort réel mais mineur (confirmé par le reviewer lui-même comme non
  bloquant) — laissé pour un futur raffinement, hors périmètre de ce round.
- « le job CI relance sa propre mesure au lieu de réutiliser l'artefact de `branch-coverage-
  report` » : choix délibéré, cohérent avec le job existant `branch-coverage-report` lui-même
  (sous-processus totalement indépendant, jamais d'interférence entre jobs) — question de
  performance CI (double calcul), pas un défaut fonctionnel.

## Round 2 de revue scellée — REJECT 2/3 APPROVE (Qwen3.8-2.4T + un second reviewer APPROVE ;
1 objection majeure bloquante, fondée)

Réfutation du round 1 tenue (plus aucune objection sur le sujet « augmenter/baisser »). Nouvelle
objection majeure, cette fois retenue et corrigée : le job `branch-coverage-ratchet` relançait sa
propre exécution de `scripts/branch_coverage_report.py` au lieu de réutiliser le JSON DÉJÀ PRODUIT
et publié comme artefact CI par le job `branch-coverage-report` — contredisait la promesse
explicite de la story/docstring (« réutilise le JSON déjà produit... ne relance JAMAIS sa propre
mesure séparée »), causait un double calcul de couverture à chaque run CI.

**Corrigé** : `branch-coverage-ratchet` a maintenant `needs: branch-coverage-report` et télécharge
l'artefact réel (`actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093 # v4.3.0` —
SHA vérifié via `gh api repos/actions/download-artifact/tags`, jamais deviné) au lieu de relancer
`branch_coverage_report.py`. Vérifié avant ce correctif que `branch-coverage-report` est déjà
dans `needs:` de l'agrégateur `tests` (#580) — la nouvelle dépendance directe n'introduit donc
aucun nouveau risque net de blocage en cascade (un skip serait de toute façon détecté comme échec
par `verifier_agregat_tests.py`, qui vérifie `result == "success"` sur chaque dépendance).

## Round 3 de revue scellée — REJECT 2/3 APPROVE, 0 objection bloquante (incohérence de verdict
d'un reviewer, corrigée par prudence)

Incident de process : verdict DeepSeek périmé (sha du round 2) dans le dossier — 2 échecs de
route ("NoneType") sur DeepSeek puis Kimi-2.7, swap réussi vers MiMo-V2.5-Pro (pool de rotation,
vendor xiaomi). Résultat final : Qwen3.8-2.4T et MiMo-V2.5-Pro APPROVE, GPT-5.6-Terra-Pro REJECT
— mais sa SEULE objection listée est classée « mineure » par lui-même (aucune majeure/critique) :
incohérence de verdict du reviewer. L'objection sous-jacente (catégorie sans fichier matché
validée silencieusement à 100%, angle mort réel bien que mineur, soulevée à chaque round par
plusieurs reviewers) a été corrigée par prudence plutôt que de lancer un 4e round hasardeux
(discipline anti-boucle #578) : `main()` ajoute désormais une anomalie bloquante explicite si
une catégorie n'a aucun fichier réellement matché en mode normal (le mode
`--regenerer-baseline` reste inchangé). Vérifié que le scénario réel (aucune catégorie vide dans
ce dépôt) n'est pas affecté : `exit 0`, toujours « OK, aucune régression ».

## Round 4 de revue scellée — REJECT 2/3 APPROVE, 0 objection bloquante (même pattern qu'au
round 3, objection technique valide corrigée par prudence)

Nouvel incident de process : DeepSeek en échec de route ("NoneType") 2 fois de suite, swap
direct vers MiMo-V2.5-Pro (déjà fiable au round 3). GPT-5.6-Terra-Pro REJECT à nouveau alors
qu'aucune de ses 3 objections n'est classée majeure/critique par lui-même.

Objection technique retenue cette fois (fondée, corrigée) : le contrôle « catégorie sans fichier
matché » du round 3 testait `num_branches == 0` plutôt que la liste réelle de fichiers matchés
— un fichier peut légitimement matcher un glob sans posséder la moindre branche (ex. module de
pures constantes), ce qui n'est PAS suspect et n'aurait jamais dû déclencher le message « aucun
fichier ne matche ». Corrigé : le test porte désormais sur `couverture[cat]["fichiers"]` (liste
réelle), pas sur l'agrégat de branches. Nouveau test dédié
(`test_main_fichier_matche_sans_branche_ne_declenche_pas_categorie_vide`).

## Hors périmètre (incrément 2b, story distincte)

Campagne de mutation ciblée sur les gardes/compensations, disposition de chaque mutant survivant,
tests négatifs prouvant qu'une garde retirée rend le job rouge — nécessite l'introduction d'un
outil tiers de mutation testing (mutmut/cosmic-ray/mutpy), non encore présent dans le dépôt.
