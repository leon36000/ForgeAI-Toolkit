"""Schémas de données centraux (architecture GLM, Phase-A/architecture-glm.md)."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional


class RenderTarget(Enum):
    COMPOSE = "docker-compose"
    K3S = "k3s"


@dataclass(frozen=True)
class GPU:
    vendor: str  # "nvidia" | "amd" | "intel"
    name: str
    vram_mb: int


@dataclass(frozen=True)
class Disk:
    path: str
    total_gb: float
    free_gb: float


@dataclass(frozen=True)
class HardwareProfile:
    cpu_model: str
    cpu_cores: int
    cpu_arch: str
    ram_gb: float
    os_name: str
    gpus: tuple[GPU, ...] = ()
    disks: tuple[Disk, ...] = ()

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)


@dataclass(frozen=True)
class Brick:
    id: str
    name_fr: str
    name_en: str
    category: str
    atlas_status: str
    description_fr: str
    description_en: Optional[str]  # None = traduction en attente (état documenté, P2)
    source_url: Optional[str]
    hw_constraints: dict[str, Any] = field(default_factory=dict)
    images: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()


@dataclass(frozen=True)
class NodeSpec:
    hostname: str
    hardware: HardwareProfile
    tailscale_ip: Optional[str] = None
    roles: tuple[str, ...] = ()


@dataclass(frozen=True)
class ServiceSpec:
    """Service concret d'un plan de déploiement (brique instanciée)."""
    name: str
    image: str
    host_port: int
    container_port: int
    volumes: tuple[str, ...] = ()
    env: dict[str, str] = field(default_factory=dict)
    healthcheck_url: Optional[str] = None
    gpu: bool = False
    depends: tuple[str, ...] = ()
    node: Optional[str] = None  # nœud cible de CE service (hostname K3s) ; None = suit le nœud global du plan ou le scheduler


@dataclass(frozen=True)
class DeploymentPlan:
    plan_id: str
    profile: str  # ex. "minimal-gpu-cuda", "minimal-cpu"
    target: RenderTarget
    services: tuple[ServiceSpec, ...]
    model: str  # modèle LLM par défaut (décision T3 : Ollama)
    embed_model: str

    def to_json(self) -> str:
        data = asdict(self)
        data["target"] = self.target.value
        return json.dumps(data, ensure_ascii=False, indent=2)
