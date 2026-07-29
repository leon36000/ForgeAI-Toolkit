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


class PlacementError(ValueError):
    """Levée lorsqu'un placement est refusé AVANT rendu : aucun nœud de
    l'inventaire ne peut honorer les contraintes du service. Refuser ici
    évite l'émission d'un manifeste voué à l'échec silencieux au scheduling
    k3s : la validation sort de l'inventaire, pas du cluster.
    """


@dataclass(frozen=True)
class NodeInventaire:
    hostname: str
    gpu_vendor: Optional[str] = None
    vram_mib: int = 0

    def __post_init__(self) -> None:
        if not self.hostname or not self.hostname.strip():
            raise ValueError(
                "ERR_PLACE_HOSTNAME_INVALIDE : hostname vide ou uniquement des espaces")
        _rejeter_caracteres_de_controle("hostname", self.hostname)
        if self.vram_mib < 0:
            raise ValueError(
                f"ERR_PLACE_VRAM_INVALIDE : vram_mib négatif ({self.vram_mib}), "
                f"attendu entier >= 0")
        vendors_autorises = {"nvidia", "amd", "intel", None}
        if self.gpu_vendor not in vendors_autorises:
            raise ValueError(
                f"ERR_PLACE_VENDOR_INCONNU : vendor '{self.gpu_vendor}' "
                f"inconnu (autorisés : nvidia, amd, intel, None)")


def valider_placement(svc, inventaire, node_demande):
    # Pas d'inventaire : on ne peut rien valider, on laisse passer pour ne
    # pas casser la rétro-compatibilité — c'est une absence d'information,
    # pas une rupture de contrat. Le scheduling k3s tranchera.
    # Distinction sémantique entre absence d'inventaire et inventaire vide :
    #   - None  = « je ne sais pas » (aucune info fournie, rétro-compatibilité : on laisse passer)
    #   - ()    = « je sais, et il n'y a rien » (l'appelant AFFIRME qu'aucun nœud n'est dispo)
    if inventaire is None:
        return node_demande

    if not inventaire:
        # Inventaire explicite mais vide : on ne peut honorer un service GPU,
        # mais un service CPU n'a pas besoin d'un nœud particulier.
        if getattr(svc, "gpu", False):
            raise PlacementError(
                "ERR_PLACE_AUCUN_NOEUD_QUALIFIE : l'inventaire fourni ne contient "
                "aucun nœud, placement d'un service GPU impossible")
        return node_demande

    # Service CPU : le vendor d'un nœud ne le concerne jamais. Aucune raison
    # de contraindre un service sans GPU sur un hôte GPU-only.
    if not svc.gpu:
        return node_demande

    hostnames = tuple(n.hostname for n in inventaire)

    if node_demande is not None and node_demande != "auto":
        # Nœud explicitement demandé : on l'audite point par point.
        noeud = next(
            (n for n in inventaire if n.hostname == node_demande), None)
        if noeud is None:
            raise PlacementError(
                f"ERR_PLACE_NOEUD_INCONNU : nœud '{node_demande}' absent de "
                f"l'inventaire (connus : {', '.join(hostnames) or 'aucun'})")
        if noeud.gpu_vendor is None:
            raise PlacementError(
                f"ERR_PLACE_CPU_ONLY : le service '{svc.name}' exige un GPU "
                f"(vendor demandé : {svc.gpu_vendor}) mais le nœud "
                f"'{noeud.hostname}' est CPU-only")
        if svc.gpu_vendor is not None and noeud.gpu_vendor != svc.gpu_vendor:
            raise PlacementError(
                f"ERR_PLACE_VENDOR_INCOMPATIBLE : service '{svc.name}' "
                f"demande le vendor '{svc.gpu_vendor}' mais le nœud "
                f"'{noeud.hostname}' expose '{noeud.gpu_vendor}'")
        if (svc.vram_min_mib is not None
                and svc.vram_min_mib > noeud.vram_mib):
            raise PlacementError(
                f"ERR_PLACE_VRAM_INSUFFISANTE : service '{svc.name}' exige "
                f"{svc.vram_min_mib} Mio de VRAM mais le nœud "
                f"'{noeud.hostname}' n'en expose que {noeud.vram_mib} Mio")
        return node_demande

    # Mode auto : parcours déterministe, on retient le PREMIER nœud dont le
    # vendor correspond ET dont la VRAM suffit. L'ordre de l'inventaire est
    # l'ordre de préférence : c'est l'auteur du manifeste qui le fixe.
    candidats_examines = []
    for noeud in inventaire:
        raison = None
        if noeud.gpu_vendor is None:
            raison = "CPU-only"
        elif (svc.gpu_vendor is not None
              and noeud.gpu_vendor != svc.gpu_vendor):
            raison = f"vendor '{noeud.gpu_vendor}' ≠ demandé '{svc.gpu_vendor}'"
        elif (svc.vram_min_mib is not None
              and svc.vram_min_mib > noeud.vram_mib):
            raison = (f"VRAM {noeud.vram_mib} Mio < requise "
                      f"{svc.vram_min_mib} Mio")
        if raison is None:
            return noeud.hostname
        candidats_examines.append(f"{noeud.hostname} ({raison})")

    vram_requise = (f", VRAM requise {svc.vram_min_mib} Mio"
                    if svc.vram_min_mib is not None else "")
    raise PlacementError(
        f"ERR_PLACE_AUCUN_NOEUD_QUALIFIE : aucun nœud ne convient pour le "
        f"service '{svc.name}' (vendor recherché : {svc.gpu_vendor}"
        f"{vram_requise}). Nœuds examinés : "
        f"{'; '.join(candidats_examines) or 'aucun'}")


class QuotaError(ValueError):
    """Le plan dépasse la capacité déclarée du cluster.

    Levée AVANT rendu du manifeste pour éviter qu'un déploiement trop gros
    ne se traduise par des pods ``Pending`` sans cause lisible côté kubectl.
    Le message chiffre systématiquement le besoin du plan et la capacité
    offerte par le cluster afin qu'un opérateur corrige l'un ou l'autre
    sans avoir à recalculer.
    """


@dataclass(frozen=True)
class CapaciteCluster:
    """Capacité totale (CPU + mémoire) qu'un cluster déclare pouvoir servir.

    Les valeurs sont normalisées en milliCPU et en MiB pour permettre une
    comparaison arithmétique directe avec le budget d'un ``DeploymentPlan``.
    Une capacité nulle ou négative n'a aucun sens physique : elle est refusée
    à l'instanciation pour ne pas produire plus tard une division par zéro
    ou un faux positif de dépassement.
    """

    cpu_millicores: int
    memoire_mib: int

    def __post_init__(self) -> None:
        if self.cpu_millicores <= 0 or self.memoire_mib <= 0:
            raise ValueError(
                "ERR_QUOTA_CAPACITE_INVALIDE: la capacité du cluster doit être "
                f"strictement positive (reçu cpu={self.cpu_millicores}, "
                f"memoire={self.memoire_mib} Mi)."
            )


class ProbeType(Enum):
    """Type de sonde de santé applicable à un service."""
    HTTP = "http"   # Sonde HTTP : GET sur une URL, vérifie le code de retour
    TCP = "tcp"     # Sonde TCP : ouvre une connexion sur un port, vérifie le transport
    EXEC = "exec"   # Sonde par exécution : lance un binaire interne, vérifie son code de sortie
    NONE = "none"   # Aucune sonde : le service n'expose aucune vérification automatique


class HealthState(Enum):
    """États de santé d'un service.

    TRANSPORT_READY n'est PAS un état prêt au sens fonctionnel : un port ouvert
    prouve uniquement que le transport répond (TCP/HTTP au niveau réseau), mais ne
    garantit pas que l'application traite correctement les requêtes. Seul
    FUNCTIONALLY_READY atteste qu'une sonde applicative a renvoyé une réponse valide.
    """
    FUNCTIONALLY_READY = "functionally_ready"   # réponse applicative correcte (sonde métier réussie)
    TRANSPORT_READY = "transport_ready"         # transport joignable, applicatif NON prouvé
    UNKNOWN = "unknown"                         # aucune preuve disponible (pas de sonde exécutée)
    FAILED = "failed"                           # preuve d'échec ou contrat de santé violé


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
    vram_min_mib: Optional[int] = None  # VRAM minimale exigée par ce service, validée contre l'inventaire au rendu.
    health_required: bool = False                   # service critique : sa santé conditionne le READY global
    probe_type: Optional[ProbeType] = None          # type de sonde ; None = à dériver ailleurs (ex: healthcheck_url)
    probe_target: Optional[Union[str, tuple]] = None  # str pour http/tcp ; argv (tuple) pour exec
    http_success_codes: tuple = (200,)              # codes HTTP acceptés comme probe_pass (entre 100 et 599)
    health_timeout_s: float = 5.0                   # durée max d'une sonde individuelle (secondes, strictement positif)
    health_interval_s: float = 5.0                  # délai entre deux tentatives de sonde (secondes, strictement positif)
    health_retries: int = 12                        # nombre de tentatives avant d'abandonner (entier strictement positif)

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
        # --- validation du contrat de santé ---
        # Les durées doivent être strictement positives (sinon la boucle d'attente diverge ou expire immédiatement).
        if self.health_timeout_s <= 0:
            raise ValueError(
                f"ERR_HEALTH_DUREE_INVALIDE: health_timeout_s={self.health_timeout_s!r} "
                f"doit être strictement positif."
            )
        if self.health_interval_s <= 0:
            raise ValueError(
                f"ERR_HEALTH_DUREE_INVALIDE: health_interval_s={self.health_interval_s!r} "
                f"doit être strictement positif."
            )
        # Le nombre de tentatives doit être strictement positif.
        if self.health_retries <= 0:
            raise ValueError(
                f"ERR_HEALTH_RETRIES_INVALIDE: health_retries={self.health_retries!r} "
                f"doit être un entier strictement positif."
            )
        # Les codes HTTP acceptés : tuple non vide, chaque code entier entre 100 et 599.
        if not self.http_success_codes:
            raise ValueError(
                "ERR_HEALTH_CODE_INVALIDE: http_success_codes ne peut pas être vide."
            )
        for code in self.http_success_codes:
            if not isinstance(code, int) or isinstance(code, bool) or code < 100 or code > 599:
                raise ValueError(
                    f"ERR_HEALTH_CODE_INVALIDE: code HTTP={code!r} hors plage [100, 599] "
                    f"ou non entier."
                )
        # Validation de probe_target selon probe_type.
        if self.probe_type is ProbeType.EXEC:
            # Pour EXEC : tuple non vide de chaînes (argv). Jamais de chaîne shell : injection.
            if (
                not isinstance(self.probe_target, tuple)
                or len(self.probe_target) == 0
                or not all(isinstance(arg, str) and arg for arg in self.probe_target)
            ):
                raise ValueError(
                    f"ERR_HEALTH_CIBLE_EXEC_INVALIDE: probe_type=EXEC exige probe_target "
                    f"tuple non vide de chaînes ; reçu={self.probe_target!r}."
                )
        elif self.probe_type in (ProbeType.HTTP, ProbeType.TCP):
            # Pour HTTP/TCP : chaîne non vide, sans caractères de contrôle.
            if not isinstance(self.probe_target, str) or not self.probe_target:
                raise ValueError(
                    f"ERR_HEALTH_CIBLE_INVALIDE: probe_type={self.probe_type.value!r} exige "
                    f"probe_target chaîne non vide ; reçu={self.probe_target!r}."
                )
            _rejeter_caracteres_de_controle("probe_target", self.probe_target)
        # probe_type is None est autorisé : la dérivation depuis healthcheck_url se fait ailleurs.
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
