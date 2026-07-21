"""Story S-TAIL — enrôlement mesh opt-in au add-node : Tailscale SaaS + Headscale souverain.

Décisions Nathan (2026-07-21) : opt-in DÉFAUT-ACTIVÉ en multi-nœud ; les DEUX voies (Tailscale
SaaS + Headscale self-hosted souverain) ; l'auth key est TOUJOURS une référence env, JAMAIS en
clair/argv (préserve EX-2 de la revue sécurité multi-nœuds).
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from forgeai.network.bootstrap import BootstrapError, render_join_plan, should_enroll_default


def test_tailscale_saas_argv():
    p = render_join_plan("ctrl", "node1", "SHA256:abc")
    argv = p.tailscale_up_argv()
    assert argv[:2] == ["tailscale", "up"]
    assert "--advertise-tags" in argv
    assert "${TAILSCALE_AUTHKEY}" in " ".join(argv)  # référence env, jamais la valeur
    assert "--login-server" not in argv  # SaaS => pas de control plane self-hosted


def test_headscale_souverain_argv():
    p = render_join_plan("ctrl", "node1", "SHA256:abc", login_server="https://headscale.local")
    argv = p.tailscale_up_argv()
    assert "--login-server" in argv
    assert argv[argv.index("--login-server") + 1] == "https://headscale.local"
    assert "${TAILSCALE_AUTHKEY}" in " ".join(argv)  # authkey toujours une référence


def test_authkey_jamais_en_clair():
    p = render_join_plan("ctrl", "node1", "SHA256:abc")
    joined = " ".join(p.tailscale_up_argv())
    assert "tskey-" not in joined  # aucune vraie clé Tailscale matérialisée
    assert p.authkey_env == "TAILSCALE_AUTHKEY"


def test_optin_defaut_active_en_multinoeud():
    # opt-in défaut-activé DÈS le 2e nœud (le mesh devient utile) ; off en mono-nœud.
    assert should_enroll_default(node_count=1) is False
    assert should_enroll_default(node_count=2) is True
    assert should_enroll_default(node_count=5) is True


def test_login_server_invalide_leve():
    with pytest.raises(BootstrapError):
        render_join_plan("ctrl", "node1", "SHA256:abc", login_server="pas-une-url")
