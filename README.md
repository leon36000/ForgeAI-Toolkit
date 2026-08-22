# ForgeAI Toolkit

Déployeur de référence d'infrastructures IA agentiques : wizard hardware-aware,
catalogue <!-- state:catalogue.entries_total -->1576<!-- /state --> entrées bilingue (FR/EN), multi-nœuds (Tailscale), gouvernance intégrée.

> Hiérarchie d'autorité de ce dépôt : [governance/AUTHORITY-MAP.md](governance/AUTHORITY-MAP.md).

## Statut de distribution (RC1 vs v1.0)

Le projet distingue explicitement deux jalons canoniques distincts :

* **RC1 (Palier distribuable)** — suivi via l'issue #428 :
  viser un palier diffusable et installable, sans prétendre que les 25 exigences canoniques
  sont déjà toutes certifiées. Statut vivant : voir le registre de mission.
* **v1.0 (Conformité canonique intégrale)** — suivi via l'issue #429 :
  viser la certification complète des 25 exigences du canon, après clôture de la RC1.
  Les statuts par exigence (`CERTIFIED`, `PARTIAL`, `FAILED`, `AUTHORIZED_CHANGED`,
  `BLOCKED_WITH_REASON`) sont tracés dans le registre de preuves.

Ni `RC1_DISTRIBUTABLE_CERTIFIED` ni `V1_CANON_COMPLIANT` ne sont affirmés comme atteints
aujourd'hui.

## Installation

> **État réel de publication :** Le paquet n'est pas encore publié sur l'index public PyPI.
> L'installation s'effectue localement depuis un clone du dépôt. Le gate d'installabilité
> wheel/sdist autonome (hors checkout) est suivi séparément dans l'issue #448.

### Installation locale (Python ≥3.10, cœur stdlib pur sans dépendance)

```bash
git clone https://github.com/leon36000/ForgeAI-Toolkit.git
cd ForgeAI-Toolkit

pip install -e .                     # installation locale du cœur (stdlib pur)

forgeai doctor                       # que peut faire VOTRE machine ?
forgeai web                          # interface web (stdlib, aucune dépendance)
```

`forgeai doctor` sonde votre environnement (CPU/GPU, Docker, kubectl/cluster, Ollama)
et rapporte quels profils et backends de déploiement sont disponibles — le Toolkit
s'adapte à ce que vous avez, sans exiger de stack particulière. Le catalogue voyage
dans le paquet : aucune donnée externe requise.

Pour les capacités de GOUVERNANCE du dépôt, distinctes du diagnostic de déploiement produit,
lancez :

```bash
python3 scripts/governance/capabilities.py
```

Construit via la méthodologie **BMAD**, exécuté par une équipe de modèles orchestrée
dans Claude Code (l'orchestrateur en session), routée par le gateway LiteLLM local
(`forge-model-bridge`). Plan de référence : [CANON/PLAN-MAITRE-EXECUTION-BMAD-v1.0.md](CANON/PLAN-MAITRE-EXECUTION-BMAD-v1.0.md).

## Support matrix et limites connues

| Axe | Statut CI | Détails & Limites |
|---|---|---|
| **Python** | 3.10, 3.11, 3.12, 3.13 | Matrice complète testée sous `ubuntu-latest`. |
| **Linux (Ubuntu)** | Support complet | Suite complète pytest et gates de gouvernance exécutés en CI. |
| **macOS / Windows** | Support partiel (limite connue) | Seul le sous-système de garde filesystem et de verrouillage portable (`guard-fs-multi-os`) est validé en CI sous macOS et Windows. L'exécution complète du Toolkit sur ces plateformes n'est pas garantie au stade actuel. |
| **PyPI** | Non publié | Distribution via clone local exclusivement pour le moment (cf. #448). |

Pour diagnostiquer les outils et capacités disponibles sur votre machine locale :

```bash
python3 scripts/governance/capabilities.py
```

## Structure canonique

| Répertoire | Rôle |
|---|---|
| `governance/` | Canon, décisions, méthode et artefacts de gouvernance |
| `CANON/` | Documents de référence gelés (plan maître, annexes) |
| `manifests/` | Plan machine-lisible : `roles.yaml`, `routes.yaml`, `phases.yaml`, `bricks.yaml`, `gates.yaml` |
| `evidence/registres/` | Journaux JSONL append-only hash-chaînés (preuves) |
| `Docs/` | Racine de la documentation active, organisée selon Diátaxis |
| `stories/` | Artefacts de gouvernance des stories |
| `src/` | Code du Toolkit |
| `tests/` | Tests (TDD strict — une fonctionnalité sans test n'existe pas) |
| `evidence/reviews/` | Verdicts de revue aveugle scellés (`<étape>/<modèle>.verdict.json`) |
| `Sandbox/` | Expérimentations jetables — jamais mergées dans `src/` |
| `scripts/` | Outillage de gouvernance (registre, no-stub-scan, tally) |

`Docs/` est la racine de la documentation active ; `governance/` porte le canon et les décisions.

## Gates (§8bis — aucun stub, aucun faux)

`python3 scripts/governance/capabilities.py` diagnostique localement quelles capacités sont
disponibles — ce n'est PAS lui-même un gate CI, juste un point d'entrée avant de lancer les
gates ci-dessous :

```bash
python3 scripts/no_stub_scan.py --all       # scan stubs/marqueurs interdits
python3 scripts/registre.py verify evidence/registres/mission.jsonl
pytest                                      # tests
```

Ces commandes sont un sous-ensemble des gates CI réels ; `.github/workflows/gates.yml` est la
source de vérité pour leur liste complète. Tout passe par PR. Zéro commit direct sur `main` une
fois la branch protection active.

## Développement et sécurité

Consultez le guide de contribution [CONTRIBUTING.md](CONTRIBUTING.md) et la politique de sécurité [SECURITY.md](SECURITY.md).

Activez la vérification locale des secrets avant chaque commit :

```bash
pip install -e ".[dev]"
pre-commit install
ggshield auth login   # authentification interactive locale — NE JAMAIS committer de token
```

**Important :** Le token d'authentification GitGuardian (`GITGUARDIAN_API_KEY` ou équivalent) est strictement local. Ne le committez jamais et ne le placez jamais en clair dans le dépôt ni dans une variable d'environnement partagée.

`gitleaks` en CI reste le gate de secrets faisant autorité, indépendamment de la disponibilité
locale de `ggshield` ou de `pre-commit`.

## Liens utiles et gouvernance

* **Gouvernance & Méthode :** [governance/AUTHORITY-MAP.md](governance/AUTHORITY-MAP.md), [AGENTS.md](AGENTS.md)
* **Plan d'exécution maître :** [CANON/PLAN-MAITRE-EXECUTION-BMAD-v1.0.md](CANON/PLAN-MAITRE-EXECUTION-BMAD-v1.0.md)
* **Documentation :** [Docs/](Docs/) (organisée selon Diátaxis), Référence CLI : [Docs/reference/cli.md](Docs/reference/cli.md)
* **Contribution :** [CONTRIBUTING.md](CONTRIBUTING.md)
* **Sécurité :** [SECURITY.md](SECURITY.md)
* **Licence :** [LICENSE](LICENSE) (Apache-2.0)

## État de la mission

_État courant : voir le registre `evidence/registres/mission.jsonl` (chaîne sha256 vérifiée)._

**P1 PROUVÉE** — machine nue → RAG fonctionnel, sur les deux backends :

```bash
PYTHONPATH=src python3 -m forgeai wizard --ci \
  --document tests/fixtures/rag/faits_forgeai.txt \
  --question "Quelle version minimale de Python est exigée par le ForgeAI Toolkit ?" \
  --expected-fact "3.10" --workdir run/p1 --teardown          # backend Compose
# … --backend k3s                                              # parité K3s
```

Preuves scellées : `evidence/registres/mission.jsonl` (chaîne sha256 vérifiée) — e2e Compose
`CI_WITNESS=2a0b6221…`, e2e K3s `CI_WITNESS=bf9e40c7…`. Couverture minimale exigée et vérifiée en CI : seuil global `--cov-fail-under=85` sur `src/forgeai` et `--fail-under=95` sur le sous-système de registre (`src/forgeai/core/registre.py`),
revue active <!-- state:governance.review_quorum -->1/1 Sol (sol_blind); historique multi_vendor 3/3<!-- /state --> APPROVE (contrat Luna/Sol; multi_vendor historique). Le multi-nœuds est livré (<!-- state:cli.subcommands_by_group.node -->7<!-- /state --> sous-commandes `forgeai node`) et les
traductions EN sont complètes (<!-- state:catalogue.descriptions_en_missing -->0<!-- /state --> `description_en` vide sur <!-- state:catalogue.entries_total -->1576<!-- /state --> briques) : l'ancien BLOCKED
sur la revue sécurité multi-nœuds est levé. Voir `Docs/reference/cli.md` pour la surface CLI (<!-- state:cli.subcommands_total -->49<!-- /state --> sous-commandes au total sur <!-- state:catalogue.categories_total -->14<!-- /state --> catégories).
