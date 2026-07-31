import subprocess
from pathlib import Path

import pytest

from forgeai.core.redaction import REDACTED
from forgeai.network.node_add import (
    NodeAddError,
    SshBootstrapper,
    key_fingerprint,
)


def test_install_key_redacts_secrets(monkeypatch) -> None:
    """G1 – ssh-copy-id échec avec un secret dans stderr -> NodeAddError REDACTED."""
    monkeypatch.setattr(
        "forgeai.network.node_add.enroll_hostkey",
        lambda ip, sha, timeout: "/tmp/fake_known_hosts",
    )

    def _mock_run(cmd, *, env, timeout, capture_output, text):
        return subprocess.CompletedProcess(
            args=cmd, returncode=1, stdout="",
            stderr="erreur Bearer " + "e" * 40,  # proof:allow
        )

    monkeypatch.setattr(subprocess, "run", _mock_run)

    bootstrapper = SshBootstrapper(hostkey_sha256="SHA256:abcdefg")
    with pytest.raises(NodeAddError) as excinfo:
        bootstrapper.install_key("192.168.1.1", "user", "passwd", Path("/tmp/key"))

    msg = str(excinfo.value)
    assert "ssh-copy-id échec" in msg
    assert "e" * 40 not in msg
    assert REDACTED in msg


def test_key_fingerprint_redacts_secrets() -> None:
    """G2 – pas de SHA256 + secret dans la sortie ssh-keygen -> NodeAddError REDACTED."""

    class FakeRunner:
        @staticmethod
        def run(cmd):
            return 0, "sortie api_key=" + "h" * 32  # proof:allow

    with pytest.raises(NodeAddError) as excinfo:
        key_fingerprint(Path("/tmp/key"), FakeRunner())

    msg = str(excinfo.value)
    assert "Impossible de trouver l'empreinte SHA256" in msg
    assert "h" * 32 not in msg
    assert REDACTED in msg


def test_install_key_keeps_benign_stderr(monkeypatch) -> None:
    """G3 – un stderr sans secret reste inchangé dans le message d'erreur."""
    monkeypatch.setattr(
        "forgeai.network.node_add.enroll_hostkey",
        lambda ip, sha, timeout: "/tmp/fake_known_hosts",
    )

    def _mock_run(cmd, *, env, timeout, capture_output, text):
        return subprocess.CompletedProcess(
            args=cmd, returncode=1, stdout="",
            stderr="Permission denied (publickey,password).",
        )

    monkeypatch.setattr(subprocess, "run", _mock_run)

    bootstrapper = SshBootstrapper(hostkey_sha256="SHA256:abcdefg")
    with pytest.raises(NodeAddError) as excinfo:
        bootstrapper.install_key("192.168.1.1", "user", "passwd", Path("/tmp/key"))

    assert "Permission denied" in str(excinfo.value)
