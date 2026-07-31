from __future__ import annotations

import hmac
import importlib.resources
import ipaddress
import json
import os
import re
import shutil
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import urllib.parse
import webbrowser
from collections import OrderedDict
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from forgeai.catalogue.loader import parse_stars
from forgeai.catalogue.spheres import SPHERES, classify_sphere, spheres_index
from forgeai.core import registre
from forgeai.core.runner import SubprocessRunner, CommandRunner
from forgeai.core.proc import kill_tree
from forgeai.core.validation import NODE_NAME_RE
from forgeai.deploy.compose import http_ok
from forgeai.hardware.detect import HardwareDetector
from forgeai.models.probe import Transport
from forgeai.models.routes import RouteError, RouteStore
from forgeai.network.discover import charger_signatures, inventaire
from forgeai.network.keys import generate_keypair, KeyError_
from forgeai.network.node_add import add_node, Bootstrapper, NodeAddError, SshBootstrapper
from forgeai.network.nodes import cluster_status, ClusterError
from forgeai.network.prepare import sonder_noeud, plan_preparation, preparer_noeud, PrepareError
from forgeai.preflight import available_backends, run_checks
from forgeai.core.redaction import redact_text
from forgeai.models._locking import atomic_write_text
from forgeai.web.ratelimit import RateLimiter
from forgeai.resources import catalogue_path, forgeai_home
from forgeai.stacks import deploy_ids, list_stacks, load_stack


_MIME_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
}

_CHASSIS_CACHE: frozenset[str] | None = None
_NODE_RE = NODE_NAME_RE  # source unique partagée (FAI-0016)


def _mime(name: str) -> str:
    lower = name.lower()
    for ext, ctype in _MIME_TYPES.items():
        if lower.endswith(ext):
            return ctype
    return "application/octet-stream"


def _asset_bytes(name: str) -> bytes | None:
    """Retourne le contenu d'un asset embarqué, ou None si interdit/absent."""
    if "/" in name or "\\" in name or ".." in name:
        return None
    try:
        resource = importlib.resources.files("forgeai.web") / "assets" / name
        return resource.read_bytes()
    except (FileNotFoundError, ModuleNotFoundError):
        return None


# OPT-001 (OBS-A060-1) — sondes matérielles + backends relancées à CHAQUE requête.
# Mesuré : /api/summary 940→1583 ms (dont _available_backends 801 ms) vs 1 ms /api/stacks ;
# saturation ~8 clients (p99>1 s à 16). Un seul cache TTL thread-safe, invalidation explicite.
_HARDWARE_TTL_S = 60.0  # matériel stable ; TTL borné pour hotplug/driver
_PROBE_TIMEOUT_S = 3.0  # OPT-002 : sondes du chemin HTTP bornées court (20 s reste pour le déploiement)

_hardware_profile_cache = None
_hardware_profile_cache_time: float = 0.0

_backends_cache: list[str] | None = None
_backends_cache_time: float = 0.0

# RLock (réentrant) : `_available_backends` appelle `_hardware_report()` en tenant déjà le verrou ;
# un Lock simple provoquerait un INTERBLOCAGE (prouvé par test_backends_et_hardware_sans_interblocage).
_hardware_lock = threading.RLock()


def _hardware_cache_clear() -> None:
    """Purge explicite du cache matériel et du cache backends."""
    global _hardware_profile_cache, _hardware_profile_cache_time
    global _backends_cache, _backends_cache_time
    with _hardware_lock:
        _hardware_profile_cache = None
        _hardware_profile_cache_time = 0.0
        _backends_cache = None
        _backends_cache_time = 0.0


def _hardware_report():
    """HardwareProfile mémoïsé (TTL) — source unique des sondes matérielles."""
    global _hardware_profile_cache, _hardware_profile_cache_time
    now = time.monotonic()
    cache = _hardware_profile_cache
    if cache is not None and now - _hardware_profile_cache_time < _HARDWARE_TTL_S:
        return cache
    with _hardware_lock:
        now = time.monotonic()
        if (
            _hardware_profile_cache is not None
            and now - _hardware_profile_cache_time < _HARDWARE_TTL_S
        ):
            return _hardware_profile_cache
        report = HardwareDetector(SubprocessRunner(timeout_s=_PROBE_TIMEOUT_S)).full_report()
        _hardware_profile_cache = report
        _hardware_profile_cache_time = now
        return report


def hardware_json() -> str:
    """JSON mémoïsé de /api/detect."""
    return _hardware_report().to_json()


def _valider_adopt(adopt, noms_services):
    """Valide le champ `adopt` reçu par POST /api/deploy.

    adopt         : la valeur brute lue du JSON (n'importe quel type).
    noms_services : ensemble (set) des noms de services du plan.

    Retourne None si tout est valide (y compris si adopt est None ou {}).
    Retourne une CHAÎNE de message d'erreur sinon (l'appelant en fera un 400).
    """
    if adopt is None or adopt == {}:
        return None
    if not isinstance(adopt, dict):
        return "adopt doit etre un objet {service: hote:port}"

    MAX_LEN = 40

    def _clip(s):
        s = str(s)
        return s if len(s) <= MAX_LEN else s[:MAX_LEN]

    for cle in sorted(adopt, key=lambda k: str(k)):
        if not isinstance(cle, str) or cle == "":
            return "adopt : nom de service invalide"
        if cle not in noms_services:
            return f"adopt : service inconnu '{_clip(cle)}'"
        valeur = adopt[cle]
        if not isinstance(valeur, str):
            return f"adopt['{_clip(cle)}'] doit etre une chaine 'hote:port'"
        if valeur.count(':') != 1:
            return f"adopt['{_clip(cle)}'] : forme attendue 'hote:port'"
        hote, _, port = valeur.partition(':')
        if not hote or ' ' in hote or any(ord(c) < 32 for c in hote):
            return f"adopt['{_clip(cle)}'] : hote invalide"
        if not port.isdigit():
            return f"adopt['{_clip(cle)}'] : port non numerique"
        p = int(port)
        if p < 1 or p > 65535:
            return f"adopt['{_clip(cle)}'] : port hors bornes"

    return None


class _CachedDetector:
    """Adaptateur : expose l'interface `full_report()` en servant le cache (aucune sonde)."""

    def full_report(self):
        return _hardware_report()


def _available_backends() -> list[str]:
    """Backends disponibles mémoïsés (TTL), avec copie défensive."""
    global _backends_cache, _backends_cache_time
    now = time.monotonic()
    cache = _backends_cache
    if cache is not None and now - _backends_cache_time < _HARDWARE_TTL_S:
        return list(cache)
    with _hardware_lock:
        now = time.monotonic()
        if (
            _backends_cache is not None
            and now - _backends_cache_time < _HARDWARE_TTL_S
        ):
            return list(_backends_cache)
        # `run_checks` attend un DÉTECTEUR (il appelle .full_report()) : on lui passe un adaptateur
        # qui sert le rapport DÉJÀ mémoïsé — évite la 3e sonde matérielle redondante.
        backends = available_backends(
            run_checks(SubprocessRunner(timeout_s=_PROBE_TIMEOUT_S), _CachedDetector(), http_ok)
        )
        _backends_cache = backends
        _backends_cache_time = now
        return list(backends)


@lru_cache(maxsize=1)  # parse mémoïsé (paquet immuable) — 1 seul parse/process (FAI-0014)
def _catalogue_entries_cached() -> tuple[dict, ...]:
    return tuple(json.loads(catalogue_path().read_text(encoding="utf-8")).get("entries", []))


def _catalogue_entries() -> list[dict]:
    # copie superficielle : le cache (tuple immuable) résiste aux mutations d'appelant
    return list(_catalogue_entries_cached())


def _json_body(obj: object) -> bytes:
    return json.dumps(obj, ensure_ascii=False).encode("utf-8")


def chassis_ids() -> frozenset[str]:
    """Intersection des briques déployées par tous les stacks hors 'tout-en-un'."""
    global _CHASSIS_CACHE
    if _CHASSIS_CACHE is not None:
        return _CHASSIS_CACHE

    profiles = [sid for sid in list_stacks() if sid != "tout-en-un"]
    common: set[str] | None = None
    for sid in profiles:
        deployed = set(deploy_ids(load_stack(sid)))
        common = deployed if common is None else common & deployed

    _CHASSIS_CACHE = frozenset(common) if common is not None else frozenset()
    return _CHASSIS_CACHE


def recommended_stack_id(detect: dict) -> str:
    """Règle serveur unique de recommandation de stack."""
    gpus = detect.get("gpus", [])
    return "agentique" if isinstance(gpus, list) and len(gpus) >= 1 else "assistant-entreprise"


def bricks_payload(sphere_id: str, stack_id: str | None) -> dict | None:
    """Catalogue d'une sphère, enrichi de l'état par rapport à un stack optionnel."""
    valid_spheres = {s.id for s in SPHERES}
    if sphere_id not in valid_spheres:
        return None

    entries = _catalogue_entries()
    deployed: set[str] = set()
    sphere_defaults: dict[str, str] = {}

    if stack_id is not None:
        try:
            stack = load_stack(stack_id)
        except FileNotFoundError:
            return None
        deployed = set(deploy_ids(stack))
        sphere_defaults = stack.get("default_by_sphere", {})

    locked = chassis_ids()
    bricks = []
    for entry in entries:
        if classify_sphere(entry) != sphere_id:
            continue
        brick_id = entry["id"]
        installed = brick_id in deployed
        bricks.append(
            {
                "id": brick_id,
                "name": entry["name"],
                "description_fr": entry.get("description_fr", ""),
                "description_en": entry.get("description_en", ""),
                "stars": parse_stars(entry.get("popularity")),
                "license": entry.get("license", ""),
                "installed": installed,
                "locked": (brick_id in locked) and installed,
                "default": sphere_defaults.get(sphere_id) == brick_id,
            }
        )

    bricks.sort(key=lambda b: (not b["installed"], -b["stars"], b["id"]))
    return {
        "sphere": sphere_id,
        "stack": stack_id,
        "total": len(bricks),
        "bricks": bricks,
    }



@lru_cache(maxsize=None)  # données immuables du paquet — cache par nom (FAI-0014)
def _read_data_text(name: str) -> str:
    from importlib import resources
    return (resources.files("forgeai.data") / name).read_text(encoding="utf-8")


# Hooks pour les tests (valeurs par défaut si non posés).
_MODELS_HOME: Path | None = None
_PROBE_TRANSPORT: Transport | None = None
_REGISTRE_PATH: Path | None = None

_NODE_BOOTSTRAPPER: Bootstrapper | None = None
_NODE_KEYS_DIR: Path | None = None

# Hook déploiement : remplace la commande wizard par défaut dans les tests.
_DEPLOY_CMD: list[str] | None = None

# Garde d'accès web (FAI-0001) : jeton capturé par chaque instance dans build_server.
_WEB_TOKEN: str | None = os.environ.get("FORGEAI_WEB_TOKEN") or None
_SELECTION_ITEM_RE = re.compile(r"^[A-Za-z0-9._/:-]{1,200}$")


def _selection_valide(lst: object) -> bool:
    """Validation de FORME seulement (P0.3b/N1b) — l'existence est validée par le wizard.
    Accepte des chaînes nues ou des objets {hf_id, node, engine} (sélection v2)."""
    if not isinstance(lst, list) or len(lst) > 2000:
        return False
    for x in lst:
        if isinstance(x, str):
            if not _SELECTION_ITEM_RE.match(x):
                return False
        elif isinstance(x, dict):
            for cle in ("hf_id", "node", "engine"):
                v = x.get(cle, "auto" if cle != "hf_id" else None)
                if v is None or not isinstance(v, str) or not _SELECTION_ITEM_RE.match(v):
                    return False
        else:
            return False
    return True

_DEPLOY_STATE = {
    "proc": None,
    "lines": [],
    "done": False,
    "exit_code": None,
    "lock": threading.Lock(),
}

_PREPARE_STATE: "OrderedDict[str, dict]" = OrderedDict()
_PREPARE_LOCK = threading.Lock()
_PREPARE_MAX = 256  # borne mémoire : au-delà, éviction du plus ancien (LRU)
_PREPARE_STATE_VERSION = 1  # schéma du fichier de persistance (REL-038A)
# REL-038B : hôtes dont une préparation est ACTIVE. Runtime seulement — JAMAIS persisté : après un
# redémarrage l'ensemble est vide, donc il ne peut par construction pas verrouiller un hôte à vie.
_PREPARE_ACTIVE: set = set()


def _prepare_state_set(host: str, state: dict) -> None:
    """Écrit l'état de préparation d'un hôte (verrouillé, borné LRU) puis le persiste.

    REL-038A : la persistance a lieu APRÈS la relâche du verrou — jamais d'E/S disque en
    tenant `_PREPARE_LOCK` (un disque lent bloquerait toutes les lectures d'état)."""
    with _PREPARE_LOCK:
        _PREPARE_STATE[host] = state
        _PREPARE_STATE.move_to_end(host)
        while len(_PREPARE_STATE) > _PREPARE_MAX:
            _PREPARE_STATE.popitem(last=False)
    _persist_prepare_state()


def _prepare_state_get(host: str) -> dict:
    """Lit l'état (verrouillé) et renvoie une COPIE défensive (jamais l'objet partagé)."""
    with _PREPARE_LOCK:
        return dict(_PREPARE_STATE.get(host, {"done": False}))


def _deploy_state_path() -> Path:
    return forgeai_home() / "deploy" / "deploy-state.json"


def _prepare_state_path() -> Path:
    """REL-038A : fichier de persistance de l'état de préparation des nœuds."""
    return forgeai_home() / "prepare" / "prepare-state.json"


def _persist_prepare_state() -> None:
    """Snapshot de l'état de préparation sur disque (best-effort, atomique).

    REL-038A : l'écriture passe par `atomic_write_text` (mkstemp + fchmod 0600 + fsync +
    os.replace) plutôt qu'une ré-implémentation — l'état nomme des hôtes d'infrastructure et
    n'a pas à être lisible par les autres comptes de la machine. `erreur` est rédigé avant
    écriture (ERR-041A) : un message PrepareError peut porter un chemin ou un fragment sensible.
    Best-effort : une panne d'écriture ne doit JAMAIS faire échouer une préparation.
    """
    try:
        with _PREPARE_LOCK:  # copie sous verrou, écriture hors verrou
            snapshot = {
                "version": _PREPARE_STATE_VERSION,
                "hosts": {
                    host: {
                        "done": state.get("done", False),
                        "resultat": state.get("resultat"),
                        "erreur": (
                            redact_text(state["erreur"])
                            if isinstance(state.get("erreur"), str)
                            else None
                        ),
                    }
                    for host, state in _PREPARE_STATE.items()
                },
            }
        atomic_write_text(_prepare_state_path(), json.dumps(snapshot, ensure_ascii=False))
    except Exception:  # noqa: BLE001 — best-effort, jamais bloquant pour une préparation
        return


def _load_prepare_state() -> None:
    """Restaure l'état de préparation depuis le disque au démarrage (fail-safe).

    REL-038A : fichier absent / illisible / JSON invalide / `version` inconnue / `hosts` mal formé
    → on repart d'un état VIDE plutôt que de propager une structure douteuse. Une entrée d'hôte
    corrompue est ignorée INDIVIDUELLEMENT, sans invalider les entrées valides du même fichier.
    """
    path = _prepare_state_path()
    try:
        if not path.exists():
            return
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("version") != _PREPARE_STATE_VERSION:
            return
        hosts = data.get("hosts")
        if not isinstance(hosts, dict):
            return
        with _PREPARE_LOCK:
            for host, state in hosts.items():
                if not isinstance(state, dict) or not isinstance(state.get("done"), bool):
                    continue  # entrée corrompue : ignorée seule
                if state["done"]:
                    _PREPARE_STATE[host] = {
                        "done": True,
                        "resultat": state.get("resultat"),
                        "erreur": state.get("erreur"),
                    }
                else:
                    # REL-038B : réconciliation IDEMPOTENTE — une entrée « en cours » restaurée est
                    # un mensonge (aucun thread ne survit à un redémarrage). On la rend TERMINALE,
                    # sinon la garde d'unicité verrouillerait cet hôte définitivement. Ré-appliquer
                    # la réconciliation sur un état déjà réconcilié ne change plus rien (point fixe).
                    _PREPARE_STATE[host] = {
                        "done": True,
                        "resultat": None,
                        "erreur": "préparation interrompue par un redémarrage",
                    }
                while len(_PREPARE_STATE) > _PREPARE_MAX:
                    _PREPARE_STATE.popitem(last=False)
    except Exception:  # noqa: BLE001 — fail-safe : un fichier douteux ne casse pas le démarrage
        return


def _persist_deploy_state() -> None:
    """Snapshot de l'état reportable sur disque (best-effort, hors lock de l'appelant)."""
    try:
        with _DEPLOY_STATE["lock"]:
            snapshot = {
                "done": _DEPLOY_STATE["done"],
                "exit_code": _DEPLOY_STATE["exit_code"],
                # Les lignes sont la sortie brute du déploiement : une commande peut
                # y avoir échotypé un secret. On rédige AVANT persistance (ERR-041A).
                "lines": [redact_text(line) for line in _DEPLOY_STATE["lines"]],
            }
        path = _deploy_state_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        # Fichier temporaire UNIQUE par écriture : deux persists concurrents (le `_reader` de
        # l'ancien deploy qui se termine + le persist initial d'un nouveau deploy) écriraient
        # sinon le MÊME .tmp et corromperaient le JSON avant `os.replace`. mkstemp garantit un
        # nom distinct ; `os.replace` est atomique (dernier écrivain gagne, jamais de corruption).
        fd, tmp_str = tempfile.mkstemp(dir=str(path.parent), prefix=".deploy-state.", suffix=".tmp")
        tmp = Path(tmp_str)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(snapshot, fh, ensure_ascii=False)
            os.replace(str(tmp), str(path))
        except Exception:
            tmp.unlink(missing_ok=True)  # nettoie le tmp orphelin ; fd déjà fermé par le with
            raise
    except Exception:
        pass


def _load_deploy_state() -> None:
    """Restaure le dernier état reportable depuis le disque au démarrage du serveur."""
    path = _deploy_state_path()
    try:
        if not path.exists():
            return
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return
        lines = data.get("lines")
        done = data.get("done")
        exit_code = data.get("exit_code")
        if not isinstance(lines, list) or not isinstance(done, bool):
            return
        with _DEPLOY_STATE["lock"]:
            _DEPLOY_STATE["lines"] = list(lines)
            _DEPLOY_STATE["done"] = done
            _DEPLOY_STATE["exit_code"] = exit_code
    except Exception:
        pass


def _models_home() -> Path:
    return _MODELS_HOME if _MODELS_HOME is not None else forgeai_home() / "models"


def _probe_transport() -> Transport | None:
    return _PROBE_TRANSPORT


def _registre_path() -> Path:
    return _REGISTRE_PATH if _REGISTRE_PATH is not None else forgeai_home() / "Registres" / "mission.jsonl"


def _node_vendors_by_host(registre_path: Path) -> dict[str, list[str]]:
    """S6b — corrèle nom d'hôte -> vendors GPU distincts depuis les sondes `node_hardware` du
    registre (réutilise cluster.read_probes/node_vendors de S7). Registre absent => {} (jamais
    d'exception). Sert à enrichir /api/nodes/status pour que l'UI filtre les moteurs par vendor."""
    from forgeai import cluster
    return {
        probe.get("node_host"): cluster.node_vendors(probe.get("hardware", {}))
        for probe in cluster.read_probes(registre_path)
    }


def _node_keys(runner: CommandRunner) -> tuple[Path, Path]:
    """Retourne la paire de clés active, la génère si elle est absente."""
    key_dir = _NODE_KEYS_DIR if _NODE_KEYS_DIR is not None else forgeai_home() / "keys"
    private = key_dir / "forgeai_ed25519"
    public = private.with_suffix(".pub")
    if not private.exists() or not public.exists():
        generate_keypair(key_dir, runner)
    return public, private


def _summary_payload(stack_id: str) -> dict:
    stack = load_stack(stack_id)
    profile = _hardware_report()  # OPT-001 : mêmes sondes, mémoïsées
    nodes: list[str] = []
    try:
        nodes = [n["name"] for n in cluster_status(SubprocessRunner(timeout_s=_PROBE_TIMEOUT_S))]
    except ClusterError:
        pass
    return {
        "stack": {
            "id": stack.get("id", stack_id),
            "name": stack.get("name", stack_id),
            "n_deploy": len(deploy_ids(stack)),
        },
        "hardware": {
            "cpu_model": getattr(profile, "cpu_model", ""),
            "gpus": len(getattr(profile, "gpus", [])),
            "ram_gb": getattr(profile, "ram_gb", 0),
        },
        "backends": _available_backends(),
        "chassis": len(chassis_ids()),
        "nodes": nodes,
    }


def _normalize_host(value: str | None) -> str | None:
    """Extrait le hostname (sans port) d'une valeur Host/netloc, gère IPv6 [::1]."""
    if not value:
        return None
    value = value.strip()
    if value.startswith("["):                       # IPv6 entre crochets : [::1]:8765
        end = value.find("]")
        return value[1:end].lower() if end != -1 else None
    if value.count(":") > 1:                         # IPv6 nu : ::1
        return value.lower()
    if ":" in value:                                 # host:port
        return value.split(":", 1)[0].lower()
    return value.lower()


def _is_loopback_host(value: str) -> bool:
    """Classe un bind comme loopback sans résoudre de nom réseau."""
    hostname = _normalize_host(value)
    if hostname == "localhost":
        return True
    if hostname is None:
        return False
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


def _is_sensitive_read_path(path: str) -> bool:
    """WEB-017 : un GET est sensible (→ même garde que les mutations) s'il est sous /api/ et n'est
    ni la sonde santé ni les traductions. Coquille UI, assets statiques, /api/health et /api/i18n/*
    restent publics. Fail-closed : tout futur /api/* non listé est sensible par défaut."""
    if not path.startswith("/api/"):
        return False
    if path == "/api/health" or path.startswith("/api/i18n/"):
        return False
    return True


def _bearer_matches(auth_header: str | None, token: str | None) -> bool:
    """Compare un Bearer ASCII valide en temps constant; toute autre forme est refusée."""
    if not token:
        return False
    candidate = auth_header or ""
    expected = "Bearer " + token
    return (
        candidate.isascii()
        and expected.isascii()
        and hmac.compare_digest(candidate, expected)
    )


def authorize_mutation(*, origin: str | None, host: str | None, auth_header: str | None,
                       bind_host: str, token: str | None,
                       sec_fetch_site: str | None = None) -> tuple[bool, int]:
    """Autorise une requête MUTANTE. Retour (autorisé, code_si_refus) : 403 CSRF/rebinding, 401 jeton.

    - jeton (prioritaire) : exigé si `token` est défini ou si le bind n'est pas loopback. Un
      `Authorization: Bearer <token>` valide (comparaison temps constant) autorise IMMÉDIATEMENT —
      `Authorization` n'est pas un en-tête CORS-safelisted, donc un Bearer valide ne peut pas être
      un vecteur CSRF/rebinding ; c'est ce qui rend possible l'accès distant authentifié
      (--host 0.0.0.0). Jeton absent, invalide ou non configuré sur un bind réseau → 401 ;
    - anti-CSRF (métadonnées navigateur) : `Sec-Fetch-Site` cross-site/same-site → refus, MÊME si Origin
      est absent (les navigateurs modernes envoient cet en-tête sur toutes les requêtes) ;
    - anti-CSRF (repli) : si Origin présent, son hôte doit être loopback ou l'hôte lié ;
    - anti DNS-rebinding : le Host doit être loopback ou l'hôte lié.
    Les clients non-navigateur (CLI, tests) n'envoient pas Sec-Fetch-Site → non pénalisés (ne sont pas
    un vecteur CSRF : pas de « confused deputy »)."""
    if token or not _is_loopback_host(bind_host):
        bearer_ok = _bearer_matches(auth_header, token)
        return (bearer_ok, 0 if bearer_ok else 401)

    if sec_fetch_site and sec_fetch_site.strip().lower() in {"cross-site", "same-site", "cross-origin"}:
        return (False, 403)

    allowed = {"127.0.0.1", "localhost", "::1"}
    bind_hostname = _normalize_host(bind_host)
    if bind_hostname:
        allowed.add(bind_hostname)

    if origin:
        origin_host = _normalize_host(urllib.parse.urlsplit(origin).netloc)
        if not origin_host or origin_host not in allowed:
            return (False, 403)

    if not host or _normalize_host(host) not in allowed:
        return (False, 403)

    return (True, 0)


_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; connect-src 'self'; font-src 'self'; "
        "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    ),
}


class ForgeAIHandler(BaseHTTPRequestHandler):
    server_version = "ForgeAI/0.1"

    def version_string(self) -> str:
        # WEB-034A : header Server sans la bannière Python (pas de sys_version).
        return self.server_version

    def end_headers(self) -> None:
        # WEB-034A : injecte les en-têtes de sécurité sur TOUTE réponse (chokepoint unique).
        for _name, _value in _SECURITY_HEADERS.items():
            self.send_header(_name, _value)
        super().end_headers()

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, code: int, obj: object) -> None:
        self._send(code, _json_body(obj), "application/json; charset=utf-8")

    def _send_internal_error(self, exc: Exception) -> None:
        """WEB-015 : erreur inattendue → trace complète pour l'opérateur (stderr), message
        générique pour le client (aucune fuite d'exception interne : type, chemins, détails).
        Imprime explicitement l'exception reçue (robuste hors bloc `except`, cf. revue)."""
        traceback.print_exception(type(exc), exc, exc.__traceback__, file=sys.stderr)
        self._send_json(500, {"error": "erreur interne"})

    def _read_json_body(self, max_length: int = 65536) -> dict | None:
        length_hdr = self.headers.get("Content-Length")
        if length_hdr is None:
            self._send_json(413, {"error": "Content-Length requis"})
            return None

        try:
            length = int(length_hdr)
        except ValueError:
            self._send_json(400, {"error": "Content-Length invalide"})
            return None

        if length < 0 or length > max_length:
            self._send_json(413, {"error": "corps trop grand"})
            return None

        try:
            body = self.rfile.read(length)
            data = json.loads(body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._send_json(400, {"error": "JSON invalide"})
            return None

        if not isinstance(data, dict):
            self._send_json(400, {"error": "JSON invalide"})
            return None

        return data

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if not self._rate_gate():
            return

        # WEB-017 : les lectures sensibles subissent la MÊME politique que les mutations
        # (jeton hors loopback, anti-DNS-rebinding Host). Réutilisation littérale = source unique.
        if _is_sensitive_read_path(path) and not self._guard_mutation():
            return

        if path in ("/", "/index.html"):
            data = _asset_bytes("index.html")
            if data is None:
                self._send(500, b"index.html missing", "text/plain; charset=utf-8")
            else:
                self._send(200, data, "text/html; charset=utf-8")
            return

        if path == "/api/detect":
            try:
                body = hardware_json().encode("utf-8")
                self._send(200, body, "application/json; charset=utf-8")
            except Exception as exc:  # noqa: BLE001
                self._send_internal_error(exc)
            return

        if path == "/api/health":
            self._send(
                200,
                json.dumps({"status": "ok"}, ensure_ascii=False).encode("utf-8"),
                "application/json; charset=utf-8",
            )
            return

        if path.startswith("/api/i18n/"):
            lang = path[len("/api/i18n/") :]
            if lang not in {"fr", "en"}:
                self._send_json(404, {"error": "locale not found"})
                return
            try:
                locale_data = json.loads(_read_data_text(f"locales/{lang}.json"))
            except (FileNotFoundError, ModuleNotFoundError, json.JSONDecodeError):
                self._send_json(500, {"error": "locale unavailable"})
                return
            web = locale_data.get("web")
            if not isinstance(web, dict):
                self._send_json(500, {"error": "locale invalid"})
                return
            self._send_json(200, web)
            return

        if path == "/api/models/local":
            # Registre des modeles open-weight verifies HF — expose TEL QUEL :
            # aucun filtrage par materiel local (directive permanente), l'UI informe seulement.
            data = json.loads(_read_data_text("modeles-locaux.json"))
            self._send_json(200, data)
            return

        if path == "/api/engines":
            try:
                data = json.loads(_read_data_text("moteurs-inference.json"))
            except (FileNotFoundError, ModuleNotFoundError, json.JSONDecodeError):
                self._send_json(500, {"error": "engines registry unavailable"})
                return
            self._send_json(200, data)
            return

        if path == "/api/engines/compatible":
            # S6 : liste de choix FILTRÉE par vendor du nœud (?vendor=amd|nvidia|intel|cpu).
            # S'appuie sur forgeai.engines.compatible_engines (moteurs-inference.json gpu_vendors).
            from forgeai.engines import compatible_engines
            vendor = (urllib.parse.parse_qs(parsed.query).get("vendor") or [""])[0]
            self._send_json(200, {"vendor": vendor, "moteurs": compatible_engines(vendor)})
            return

        if path == "/api/models":
            store = RouteStore(_models_home())
            self._send_json(200, [r.public_dict() for r in store.list()])
            return

        if path == "/api/stacks/recommended":
            try:
                detect = json.loads(hardware_json())
                self._send_json(200, {"recommended_id": recommended_stack_id(detect)})
            except Exception as exc:  # noqa: BLE001
                self._send_internal_error(exc)
            return

        if path == "/api/stacks":
            stack_ids = list_stacks()
            ordered = [sid for sid in stack_ids if sid != "tout-en-un"]
            if "tout-en-un" in stack_ids:
                ordered.append("tout-en-un")
            summaries = []
            for sid in ordered:
                stack = load_stack(sid)
                summaries.append(
                    {
                        "id": stack.get("id", sid),
                        "name": stack.get("name", sid),
                        "description_fr": stack.get("description_fr", ""),
                        "description_en": stack.get("description_en", ""),
                        "n_deploy": len(deploy_ids(stack)),
                        "defaults": stack.get("default_by_sphere", {}),
                        "surface": stack.get("surface"),
                    }
                )
            self._send_json(200, summaries)
            return

        if path.startswith("/api/stacks/"):
            sid = path[len("/api/stacks/") :]
            if not sid or "/" in sid:
                self._send_json(404, {"error": "stack not found"})
                return
            try:
                stack = load_stack(sid)
                self._send_json(200, stack)
            except FileNotFoundError:
                self._send_json(404, {"error": "stack not found"})
            return

        if path == "/api/spheres":
            entries = _catalogue_entries()
            index = spheres_index(entries)
            spheres = [
                {
                    "id": sphere.id,
                    "num": sphere.num,
                    "name_fr": sphere.name_fr,
                    "name_en": sphere.name_en,
                    "count": len(index.get(sphere.id, [])),
                }
                for sphere in sorted(SPHERES, key=lambda s: s.num)
            ]
            self._send_json(200, spheres)
            return

        if path == "/api/bricks":
            query = urllib.parse.parse_qs(parsed.query)
            sphere_list = query.get("sphere")
            if not sphere_list:
                self._send_json(400, {"error": "sphere requis"})
                return
            sphere_id = sphere_list[0]
            stack_id = query.get("stack", [None])[0]
            payload = bricks_payload(sphere_id, stack_id)
            if payload is None:
                self._send_json(404, {"error": "not found"})
                return
            self._send_json(200, payload)
            return

        if path == "/api/summary":
            query = urllib.parse.parse_qs(parsed.query)
            stack_list = query.get("stack")
            if not stack_list:
                self._send_json(400, {"error": "stack requis"})
                return
            stack_id = stack_list[0]
            try:
                self._send_json(200, _summary_payload(stack_id))
            except FileNotFoundError:
                self._send_json(404, {"error": "stack not found"})
            return

        if path == "/api/discover":
            query = urllib.parse.parse_qs(parsed.query)
            node_list = query.get("node")
            if not node_list or node_list[0] != "local":
                self._send_json(400, {"error": "seul 'local' est supporté par cette route"})
                return
            try:
                signatures = charger_signatures()
                payload = inventaire(SubprocessRunner(), signatures)
                self._send_json(200, payload)
            except Exception as exc:  # noqa: BLE001
                self._send_internal_error(exc)
            return

        if path == "/api/deploy/events":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()

            if _DEPLOY_STATE["proc"] is None:
                # Aucun process vivant : soit aucun deploy n'a tourné, soit l'état a été
                # restauré du disque après un restart (proc perdu, statut reportable). On
                # rejoue les lignes mémorisées puis on clôt avec l'exit_code connu (#139).
                with _DEPLOY_STATE["lock"]:
                    lines = list(_DEPLOY_STATE["lines"])
                    done = _DEPLOY_STATE["done"]
                    exit_code = _DEPLOY_STATE["exit_code"]
                payload = json.dumps(
                    {"exit_code": exit_code if done else None}, ensure_ascii=False
                )
                try:
                    for line in lines:
                        self.wfile.write(f"data: {line}\n\n".encode("utf-8"))
                    self.wfile.write(f"event: end\ndata: {payload}\n\n".encode("utf-8"))
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    pass
                return

            idx = 0
            while True:
                with _DEPLOY_STATE["lock"]:
                    lines = _DEPLOY_STATE["lines"]
                    done = _DEPLOY_STATE["done"]
                    exit_code = _DEPLOY_STATE["exit_code"]
                    while idx < len(lines):
                        try:
                            self.wfile.write(f"data: {lines[idx]}\n\n".encode("utf-8"))
                            self.wfile.flush()
                        except (BrokenPipeError, ConnectionResetError):
                            return
                        idx += 1
                    if done:
                        payload = json.dumps({"exit_code": exit_code}, ensure_ascii=False)
                        try:
                            self.wfile.write(f"event: end\ndata: {payload}\n\n".encode("utf-8"))
                            self.wfile.flush()
                        except (BrokenPipeError, ConnectionResetError):
                            pass
                        return
                time.sleep(0.2)

        if path == "/api/nodes/status":
            runner = SubprocessRunner()
            try:
                nodes = cluster_status(runner)
            except ClusterError as exc:
                # WEB-015 : ClusterError peut encapsuler un {exc} interne (kubectl illisible) ;
                # rédige le détail avant de l'exposer au client (secret-safe).
                self._send_json(200, {"nodes": [], "detail": redact_text(str(exc))})
                return
            # S6b : enrichit chaque nœud de son/ses vendor(s) GPU (sondes node_hardware du
            # registre) pour que le dropdown moteur de l'UI se filtre par vendor. Nœud sans
            # sonde => vendors:[] (le champ existe toujours, jamais absent ni None).
            vendors_by_host = _node_vendors_by_host(_registre_path())
            for node in nodes:
                node["vendors"] = vendors_by_host.get(node.get("name"), [])
            self._send_json(200, {"nodes": nodes})
            return

        if path == "/api/nodes/receptacles":
            runner = SubprocessRunner()
            helm_present = shutil.which("helm") is not None
            nodes_out: list[dict] = []
            detail: str | None = None
            try:
                nodes = cluster_status(runner)
                for n in nodes:
                    try:
                        etat = sonder_noeud(runner, n["name"])
                    except PrepareError:
                        etat = {
                            "hostname": n["name"],
                            "ready": None,
                            "gpu_nvidia": 0,
                            "gpu_amd": 0,
                            "arch": "",
                            "labels": {},
                        }
                    plan = plan_preparation(etat, helm_present)
                    labels = etat.get("labels", {})
                    current = labels.get("forgeai/receptacle")
                    pret = current in ("pret", "pret-cpu")
                    restantes = sum(1 for s in plan if s.get("commande") is not None)
                    nodes_out.append(
                        {
                            "hostname": etat["hostname"],
                            "ready": etat["ready"],
                            "gpu_nvidia": etat["gpu_nvidia"],
                            "gpu_amd": etat["gpu_amd"],
                            "receptacle_actuel": current,
                            "pret": pret,
                            "etapes_restantes": restantes,
                        }
                    )
            except ClusterError as exc:
                detail = redact_text(str(exc))  # WEB-015 : secret-safe (ClusterError wrappe {exc})
            if detail is not None:
                self._send_json(200, {"nodes": [], "detail": detail})
            else:
                self._send_json(200, {"nodes": nodes_out})
            return

        if path.startswith("/api/nodes/prepare/"):
            host = path[len("/api/nodes/prepare/") :]
            state = _prepare_state_get(host)
            self._send_json(200, state)
            return

        basename = path.rsplit("/", 1)[-1]
        data = _asset_bytes(basename)
        if data is not None:
            self._send(200, data, _mime(basename))
            return

        payload = json.dumps({"error": "not found", "path": path}, ensure_ascii=False).encode("utf-8")
        self._send(404, payload, "application/json; charset=utf-8")

    def _rate_gate(self) -> bool:
        """WEB-016 : rate-limit global (hors loopback) + lockout anti-bruteforce (même en loopback).
        Envoie 429 + Retry-After et retourne False si la requête est limitée."""
        ip = self.client_address[0]
        retry = self.server.forgeai_rate_limiter.check(ip, is_loopback=_is_loopback_host(ip))
        if retry is not None:
            secs = max(1, int(retry + 0.999))
            body = _json_body({"error": "rate_limited", "retry_after": secs})
            self.send_response(429)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Retry-After", str(secs))
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return False
        return True

    def _is_secure_transport(self) -> bool:
        """WEB-034B : le transport est sûr si le client est en loopback (jamais sur le réseau) ou
        si la connexion est chiffrée (TLS). On se base sur l'adresse SOURCE réelle, pas sur le bind :
        un serveur lié 0.0.0.0 accepte donc toujours l'UI locale."""
        if _is_loopback_host(self.client_address[0]):
            return True
        return isinstance(self.connection, ssl.SSLSocket)

    def _require_secure_transport(self) -> bool:
        """WEB-034B : refuse (426) une requête porteuse d'identifiants sur un transport non chiffré
        venant du réseau. Message générique (ne dit pas quel secret) orientant vers TLS/tunnel."""
        if not self.headers.get("Authorization"):
            return True
        if self._is_secure_transport():
            return True
        self._send_json(426, {"error": "transport non securise : utilisez TLS ou le loopback/tunnel"})
        return False

    def _guard_mutation(self) -> bool:
        """Garde anti-CSRF / anti DNS-rebinding / jeton sur les routes mutantes.
        Envoie 403/401 et retourne False si la requête est refusée."""
        if not self._require_secure_transport():
            return False
        auth_values = self.headers.get_all("Authorization") or []
        allowed, code = authorize_mutation(
            origin=self.headers.get("Origin"),
            host=self.headers.get("Host"),
            auth_header=auth_values[0] if len(auth_values) == 1 else None,
            bind_host=self.server.forgeai_bind_host,
            sec_fetch_site=self.headers.get("Sec-Fetch-Site"),
            **{"token": self.server.forgeai_auth_value},
        )
        if not allowed:
            if code == 401:
                self.server.forgeai_rate_limiter.record_auth_failure(self.client_address[0])
            msg = "jeton requis ou invalide" if code == 401 else "origine/hôte non autorisé"
            self._send_json(code, {"error": msg})
            return False
        return True

    def do_POST(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if not self._rate_gate():
            return

        if not self._guard_mutation():
            return

        if path == "/api/detect/refresh":
            # PERF-030A : invalidation EXPLICITE du cache matériel (OPT-001), puis re-sonde.
            # Route MUTANTE : elle hérite des gardes ci-dessus (rate-limit, transport, jeton/CSRF/
            # rebinding) — un refresh force des sondes sous-processus coûteuses, il ne doit jamais
            # être anonyme (sinon vecteur d'amplification depuis une page tierce).
            _hardware_cache_clear()
            self._send(200, hardware_json().encode("utf-8"), "application/json; charset=utf-8")
            return

        if path == "/api/nodes":
            data = self._read_json_body()
            if data is None:
                return

            required = ["ip", "user", "password", "hostkey"]
            missing = [field for field in required if field not in data]
            if missing:
                self._send_json(400, {"error": "champs manquants", "missing": missing})
                return

            ip = data["ip"]
            user = data["user"]
            password = data["password"]  # proof:allow (identifiant ; valeur jamais journalisee)
            hostkey = data["hostkey"]  # SSH-021 : empreinte SHA256, pas de TOFU

            try:
                runner = SubprocessRunner()
                pubkey, privkey = _node_keys(runner)
                bootstrapper = (
                    _NODE_BOOTSTRAPPER if _NODE_BOOTSTRAPPER is not None
                    else SshBootstrapper(hostkey_sha256=hostkey)
                )
                record = add_node(
                    ip,
                    user,
                    password,
                    pubkey=pubkey,
                    privkey=privkey,
                    bootstrapper=bootstrapper,
                    runner=runner,
                    registre_path=_registre_path(),
                )
            except NodeAddError as exc:
                self._send_json(400, {"error": str(exc)})
                return
            except KeyError_:
                self._send_json(500, {"error": "erreur de gestion des clés"})
                return
            except FileNotFoundError as exc:
                # outil requis absent (ex. sshpass, ssh-keygen) — réponse propre,
                # jamais de crash silencieux du handler (preuve navigateur B-02d)
                self._send_json(500, {"error": f"outil requis absent : {exc.filename or exc}"})
                return
            except Exception:
                # aucune valeur soumise n'est reflétée
                self._send_json(500, {"error": "erreur interne lors de l'ajout du nœud"})
                return

            self._send_json(
                201,
                {
                    "node": {
                        "ip": record.ip,
                        "user": record.user,
                        "key_fingerprint": record.key_fingerprint,
                    }
                },
            )
            return

        if path == "/api/nodes/prepare":
            data = self._read_json_body()
            if data is None:
                return

            if "host" not in data:
                self._send_json(400, {"error": "host requis"})
                return

            host = data["host"]
            if not _NODE_RE.match(host):
                self._send_json(400, {"error": "host invalide"})
                return

            # REL-038B : test-et-marquage ATOMIQUE sous le MÊME verrou — sinon deux requêtes
            # concurrentes voient toutes deux « libre » et lancent deux préparations du même nœud.
            # Unicité PAR HÔTE (et non globale) : préparer plusieurs nœuds distincts en parallèle
            # est un usage légitime d'un toolkit multi-nœuds.
            with _PREPARE_LOCK:
                if host in _PREPARE_ACTIVE:
                    self._send_json(409, {"error": "préparation déjà en cours pour cet hôte"})
                    return
                _PREPARE_ACTIVE.add(host)

            def _run_prepare() -> None:
                try:
                    _prepare_state_set(host, {"done": False, "resultat": None, "erreur": None})
                    resultat, erreur = None, None
                    try:
                        runner = SubprocessRunner()
                        helm_present = shutil.which("helm") is not None
                        resultat = preparer_noeud(
                            runner, host, appliquer=True, helm_present=helm_present
                        )
                    except PrepareError as exc:
                        erreur = str(exc)
                    except Exception as exc:  # noqa: BLE001
                        traceback.print_exc(file=sys.stderr)
                        erreur = "erreur interne"
                    _prepare_state_set(host, {"done": True, "resultat": resultat, "erreur": erreur})
                finally:
                    # Libération dans un `finally` : une exception ne doit JAMAIS laisser un hôte
                    # verrouillé (sinon plus aucune préparation possible sans redémarrer).
                    with _PREPARE_LOCK:
                        _PREPARE_ACTIVE.discard(host)

            threading.Thread(target=_run_prepare, daemon=True).start()
            self._send_json(202, {"started": True, "host": host})
            return

        if path == "/api/deploy":
            data = self._read_json_body()
            if data is None:
                return

            required = ["stack", "backend", "confirm"]
            missing = [field for field in required if field not in data]
            if missing:
                self._send_json(400, {"error": "champs manquants", "missing": missing})
                return

            stack_id = data["stack"]
            backend = data["backend"]
            confirm = data["confirm"]

            if confirm != "FORCER":
                self._send_json(400, {"error": "confirmation 'FORCER' requise"})
                return

            if backend not in {"compose", "k3s"}:
                self._send_json(400, {"error": "backend invalide"})
                return

            node = data.get("node", "local")
            if node not in ("local", "auto") and not _NODE_RE.match(node):
                self._send_json(400, {"error": "node invalide"})
                return

            bricks_sel = data.get("bricks", [])
            models_sel = data.get("models", [])
            embeddings_sel = data.get("embeddings", [])
            rag_node = data.get("rag_node")
            if (not _selection_valide(bricks_sel) or not _selection_valide(models_sel)
                    or not _selection_valide(embeddings_sel)):
                self._send_json(400, {"error": "selection invalide"})
                return
            if rag_node is not None and (not isinstance(rag_node, str)
                    or (rag_node not in ("local", "auto") and not _NODE_RE.match(rag_node))):
                self._send_json(400, {"error": "rag_node invalide"})
                return

            adopt = data.get("adopt")

            try:
                load_stack(stack_id)
            except FileNotFoundError:
                self._send_json(404, {"error": "stack not found"})
                return

            # Validation de `adopt` à la FRONTIÈRE : la valeur atteint le YAML rendu et vient
            # d'une entrée réseau. La validation en profondeur (ServiceSpec) ne dispense pas
            # de refuser ici proprement — une ValueError qui remonterait donnerait un 500 sur
            # une simple faute de saisie. Placée APRÈS le contrôle d'existence du stack pour
            # ne pas transformer un 404 légitime en 500.
            if adopt is not None:
                # Le stack n'est chargé QUE s'il y a quelque chose à valider : sans `adopt`,
                # cet appel serait un travail inutile — et un risque, car rien ne garantit
                # que load_stack rende un objet exploitable dans tous les contextes.
                erreur_adopt = _valider_adopt(adopt, set(deploy_ids(load_stack(stack_id))))
                if erreur_adopt is not None:
                    self._send_json(400, {"error": erreur_adopt})
                    return

            with _DEPLOY_STATE["lock"]:
                proc = _DEPLOY_STATE["proc"]
                if proc is not None and proc.poll() is None:
                    self._send_json(409, {"error": "déploiement déjà en cours"})
                    return

                _DEPLOY_STATE["lines"].clear()
                _DEPLOY_STATE["done"] = False
                _DEPLOY_STATE["exit_code"] = None

                # Trace de gouvernance AVANT le spawn : un crash du backend en cours de
                # déploiement laisse ainsi une trace `deploy_started` au registre (best-effort ;
                # on tient déjà le lock deploy, l'except appende directement sans le reprendre).
                try:
                    registre.append(
                        _registre_path(),
                        "deploy_started",
                        "web",
                        {"stack": stack_id, "backend": backend, "node": node},
                    )
                except Exception:
                    _DEPLOY_STATE["lines"].append(
                        "avertissement: échec traçage registre deploy_started"
                    )

                cmd = _DEPLOY_CMD
                if cmd is None:
                    cmd = [
                        sys.executable,
                        "-m",
                        "forgeai",
                        "wizard",
                        "--ci",
                        "--workdir",
                        str(forgeai_home() / "deploy"),
                        "--backend",
                        backend,
                        "--node",
                        node,
                        "--stack",
                        stack_id,
                    ]
                    if bricks_sel or models_sel or embeddings_sel or rag_node or adopt:
                        workdir = forgeai_home() / "deploy"
                        workdir.mkdir(parents=True, exist_ok=True)
                        sel_path = workdir / "selection-demande.json"
                        contenu = {"bricks": bricks_sel, "models": models_sel,
                                   "embeddings": embeddings_sel}
                        if rag_node is not None:
                            contenu["rag_node"] = rag_node
                        if adopt:
                            contenu["adopt"] = adopt
                        sel_path.write_text(json.dumps(contenu, ensure_ascii=False),
                                            encoding="utf-8")
                        cmd += ["--selection", str(sel_path)]
                    if data.get("dry_run"):
                        cmd.append("--dry-run")

                # REL-038C : groupe de processus DÉDIÉ. Sans cela le déploiement partage le groupe
                # du serveur : un Ctrl-C destiné au serveur tuerait un déploiement en cours (docker
                # compose / k3s interrompu au milieu), et l'arrêt du serveur laisserait le
                # sous-processus ORPHELIN. Un groupe propre le rend adressable.
                # Le réglage est SPÉCIFIQUE À LA PLATEFORME (même convention que CLI-036 dans
                # core/proc.py) : `start_new_session` est accepté mais SILENCIEUSEMENT IGNORÉ sous
                # Windows (CPython : `unused_start_new_session`) — le passer seul y laisserait donc
                # l'isolation absente alors que le code aurait l'air de la fournir.
                popen_kwargs: dict = {
                    "stdout": subprocess.PIPE,
                    "stderr": subprocess.STDOUT,
                    "text": True,
                    "bufsize": 1,
                }
                if os.name == "posix":
                    popen_kwargs["start_new_session"] = True
                else:
                    popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
                new_proc = subprocess.Popen(cmd, **popen_kwargs)
                _DEPLOY_STATE["proc"] = new_proc

            _persist_deploy_state()

            def _reader() -> None:
                try:
                    for line in new_proc.stdout:
                        with _DEPLOY_STATE["lock"]:
                            _DEPLOY_STATE["lines"].append(line.rstrip("\r\n"))
                    new_proc.wait()
                    with _DEPLOY_STATE["lock"]:
                        _DEPLOY_STATE["exit_code"] = new_proc.returncode
                        _DEPLOY_STATE["done"] = True
                    _persist_deploy_state()
                except Exception:
                    with _DEPLOY_STATE["lock"]:
                        if new_proc.returncode is None:
                            try:
                                new_proc.kill()
                                new_proc.wait()
                            except Exception:
                                pass
                        _DEPLOY_STATE["exit_code"] = new_proc.returncode if new_proc.returncode is not None else -1
                        _DEPLOY_STATE["done"] = True
                    _persist_deploy_state()

            threading.Thread(target=_reader, daemon=True).start()
            self._send_json(202, {"started": True})
            return

        if path != "/api/models":
            self._send_json(404, {"error": "not found"})
            return

        data = self._read_json_body()
        if data is None:
            return

        required = ["name", "provenance", "model_id", "api_key", "passphrase"]
        missing = [field for field in required if field not in data]
        if missing:
            self._send_json(400, {"error": "champs manquants", "missing": missing})
            return

        name = data["name"]
        provenance = data["provenance"]
        model_id = data["model_id"]
        api_key = data["api_key"]  # proof:allow (identifiant ; la valeur n'est jamais journalisee)
        passphrase = data["passphrase"]
        base_url = data.get("base_url")

        try:
            store = RouteStore(_models_home())
            route, result = store.add_cloud(
                name,
                provenance,
                model_id,
                api_key,
                passphrase,
                base_url=base_url,
                transport=_probe_transport(),
            )
        except RouteError as exc:
            self._send_json(400, {"error": str(exc)})
            return

        # Journalisation best-effort : la route EST créée (clé scellée) même si le
        # registre échoue, mais l'échec est SIGNALÉ au client (objection revue B-02c —
        # jamais avalé en silence).
        registre_journalise = True
        try:
            reg_path = _registre_path()
            reg_path.parent.mkdir(parents=True, exist_ok=True)
            registre.append(
                reg_path,
                "route_cloud_ajoutee",
                "web",
                {
                    "name": route.name,
                    "provenance": route.provenance,
                    "model_id": route.model_id,
                    "key_fingerprint": route.key_fingerprint,
                },
            )
        except Exception:
            registre_journalise = False

        self._send_json(
            201,
            {
                "route": route.public_dict(),
                "probe": {"light": result.light, "detail": result.detail},
                "registre_journalise": registre_journalise,
            },
        )

    def log_message(self, *args) -> None:  # noqa: ARG002
        return


def build_server(host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
    _load_deploy_state()  # reporte le dernier statut de deploy connu après un restart (#139)
    _load_prepare_state()  # REL-038A : l'état de préparation survit aussi au redémarrage
    server = ThreadingHTTPServer((host, port), ForgeAIHandler)
    server.forgeai_bind_host = server.server_address[0]
    server.forgeai_auth_value = _WEB_TOKEN
    server.forgeai_rate_limiter = RateLimiter.from_env()
    cert = os.environ.get("FORGEAI_TLS_CERT")
    key = os.environ.get("FORGEAI_TLS_KEY")
    if cert and key:
        # WEB-034B : TLS explicite (opt-in opérateur) — le transport devient sûr, la garde 426 ne
        # s'applique plus. Aucun certificat n'est généré : l'opérateur fournit son matériel.
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certfile=cert, keyfile=key)
        server.socket = context.wrap_socket(server.socket, server_side=True)
        server.forgeai_tls = True
    else:
        server.forgeai_tls = False
    return server


def _terminate_active_deploy(grace_seconds: float = 5.0) -> None:
    """REL-038C : termine un déploiement encore actif à l'arrêt du serveur (anti-orphelin).

    Sans ce nettoyage, `serve()` rendait la main en laissant tourner un `forgeai deploy` que plus
    personne ne supervise ni ne peut interrompre. Réutilise `kill_tree` (CLI-036) : SIGTERM au
    GROUPE, délai de grâce, puis SIGKILL. Best-effort — l'arrêt du serveur ne doit jamais lever.
    """
    try:
        with _DEPLOY_STATE["lock"]:
            proc = _DEPLOY_STATE["proc"]
            if proc is None or proc.poll() is not None:
                return  # aucun déploiement actif : rien à nettoyer
        kill_tree(proc, grace_seconds)
    except Exception:  # noqa: BLE001 — un échec de nettoyage ne doit pas empêcher l'arrêt
        return


def serve(
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = True,
) -> None:
    server = build_server(host, port)
    scheme = "https" if getattr(server, "forgeai_tls", False) else "http"
    url = f"{scheme}://{host}:{server.server_address[1]}"
    print(url)
    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
        server.server_close()
    finally:
        # REL-038C : couvre l'arrêt NORMAL comme le KeyboardInterrupt — aucun déploiement ne
        # survit au serveur qui l'a lancé.
        _terminate_active_deploy()


def web_command(args) -> int:
    serve(
        getattr(args, "host", "127.0.0.1"),
        getattr(args, "port", 8765),
        open_browser=not getattr(args, "no_browser", False),
    )
    return 0
