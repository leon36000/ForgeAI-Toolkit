"""Flux de déploiement openbao production (compose) : stores fichier + amorçage.

Le sidecar/service openbao-unsealer monte RO le répertoire des clés et n'en lit que `unseal_key`. Le
root_token ne doit donc JAMAIS résider dans ce répertoire : FileKeyStore écrit `unseal_key` dans `keys_dir`
(monté RO à l'unsealer) et `root_token` dans un fichier SÉPARÉ `root_path` (jamais monté). Aucune dépendance
(stdlib pure). Aucun secret n'apparaît dans un message d'erreur.
"""
from __future__ import annotations

import base64
import json
import os
import stat
import subprocess
import time
from collections.abc import Callable
from pathlib import Path

from forgeai.i18n import t
from forgeai.models.vault import (
    atomic_write_secret_text,
    prepare_secure_directory,
    read_secret_text,
)
from forgeai.secrets.openbao_init import ensure_openbao_ready, http_transport

# --- SECRET-020B : source unique de décision du groupe dédié openbao (ADR SECRET-020A §8) ---
# POSIX-only : import conditionnel pour préserver la portabilité 3 OS héritée de PORT-286.
# Sur Windows : grp = None -> resolve_openbao_gid() rend None -> tous les appelants basculent
# sur le repli documenté (0644 sans group_add, 0711 sans chown), qui est le comportement
# historique prouvé e2e S6.
try:
    import grp
except ImportError:  # pragma: no cover — Windows : pas de groupes POSIX
    grp = None  # type: ignore[assignment]

OPENBAO_GROUP = "forgeai-openbao"


def resolve_openbao_gid() -> int | None:
    """GID du groupe dédié forgeai-openbao, résolu DYNAMIQUEMENT (jamais codé en dur —
    ADR SECRET-020A §8 : REJECT 2/3 vécu sur un GID fixe). Renvoie None si le groupe
    n'existe pas OU si la plateforme n'a pas de groupes POSIX (Windows) : tous les
    appelants basculent alors sur le repli documenté (0644 sans group_add, 0711 sans
    chown), qui EST le comportement historique prouvé e2e (S6 : re-unseal muet après
    restart). Source unique : FileKeyStore.write, prepare_key_store, et le renderer
    compose (group_add) consultent tous cette fonction — un 0640 sans group_add (ou
    l'inverse) serait la régression e2e S6 exacte.
    """
    if grp is None:
        return None
    try:
        return grp.getgrnam(OPENBAO_GROUP).gr_gid
    except KeyError:
        return None


class OpenBaoFlowError(RuntimeError):
    """Échec d'amorçage openbao au déploiement. Ne contient jamais de token/clé."""


class FileKeyStore:
    """key_store fichier pour ensure_openbao_ready. `unseal_key` -> keys_dir/unseal_key (monté RO à
    l'unsealer) ; `root_token` -> root_path (SÉPARÉ, jamais monté). read() renvoie None si non initialisé."""

    def __init__(self, keys_dir: Path, root_path: Path) -> None:
        self._unseal_path = Path(keys_dir) / "unseal_key"
        self._root_path = Path(root_path)

    def read(self) -> dict | None:
        try:
            unseal = read_secret_text(self._unseal_path).strip()
            root = read_secret_text(self._root_path).strip()
        except FileNotFoundError:
            return None
        if not unseal or not root:
            return None
        return {"unseal_key": unseal, "root_token": root}

    def write(self, data: dict) -> None:
        prepare_secure_directory(self._root_path.parent, final_mode=0o700)
        # SECRET-020B (correctif revue Grok) : NE PAS figer 0o711 ici — cela clobberait le
        # 0750+groupe pose par prepare_key_store dans le flux reel (prepare_key_store PUIS
        # write). On DELEGUE a prepare_key_store : source unique de durcissement du repertoire
        # des cles, group-aware avec repli, pilotee par le meme resolve_openbao_gid().
        prepare_key_store(self._unseal_path.parent)
        # root_token -> 0600, ISOLÉ dans un fichier séparé jamais monté à l'unsealer (owner seul).
        _write_file(self._root_path, data["root_token"], 0o600)
        # unseal_key : 0640 + groupe dédié forgeai-openbao QUAND le groupe existe sur l'hôte
        # (résolu dynamiquement via resolve_openbao_gid() — ADR SECRET-020A §8 : jamais de GID
        # en dur). Le bit groupe 0640 permet à l'unsealer non-root (membre du groupe via
        # group_add compose / defaultMode k3s 0o440) de lire la clé tout en la retirant au
        # reste du monde. Repli documenté : si le groupe n'existe pas (ou plateforme non-POSIX),
        # on reste en 0644 — comportement historique prouvé e2e S6 (re-unseal muet après
        # restart). Si le chown échoue (PermissionError : groupe présent mais non-writable),
        # on REPLIE à 0644 pour ne JAMAIS laisser un 0640 orphelin de groupe qui casserait le
        # re-unseal (régression e2e S6 exactement). La clé d'unseal est co-localisée avec le
        # STORAGE scellé sur le même hôte (MÊME frontière de confiance). Le ROOT reste 0600 et
        # isolé (l'unsealer ne le voit jamais).
        gid = resolve_openbao_gid()
        if gid is None:
            _write_file(self._unseal_path, data["unseal_key"], 0o644)  # NOSONAR(S2612) — justification : governance/sonar-suppressions.json
            return
        _write_file(self._unseal_path, data["unseal_key"], 0o640)  # NOSONAR(S2612) — justification : governance/sonar-suppressions.json
        try:
            os.chown(self._unseal_path, -1, gid)
        except (PermissionError, OSError):
            # Repli : ne JAMAIS laisser un 0640 orphelin de groupe (casserait le re-unseal e2e).
            os.chmod(self._unseal_path, 0o644)  # NOSONAR(S2612) — justification : governance/sonar-suppressions.json


def _mutation_sonar_temporaire_s2612(chemin) -> None:
    """MUTATION CONTRÔLÉE TEMPORAIRE (#446, critère 5) — À RETIRER.

    Occurrence de S2612 VOISINE des trois sites supprimés par `# NOSONAR(S2612)`, mais SANS
    suppression. Si SonarCloud la remonte, cela prouve que les suppressions au site ne masquent
    pas les occurrences voisines — ce qu'aucun gate local ne peut établir."""
    os.chmod(chemin, 0o777)


class FileSecretStore:
    """secret_store fichier pour ensure_openbao_ready : {"token": <app_token>} en JSON, 0600."""

    def __init__(self, path: Path) -> None:
        self._path = Path(path)

    def read(self) -> dict | None:
        try:
            text = read_secret_text(self._path).strip()
        except FileNotFoundError:
            return None
        return json.loads(text) if text else None

    def write(self, data: dict) -> None:
        try:
            parent_state = self._path.parent.lstat()
        except FileNotFoundError:
            parent_state = None
        if (
            parent_state is not None
            and stat.S_ISDIR(parent_state.st_mode)
            and stat.S_IMODE(parent_state.st_mode) & 0o200 == 0
        ):
            raise OSError(t("deploy.openbao_flow.file_secret_store.repertoire_non_inscriptible"))
        prepare_secure_directory(self._path.parent, final_mode=0o700)
        _write_file(self._path, json.dumps(dict(data)), 0o600)  # token opérateur, owner seul


def _write_file(path: Path, content: str, mode: int) -> None:
    """Écrit `content` avec le mode donné (0600 pour les secrets owner-seul ; 0644 pour l'unseal_key
    que le conteneur unsealer non-root doit lire)."""
    payload = content if content.endswith("\n") else content + "\n"
    atomic_write_secret_text(path, payload, mode=mode)


def prepare_key_store(keys_dir: Path) -> Path:
    """Pré-crée le répertoire des clés AVANT le démarrage d'openbao (le bind-mount hôte doit exister et
    appartenir à l'opérateur ; sinon docker le crée root et le flux Python ne peut plus écrire). Mode
    0o750 + groupe dédié forgeai-openbao QUAND le groupe existe (résolu dynamiquement via
    resolve_openbao_gid() — ADR SECRET-020A §8) : traversable ET lisible par le groupe, ce qui permet
    à l'unsealer non-root (membre du groupe via group_add compose / defaultMode k3s 0o440) d'OUVRIR
    le fichier unseal_key par son nom. Repli documenté : si le groupe n'existe pas (ou plateforme
    non-POSIX), on reste en 0o711 (traversable mais non listable par les autres) — comportement
    historique prouvé e2e S6. Si le chown échoue (PermissionError), on REPLIE à 0o711 pour ne JAMAIS
    laisser un 0750 orphelin de groupe qui bloquerait la traversée. Le répertoire ne contient QUE
    l'unseal_key (le root est ailleurs, 0600). Idempotent (create-if-absent). Renvoie le chemin."""
    d = Path(keys_dir)
    gid = resolve_openbao_gid()
    if gid is None:
        # Repli : pas de groupe POSIX (Windows) ou groupe absent -> 0o711 historique (prouvé e2e S6).
        prepare_secure_directory(d, final_mode=0o711)
        return d
    prepare_secure_directory(d, final_mode=0o750)
    try:
        os.chown(d, -1, gid)
    except (PermissionError, OSError):
        # Repli : ne JAMAIS laisser un 0750 orphelin de groupe (casserait la traversée e2e).
        prepare_secure_directory(d, final_mode=0o711)
    return d


# --------------------------------------------------------------------------
# key_store k3s : Secret Kubernetes (le sidecar S3 ne monte QUE l'item unseal_key -> le root est
# dans le Secret mais jamais dans le volume du sidecar). Les secrets transitent par STDIN (manifeste
# `kubectl apply -f -`) et par la sortie de `kubectl get`, JAMAIS par argv (invariant : pas de secret
# en ligne de commande, visible via ps).
# --------------------------------------------------------------------------

def _default_run(args: list[str], *, input: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(args, input=input, capture_output=True, text=True, timeout=120)


class KubectlKeyStore:
    """key_store pour ensure_openbao_ready adossé à un Secret k8s `secret_name` du namespace donné.

    `write({"unseal_key":..., "root_token":...})` -> applique un Secret avec les DEUX valeurs (base64) via
    STDIN (jamais en argv). Le sidecar (S3) ne monte que l'item unseal_key -> il ne voit jamais le root.
    `read()` -> lit les valeurs via `kubectl get -o jsonpath` (base64 -> décodé) ; None si le Secret ou une
    clé est absent. `run` est injecté (testable sans cluster)."""

    def __init__(self, secret_name: str, namespace: str, *,
                 run: Callable[..., subprocess.CompletedProcess] = _default_run) -> None:
        self._name = secret_name
        self._ns = namespace
        self._run = run

    def _get_value(self, key: str) -> str | None:
        proc = self._run([
            "kubectl", "get", "secret", self._name, "-n", self._ns,
            "-o", f"jsonpath={{.data.{key}}}",
        ])
        if proc.returncode != 0:
            return None  # Secret absent (create-if-absent : non initialisé)
        raw = (proc.stdout or "").strip()
        if not raw:
            return None
        return base64.b64decode(raw).decode("utf-8")

    def read(self) -> dict | None:
        unseal = self._get_value("unseal_key")
        root = self._get_value("root_token")
        if not unseal or not root:
            return None
        return {"unseal_key": unseal, "root_token": root}

    def write(self, data: dict) -> None:
        b64_unseal = base64.b64encode(data["unseal_key"].encode("utf-8")).decode("ascii")
        b64_root = base64.b64encode(data["root_token"].encode("utf-8")).decode("ascii")
        manifest = (
            "apiVersion: v1\n"
            "kind: Secret\n"
            "metadata:\n"
            f"  name: {self._name}\n"
            f"  namespace: {self._ns}\n"
            "type: Opaque\n"
            "data:\n"
            f"  unseal_key: {b64_unseal}\n"
            f"  root_token: {b64_root}\n"
        )
        proc = self._run(["kubectl", "apply", "-f", "-"], input=manifest)
        if proc.returncode != 0:
            # stderr peut contenir le nom du Secret mais jamais la valeur (celle-ci était en stdin)
            raise OpenBaoFlowError(
                t("deploy.openbao_flow.kubectl_key_store.apply_echec",
                  name=self._name, code=proc.returncode))


# --------------------------------------------------------------------------
# Amorçage : rendre openbao prêt (init+unseal+KV+policy+token) et attente de joignabilité
# --------------------------------------------------------------------------

def initialize_openbao(
    bao_url: str,
    key_store,
    secret_store,
    *,
    request_factory: Callable[..., Callable[..., tuple[int, dict]]] = http_transport,
    timeout: float = 10.0,
) -> str:
    """Rend openbao prêt via le cœur S2 `ensure_openbao_ready` (transport HTTP construit depuis bao_url)
    et renvoie le token applicatif scopé. Séparé pour être mocké en bloc par le flux de déploiement."""
    return ensure_openbao_ready(request_factory(bao_url, timeout), key_store, secret_store)


def wait_reachable(
    url: str,
    *,
    probe: Callable[[str], bool],
    attempts: int = 60,
    delay: float = 2.0,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Attend qu'openbao réponde (process démarré, même SCELLÉ) avant l'init. `probe(url) -> bool` et
    `sleep` sont injectés (testable). Lève OpenBaoFlowError après `attempts` échecs (jamais de faux succès)."""
    for _ in range(attempts):
        if probe(url):
            return
        sleep(delay)
    raise OpenBaoFlowError(t("deploy.openbao_flow.wait_reachable.injoignable", url=url, attempts=attempts))
