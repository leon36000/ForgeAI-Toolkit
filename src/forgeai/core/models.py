"""Schémas de données centraux (architecture GLM, archive/phase-a/architecture-glm.md)."""
from __future__ import annotations

import json
import unicodedata
from dataclasses import asdict, dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping, Optional, Union

from forgeai.i18n import t


def _rejeter_caracteres_de_controle(nom_champ: str, valeur: str) -> None:
    """Lève ValueError si `valeur` contient un caractère de contrôle Unicode (catégorie Cc,
    soit \\x00–\\x1f et \\x7f — couvre \\n, \\r, \\t). Ces champs sont interpolés en brut dans
    le YAML/Compose rendu (renderers/k3s.py, renderers/compose.py) ; un caractère de contrôle
    y permettrait d'injecter des documents arbitraires. Le message nomme le champ fautif mais
    ne reproduit PAS la valeur complète (anti-fuite du payload dans les logs)."""
    for position, caractere in enumerate(valeur):
        if unicodedata.category(caractere) == "Cc":
            raise ValueError(t("core.models.controle.caractere_controle",
                                nom_champ=nom_champ, position=position,
                                caractere_repr=repr(caractere)))


def _valider_port(nom_champ: str, valeur: int) -> None:
    """Lève ValueError si `valeur` n'est pas un port TCP valide : un entier (jamais un bool,
    sous-classe d'`int` en Python) dans [1, 65535]. Reprend EXACTEMENT le motif déjà utilisé
    pour valider le port de `adopted_endpoint` dans `ServiceSpec.__post_init__` (ci-dessous) :
    même famille d'exception (ValueError), même borne [1, 65535]. Centralisé ici car
    `host_port` et `container_port` (BUG-servicespec-validation / BUG B) n'étaient bornés
    NULLE PART avant rendu — un port invalide produisait un manifeste k3s/compose invalide
    au lieu d'être refusé dès la construction du ServiceSpec."""
    if not isinstance(valeur, int) or isinstance(valeur, bool) or valeur < 1 or valeur > 65535:
        raise ValueError(t("core.models.service.port_hors_bornes",
                            nom_champ=nom_champ, valeur_repr=repr(valeur)))


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
        raise ValueError(t("core.models.memoire.format_inattendu", valeur=valeur))

def _resoudre_ressources(resource_class: str, resources: dict | None) -> dict:
    """Résout les ressources effectives à partir d'une classe et d'une éventuelle dérogation.
    Retourne toujours un dictionnaire non None."""
    # a) Vérification de la classe
    if resource_class not in _CLASSES_RESSOURCES:
        classes_admises = ", ".join(_CLASSES_RESSOURCES.keys())
        raise ValueError(t("core.models.ressources.classe_inconnue",
                            resource_class=resource_class, classes_admises=classes_admises))

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
        raise ValueError(t("core.models.ressources.derogation_partielle",
                            erreurs_str=", ".join(erreurs)))

    # d) Validation des formats CPU et mémoire
    cpu_re = re.compile(r'^\d+m?$')
    mem_re = re.compile(r'^\d+(Mi|Gi)$')

    req_cpu = resources["requests"]["cpu"]
    req_mem = resources["requests"]["memory"]
    lim_cpu = resources["limits"]["cpu"]
    lim_mem = resources["limits"]["memory"]

    for nom, val in [("requests.cpu", req_cpu), ("limits.cpu", lim_cpu)]:
        if not cpu_re.match(val):
            raise ValueError(t("core.models.ressources.cpu_invalide", val=val, nom=nom))
    for nom, val in [("requests.memory", req_mem), ("limits.memory", lim_mem)]:
        if not mem_re.match(val):
            raise ValueError(t("core.models.ressources.memoire_invalide", val=val, nom=nom))

    # e) Cohérence limits >= requests (comparaison numérique normalisée)
    req_cpu_milli = _cpu_en_milli(req_cpu)
    lim_cpu_milli = _cpu_en_milli(lim_cpu)
    req_mem_mib = _memoire_en_mib(req_mem)
    lim_mem_mib = _memoire_en_mib(lim_mem)

    if lim_cpu_milli < req_cpu_milli:
        raise ValueError(t("core.models.ressources.limits_inferieures_cpu",
                            lim_cpu=lim_cpu, req_cpu=req_cpu))
    if lim_mem_mib < req_mem_mib:
        raise ValueError(t("core.models.ressources.limits_inferieures_memoire",
                            lim_mem=lim_mem, req_mem=req_mem))

    # Tout est valide, retourner le dictionnaire de ressources tel quel
    return resources


class PlacementError(ValueError):
    """Levée lorsqu'un placement est refusé AVANT rendu : aucun nœud de
    l'inventaire ne peut honorer les contraintes du service. Refuser ici
    évite l'émission d'un manifeste voué à l'échec silencieux au scheduling
    k3s : la validation sort de l'inventaire, pas du cluster.
    """


# Vendors GPU reconnus pour la réservation au rendu — liste canonique UNIQUE, RES-012A/LAB-033A.
# Reprise de la liste jusqu'ici codée en dur dans `renderers/k3s.py` (seul renderer qui la
# validait). Centralisée ici pour que `ServiceSpec.__post_init__` (BUG-servicespec-validation /
# BUG A) et `NodeInventaire.__post_init__` partagent la MÊME source de vérité : sans ça, k3s.py
# refusait un `gpu_vendor` inconnu au rendu tandis que `renderers/compose.py` (qui ne valide
# rien, `vendor = svc.gpu_vendor or "nvidia"`) le faisait silencieusement retomber sur "nvidia"
# — le même plan produisait un refus explicite sur un renderer et un comportement divergent et
# silencieux sur l'autre.
GPU_VENDORS_CONNUS: frozenset[str] = frozenset({"nvidia", "amd", "intel"})


@dataclass(frozen=True)
class NodeInventaire:
    hostname: str
    gpu_vendor: Optional[str] = None
    vram_mib: int = 0

    def __post_init__(self) -> None:
        if not self.hostname or not self.hostname.strip():
            raise ValueError(t("core.models.placement.hostname_invalide"))
        _rejeter_caracteres_de_controle("hostname", self.hostname)
        if self.vram_mib < 0:
            raise ValueError(t("core.models.placement.vram_invalide", vram_mib=self.vram_mib))
        vendors_autorises = GPU_VENDORS_CONNUS | {None}
        if self.gpu_vendor not in vendors_autorises:
            raise ValueError(t("core.models.placement.vendor_inconnu",
                                gpu_vendor=self.gpu_vendor))


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
            raise PlacementError(t("core.models.placement.aucun_noeud_inventaire_vide"))
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
            raise PlacementError(t("core.models.placement.noeud_inconnu",
                                    node_demande=node_demande,
                                    hostnames_str=(", ".join(hostnames)
                                                   or t("core.models.placement.aucun"))))
        if noeud.gpu_vendor is None:
            raise PlacementError(t("core.models.placement.cpu_only",
                                    svc_name=svc.name, gpu_vendor=svc.gpu_vendor,
                                    noeud_hostname=noeud.hostname))
        if svc.gpu_vendor is not None and noeud.gpu_vendor != svc.gpu_vendor:
            raise PlacementError(t("core.models.placement.vendor_incompatible",
                                    svc_name=svc.name, svc_gpu_vendor=svc.gpu_vendor,
                                    noeud_hostname=noeud.hostname,
                                    noeud_gpu_vendor=noeud.gpu_vendor))
        if (svc.vram_min_mib is not None
                and svc.vram_min_mib > noeud.vram_mib):
            raise PlacementError(t("core.models.placement.vram_insuffisante",
                                    svc_name=svc.name, vram_min_mib=svc.vram_min_mib,
                                    noeud_hostname=noeud.hostname,
                                    noeud_vram_mib=noeud.vram_mib))
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
            raison = t("core.models.placement.raison_vendor_incompatible",
                       noeud_gpu_vendor=noeud.gpu_vendor, svc_gpu_vendor=svc.gpu_vendor)
        elif (svc.vram_min_mib is not None
              and svc.vram_min_mib > noeud.vram_mib):
            raison = t("core.models.placement.raison_vram_insuffisante_candidat",
                       noeud_vram_mib=noeud.vram_mib, vram_min_mib=svc.vram_min_mib)
        if raison is None:
            return noeud.hostname
        candidats_examines.append(f"{noeud.hostname} ({raison})")

    vram_requise = (t("core.models.placement.suffixe_vram_requise",
                       vram_min_mib=svc.vram_min_mib)
                    if svc.vram_min_mib is not None else "")
    raise PlacementError(t("core.models.placement.aucun_noeud_qualifie_auto",
                            svc_name=svc.name, svc_gpu_vendor=svc.gpu_vendor,
                            vram_requise=vram_requise,
                            candidats_str=("; ".join(candidats_examines)
                                           or t("core.models.placement.aucun"))))


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
    """Capacité totale (CPU + mémoire + GPU) qu'un cluster déclare pouvoir servir.

    Les valeurs CPU et mémoire sont normalisées en milliCPU et en MiB pour permettre une
    comparaison arithmétique directe avec le budget d'un ``DeploymentPlan``.
    Une capacité nulle ou négative n'a aucun sens physique : elle est refusée
    à l'instanciation pour ne pas produire plus tard une division par zéro
    ou un faux positif de dépassement.

    ``ressources_gpu`` mappe le nom de la ressource device plugin (ex.
    ``amd.com/gpu``) vers la quantité disponible. Il est immuable et ses
    valeurs doivent être positives ou nulles.
    """

    cpu_millicores: int
    memoire_mib: int
    ressources_gpu: Mapping[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.cpu_millicores <= 0 or self.memoire_mib <= 0:
            raise ValueError(t("core.models.quota.capacite_invalide",
                                cpu_millicores=self.cpu_millicores,
                                memoire_mib=self.memoire_mib))
        negatifs = [
            f"{nom!r}: {qte}" for nom, qte in self.ressources_gpu.items() if qte < 0
        ]
        if negatifs:
            raise ValueError(t("core.models.quota.gpu_invalide",
                                negatifs_str=", ".join(negatifs)))
        object.__setattr__(
            self,
            "ressources_gpu",
            MappingProxyType(dict(self.ressources_gpu)),
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
    adopted_endpoint: Optional[str] = None  # hôte:port d'un service DÉJÀ présent sur le nœud, adopté au lieu d'être redéployé ; None = déployé par nous

    def __post_init__(self) -> None:
        # SEC-YAML-INJECT — suivi de #151 : ces scalaires atteignent en brut le YAML/Compose.
        # Le renderer compose n'a pas de `_safe`, donc défense à la source = couverture de
        # tous les renderers actuels et futurs ; dataclass frozen : lecture de self.* autorisée en __post_init__.
        _rejeter_caracteres_de_controle("name", self.name)
        _rejeter_caracteres_de_controle("image", self.image)
        if self.healthcheck_url is not None:
            _rejeter_caracteres_de_controle("healthcheck_url", self.healthcheck_url)
        if self.node is not None:
            _rejeter_caracteres_de_controle("node", self.node)
        # BUG B (BUG-servicespec-validation) — host_port/container_port n'étaient bornés
        # nulle part avant rendu. Même motif que la validation du port de `adopted_endpoint`
        # plus bas dans cette même méthode (réutilisé via `_valider_port`, pas réinventé).
        _valider_port("host_port", self.host_port)
        _valider_port("container_port", self.container_port)
        # BUG A (BUG-servicespec-validation) — gpu_vendor n'était validé par AUCUN renderer
        # de façon cohérente : k3s.py refuse un vendor inconnu au rendu
        # (test_k3s_gpu_vendor_inconnu_refuse) mais compose.py le fait silencieusement
        # retomber sur "nvidia". Validé ICI, à la construction, pour que les deux renderers
        # héritent automatiquement de la même garde. Vérifié indépendamment de `self.gpu` :
        # un gpu_vendor incohérent est un défaut de données dès la construction, pas
        # seulement au moment où un renderer le lirait.
        if self.gpu_vendor is not None and self.gpu_vendor not in GPU_VENDORS_CONNUS:
            raise ValueError(t("core.models.service.gpu_vendor_inconnu",
                                gpu_vendor=self.gpu_vendor))
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
            raise ValueError(t("core.models.health.duree_invalide_timeout",
                                health_timeout_s_repr=repr(self.health_timeout_s)))
        if self.health_interval_s <= 0:
            raise ValueError(t("core.models.health.duree_invalide_interval",
                                health_interval_s_repr=repr(self.health_interval_s)))
        # Le nombre de tentatives doit être strictement positif.
        if self.health_retries <= 0:
            raise ValueError(t("core.models.health.retries_invalide",
                                health_retries_repr=repr(self.health_retries)))
        # Les codes HTTP acceptés : tuple non vide, chaque code entier entre 100 et 599.
        if not self.http_success_codes:
            raise ValueError(t("core.models.health.code_vide"))
        for code in self.http_success_codes:
            if not isinstance(code, int) or isinstance(code, bool) or code < 100 or code > 599:
                raise ValueError(t("core.models.health.code_hors_plage",
                                    code_repr=repr(code)))
        # Validation de probe_target selon probe_type.
        if self.probe_type is ProbeType.EXEC:
            # Pour EXEC : tuple non vide de chaînes (argv). Jamais de chaîne shell : injection.
            # Un ARGUMENT vide est légitime (`--password ""` est un argv valide) ; seul un
            # TUPLE vide est un contrat absent. Rejeter la chaîne vide interdirait un usage réel.
            if (
                not isinstance(self.probe_target, tuple)
                or len(self.probe_target) == 0
                or not all(isinstance(arg, str) for arg in self.probe_target)
            ):
                raise ValueError(t("core.models.health.cible_exec_invalide",
                                    probe_target_repr=repr(self.probe_target)))
        elif self.probe_type in (ProbeType.HTTP, ProbeType.TCP):
            # Pour HTTP/TCP : chaîne non vide, sans caractères de contrôle.
            if not isinstance(self.probe_target, str) or not self.probe_target:
                raise ValueError(t("core.models.health.cible_invalide",
                                    probe_type_repr=repr(self.probe_type.value),
                                    probe_target_repr=repr(self.probe_target)))
            _rejeter_caracteres_de_controle("probe_target", self.probe_target)
        # probe_type is None est autorisé : la dérivation depuis healthcheck_url se fait ailleurs.
        for i, dep in enumerate(self.depends):
            _rejeter_caracteres_de_controle(f"depends[{i}]", dep)
        # adopted_endpoint : hôte:port d'un service DÉJÀ présent sur le nœud que nous adoptons.
        # None = service déployé par nous (comportement actuel, inchangé).
        if self.adopted_endpoint is not None:
            # IPv6 littéral non supporté dans cette tranche : on exige exactement un seul ':'.
            if self.adopted_endpoint.count(':') != 1:
                raise ValueError(t("core.models.adopt.forme_invalide_colon",
                                    adopted_endpoint_repr=repr(self.adopted_endpoint)))
            hote, _, port_str = self.adopted_endpoint.rpartition(':')
            if not hote:
                raise ValueError(t("core.models.adopt.hote_vide",
                                    adopted_endpoint_repr=repr(self.adopted_endpoint)))
            if any(c.isspace() or ord(c) < 32 for c in hote):
                raise ValueError(t("core.models.adopt.hote_invalide",
                                    adopted_endpoint_repr=repr(self.adopted_endpoint)))
            if not port_str.isdigit():
                raise ValueError(t("core.models.adopt.port_non_numerique",
                                    adopted_endpoint_repr=repr(self.adopted_endpoint)))
            port_int = int(port_str)
            if port_int < 1 or port_int > 65535:
                raise ValueError(t("core.models.adopt.port_hors_bornes",
                                    adopted_endpoint_repr=repr(self.adopted_endpoint),
                                    port_int=port_int))
        for cle, valeur in self.env.items():
            _rejeter_caracteres_de_controle("env (key)", cle)
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
        # HEALTH-029 : `probe_type` est une enum, non sérialisable telle quelle. Le champ existait
        # depuis HEALTH-028B mais n'avait jamais été peuple de bout en bout, si bien que ce chemin
        # n'avait jamais ete exerce — le plan echouait des qu'une sonde etait reellement declaree.
        for service in data.get("services", []):
            sonde = service.get("probe_type")
            if sonde is not None and not isinstance(sonde, str):
                service["probe_type"] = sonde.value
        return json.dumps(data, ensure_ascii=False, indent=2)
