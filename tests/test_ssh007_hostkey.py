"""Tests unitaires SSH-007 — enrôlement explicite de l'empreinte de la clé d'hôte SSH."""

from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import forgeai.network.remote_probe as rp
from forgeai.network.remote_probe import RemoteProbeError, SshRunner

# Empreinte valide de test (factice, mais au bon format)
GOOD = "SHA256:AAAAgoodfingerprintvalue0000000000000000000"
BAD = "SHA256:ATTAQUANT0000000fingerprintvalue0000000000"

HOST = "testhost"
USER = "testuser"
KEYFILE = "/tmp/id_rsa_test"
OFFERED_LINE = f"{HOST} ssh-ed25519 AAAAoffered\n"


# ---------------------------------------------------------------------------
# Dispatcher fake pour subprocess.run
# ---------------------------------------------------------------------------
def fake_run_dispatcher(good_fp=GOOD, bad_fp=BAD):
    """Retourne un callable remplaçant subprocess.run, enregistrant les argv observés."""
    calls = []

    def fake(cmd, **kwargs):
        calls.append(cmd)
        exe = cmd[0] if cmd else ""
        if exe == "ssh-keyscan":
            return subprocess.CompletedProcess(cmd, 0, stdout=OFFERED_LINE, stderr="")
        if exe == "ssh-keygen":
            tmpfile = [a for a in cmd if not a.startswith("-")]
            if len(tmpfile) < 2:
                return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="")
            fname = tmpfile[-1]
            with open(fname) as fh:
                content = fh.read()
            fp = good_fp if OFFERED_LINE.rstrip() in content else bad_fp
            return subprocess.CompletedProcess(
                cmd, 0, stdout=f"256 {fp} {HOST} (ED25519)\n", stderr="")
        if exe == "ssh":
            return subprocess.CompletedProcess(cmd, 0, stdout="ok\n", stderr="")
        raise RuntimeError(f"Commande inattendue: {cmd}")

    fake.calls = calls
    return fake


# G1 — empreinte vide
def test_empty_fingerprint():
    with pytest.raises(RemoteProbeError, match="SSH-007"):
        SshRunner(USER, HOST, KEYFILE, "")


# G2 — empreinte mal formée (pas de deux-points)
def test_malformed_fingerprint():
    with pytest.raises(RemoteProbeError, match="SSH-007"):
        SshRunner(USER, HOST, KEYFILE, "pas-de-deux-points")


# G2b — empreinte avec deux-points mais MAUVAIS préfixe (MD5:/foo:) : refus AVANT
#       tout appel réseau (CA2). Le : seul ne suffit pas — il faut le préfixe SHA256:.
@pytest.mark.parametrize("bad", ["MD5:abc123", "foo:bar", "sha256:minuscule"])
def test_malformed_fingerprint_wrong_prefix(bad, monkeypatch):
    def _boom(*a, **k):
        raise AssertionError("aucun appel réseau ne doit avoir lieu avant validation")
    monkeypatch.setattr(subprocess, "run", _boom)
    with pytest.raises(RemoteProbeError, match="SSH-007"):
        SshRunner(USER, HOST, KEYFILE, bad)


# G3 — correspondance réussie : vérification du known_hosts et des options ssh
def test_successful_enrollment(monkeypatch, tmp_path):
    fake = fake_run_dispatcher()
    monkeypatch.setattr(subprocess, "run", fake)

    r = SshRunner(USER, HOST, KEYFILE, GOOD)
    code, out = r.run(["echo", "x"])

    ssh_calls = [c for c in fake.calls if c[0] == "ssh"]
    assert len(ssh_calls) == 1
    ssh_args = ssh_calls[0]
    assert "-o" in ssh_args
    assert "StrictHostKeyChecking=yes" in ssh_args
    assert any("UserKnownHostsFile=" in a for a in ssh_args)
    assert "accept-new" not in str(ssh_args)

    kh_path = r._known_hosts
    assert os.path.exists(kh_path)
    with open(kh_path) as f:
        content = f.read()
    assert content.rstrip() == OFFERED_LINE.rstrip()

    st = os.stat(kh_path)
    assert stat.S_IMODE(st.st_mode) == 0o600

    r.close()
    assert not os.path.exists(kh_path)


# G4 — aucune clé offerte ne correspond → RemoteProbeError, pas d'appel ssh métier
def test_mismatched_fingerprint(monkeypatch):
    fake = fake_run_dispatcher(good_fp="SHA256:someotherempreinte")
    monkeypatch.setattr(subprocess, "run", fake)
    r = SshRunner(USER, HOST, KEYFILE, GOOD)

    with pytest.raises(RemoteProbeError, match="SSH-007"):
        r.run(["echo", "x"])

    ssh_calls = [c for c in fake.calls if c[0] == "ssh"]
    assert len(ssh_calls) == 0


# G5 — close() supprime le fichier known_hosts même après run
def test_close_removes_known_hosts(monkeypatch, tmp_path):
    fake = fake_run_dispatcher()
    monkeypatch.setattr(subprocess, "run", fake)
    r = SshRunner(USER, HOST, KEYFILE, GOOD)
    r.run(["echo", "x"])
    kh_path = r._known_hosts
    assert os.path.exists(kh_path)
    r.close()
    assert not os.path.exists(kh_path)
    r.close()  # rappel sans effet


# G6 — détectance : l'argv de run ne contient jamais accept-new
def test_no_accept_new_in_argv(monkeypatch):
    fake = fake_run_dispatcher()
    monkeypatch.setattr(subprocess, "run", fake)
    r = SshRunner(USER, HOST, KEYFILE, GOOD)
    _, _ = r.run(["ls"])
    ssh_calls = [c for c in fake.calls if c[0] == "ssh"]
    assert len(ssh_calls) > 0
    for call in ssh_calls:
        assert "StrictHostKeyChecking=accept-new" not in call
        assert "accept-new" not in call


# G7 — intégration CLI : --hostkey requis pour node probe
def test_cli_probe_requires_hostkey(monkeypatch, tmp_path):
    import forgeai.cli as cli

    monkeypatch.setattr(cli, "_node_probe", lambda args: 0)  # no-op
    with pytest.raises(SystemExit) as excinfo:
        cli.main([
            "node", "probe", "--node-host", "h", "--user", "u", "--keyfile", "k",
            "--registre", str(tmp_path / "r.jsonl"),
            # --hostkey absent
        ])
    assert excinfo.value.code != 0


def test_cli_discover_local_no_hostkey(monkeypatch, tmp_path):
    import forgeai.cli as cli

    monkeypatch.setattr(cli, "_node_discover", lambda args: 0)
    # hostname est POSITIONNEL ('local'), pas un flag --hostname
    cli.main([
        "node", "discover", "local", "--registre", str(tmp_path / "r.jsonl"),
    ])


def test_cli_discover_remote_requires_hostkey(monkeypatch, capsys, tmp_path):
    import forgeai.cli as cli

    monkeypatch.setattr(
        "forgeai.network.remote_probe.SshRunner.__init__",
        lambda self, user, host, keyfile, hostkey, timeout_s=20.0: None,
    )
    monkeypatch.setattr("forgeai.network.remote_probe.SshRunner.run", lambda self, argv: (0, "fake"))
    monkeypatch.setattr("forgeai.network.discover.charger_signatures", lambda: [])
    monkeypatch.setattr("forgeai.network.discover.inventaire", lambda *a, **k: {})
    monkeypatch.setattr("forgeai.core.registre.append", lambda *a: None)

    res = cli.main([
        "node", "discover", "h", "--user", "u", "--keyfile", "k",
        "--registre", str(tmp_path / "r.jsonl"),
        # hostname positionnel 'h' ; pas de --hostkey
    ])
    captured = capsys.readouterr()
    assert "ECHEC DISCOVER" in captured.err
    assert "SSH-007" in captured.err
    assert res == 12
