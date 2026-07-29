"""Schémas de données centraux (architecture GLM, Phase-A/architecture-glm.md)."""
from __future__ import annotations

import json
import unicodedata
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional


def _rejeter_caracteres_de_controle(nom_champ: str, valeur: str) -> None:
    """Lève ValueError si `valeur` contient un caractère de contrôle Unicode (catégorie Cc,
    soit \\x00–\\x1f et \\x7f — couvre \\n, \\r, \\t). Ces champs sont interpolés en brut dans
    le YAML/Compose rendu (renderers/k3s.py, renderers/compose.py) ; un caractère de contrôle
    y permettrait d'injecter des documents arbitraires. Le message nomme le champ fautif mais
    ne reproduit PAS la valeur complète (anti-fuite du payload dans les logs)."""
    for position, caractere in enumerate(valeur):
        if unicodedata.category(caractere) == "Cc":
            raise ValueError(
                f"champ '{nom_champ}' contient un caractère de contrôle "
                f"à la position {position} : {caractere!r}")


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


import re

# Ces valeurs proviennent de l'ADR RES-012A. Toute révision passe par une évolution de table relue.
_CLASSES_RESSOURCES: dict[str, dict[str, dict[str, str]]] = {
    "llm": {
        "requests": {"cpu": "1000m", "memory": "4Gi"},
        "limits": {"cpu": "4000m", "memory": "8Gi"},
    },
    "db": {
        "requests": {"cpu": "250m", "memory": "512Mi"},
        "limits": {"cpu": "1000m", "memory": "2Gi"},
    },
    "sidecar": {
        "requests": {"cpu": "100m", "memory": "128Mi"},
        "limits": {"cpu": "500m", "memory": "512Mi"},
    },
    "utilitaire": {
        "requests": {"cpu": "50m", "memory": "64Mi"},
        "limits": {"cpu": "250m", "memory": "256Mi"},
    },
}

def _cpu_en_milli(valeur: str) -> int:
    """Convertit une chaîne CPU en milliCPU (entier) pour comparaison numérique.
    
    La comparaison lexicale échouerait pour des valeurs comme '1000m' vs '2' (car '2' > '1' lexicalement).
    Il faut donc normaliser en entiers."""
    if valeur.endswith('m'):
        return int(valeur[:-1])
    else:
        return int(valeur) * 1000

def _memoire_en_mib(valeur: str) -> int:
    """Convertit une chaîne mémoire en MiB (entier) pour comparaison numérique.
    
    Même raison que pour le CPU : une comparaison lexicale serait incorrecte ('1Gi' > '1024Mi' lexicalement)."""
    if valeur.endswith('Gi'):
        return int(valeur[:-2]) * 1024
    elif valeur.endswith('Mi'):
        return int(valeur[:-2])
    else:
        # Ne devrait pas arriver car déjà validé, mais sécurité
        raise ValueError(f"Format mémoire inattendu : {valeur}")

def _resoudre_ressources(resource_class: str, resources: dict | None) -> dict:
    """Résout les ressources effectives à partir d'une classe et d'une éventuelle dérogation.
    Retourne toujours un dictionnaire non None."""
    # a) Vérification de la classe
    if resource_class not in _CLASSES_RESSOURCES:
        classes_admises = ", ".join(_CLASSES_RESSOURCES.keys())
        raise ValueError(f"ERR_RES_CLASSE_INCONNUE: classe '{resource_class}' inconnue. Admises : {classes_admises}")

    # b) Aucune dérogation -> copie des valeurs de la classe
    if resources is None:
        return {k: v.copy() for k, v in _CLASSES_RESSOURCES[resource_class].items()}

    # c) Dérogation présente : vérification des quatre champs obligatoires
    erreurs = []
    if "requests" not in resources or "cpu" not in resources.get("requests", {}):
        erreurs.append("requests.cpu")
    if "requests" not in resources or "memory" not in resources.get("requests", {}):
        erreurs.append("requests.memory")
    if "limits" not in resources or "cpu" not in resources.get("limits", {}):
        erreurs.append("limits.cpu")
    if "limits" not in resources or "memory" not in resources.get("limits", {}):
        erreurs.append("limits.memory")
    if erreurs:
        raise ValueError(f"ERR_RES_DEROGATION_PARTIELLE: champs manquants dans la dérogation : {', '.join(erreurs)}")

    # d) Validation des formats CPU et mémoire
    cpu_re = re.compile(r'^\d+m?$')
    mem_re = re.compile(r'^\d+(Mi|Gi)$')

    req_cpu = resources["requests"]["cpu"]
    req_mem = resources["requests"]["memory"]
    lim_cpu = resources["limits"]["cpu"]
    lim_mem = resources["limits"]["memory"]

    for nom, val in [("requests.cpu", req_cpu), ("limits.cpu", lim_cpu)]:
        if not cpu_re.match(val):
            raise ValueError(f"ERR_RES_CPU_INVALIDE: '{val}' pour {nom} n'est pas un entier avec suffixe optionnel m.")
    for nom, val in [("requests.memory", req_mem), ("limits.memory", lim_mem)]:
        if not mem_re.match(val):
            raise ValueError(f"ERR_RES_MEMOIRE_INVALIDE: '{val}' pour {nom} n'est pas un entier suivi de Mi ou Gi.")

    # e) Cohérence limits >= requests (comparaison numérique normalisée)
    req_cpu_milli = _cpu_en_milli(req_cpu)
    lim_cpu_milli = _cpu_en_milli(lim_cpu)
    req_mem_mib = _memoire_en_mib(req_mem)
    lim_mem_mib = _memoire_en_mib(lim_mem)

    if lim_cpu_milli < req_cpu_milli:
        raise ValueError(f"ERR_RES_LIMITS_INFERIEURES: limits.cpu ({lim_cpu}) < requests.cpu ({req_cpu})")
    if lim_mem_mib < req_mem_mib:
        raise ValueError(f"ERR_RES_LIMITS_INFERIEURES: limits.memory ({lim_mem}) < requests.memory ({req_mem})")

    # Tout est valide, retourner le dictionnaire de ressources tel quel
    return resources


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
    gpu_vendor: Optional[str] = None  # "nvidia"|"amd"|"intel" — réservation GPU au rendu
    depends: tuple[str, ...] = ()
    command: tuple[str, ...] = ()  # arguments passés à l'entrypoint du conteneur (ex. litellm --config …)
    node: Optional[str] = None  # nœud cible de CE service (hostname K3s) ; None = suit le nœud global du plan ou le scheduler
    # RES-012B / ADR RES-012A — schéma de ressources. Ajoutés APRÈS `node` pour ne casser
    # aucun appel positionnel existant. `resources` (dérogation) prime sur `resource_class`.
    resource_class: str = "utilitaire"
    resources: Optional[dict] = None

    def __post_init__(self) -> None:
        # SEC-YAML-INJECT — suivi de #151 : ces scalaires atteignent en brut le YAML/Compose.
        # Le renderer compose n'a pas de `_safe`, donc défense à la source = couverture de
        # tous les renderers ; dataclass frozen : lecture de self.* autorisée en __post_init__.
        _rejeter_caracteres_de_controle("name", self.name)
        _rejeter_caracteres_de_controle("image", self.image)
        if self.healthcheck_url is not None:
            _rejeter_caracteres_de_controle("healthcheck_url", self.healthcheck_url)
        if self.node is not None:
            _rejeter_caracteres_de_controle("node", self.node)
        for i, volume in enumerate(self.volumes):
            _rejeter_caracteres_de_controle(f"volumes[{i}]", volume)
        for i, arg in enumerate(self.command):
            _rejeter_caracteres_de_controle(f"command[{i}]", arg)
        # Résolution fail-fast : aucun spec invalide ne peut exister, quel que soit le
        # renderer. Le renderer lit EXCLUSIVEMENT `ressources_effectives` — il ne contient
        # plus aucun magic number et ne valide rien. Dataclass frozen -> object.__setattr__.
        object.__setattr__(self, "ressources_effectives",
                           _resoudre_ressources(self.resource_class, self.resources))
        for i, dep in enumerate(self.depends):
            _rejeter_caracteres_de_controle(f"depends[{i}]", dep)
        for cle, valeur in self.env.items():
            _rejeter_caracteres_de_controle("env (clé)", cle)
            _rejeter_caracteres_de_controle(f"env[{cle}]", valeur)


@dataclass(frozen=True)
class DeploymentPlan:
    plan_id: str
    profile: str  # ex. "minimal-gpu-cuda", "minimal-cpu"
    target: RenderTarget
    services: tuple[ServiceSpec, ...]
    model: str  # modèle LLM par défaut (décision T3 : Ollama)
    embed_model: str

    def __post_init__(self) -> None:
        # SEC-YAML-INJECT — durcissement à la source : ces scalaires atteignent en brut le
        # YAML/Compose rendu. Rejet (pas nettoyage) des caractères de contrôle, dès la
        # construction, pour protéger tous les renderers actuels et futurs (dataclass frozen :
        # lecture de self.* autorisée en __post_init__).
        _rejeter_caracteres_de_controle("plan_id", self.plan_id)
        _rejeter_caracteres_de_controle("profile", self.profile)
        _rejeter_caracteres_de_controle("model", self.model)
        _rejeter_caracteres_de_controle("embed_model", self.embed_model)

    def to_json(self) -> str:
        data = asdict(self)
        data["target"] = self.target.value
        return json.dumps(data, ensure_ascii=False, indent=2)
