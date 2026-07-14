# ForgeAI Toolkit

Déployeur de référence d'infrastructures IA agentiques : wizard hardware-aware,
catalogue 1021 entrées bilingue (FR/EN), multi-nœuds (Tailscale), gouvernance intégrée.

Construit via la méthodologie **BMAD**, exécuté par une équipe de modèles orchestrée
dans Claude Code (Fable = orchestrateur/juge), routée par le gateway LiteLLM local
(`forge-model-bridge`). Plan de référence : [CANON/PLAN-MAITRE-EXECUTION-BMAD-v1.0.md](CANON/PLAN-MAITRE-EXECUTION-BMAD-v1.0.md).

## Structure canonique

| Répertoire | Rôle |
|---|---|
| `CANON/` | Documents de référence gelés (plan maître, annexes) |
| `manifests/` | Plan machine-lisible : `roles.yaml`, `routes.yaml`, `phases.yaml`, `bricks.yaml`, `gates.yaml` |
| `Registres/` | Journaux JSONL append-only hash-chaînés (preuves) |
| `Docs/` | Documentation Diátaxis |
| `src/` | Code du Toolkit |
| `tests/` | Tests (TDD strict — une fonctionnalité sans test n'existe pas) |
| `reviews/` | Verdicts de revue aveugle scellés (`<étape>/<modèle>.verdict.json`) |
| `Sandbox/` | Expérimentations jetables — jamais mergées dans `src/` |
| `scripts/` | Outillage de gouvernance (registre, no-stub-scan, tally) |

## Gates (§8bis — aucun stub, aucun faux)

```bash
python3 scripts/no_stub_scan.py --all      # scan stubs/marqueurs interdits
python3 scripts/registre.py verify Registres/mission.jsonl
pytest                                      # tests
```

Tout passe par PR. Zéro commit direct sur `main` une fois la branch protection active.
