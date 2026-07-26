"""Story B-09 — preuve bout-en-bout de la CLI `forgeai model` contre un VRAI serveur HTTP
local (stdlib) compatible OpenAI. Prouve : test de connexion réel, clé lue via env (jamais
argv), registre = empreinte seule, `list`/`test` n'exposent jamais la clé.
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from forgeai.cli import main

SECRET = "sk-cli-secret-NEVER-LEAK-99"


class _OpenAIStub(BaseHTTPRequestHandler):
    received_auth: list[str] = []
    logs: list[str] = []

    def do_POST(self):
        self.received_auth.append(self.headers.get("Authorization", ""))
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)
        body = json.dumps({"choices": [{"message": {"content": "pong"}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        # Capture au lieu d'écrire sur stderr (n'encombre pas la sortie pytest).
        type(self).logs.append(fmt % args if args else fmt)


@pytest.fixture
def stub_server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _OpenAIStub)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    port = srv.server_address[1]
    yield f"http://127.0.0.1:{port}/v1"
    srv.shutdown()


def test_cli_add_cloud_flux_complet(tmp_path, stub_server, monkeypatch, capsys):
    home = tmp_path / "models"
    registre = tmp_path / "registre.jsonl"
    monkeypatch.setenv("FORGEAI_TEST_KEY", SECRET)
    monkeypatch.setenv("FORGEAI_TEST_PP", "passphrase-coffre")

    rc = main(["model", "add-cloud", "--name", "local-stub", "--provenance", "direct",
               "--base-url", stub_server, "--model-id", "demo",
               "--api-key-env", "FORGEAI_TEST_KEY", "--passphrase-env", "FORGEAI_TEST_PP",
               "--home", str(home), "--registre", str(registre)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "GREEN" in out and SECRET not in out          # jamais la clé à l'écran

    # registre : empreinte seulement, jamais la clé
    reg = registre.read_text()
    assert "sha256:" in reg and SECRET not in reg
    # routes.json : pas de clé ; vault : scellé (pas de clé en clair)
    assert SECRET not in (home / "routes.json").read_text()
    assert SECRET not in (home / "vault.json").read_text()
    # le serveur a bien reçu la clé en en-tête (preuve d'appel réel authentifié)
    assert any(SECRET in a for a in _OpenAIStub.received_auth)

    # list n'expose jamais la clé
    main(["model", "list", "--home", str(home)])
    assert SECRET not in capsys.readouterr().out

    # test re-sonde la route (GREEN) via le coffre
    rc = main(["model", "test", "--name", "local-stub",
               "--passphrase-env", "FORGEAI_TEST_PP", "--home", str(home)])
    assert rc == 0
    assert "GREEN" in capsys.readouterr().out


def test_cli_add_cloud_echec_reseau_rien_ajoute(tmp_path, monkeypatch, capsys):
    home = tmp_path / "models"
    monkeypatch.setenv("K", SECRET); monkeypatch.setenv("P", "pp")
    # port fermé → échec réseau → aucune route, message clair, code 9
    rc = main(["model", "add-cloud", "--name", "cassee", "--provenance", "direct",
               "--base-url", "http://127.0.0.1:1/v1", "--model-id", "m",
               "--api-key-env", "K", "--passphrase-env", "P", "--home", str(home),
               "--registre", str(tmp_path / "r.jsonl")])
    assert rc == 9
    assert not (home / "routes.json").exists()
    err = capsys.readouterr().err
    assert "ECHEC ROUTE" in err and SECRET not in err


@pytest.mark.parametrize(
    "protected_name",
    [
        "routes.json",
        "vault.json",
        "gateway.json",
        ".models-transaction.json",
        ".models-transaction.lock",
        "Routes.json",
        "Vault.json",
        ".Models-Transaction.json",
        ".Models-Transaction.lock",
    ],
)
def test_cli_export_refuse_ecraser_un_fichier_protege(
    tmp_path, protected_name, capsys
):
    """--out ne peut jamais viser l'état vivant du répertoire exporté."""
    home = tmp_path / "models"
    home.mkdir()
    (home / "routes.json").write_text("[]", encoding="utf-8")
    (home / "vault.json").write_text('{"sentinelle":"coffre"}', encoding="utf-8")
    (home / "gateway.json").write_text('{"sentinelle":"gateway"}', encoding="utf-8")
    protected = home / protected_name
    before = protected.read_bytes() if protected.exists() else None

    rc = main(
        [
            "export",
            "--home",
            str(home),
            "--out",
            str(protected),
            "--registre",
            str(tmp_path / "registre.jsonl"),
        ]
    )

    assert rc == 11
    assert "ECHEC EXPORT" in capsys.readouterr().err
    if before is None:
        assert not protected.exists() or protected.read_bytes() == b""
    else:
        assert protected.read_bytes() == before
