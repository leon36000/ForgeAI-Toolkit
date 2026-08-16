"""Tests P2-F21/F22 — clés ed25519, état cluster (fixture réelle), plan de jonction.
ssh-keygen/kubectl simulés (services externes, tests/ uniquement)."""
import json
import stat
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from forgeai.core.runner import FixtureRunner
from forgeai.network.bootstrap import BootstrapError, render_join_plan
from forgeai.network.keys import (
    KeyError_,
    commit_rotation,
    generate_keypair,
    stage_rotation,
)
from forgeai.network.nodes import ClusterError, cluster_status

FIXTURES = Path(__file__).parent / "fixtures" / "k3s"


class SshKeygenRunner:
    """Simule ssh-keygen : écrit une paire de clés plausible aux chemins -f."""
    def __init__(self):
        self.calls = []

    def run(self, argv):
        self.calls.append(argv)
        if argv[0] != "ssh-keygen":
            return 127, ""
        path = Path(argv[argv.index("-f") + 1])
        path.write_text("PRIVATE KEY MATERIAL\n", encoding="utf-8")
        path.with_suffix(".pub").write_text(
            "ssh-ed25519 AAAAC3Nz...forgeai forgeai-toolkit\n", encoding="utf-8")
        return 0, ""


def test_generate_keypair_permissions(tmp_path):
    paths = generate_keypair(tmp_path / "keys", SshKeygenRunner())
    assert paths["private"].exists() and paths["public"].exists()
    assert stat.S_IMODE(paths["private"].stat().st_mode) == 0o600
    assert stat.S_IMODE((tmp_path / "keys").stat().st_mode) == 0o700


def test_generate_refuse_ecrasement(tmp_path):
    runner = SshKeygenRunner()
    generate_keypair(tmp_path / "k", runner)
    with pytest.raises(KeyError_, match="existe déjà"):
        generate_keypair(tmp_path / "k", runner)


def test_rotation_deux_temps_ne_verrouille_pas(tmp_path):
    # L'ancienne clé reste active pendant le staging (anti-lockout, objection Gemini).
    runner = SshKeygenRunner()
    key_dir = tmp_path / "k"
    active = generate_keypair(key_dir, runner)
    old_priv_content = active["private"].read_text(encoding="utf-8")

    staged = stage_rotation(key_dir, runner)
    assert staged["new_private"].exists()
    # clé active INCHANGÉE tant que la rotation n'est pas committée
    assert active["private"].read_text(encoding="utf-8") == old_priv_content
    assert active["public"].exists()


def test_commit_rotation_revoque_et_promeut(tmp_path):
    runner = SshKeygenRunner()
    key_dir = tmp_path / "k"
    first_pub = generate_keypair(key_dir, runner)["public"].read_text(encoding="utf-8")
    stage_rotation(key_dir, runner)
    paths = commit_rotation(key_dir)
    revoked = paths["revoked"].read_text(encoding="utf-8")
    assert first_pub.strip() in revoked
    assert "révoquée" in revoked
    assert stat.S_IMODE(paths["private"].stat().st_mode) == 0o600
    assert not (key_dir / "forgeai_ed25519.new").exists()  # staging promu


def test_commit_sans_staging_echoue(tmp_path):
    runner = SshKeygenRunner()
    key_dir = tmp_path / "k"
    generate_keypair(key_dir, runner)
    with pytest.raises(KeyError_, match="aucune rotation stagée"):
        commit_rotation(key_dir)


def test_cluster_status_sur_fixture_reelle():
    # Fixture = capture réelle du cluster (2026-07-14) : 4 nœuds, dont 2 Ready
    # (pc1, pc2) et 2 en état Unknown (pc3, pc4 hors ligne au moment de la capture).
    # On vérifie la lecture fidèle de cet état — jamais un « tout vert » inventé.
    runner = FixtureRunner({"kubectl": (FIXTURES / "get_nodes_real.json").read_text("utf-8")})
    nodes = cluster_status(runner)
    assert len(nodes) == 4
    by_name = {n["name"]: n for n in nodes}
    assert by_name["pc1-x870e-taichi"]["ready"] is True
    assert "control-plane" in by_name["pc1-x870e-taichi"]["roles"]
    ready_count = sum(1 for n in nodes if n["ready"])
    assert ready_count == 2  # reflète l'état réel capturé, pas un idéal


def test_cluster_status_gpu_lu_correctement():
    runner = FixtureRunner({"kubectl": (FIXTURES / "get_nodes_real.json").read_text("utf-8")})
    gpu_nodes = [n for n in cluster_status(runner) if n["gpu_allocatable"] != "0"]
    assert gpu_nodes  # le cluster expose des GPU (pc1 = RTX 5090, etc.)


def test_cluster_status_cluster_injoignable():
    with pytest.raises(ClusterError, match="joignable"):
        cluster_status(FixtureRunner({}))  # kubectl absent → code 127


def test_cluster_status_ignore_noeud_structure_incomplete():
    payload = json.dumps({
        "items": [
            {
                "metadata": {"name": "node-sain"},
                "status": {
                    "conditions": [{"type": "Ready", "status": "True"}],
                    "allocatable": {"nvidia.com/gpu": "1"},
                    "capacity": {"nvidia.com/gpu": "1"},
                    "nodeInfo": {
                        "kubeletVersion": "v1.31.1+k3s1",
                        "architecture": "amd64",
                    },
                },
            },
            {
                "metadata": {"name": "node-en-cours-de-join"},
                "status": {},
            },
        ]
    })
    runner = FixtureRunner({"kubectl": payload})
    nodes = cluster_status(runner)
    assert len(nodes) == 1
    assert nodes[0]["name"] == "node-sain"


def test_cluster_status_tous_noeuds_malformes_leve_clustererror():
    payload = json.dumps({
        "items": [
            {
                "metadata": {"name": "node-incomplet"},
                "status": {},
            }
        ]
    })
    runner = FixtureRunner({"kubectl": payload})
    with pytest.raises(ClusterError):
        cluster_status(runner)


def test_cluster_status_noeud_bien_forme_inchange_apres_correctif():
    runner = FixtureRunner({"kubectl": (FIXTURES / "get_nodes_real.json").read_text("utf-8")})
    nodes = cluster_status(runner)
    assert len(nodes) == 4


def test_join_plan_refuse_tofu():
    with pytest.raises(BootstrapError, match="pas de TOFU"):
        render_join_plan("ctrl", "node2", node_hostkey_sha256="")


def test_join_plan_authkey_jamais_en_clair():
    plan = render_join_plan("ctrl", "node2", node_hostkey_sha256="SHA256:abc123")
    argv = plan.tailscale_up_argv()
    assert "${TAILSCALE_AUTHKEY}" in argv          # référence, pas la valeur
    assert "--advertise-tags" in argv
    assert plan.acl_deny_all_default()["default"] == "deny"   # EX-3
    assert "StrictHostKeyChecking=yes" in plan.ssh_options()  # EX-1


def test_join_plan_tag_invalide():
    with pytest.raises(BootstrapError, match="tag:"):
        render_join_plan("c", "n", node_hostkey_sha256="SHA256:x", tailscale_tag="forgeai")
