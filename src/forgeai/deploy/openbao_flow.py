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
import subprocess
import time
from collections.abc import Callable
from pathlib import Path

from forgeai.secrets.openbao_init import ensure_openbao_ready, http_transport


class OpenBaoFlowError(RuntimeError):
    """Échec d'amorçage openbao au déploiement. Ne contient jamais de token/clé."""


class FileKeyStore:
    """key_store fichier pour ensure_openbao_ready. `unseal_key` -> keys_dir/unseal_key (monté RO à
    l'unsealer) ; `root_token` -> root_path (SÉPARÉ, jamais monté). read() renvoie None si non initialisé."""

    def __init__(self, keys_dir: Path, root_path: Path) -> None:
        self._unseal_path = Path(keys_dir) / "unseal_key"
        self._root_path = Path(root_path)

    def read(self) -> dict | None:
        if not self._unseal_path.exists() or not self._root_path.exists():
            return None
        unseal = self._unseal_path.read_text(encoding="utf-8").strip()
        root = self._root_path.read_text(encoding="utf-8").strip()
        if not unseal or not root:
            return None
        return {"unseal_key": unseal, "root_token": root}

    def write(self, data: dict) -> None:
        # root_token -> 0600, ISOLÉ dans un fichier séparé jamais monté à l'unsealer (owner seul).
        self._root_path.parent.mkdir(parents=True, exist_ok=True)
        _write_file(self._root_path, data["root_token"], 0o600)
        # unseal_key -> 0644 : le conteneur openbao-unsealer tourne sous l'UID NON-root de l'image
        # (≠ UID de l'opérateur qui écrit), via un bind-mount hôte -> il ne pourrait PAS lire un 0600
        # possédé par l'opérateur (prouvé e2e S6 : re-unseal muet après restart). La clé d'unseal est
        # co-localisée avec le STORAGE scellé sur le même hôte (MÊME frontière de confiance : qui lit
        # l'hôte a déjà les deux) -> 0644 n'élargit pas la surface au-delà du contrôle d'accès au nœud
        # (documenté). Le ROOT reste 0600 et isolé (l'unsealer ne le voit jamais).
        self._unseal_path.parent.mkdir(parents=True, exist_ok=True)
        _write_file(self._unseal_path, data["unseal_key"], 0o644)


class FileSecretStore:
    """secret_store fichier pour ensure_openbao_ready : {"token": <app_token>} en JSON, 0600."""

    def __init__(self, path: Path) -> None:
        self._path = Path(path)

    def read(self) -> dict | None:
        if not self._path.exists():
            return None
        text = self._path.read_text(encoding="utf-8").strip()
        return json.loads(text) if text else None

    def write(self, data: dict) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        _write_file(self._path, json.dumps(dict(data)), 0o600)  # token opérateur, owner seul


def _write_file(path: Path, content: str, mode: int) -> None:
    """Écrit `content` avec le mode donné (0600 pour les secrets owner-seul ; 0644 pour l'unseal_key
    que le conteneur unsealer non-root doit lire)."""
    path.write_text(content if content.endswith("\n") else content + "\n", encoding="utf-8")
    os.chmod(path, mode)


def prepare_key_store(keys_dir: Path) -> Path:
    """Pré-crée le répertoire des clés AVANT le démarrage d'openbao (le bind-mount hôte doit exister et
    appartenir à l'opérateur ; sinon docker le crée root et le flux Python ne peut plus écrire). Mode
    0o711 : le conteneur openbao-unsealer (UID NON-root de l'image ≠ opérateur) doit TRAVERSER le
    répertoire pour lire /keys/unseal_key par son nom (un 0700 le lui interdirait, prouvé e2e S6) SANS
    pouvoir le LISTER (pas de bit read pour les autres). Le répertoire ne contient QUE l'unseal_key (le
    root est ailleurs, 0600). Idempotent (create-if-absent). Renvoie le chemin."""
    d = Path(keys_dir)
    d.mkdir(parents=True, exist_ok=True)
    # 0o711 : traversable par l'UID non-root du conteneur unsealer (pour lire /keys/unseal_key par son
    # nom) MAIS non LISTABLE par les autres (pas de bit read). Risque accepté et documenté (S2612) : la
    # clé d'unseal est co-localisée avec le storage scellé sur le même hôte (même frontière de confiance).
    os.chmod(d, 0o711)  # nosec B103
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
                f"kubectl apply Secret {self._name} a échoué (code {proc.returncode})")


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
    raise OpenBaoFlowError(f"openbao injoignable à {url} après {attempts} tentatives")
