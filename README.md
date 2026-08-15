# ForgeAI Toolkit

Déployeur de référence d'infrastructures IA agentiques : wizard hardware-aware,
catalogue <!-- state:catalogue.entries_total -->1576<!-- /state --> entrées bilingue (FR/EN), multi-nœuds (Tailscale), gouvernance intégrée.

> Hiérarchie d'autorité de ce dépôt : [governance/AUTHORITY-MAP.md](governance/AUTHORITY-MAP.md).

## Installation (n'importe quelle machine, Python ≥3.10)

```bash
pip install forgeai-toolkit          # cœur sans aucune dépendance (stdlib pur)

forgeai doctor                       # que peut faire VOTRE machine ?
forgeai web                          # interface web (stdlib, aucune dépendance)
```

`forgeai doctor` sonde votre environnement (CPU/GPU, Docker, kubectl/cluster, Ollama)
et rapporte quels profils et backends de déploiement sont disponibles — le Toolkit
s'adapte à ce que vous avez, sans exiger de stack particulière. Le catalogue voyage
dans le paquet : aucune donnée externe requise.

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

## Développement (sécurité pre-commit)

Activez la vérification locale des secrets avant chaque commit :

```bash
pip install -e ".[dev]"
pre-commit install
ggshield auth login   # authentification interactive locale — NE JAMAIS committer de token
```

**Important :** Le token d'authentification GitGuardian (`GITGUARDIAN_API_KEY` ou équivalent) est strictement local. Ne le committez jamais et ne le placez jamais en clair dans le dépôt ni dans une variable d'environnement partagée.

## État de la mission

_État courant : voir le registre `Registres/mission.jsonl` (chaîne sha256 vérifiée)._

**P1 PROUVÉE** — machine nue → RAG fonctionnel, sur les deux backends :

```bash
PYTHONPATH=src python3 -m forgeai wizard --ci \
  --document tests/fixtures/rag/faits_forgeai.txt \
  --question "Quelle version minimale de Python est exigée par le ForgeAI Toolkit ?" \
  --expected-fact "3.10" --workdir run/p1 --teardown          # backend Compose
# … --backend k3s                                              # parité K3s
```

Preuves scellées : `Registres/mission.jsonl` (chaîne sha256 vérifiée) — e2e Compose
`CI_WITNESS=2a0b6221…`, e2e K3s `CI_WITNESS=bf9e40c7…`. Couverture <!-- state:observations.coverage.global -->94<!-- /state --> % (registre <!-- state:observations.coverage.registre -->98<!-- /state --> %),
revue aveugle code 3/3 APPROVE (vendors non-Anthropic). Le multi-nœuds est livré (<!-- state:cli.subcommands_by_group.node -->7<!-- /state --> sous-commandes `forgeai node`) et les
traductions EN sont complètes (<!-- state:catalogue.descriptions_en_missing -->0<!-- /state --> `description_en` vide sur <!-- state:catalogue.entries_total -->1576<!-- /state --> briques) : l'ancien BLOCKED
sur la revue sécurité multi-nœuds est levé. Voir `Docs/reference/cli.md` pour la surface CLI.
