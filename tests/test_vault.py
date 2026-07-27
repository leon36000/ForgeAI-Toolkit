"""Story E3b — client coffre openbao (KV v2), stdlib pur.

Spec exécutable (TDAD, AVANT le code). Un faux serveur openbao KV v2 (http.server) valide le
contrat HTTP réel : écriture `POST /v1/secret/data/<path>` + lecture `GET …` authentifiées par
en-tête `X-Vault-Token`. Le comportement contre un openbao RÉEL est prouvé par l'e2e journalisé
au registre. Invariant secrets : ni le token ni la valeur ne doivent apparaître dans une exception.
"""
import json
import os
import stat
import sys
import threading
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from secrets import token_hex

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from forgeai.models import vault as file_vault_module
from forgeai.models.vault import Vault as FileVault
from forgeai.secrets.vault import VaultError, read, store

TOKEN = "root-token-e3b"


class _KVHandler(BaseHTTPRequestHandler):
    """openbao KV v2 minimal : exige le bon X-Vault-Token, stocke/rend sous data.data."""

    store: dict = {}

    def log_message(self, *args):  # silence
        return

    def _auth_ok(self) -> bool:
        return self.headers.get("X-Vault-Token") == TOKEN

    def do_POST(self):
        if not self._auth_ok():
            self.send_response(403)
            self.end_headers()
            return
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        path = self.path.split("/v1/secret/data/", 1)[-1]
        _KVHandler.store[path] = body.get("data", {})
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"data": {"created_time": "2026-01-01T00:00:00Z"}}).encode())

    def do_GET(self):
        if not self._auth_ok():
            self.send_response(403)
            self.end_headers()
            return
        path = self.path.split("/v1/secret/data/", 1)[-1]
        if path not in _KVHandler.store:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'{"errors":[]}')
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        payload = {"data": {"data": _KVHandler.store[path], "metadata": {"version": 1}}}
        self.wfile.write(json.dumps(payload).encode())


@pytest.fixture
def bao():
    _KVHandler.store = {}
    server = HTTPServer(("127.0.0.1", 0), _KVHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        yield base
    finally:
        server.shutdown()


def test_store_puis_read_round_trip(bao):
    store(bao, TOKEN, "forgeai/litellm", {"master_key": "sk-secret-xyz"})  # proof:allow — valeur de test
    assert read(bao, TOKEN, "forgeai/litellm") == {"master_key": "sk-secret-xyz"}  # proof:allow


def test_read_chemin_absent_leve_vaulterror(bao):
    with pytest.raises(VaultError):
        read(bao, TOKEN, "forgeai/inexistant")


def test_serveur_injoignable_leve_vaulterror():
    with pytest.raises(VaultError):
        read("http://127.0.0.1:1", TOKEN, "forgeai/litellm")


def test_mauvais_token_leve_vaulterror(bao):
    with pytest.raises(VaultError):
        store(bao, "mauvais-token", "forgeai/litellm", {"k": "v"})


def test_exception_ne_fuit_ni_token_ni_valeur(bao):
    # openbao injoignable : le message d'erreur ne doit contenir ni le token ni la valeur secrète.
    secret_value = "sk-ne-doit-pas-fuiter"  # proof:allow — valeur de test
    try:
        store("http://127.0.0.1:1", "TOKEN-CONFIDENTIEL", "forgeai/x", {"k": secret_value})
        raise AssertionError("aurait dû lever VaultError")
    except VaultError as exc:
        msg = str(exc)
        if "TOKEN-CONFIDENTIEL" in msg or secret_value in msg:
            raise AssertionError("VaultError disclosed a secret input")


def test_model_vault_refuses_target_symlink_before_reading_referent(
    tmp_path, monkeypatch
):
    referent = tmp_path / "external-vault.json"
    referent.write_text('{"external": "unchanged"}', encoding="utf-8")
    referent_digest = sha256(referent.read_bytes()).digest()
    target = tmp_path / "vault.json"
    target.symlink_to(referent)
    original_link = os.readlink(target)
    sentinel = token_hex(32)
    referent_was_read = False
    real_read_text = Path.read_text

    def observe_completed_read(path, *args, **kwargs):
        nonlocal referent_was_read
        content = real_read_text(path, *args, **kwargs)
        if Path(path) == target:
            referent_was_read = True
        return content

    monkeypatch.setattr(Path, "read_text", observe_completed_read)

    with pytest.raises(OSError) as caught:
        FileVault(target).put("cloud-key", sentinel, "test-passphrase")

    if sentinel in str(caught.value):
        raise AssertionError("vault exception disclosed the secret payload")
    if referent_was_read:
        raise AssertionError("vault read a target-symlink referent")
    assert target.is_symlink()
    assert os.readlink(target) == original_link
    if sha256(referent.read_bytes()).digest() != referent_digest:
        raise AssertionError("vault changed a target-symlink referent")


def test_model_vault_refuses_fifo_without_blocking_read(tmp_path, monkeypatch):
    target = tmp_path / "vault-fifo"
    os.mkfifo(target)
    observed_flags: list[int] = []
    path_read_attempted = False
    real_open = os.open
    real_read_text = Path.read_text

    def observe_real_open(path, flags, *args, **kwargs):
        if Path(path) == target:
            observed_flags.append(flags)
            required = os.O_NOFOLLOW | os.O_NONBLOCK
            if flags & required != required:
                raise OSError("unsafe vault open flags")
        return real_open(path, flags, *args, **kwargs)

    def reject_blocking_path_read(path, *args, **kwargs):
        nonlocal path_read_attempted
        if Path(path) == target:
            path_read_attempted = True
            raise OSError("blocking vault read refused by test")
        return real_read_text(path, *args, **kwargs)

    monkeypatch.setattr(file_vault_module.os, "open", observe_real_open)
    monkeypatch.setattr(Path, "read_text", reject_blocking_path_read)

    with pytest.raises(OSError):
        FileVault(target).names()

    if path_read_attempted:
        raise AssertionError("vault attempted a blocking FIFO read")
    if len(observed_flags) != 1:
        raise AssertionError("vault did not perform one bounded target open")
    assert stat.S_ISFIFO(target.stat().st_mode)


def test_model_vault_refuses_parent_symlink_before_external_change(tmp_path):
    external_dir = tmp_path / "external-vault-parent"
    external_dir.mkdir()
    os.chmod(external_dir, 0o750)
    external_mode = stat.S_IMODE(external_dir.stat().st_mode)
    external_file = external_dir / "existing"
    external_file.write_bytes(token_hex(32).encode("ascii"))
    external_digest = sha256(external_file.read_bytes()).digest()
    parent_link = tmp_path / "vault-parent"
    parent_link.symlink_to(external_dir, target_is_directory=True)
    original_link = os.readlink(parent_link)

    with pytest.raises(OSError):
        FileVault(parent_link / "vault.json").put(
            "cloud-key", token_hex(32), "test-passphrase"
        )

    assert parent_link.is_symlink()
    assert os.readlink(parent_link) == original_link
    assert stat.S_IMODE(external_dir.stat().st_mode) == external_mode
    if {entry.name for entry in external_dir.iterdir()} != {"existing"}:
        raise AssertionError("vault wrote through a parent symlink")
    if sha256(external_file.read_bytes()).digest() != external_digest:
        raise AssertionError("vault changed parent-symlink referent content")


def test_model_vault_parent_is_private_at_first_creation(tmp_path, monkeypatch):
    parent = tmp_path / "vault-parent"
    target = parent / "vault.json"
    observed_creation_modes: list[int] = []
    real_mkdir = os.mkdir

    def observe_real_mkdir(path, mode=0o777, *args, **kwargs):
        result = real_mkdir(path, mode, *args, **kwargs)
        if Path(path) == parent:
            observed_creation_modes.append(stat.S_IMODE(os.lstat(path).st_mode))
        return result

    monkeypatch.setattr(file_vault_module.os, "mkdir", observe_real_mkdir)
    previous_umask = os.umask(0)
    try:
        FileVault(target).put("cloud-key", token_hex(32), "test-passphrase")
    finally:
        os.umask(previous_umask)

    if not observed_creation_modes or any(
        mode & ~0o700 for mode in observed_creation_modes
    ):
        raise AssertionError("vault parent exposed excess creation permissions")
    assert stat.S_IMODE(parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(target.stat().st_mode) == 0o600


def test_model_vault_creates_nested_parent_under_restrictive_umask(
    tmp_path, monkeypatch
):
    parents = (tmp_path / "a", tmp_path / "a" / "b")
    target = parents[-1] / "vault.json"
    observed_creation_modes = {candidate: [] for candidate in parents}
    real_mkdir = os.mkdir

    def observe_real_mkdir(path, mode=0o777, *args, **kwargs):
        result = real_mkdir(path, mode, *args, **kwargs)
        candidate = Path(path)
        if candidate in observed_creation_modes:
            observed_creation_modes[candidate].append(
                stat.S_IMODE(os.lstat(candidate).st_mode)
            )
        return result

    monkeypatch.setattr(file_vault_module.os, "mkdir", observe_real_mkdir)
    previous_umask = os.umask(0o777)
    try:
        vault = FileVault(target)
        vault.put("first-key", token_hex(32), "test-passphrase")
        vault.put("second-key", token_hex(32), "test-passphrase")
    finally:
        os.umask(previous_umask)

    for candidate, modes in observed_creation_modes.items():
        if not modes or any(mode & ~0o700 for mode in modes):
            raise AssertionError(
                f"vault parent creation was not private: {candidate.name}"
            )
        assert stat.S_IMODE(candidate.stat().st_mode) == 0o700
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
