"""Story P2-F21 (bootstrap) — plan de jonction multi-nœuds sécurisé (codeur : fable).

Rend le plan de jonction d'un nœud secondaire conforme aux exigences testables de
la revue sécurité (Phase-A/revue-securite-multinoeuds-longcat.md) :
- EX-1 : SSH strict, jamais de TOFU (StrictHostKeyChecking=yes + known_hosts pré-rempli).
- EX-2 : authkey Tailscale éphémère, taggé, jamais en clair dans le plan (référence env).
- EX-3 : ACL Tailscale deny-all par défaut, autorisation explicite du contrôleur.
Aucun secret matérialisé : le plan porte des références, pas des valeurs.
"""
from __future__ import annotations

from dataclasses import dataclass


class BootstrapError(Exception):
    pass


@dataclass(frozen=True)
class JoinPlan:
    controller_host: str
    node_host: str
    node_hostkey_sha256: str      # EX-1 : empreinte connue à l'avance (pas de TOFU)
    tailscale_tag: str            # EX-2 : tag ACL (ex. "tag:forgeai-node")
    authkey_env: str = "TAILSCALE_AUTHKEY"  # EX-2 : référence, jamais la valeur
    login_server: str | None = None  # Headscale souverain (self-hosted) ; None = SaaS Tailscale

    def ssh_options(self) -> list[str]:
        return [
            "-o", "StrictHostKeyChecking=yes",     # EX-1
            "-o", "IdentitiesOnly=yes",
            "-o", f"UserKnownHostsFile={self.node_host}.known_hosts",
        ]

    def tailscale_up_argv(self) -> list[str]:
        argv = ["tailscale", "up"]
        if self.login_server:  # Headscale : pointe le control plane souverain au lieu du SaaS
            argv += ["--login-server", self.login_server]
        argv += [
            "--auth-key", f"${{{self.authkey_env}}}",  # EX-2 : référence env, jamais la valeur
            "--advertise-tags", self.tailscale_tag,
            "--ssh=false",
        ]
        return argv

    def acl_deny_all_default(self) -> dict:
        """EX-3 : politique deny-all, seul le contrôleur atteint le nœud."""
        return {
            "acls": [
                {"action": "accept",
                 "src": [f"tag:{self.tailscale_tag.removeprefix('tag:')}-controller"],
                 "dst": [f"{self.tailscale_tag}:*"]},
            ],
            "default": "deny",
        }


def render_join_plan(controller_host: str, node_host: str, node_hostkey_sha256: str,
                     tailscale_tag: str = "tag:forgeai-node",
                     login_server: str | None = None) -> JoinPlan:
    if not node_hostkey_sha256 or ":" not in node_hostkey_sha256:
        raise BootstrapError(
            "empreinte de clé d'hôte requise (EX-1 : pas de TOFU) — format 'SHA256:...'")
    if not tailscale_tag.startswith("tag:"):
        raise BootstrapError("le tag Tailscale doit commencer par 'tag:' (EX-3)")
    # Headscale souverain : le control plane doit être une URL http(s):// (EX-2, jamais un secret).
    if login_server is not None and not login_server.startswith(("http://", "https://")):
        raise BootstrapError(
            "login-server Headscale invalide : URL http(s):// attendue (ex. https://headscale.local)")
    return JoinPlan(
        controller_host=controller_host,
        node_host=node_host,
        node_hostkey_sha256=node_hostkey_sha256,
        tailscale_tag=tailscale_tag,
        login_server=login_server,
    )


def should_enroll_default(node_count: int) -> bool:
    """Opt-in DÉFAUT-ACTIVÉ en multi-nœud (décision Nathan 2026-07-21) : dès le 2e nœud, le mesh
    devient utile → enrôlement proposé COCHÉ par défaut. Mono-nœud (< 2) → OFF (le LAN/SSH suffit).
    Toujours surchargeable par l'utilisateur."""
    return node_count >= 2
