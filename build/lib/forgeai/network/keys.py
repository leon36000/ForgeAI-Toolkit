"""Story P2-F21 (clés) — cycle de vie des clés ed25519 (codeur : fable).

Exigences sécurité de la revue LongCat (Phase-A/revue-securite-multinoeuds-longcat.md) :
- EX-5 : rotation — `rotate_keypair` régénère, archive l'ancienne clé publique dans
  revoked_keys (liste de révocation à distribuer), et horodate.
- Permissions : clé privée 0600, répertoire 0700 (SEC-01).
Génération via ssh-keygen (runner injectable — testable sans toucher au système).
"""
from __future__ import annotations

import os
import time
from pathlib import Path

from forgeai.core.runner import CommandRunner


class KeyError_(Exception):
    pass


def generate_keypair(key_dir: Path, runner: CommandRunner,
                     name: str = "forgeai_ed25519") -> dict[str, Path]:
    key_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(key_dir, 0o700)
    private = key_dir / name
    if private.exists():
        raise KeyError_(
            f"{private} existe déjà — utiliser rotate_keypair (pas d'écrasement silencieux)")
    code, _ = runner.run([
        "ssh-keygen", "-t", "ed25519", "-N", "", "-C", "forgeai-toolkit",
        "-f", str(private),
    ])
    if code != 0 or not private.exists():
        raise KeyError_(f"ssh-keygen a échoué (code {code})")
    os.chmod(private, 0o600)
    return {"private": private, "public": private.with_suffix(".pub")}


def stage_rotation(key_dir: Path, runner: CommandRunner,
                   name: str = "forgeai_ed25519") -> dict[str, Path]:
    """EX-5, phase 1 — génère la nouvelle paire SANS toucher à l'ancienne clé active.

    La rotation en deux temps évite le lockout du contrôleur (revue de code P2,
    objection critique Gemini) : l'ancienne clé reste opérationnelle tant que la
    nouvelle clé publique n'est pas déployée et confirmée sur les nœuds.
    """
    paths = generate_keypair(key_dir, runner, f"{name}.new")
    return {"new_private": paths["private"], "new_public": paths["public"]}


def commit_rotation(key_dir: Path, name: str = "forgeai_ed25519") -> dict[str, Path]:
    """EX-5, phase 2 — à exécuter APRÈS déploiement de la nouvelle clé publique.

    Archive l'ancienne clé publique dans la liste de révocation, puis promeut la
    paire stagée en paire active. Refuse de committer si le staging est absent.
    """
    staged_priv = key_dir / f"{name}.new"
    staged_pub = staged_priv.with_suffix(".pub")
    if not staged_priv.exists() or not staged_pub.exists():
        raise KeyError_(
            f"aucune rotation stagée pour {name} — lancer stage_rotation d'abord")

    active_priv = key_dir / name
    active_pub = active_priv.with_suffix(".pub")
    revoked = key_dir / "revoked_keys"
    if active_pub.exists():
        stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with revoked.open("a", encoding="utf-8") as fh:
            fh.write(f"# révoquée {stamp}\n{active_pub.read_text(encoding='utf-8')}")
        os.chmod(revoked, 0o600)

    staged_priv.replace(active_priv)      # promotion atomique (même système de fichiers)
    staged_pub.replace(active_pub)
    os.chmod(active_priv, 0o600)
    return {"private": active_priv, "public": active_pub, "revoked": revoked}
