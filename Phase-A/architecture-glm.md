<!-- Livrable Phase A — §1 plan maître
membre: glm (GLM-5.2 via forge-model-bridge, provider_id=glm52)
date: 2026-07-14 | statut: DONE | claim: UNVERIFIED (revue aveugle à venir au plan-freeze)
note Fable: produit en 2 lots (la route glm52 timeout au-delà de ~90 lignes de sortie).
-->
# Architecture ForgeAI Toolkit

## 1. Arborescence src/ — modules Python avec responsabilité une phrase chacun
```text
src/
├── tui/              # Interface textuelle (wizard) guidant l'utilisateur dans la sélection et le déploiement.
├── hardware/         # Détecte et collecte les caractéristiques physiques (CPU, RAM, GPU, disques) de la machine hôte.
├── catalogue/        # Charge, valide et gère les 1021 briques depuis les registres JSONL hash-chaînés.
├── rag/              # Indexe les briques et fournit un moteur de recherche sémantique pour le LLM (P1).
├── planner/          # Génère le plan de déploiement en croisant l'inventaire matériel avec les contraintes des briques.
├── renderers/        # Transforme le plan d'exécution en fichiers Docker Compose ou manifests K3s.
├── network/          # Configure et gère le maillage multi-nœuds via Tailscale.
└── core/             # Centralise les utilitaires, la configuration globale et les structures de données partagées.
```

## 2. Schémas de données — dataclasses Python complètes avec champs typés
```python
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional

class RenderTarget(Enum):
    COMPOSE = "docker-compose"
    K3S = "k3s"

@dataclass
class HardwareProfile:
    cpu_cores: int
    cpu_arch: str
    ram_gb: float
    os: str
    gpus: list[dict] = field(default_factory=list) # e.g., [{"name": "RTX 3090", "vram_gb": 24}]
    disks: list[dict] = field(default_factory=list) # e.g., [{"path": "/", "gb": 500}]

@dataclass
class Brick:
    id: str
    name_fr: str
    name_en: str
    category: str
    atlas_status: str # e.g., "stable", "beta"
    hw_constraints: dict # e.g., {"min_ram_gb": 4, "gpu_required": False}
    images: list[str]
    dependencies: list[str] = field(default_factory=list)

@dataclass
class NodeSpec:
    hostname: str
    hardware: HardwareProfile
    tailscale_ip: Optional[str] = None
    roles: list[str] = field(default_factory=list) # e.g., ["master", "worker"]

@dataclass
class DeploymentPlan:
    plan_id: str
    target: RenderTarget
    bricks: list[Brick]
    nodes: list[NodeSpec]
    network_config: dict = field(default_factory=dict)
```

## 3. API des hooks internes

Les points d'extension du pipeline utilisent des alias de types `Callable` pour injecter la logique personnalisée via le module `src.core`.

```python
from typing import Callable, Any
from src.core import HardwareProfile, Brick, DeploymentPlan, RenderTarget

# Exécuté avant la détection matérielle (ex: simulation, pré-config)
PreDetectHook = Callable[[HardwareProfile], HardwareProfile]
# Exécuté après la détection (ex: surcharge de RAM, filtrage GPU)
PostDetectHook = Callable[[HardwareProfile], HardwareProfile]
# Filtre les briques du catalogue selon le profil et l'historique RAG
SelectionFilter = Callable[[list[Brick], HardwareProfile], list[Brick]]
# Transforme le plan de déploiement en configuration finale (string)
RenderTransformer = Callable[[DeploymentPlan, RenderTarget], str]
# Étapes personnalisées de validation ou de pré-déploiement
DeployStep = Callable[[DeploymentPlan, RenderTarget], bool]
# Émetteur de preuve pour le registre hash-chaîné
ProofEmitter = Callable[[str, dict[str, Any]], None]
```

## 4. Flux bout-en-bout

1. Lancement du wizard interactif via `src.tui`.
2. Exécution des `PreDetectHook` (pré-configuration de l'environnement).
3. Détection du matériel via `src.hardware` produisant un `HardwareProfile`.
4. Exécution des `PostDetectHook` (ajustements de seuils ou exclusions).
5. Sélection des `Brick` depuis `src.catalogue` en appliquant le `SelectionFilter`.
6. Génération du `DeploymentPlan` (incluant les `NodeSpec`) par `src.planner`.
7. Application du `RenderTransformer` via `src.renderers` selon le `RenderTarget`.
8. Validation syntaxique et sémantique de l'artefact généré (docker-compose / k3s).
9. Déploiement via `src.network` avec exécution séquentielle des `DeployStep`.
10. Collecte des statuts de déploiement et des journaux d'exécution distants.
11. Génération du hachage SHA-256 chaîné avec l'entrée précédente du registre.
12. Persistance de la preuve via `ProofEmitter` dans le registre JSONL par `src.core`.

## 5. ADR

ADR-1 : Dataclasses immuables (frozen=True) — Préserve l'intégrité des données traversant les étapes du pipeline.
ADR-2 : Registres JSONL hash-chaînés — Garantit la traçabilité et la non-répudiation des preuves de déploiement.
ADR-3 : Hooks typés via `Callable` — Permet l'extensibilité du pipeline sans modifier le cœur métier de `src.core`.
ADR-4 : Énumération `RenderTarget(COMPOSE|K3S)` — Découple la planification logique de l'infrastructure physique cible.
ADR-5 : Module RAG isolé dans `src.rag` — Allège l'empreinte mémoire pour les déploiements en mode autonomie stricte.
ADR-6 : Boucle événementielle asyncio dans `src.tui` — Maintient la réactivité de l'UI lors des appels réseau bloquants de `src.network`.
