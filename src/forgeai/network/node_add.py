import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from forgeai.core.registre import append
from forgeai.core.runner import CommandRunner


class NodeAddError(Exception):
    """Erreur levée lors de l'ajout d'un nœud."""


@dataclass(frozen=True)
class NodeRecord:
    ip: str
    user: str
    key_fingerprint: str


class Bootstrapper(Protocol):
    def install_key(self, ip: str, user: str, passwd: str, pubkey: Path) -> None:
        """Installe la clé publique sur le nœud en utilisant le mot de passe éphémère."""
        ...

    def verify_key(self, ip: str, user: str, privkey: Path) -> bool:
        """Vérifie que l'authentification par clé fonctionne."""
        ...


class SshBootstrapper:
    """Implémentation réelle du bootstrap SSH avec mot de passe éphémère."""

    def __init__(self, timeout_s: float = 20.0) -> None:
        self._timeout = timeout_s

    def install_key(self, ip: str, user: str, passwd: str, pubkey: Path) -> None:
        cmd = [
            "sshpass", "-e", "ssh-copy-id",
            "-i", str(pubkey),
            "-o", "StrictHostKeyChecking=accept-new",
            f"{user}@{ip}"
        ]
        env = {**os.environ, "SSHPASS": passwd}
        try:
            proc = subprocess.run(cmd, env=env, timeout=self._timeout,
                                  capture_output=True, text=True)
            if proc.returncode != 0:
                raise NodeAddError(f"ssh-copy-id échec: {proc.stderr.strip()}")
        except subprocess.TimeoutExpired as e:
            raise NodeAddError(f"Timeout lors de l'installation de la clé: {e}") from e

    def verify_key(self, ip: str, user: str, privkey: Path) -> bool:
        cmd = [
            "ssh", "-i", str(privkey),
            "-o", "BatchMode=yes",
            "-o", "StrictHostKeyChecking=accept-new",
            f"{user}@{ip}",
            "true"
        ]
        try:
            proc = subprocess.run(cmd, timeout=self._timeout,
                                  capture_output=True)
            return proc.returncode == 0
        except subprocess.TimeoutExpired:
            return False


def key_fingerprint(pubkey: Path, runner: CommandRunner) -> str:
    """Retourne l'empreinte SHA256 de la clé publique."""
    retcode, output = runner.run(["ssh-keygen", "-lf", str(pubkey)])
    match = re.search(r'SHA256:\S+', output)
    if not match:
        raise NodeAddError(f"Impossible de trouver l'empreinte SHA256 dans la sortie: {output}")
    return match.group(0)


def add_node(ip: str, user: str, passwd: str, *,
             pubkey: Path, privkey: Path,
             bootstrapper: Bootstrapper,
             runner: CommandRunner,
             registre_path: Path) -> NodeRecord:
    """
    Ajoute un nœud au cluster de manière sécurisée.
    Le mot de passe est utilisé une seule fois pour l'installation de la clé
    puis n'est jamais conservé.
    """
    # 1. Installation unique avec le mot de passe (passe par l'environnement mémoire)
    bootstrapper.install_key(ip, user, passwd, pubkey)

    # 2. Bascule immédiate sur l'authentification par clé
    if not bootstrapper.verify_key(ip, user, privkey):
        raise NodeAddError("bascule clé échouée")

    # 3. Empreinte de la clé publique
    fp = key_fingerprint(pubkey, runner)

    # 4. Journalisation sécurisée (sans le mot de passe)
    append(registre_path, "node_added", "network", {
        "ip": ip,
        "user": user,
        "key_fingerprint": fp
    })

    return NodeRecord(ip, user, fp)
