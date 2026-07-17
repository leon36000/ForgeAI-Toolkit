import pytest

from forgeai.network.tailscale import (
    TailscaleError,
    tailscale_install_argv,
    NodeNetworkPlan,
    render_node_network,
)
from forgeai.network.bootstrap import JoinPlan

FAKE_SHA = "SHA256:abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"


def test_install_version_epinglee():
    argv = tailscale_install_argv("1.80.2")
    assert "tailscale=1.80.2" in argv
    assert argv == ["apt-get", "install", "-y", "--no-install-recommends", "tailscale=1.80.2"]


def test_install_refuse_latest_et_vide():
    with pytest.raises(TailscaleError, match="version Tailscale doit être épinglée"):
        tailscale_install_argv("latest")
    with pytest.raises(TailscaleError, match="version Tailscale doit être épinglée"):
        tailscale_install_argv("")


def test_tailnet_authkey_reference_env_jamais_valeur():
    plan = render_node_network(
        controller_host="ctrl.example.com",
        node_host="node1.example.com",
        node_hostkey_sha256=FAKE_SHA,
        tailscale_version="1.80.2",
        tailscale_tag="tag:forgeai-node",
        lan_only=False,
    )
    assert plan.up_argv is not None
    # La référence d'environnement est présente, jamais une valeur en clair
    assert "${TAILSCALE_AUTHKEY}" in plan.up_argv
    # Vérifie qu'aucun secret n'est matérialisé (pas de chaîne suspecte de type clé)
    assert not any(arg.startswith("tskey-") for arg in plan.up_argv)

    assert plan.acl is not None
    assert plan.acl["default"] == "deny"
    assert plan.join is not None
    assert isinstance(plan.join, JoinPlan)

    acls = plan.acl.get("acls", [])
    assert any(
        entry["action"] == "accept"
        and "tag:forgeai-node-controller" in entry["src"]
        and "tag:forgeai-node:*" in entry["dst"]
        for entry in acls
    )


def test_lan_only_saute_le_tailnet():
    plan = render_node_network(
        controller_host="ctrl.example.com",
        node_host="node1.example.com",
        node_hostkey_sha256=FAKE_SHA,
        tailscale_version="1.80.2",
        tailscale_tag="tag:forgeai-node",
        lan_only=True,
    )
    assert plan.lan_only is True
    assert plan.up_argv is None
    assert plan.acl is None
    assert plan.join is None
    assert plan.install_argv is not None
    assert len(plan.install_argv) > 0
    assert "tailscale=1.80.2" in plan.install_argv


def test_install_toujours_present_dans_les_deux_modes():
    tails = render_node_network(
        controller_host="ctrl.example.com",
        node_host="node1.example.com",
        node_hostkey_sha256=FAKE_SHA,
        tailscale_version="1.80.2",
        lan_only=False,
    )
    lan = render_node_network(
        controller_host="ctrl.example.com",
        node_host="node2.example.com",
        node_hostkey_sha256=FAKE_SHA,
        tailscale_version="1.80.2",
        lan_only=True,
    )
    assert "tailscale=1.80.2" in tails.install_argv
    assert "tailscale=1.80.2" in lan.install_argv


def test_cli_node_tailscale_tailnet_et_lan_only(tmp_path, capsys):
    """Chemin CLI : mode tailnet (auth-key par référence env) et mode LAN-seulement."""
    from forgeai.cli import main

    reg = tmp_path / "r.jsonl"
    rc = main(["node", "tailscale", "--node-host", "n1", "--controller-host", "ctrl",
               "--hostkey", "SHA256:abc", "--version", "1.80.2", "--registre", str(reg)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "tailnet" in out and "tailscale=1.80.2" in out
    content = reg.read_text(encoding="utf-8")
    assert "${TAILSCALE_AUTHKEY}" in content  # auth-key par référence, jamais la valeur

    rc2 = main(["node", "tailscale", "--node-host", "n2", "--controller-host", "ctrl",
                "--hostkey", "SHA256:abc", "--version", "1.80.2", "--lan-only",
                "--registre", str(reg)])
    assert rc2 == 0
    assert "LAN-seulement" in capsys.readouterr().out
