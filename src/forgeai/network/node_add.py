import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from forgeai.core.registre import append
from forgeai.core.runner import CommandRunner
from forgeai.network.remote_probe import enroll_hostkey, RemoteProbeError
from forgeai.core.redaction import redact_text
from forgeai.i18n import t


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

    def __init__(self, timeout_s: float = 20.0, hostkey_sha256: str = "") -> None:
        if not hostkey_sha256 or not hostkey_sha256.startswith("SHA256:"):
            raise RemoteProbeError(
                t("network.node_add.ssh_bootstrapper.empreinte_requise")
            )
        self._timeout = timeout_s
        self._hostkey_sha256 = hostkey_sha256

    def install_key(self, ip: str, user: str, passwd: str, pubkey: Path) -> None:
        kh = enroll_hostkey(ip, self._hostkey_sha256, self._timeout)
        try:
            cmd = [
                "sshpass", "-e", "ssh-copy-id",
                "-i", str(pubkey),
                "-o", "StrictHostKeyChecking=yes",
                "-o", f"UserKnownHostsFile={kh}",
                f"{user}@{ip}"
            ]
            env = {**os.environ, "SSHPASS": passwd}
            try:
                proc = subprocess.run(cmd, env=env, timeout=self._timeout,
                                      capture_output=True, text=True)
                if proc.returncode != 0:
                    raise NodeAddError(t("network.node_add.install_key.ssh_copy_id_echec",
                                          detail=redact_text(proc.stderr.strip())))
            except subprocess.TimeoutExpired as e:
                raise NodeAddError(t("network.node_add.install_key.timeout", detail=e)) from e
        finally:
            if os.path.exists(kh):
                os.unlink(kh)

    def verify_key(self, ip: str, user: str, privkey: Path) -> bool:
        kh = enroll_hostkey(ip, self._hostkey_sha256, self._timeout)
        try:
            cmd = [
                "ssh", "-i", str(privkey),
                "-o", "BatchMode=yes",
                "-o", "StrictHostKeyChecking=yes",
                "-o", f"UserKnownHostsFile={kh}",
                f"{user}@{ip}",
                "true"
            ]
            try:
                proc = subprocess.run(cmd, timeout=self._timeout,
                                      capture_output=True)
                return proc.returncode == 0
            except subprocess.TimeoutExpired:
                return False
        finally:
            if os.path.exists(kh):
                os.unlink(kh)


# fullmatch (pas .match + `$`) : `$` matcherait un newline final → une cible `admin\n` passerait.
# fullmatch exige la chaîne ENTIÈRE. Le point est admis dans le user (comptes `first.last`).
_SSH_USER_RE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,31}")
_SSH_HOST_RE = re.compile(r"[A-Za-z0-9_.:][A-Za-z0-9_.:-]{0,253}")


def validate_ssh_target(ip: str, user: str) -> None:
    """Valide que `ip` et `user` sont des valeurs sûres pour l'argv SSH (jamais de tiret en
    tête = option ssh, ni espace/newline/métacaractère). Le message n'écho pas la charge."""
    if not _SSH_USER_RE.fullmatch(user):
        raise NodeAddError(t("network.node_add.validate_ssh_target.user_invalide"))
    if not _SSH_HOST_RE.fullmatch(ip):
        raise NodeAddError(t("network.node_add.validate_ssh_target.ip_invalide"))


def key_fingerprint(pubkey: Path, runner: CommandRunner) -> str:
    """Retourne l'empreinte SHA256 de la clé publique."""
    retcode, output = runner.run(["ssh-keygen", "-lf", str(pubkey)])
    match = re.search(r'SHA256:\S+', output)
    if not match:
        raise NodeAddError(t("network.node_add.key_fingerprint.empreinte_introuvable",
                              detail=redact_text(output)))
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
    validate_ssh_target(ip, user)

    # 1. Installation unique avec le mot de passe (passe par l'environnement mémoire)
    bootstrapper.install_key(ip, user, passwd, pubkey)

    # 2. Bascule immédiate sur l'authentification par clé
    if not bootstrapper.verify_key(ip, user, privkey):
        raise NodeAddError(t("network.node_add.add_node.bascule_echouee"))

    # 3. Empreinte de la clé publique
    fp = key_fingerprint(pubkey, runner)

    # 4. Journalisation sécurisée (sans le mot de passe)
    append(registre_path, "node_added", "network", {
        "ip": ip,
        "user": user,
        "key_fingerprint": fp
    })

    return NodeRecord(ip, user, fp)
