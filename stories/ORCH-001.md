# Story ORCH-001 — Plan de contrôle multi-IDE

## Identité

- **Package:** ORCH-001
- **Branche:** chore/ORCH-001-multi-ide-control-plane
- **Priorité:** P0_BLOCKER
- **Lane:** governance
- **Milestone:** M0-ORCHESTRATION

## Cause racine

Avant cette story, le dépôt ForgeAI Toolkit ne possédait aucun système de coordination entre IDE. Il était possible qu'un agent démarre une correction dont les dépendances n'étaient pas encore fusionnées, qu'un autre agent travaille sur les mêmes fichiers simultanément (collision de lane), ou qu'une PR soit construite depuis un `main` périmé.

**Preuve rouge :**
```
$ python3 scripts/coordination/validate_coordination.py
python3: can't open file '.../scripts/coordination/validate_coordination.py': [Errno 2] No such file or directory
exit: 2
```

## Périmètre installé

| Fichier / Dossier | Rôle |
|---|---|
| `coordination/work-packages.json` | Registre de tous les packages (60 total, 9 COPILOT + 51 externes) |
| `coordination/active-claims.json` | Claims actifs avec lease sur lane et chemins |
| `coordination/completed.json` | Packages fusionnés avec SHA prouvé |
| `scripts/coordination/validate_coordination.py` | Valide cohérence JSON + unicité de lane |
| `scripts/coordination/simulate_orchestration.py` | 10 simulations anti-collision |
| `.github/workflows/scope-guard.yml` | CI: validation + vérification périmètre sur PR et merge_group |
| `.github/workflows/gates.yml` | Ajout du trigger `merge_group` |
| `stories/ORCH-001.md` | Ce fichier |
| `reviews/ORCH-001/` | Revues aveugles scellées |
| `Registres/PATCH-ORCH-001.jsonl` | Entrée registre |
| `.cursor/rules/forgeai-orchestration.mdc` | Règles path-scoped Cursor IDE |

> Note (RC1-010/#440) : les trois chemins `coordination/*.json` ci-dessus ont été déplacés vers
> `archive/coordination/*.json` (lot 1) et `.cursor/rules/forgeai-orchestration.mdc` vers
> `archive/cursor/rules/forgeai-orchestration.mdc` (lot 2). Le tableau ci-dessus reste tel
> qu'écrit au moment de cette story (compte-rendu daté, non réécrit) ; cette note documente
> l'emplacement actuel sans altérer le récit historique.

## Tests effectués

### Test rouge (avant patch)
```
python3 scripts/coordination/validate_coordination.py → FileNotFoundError (exit 2)
```

### Test vert (après patch)
```
python3 scripts/coordination/validate_coordination.py
PASS — validate_coordination: 60 packages, 0 claims actifs, 0 complétés, zéro erreur.

python3 scripts/coordination/simulate_orchestration.py
simulate_orchestration: 10/10 PASS
```

### Gates complètes
```
python3 scripts/no_stub_scan.py --all
NO-STUB-SCAN : OK (253 fichiers scannés, zéro violation)

python3 scripts/registre.py verify Registres/*.jsonl
OK — zéro erreur (chaînes intègres)
```

## Tests négatifs simulés (10/10)

1. Double claim ORCH-001 → REJETÉ
2. Claim UI-039 sans ORCH-001 complété → REJETÉ
3. Collision lane web-ui (UI-039 actif + UI-040 tenté) → REJETÉ
4. Base périmée → REJETÉ
5. DOC-032 avec deps partielles → REJETÉ
6. Package inconnu → REJETÉ
7. ORCH-001 sans deps (éligible) → ACCEPTÉ
8. UI-039 après ORCH-001 complété → ACCEPTÉ
9. UI-040 après UI-039 complété → ACCEPTÉ
10. DOC-032 avec toutes les deps → ACCEPTÉ

## Sécurité

- Aucun secret dans les fichiers de coordination.
- Aucun identifiant, token ou clé dans `coordination/**`.
- ggshield AI hooks documentés dans AGENTS.md (section multi-IDE).

## Performance

Sans objet : les scripts s'exécutent en < 1 s, aucune régression mesurable.

## Limitations

- `scope-guard.yml` vérifie les allowlists statiquement depuis `work-packages.json`.
  Une mise à jour de scope nécessite une PR sur `coordination/`.
- La vérification de la base commit est symbolique en CI (compare au SHA d'audit).
  Une vérification stricte contre le dernier `origin/main` dynamique est documentée
  mais non bloquante en CI pour éviter des faux positifs lors de batches simultanés.

## Risques ouverts

- Aucun script de heartbeat automatique (claim TTL) n'est implémenté dans cette story.
  Si un agent crash sans libérer son claim, une intervention manuelle est nécessaire.
  → Issue de suivi à ouvrir après fusion.

## Correctif post-review : couverture SonarCloud

Le premier push a échoué le quality gate SonarCloud (`Coverage on New Code: 0.0%`,
requis ≥ 80 %), car `scripts/coordination/*.py` est inclus dans `sonar.sources` mais
n'était mesuré par aucun test (`pytest --cov=src/forgeai` ne couvrait pas ce chemin).

**Correction :**
- `scripts/coordination/test_validate_coordination.py` (22 tests) et
  `scripts/coordination/test_simulate_orchestration.py` (13 tests) ajoutés.
- `.github/workflows/sonarcloud.yml` : la commande pytest couvre désormais
  `tests/` **et** `scripts/coordination/` (`--cov=src/forgeai --cov=scripts/coordination`).

**Preuve :** couverture locale `scripts/coordination` = 99 % (388 lignes, 2 non couvertes
= blocs `if __name__ == "__main__"`), 35/35 tests verts, collection pytest vérifiée sans
collision avec la suite `tests/` existante.

## Correctif post-review 2 : duplication SonarCloud

Second push : le job `sonarcloud-scan` a d'abord échoué sur un test flaky préexistant
hors périmètre (`tests/test_multinoeud.py::test_summary_nodes`, timeout réseau, sans
rapport avec cette PR) — relancé avec succès. Le quality gate a ensuite signalé
`Duplication on New Code: 4.1 % (requis ≤ 3 %)` : les 35 tests ajoutés partageaient une
structure quasi identique (construction de fixtures + assertion sur `main()`).

**Correction :** consolidation via `pytest.mark.parametrize` :
- `test_validate_coordination.py` : 18 scénarios fusionnés dans une matrice `SCENARIOS`
  + un seul test paramétré (128 → 46 lignes).
- `test_simulate_orchestration.py` : 8 cas `try_claim` fusionnés dans `TRY_CLAIM_CASES`
  + un seul test paramétré ; le fixture de packages dupliqué extrait en fonction
  partagée `_full_wp_packages()` (76 → 49 lignes).

Résultat : 35/35 tests toujours verts, couverture inchangée à 99 %.

## Revue aveugle scellée 1 : REJECT 2/3 (défaut réel confirmé)

Tous les gates CI automatisés étant verts, une revue aveugle scellée 3 vendors a été
lancée (`~/proof-method/scripts/civ_review.py`, modèles `DeepSeek-V4-Pro`,
`Gemini-3.1-Pro`, `LongCat-2.0`, dossier `reviews/ORCH-001/civ`, pack diff verbatim
81 032 octets). Dépouillement déterministe (`scripts/revue.py tally`) :
**REJECT — 2/3 APPROVE** (3 vendors distincts confirmés : deepseek, google, meituan ;
`prompt_sha256=a754a77f…`). Consignée au registre : `Registres/mission.jsonl` seq 255.

**Objection majeure (Gemini-3.1-Pro), confirmée par test RED/GREEN — défaut réel, pas
un faux positif :** le job `scope-guard` (`.github/workflows/scope-guard.yml`) itérait
sur **TOUS** les claims actifs et exigeait que les fichiers modifiés respectent les
`allowed_paths` de **CHAQUE** claim. Puisque jusqu'à 6 claims concurrents sont autorisés
(AGENTS.md), une PR valide pour son propre package aurait été rejetée à tort dès qu'un
second claim était actif, ses fichiers n'étant pas dans les `allowed_paths` de cet
*autre* claim. Non détecté par mes tests initiaux car `coordination/active-claims.json`
était vide pendant tout le développement (0 claim actif ⇒ branche `SKIP` jamais
exercée avec ≥2 claims).

**Preuve RED :** rejeu de la logique bugguée (boucle `for claim in claims`) avec 2
claims concurrents simulés (`ORCH-001`, `HW-037`) et des fichiers modifiés strictement
dans le périmètre d'`ORCH-001` → la logique bugguée génère bien
`HORS SCOPE: coordination/work-packages.json n'est pas dans allowed_paths de HW-037`.

**Correction :** extraction de la logique vers un module testable
`scripts/coordination/scope_guard.py` (fonctions pures `find_claim_for_branch`,
`check_scope`, `main`). Le guard résout désormais **le seul claim propriétaire de la
PR courante** via un nouveau champ `branch` sur chaque claim (résolu par
`GITHUB_HEAD_REF` en CI, `git branch --show-current` en local) et n'applique que les
règles de CE claim — jamais celles des autres claims concurrents.
`coordination/active-claims.json` documente le champ `branch` dans sa `_description`.
`.github/workflows/scope-guard.yml` appelle désormais directement le module.

**Preuve GREEN :** même scénario (2 claims concurrents, fichiers dans le périmètre
d'ORCH-001) → `check_scope` retourne `[]` (aucune erreur). Suite complète :
`scripts/coordination/test_scope_guard.py` (23 tests, dont
`test_check_scope_ignores_other_claims_scope` qui reproduit exactement le scénario du
rapport). 58/58 tests verts sur `scripts/coordination/`, couverture 99 % (mêmes lignes
`__main__`/appel subprocess réel non couvertes, conforme à la convention du dépôt).

Aucun fichier hors `allowed_paths` d'ORCH-001 n'a été touché (les verdicts scellés sont
rangés sous `reviews/ORCH-001/civ/`, conforme au glob `reviews/ORCH-001/**` déclaré
dans `ISSUES/ORCH-001.md` — pas de modification unilatérale de mon propre périmètre).

**Correctif de périmètre (auto-détecté) :** l'entrée `revue_scellee` du verdict REJECT
ci-dessus avait été initialement ajoutée à `Registres/mission.jsonl`, qui n'est **pas**
dans `allowed_paths` d'ORCH-001 (seul `Registres/PATCH-ORCH-001.jsonl` y figure). Une
seconde revue aveugle scellée (round 2, voir ci-dessous) a détecté cette violation
avant même que le tally ne soit dépouillé (objection Gemini-3.1-Pro sur le `.tmp`
intermédiaire). Correction : `mission.jsonl` restauré à l'état `origin/main`, l'entrée
`revue_scellee` re-consignée dans `Registres/PATCH-ORCH-001.jsonl` (seq 2, hash-chaîné
sur seq 1, propre à ORCH-001, strictement dans le périmètre).

## Revue aveugle scellée 2 : en cours sur le diff corrigé

Second round lancé sur le diff intégrant le correctif `scope_guard.py`. Round
interrompu techniquement (processus arrière-plan clos avant complétion) ; un round
propre a été relancé après la correction de périmètre ci-dessus.

**Résultat round 2 : APPROVE 3/3.** Dossier `reviews/ORCH-001/civ2/`, dépouillement
déterministe (`scripts/revue.py tally reviews/ORCH-001/civ2`) : `result=APPROVE,
reason="3/3 APPROVE"`, 3 vendors distincts confirmés (deepseek, google, meituan),
`prompt_sha256=5d0854eb…`, zéro objection. Consignée au registre scopé :
`Registres/PATCH-ORCH-001.jsonl` seq 3.

**`reviews/BINDING.txt` volontairement non modifié** : ce fichier n'est pas dans
`allowed_paths` d'ORCH-001 et sa modification (rendre une revue *liante* pour le gate
CI `reviews-sealed`) est une décision de gouvernance qui dépasse le périmètre de cette
story — elle revient au mainteneur/CODEOWNERS lors de la fusion. La preuve APPROVE 3/3
est disponible et vérifiable indépendamment dans `reviews/ORCH-001/civ2/`.

## État final

- Tous les gates CI automatisés sont verts (11/11) sur le dernier commit poussé.
- Revue aveugle scellée : REJECT 2/3 (round 1, défaut réel corrigé) → **APPROVE 3/3**
  (round 2, dossier `reviews/ORCH-001/civ2/`).
- Registre `Registres/PATCH-ORCH-001.jsonl` : 3 entrées, chaîne intègre.
- `Registres/mission.jsonl` : chaîne intègre, non modifiée par cette story (254 entrées,
  état `origin/main`).
- Périmètre respecté : `git diff origin/main...HEAD --stat` ne montre aucun fichier
  hors `allowed_paths`.
- Reste hors de mon autorité d'agent : ajout à `reviews/BINDING.txt` (gouvernance) et
  fusion de la PR (gate humain, CODEOWNERS = Nathan).


