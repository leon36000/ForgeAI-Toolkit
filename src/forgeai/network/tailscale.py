from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .bootstrap import render_join_plan, JoinPlan


class TailscaleError(Exception):
    """Erreur spécifique à la gestion du réseau Tailscale."""


def tailscale_install_argv(version: str) -> list[str]:
    """
    Retourne la commande apt pour installer une version **épinglée** de Tailscale.

    La version ne peut pas être vide ni égale à "latest", conformément à la
    politique de reproductibilité et de sécurité.
    """
    if not version or version == "latest":
        raise TailscaleError("version Tailscale doit être épinglée (pas 'latest')")
    return ["apt-get", "install", "-y", "--no-install-recommends", f"tailscale={version}"]


@dataclass(frozen=True)
class NodeNetworkPlan:
    """
    Plan complet de mise en réseau d'un nœud, incluant l'installation et,
    sauf en mode LAN-only, la jonction au tailnet (authkey par référence, deny-all).
    """

    node_host: str
    install_argv: list[str]          # toujours présent (installation épinglée)
    lan_only: bool
    up_argv: Optional[list[str]]     # None → pas de jonction tailscale
    acl: Optional[dict]              # None si LAN-only
    join: Optional[JoinPlan]         # None si LAN-only


def render_node_network(
    controller_host: str,
    node_host: str,
    node_hostkey_sha256: str,
    *,
    tailscale_version: str,
    tailscale_tag: str = "tag:forgeai-node",
    lan_only: bool = False,
) -> NodeNetworkPlan:
    """
    Construit le plan réseau d'un nœud secondaire.

    - Vérifie que la version de Tailscale est épinglée.
    - En mode LAN-only, l'installation a lieu mais aucune configuration tailnet
      n'est générée (up_argv, acl, join = None).
    - Sinon, réutilise `render_join_plan` pour créer le plan de jonction conforme
      aux exigences EX-2/EX-3 de la revue de sécurité (authkey en référence, deny-all).
    """
    install = tailscale_install_argv(tailscale_version)

    if lan_only:
        return NodeNetworkPlan(
            node_host=node_host,
            install_argv=install,
            lan_only=True,
            up_argv=None,
            acl=None,
            join=None,
        )

    join = render_join_plan(
        controller_host=controller_host,
        node_host=node_host,
        node_hostkey_sha256=node_hostkey_sha256,
        tailscale_tag=tailscale_tag,
    )

    return NodeNetworkPlan(
        node_host=node_host,
        install_argv=install,
        lan_only=False,
        up_argv=join.tailscale_up_argv(),
        acl=join.acl_deny_all_default(),
        join=join,
    )
