"""Story E3b — client coffre openbao (KV v2), stdlib pur.

Spec exécutable (TDAD, AVANT le code). Un faux serveur openbao KV v2 (http.server) valide le
contrat HTTP réel : écriture `POST /v1/secret/data/<path>` + lecture `GET …` authentifiées par
en-tête `X-Vault-Token`. Le comportement contre un openbao RÉEL est prouvé par l'e2e journalisé
au registre. Invariant secrets : ni le token ni la valeur ne doivent apparaître dans une exception.
"""
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from secrets import token_hex

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

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
        assert "TOKEN-CONFIDENTIEL" not in msg
        assert secret_value not in msg


def test_model_vault_refuses_target_symlink_without_touching_referent(tmp_path):
    referent = tmp_path / "external-vault.json"
    referent.write_text('{"external": "unchanged"}', encoding="utf-8")
    target = tmp_path / "vault.json"
    target.symlink_to(referent)
    original_link = os.readlink(target)
    sentinel = token_hex(32)

    with pytest.raises(OSError) as caught:
        FileVault(target).put("cloud-key", sentinel, "test-passphrase")

    if sentinel in str(caught.value):
        raise AssertionError("vault exception disclosed the secret payload")
    assert target.is_symlink()
    assert os.readlink(target) == original_link
    assert referent.read_text(encoding="utf-8") == '{"external": "unchanged"}'
