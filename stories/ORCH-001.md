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

