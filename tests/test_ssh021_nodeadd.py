"""Tests unitaires SSH-021 — validation SSH canonique appliquée à node_add (fin du TOFU résiduel)."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from forgeai.network.remote_probe import RemoteProbeError
from forgeai.network.node_add import SshBootstrapper

GOOD = "SHA256:AAAAgood0000000000000000000000000000000000"
BAD = "SHA256:AAAtestbad0000000000000000000000000000000000"
HOST = "testhost"
USER = "testuser"
KEYFILE_RSA = Path("/tmp/id_rsa_test")
OFFERED_LINE = f"{HOST} ssh-ed25519 AAAAoffered\n"


class FakeSubprocess:
    """Remplace subprocess.run : enregistre les argv et répond selon l'exécutable."""

    def __init__(self):
        self.calls = []

    def dispatcher(self, cmd, **kwargs):
        self.calls.append(cmd)
        exe = os.path.basename(cmd[0]) if cmd else ""
        if exe == "ssh-keyscan":
            return subprocess.CompletedProcess(cmd, 0, stdout=OFFERED_LINE, stderr="")
        elif exe == "ssh-keygen":
            tmpfile = cmd[-1]
            try:
                with open(tmpfile, "r") as f:
                    content = f.read()
            except OSError:
                content = ""
            fp = GOOD if content.strip() == OFFERED_LINE.strip() else BAD
            return subprocess.CompletedProcess(cmd, 0, stdout=f"256 {fp} {HOST} (ED25519)\n", stderr="")
        elif exe == "sshpass":
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        elif exe == "ssh":
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="unknown executable")


@pytest.fixture(autouse=True)
def mock_subprocess_run(monkeypatch):
    fake = FakeSubprocess()
    monkeypatch.setattr(subprocess, "run", fake.dispatcher)
    yield fake


# G1 — empreinte vide au constructeur → refus AVANT réseau
def test_g1_empty_hostkey_raises_before_network(mock_subprocess_run):
    with pytest.raises(RemoteProbeError, match="format 'SHA256:"):
        SshBootstrapper(hostkey_sha256="")
    assert len(mock_subprocess_run.calls) == 0


# G2 — install_key MATCH → ssh-copy-id avec =yes + known_hosts, sans accept-new
def test_g2_install_key_strict_and_known_hosts(mock_subprocess_run):
    SshBootstrapper(hostkey_sha256=GOOD).install_key(HOST, USER, "dummy", KEYFILE_RSA)
    for call in mock_subprocess_run.calls:
        assert "accept-new" not in " ".join(call), f"accept-new dans {call}"
    copy_calls = [c for c in mock_subprocess_run.calls if os.path.basename(c[0]) == "sshpass"]
    assert len(copy_calls) >= 1
    cmd_str = " ".join(copy_calls[0])
    assert "StrictHostKeyChecking=yes" in cmd_str
    assert "UserKnownHostsFile=" in cmd_str


# G3 — install_key MISMATCH → refus, ssh-copy-id JAMAIS lancé
def test_g3_mismatch_raises_before_ssh_copy_id(mock_subprocess_run):
    b = SshBootstrapper(hostkey_sha256=BAD)
    with pytest.raises(RemoteProbeError, match="aucune clé d'hôte offerte"):
        b.install_key(HOST, USER, "dummy", KEYFILE_RSA)
    copy_calls = [c for c in mock_subprocess_run.calls if os.path.basename(c[0]) == "sshpass"]
    assert len(copy_calls) == 0, f"ssh-copy-id lancé malgré mismatch : {copy_calls}"


# G4 — verify_key MATCH → ssh avec =yes + known_hosts, sans accept-new
def test_g4_verify_key_strict(mock_subprocess_run):
    assert SshBootstrapper(hostkey_sha256=GOOD).verify_key(HOST, USER, KEYFILE_RSA) is True
    for call in mock_subprocess_run.calls:
        assert "accept-new" not in " ".join(call), f"accept-new dans {call}"
    ssh_calls = [c for c in mock_subprocess_run.calls if os.path.basename(c[0]) == "ssh"]
    assert len(ssh_calls) >= 1
    ssh_cmd = " ".join(ssh_calls[0])
    assert "StrictHostKeyChecking=yes" in ssh_cmd
    assert "UserKnownHostsFile=" in ssh_cmd


# G5 — CLI : `node add` exige --hostkey (argparse required → SystemExit)
def test_g5_cli_requires_hostkey(tmp_path):
    import forgeai.cli as cli
    with pytest.raises(SystemExit) as ei:
        cli.main([
            "node", "add", "--ip", "1.2.3.4", "--user", "u", "--password-env", "PW",
            "--pubkey", "k.pub", "--privkey", "k", "--registre", str(tmp_path / "r.jsonl"),
            # --hostkey absent
        ])
    assert ei.value.code == 2
