"""Story B-11 (DM-6) — branchement brique → gateway unique.

Prouve : (1) aucune brique ne pointe vers un modèle/fournisseur — tout via le gateway,
clé = jeton interne du gateway (jamais une clé fournisseur) ; (2) le câblage est PROUVÉ
par un appel traversant réel (brique → gateway → réponse non vide), pas une config présente.
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from forgeai.models.gateway import (
    BrickWiring,
    GatewayConfig,
    GatewayError,
    assert_via_gateway,
    prove_traversal,
    wire_all,
    wire_brick,
)
from forgeai.models.routes import RouteStore

GW = GatewayConfig("http://127.0.0.1:4000/v1", key_env="FORGEAI_GATEWAY_KEY")


class _GreenTransport:
    def __init__(self):
        self.calls = []

    def post(self, url, headers, body, timeout):
        self.calls.append({"url": url, "headers": headers})
        return 200, json.dumps({"choices": [{"message": {"content": "pong"}}]})


# ---------- câblage ----------

def test_wire_brick_pointe_vers_le_gateway():
    w = wire_brick("rag-worker", "chat", "glm-4.6", GW)
    assert w.env["OPENAI_API_BASE"] == GW.base_url
    assert w.env["OPENAI_MODEL"] == "glm-4.6"
    assert w.env["OPENAI_API_KEY"] == "${FORGEAI_GATEWAY_KEY}"  # référence, pas la valeur


def test_gateway_refuse_hote_fournisseur():
    with pytest.raises(GatewayError):
        GatewayConfig("https://openrouter.ai/api/v1")  # un fournisseur n'est pas LE gateway


def test_wire_all_resout_role_vers_route():
    store = RouteStore.__new__(RouteStore)  # get() monkeypaté ci-dessous
    from forgeai.models.routes import CloudRoute
    store.get = lambda name: CloudRoute(name, "openrouter", "http://x/v1", "z/glm-4.6",
                                        "sha256:abc", "2026-07-15")
    wirings = wire_all([("b1", "chat"), ("b2", "chat")], {"chat": "r-glm"}, store, GW)
    assert len(wirings) == 2 and all(w.env["OPENAI_MODEL"] == "z/glm-4.6" for w in wirings)


def test_wire_all_role_sans_route_echoue():
    store = RouteStore.__new__(RouteStore)
    with pytest.raises(GatewayError):
        wire_all([("b1", "inconnu")], {"chat": "r"}, store, GW)


# ---------- enforcement de l'invariant ----------

def test_assert_conforme_sans_violation():
    wirings = [wire_brick("b1", "chat", "m", GW), wire_brick("b2", "embed", "e", GW)]
    assert assert_via_gateway(wirings, GW) == []


def test_assert_detecte_brique_pointant_fournisseur():
    rogue = BrickWiring("rogue", "chat", {
        "OPENAI_API_BASE": "https://api.openai.com/v1",  # pointe DIRECTEMENT un fournisseur
        "OPENAI_API_KEY": "${FORGEAI_GATEWAY_KEY}", "OPENAI_MODEL": "gpt"})
    violations = assert_via_gateway([rogue], GW)
    assert violations and "rogue" in violations[0]


def test_assert_detecte_cle_en_clair():
    leaky = BrickWiring("leaky", "chat", {
        "OPENAI_API_BASE": GW.base_url,
        "OPENAI_API_KEY": "sk-EN-CLAIR-INTERDIT",  # clé littérale = violation
        "OPENAI_MODEL": "m"})
    violations = assert_via_gateway([leaky], GW)
    assert any("clair" in v for v in violations)


# ---------- preuve traversante réelle (brique → gateway → réponse) ----------

class _GatewayStub(BaseHTTPRequestHandler):
    seen_model: list[str] = []
    logs: list[str] = []

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        payload = json.loads(self.rfile.read(n) or b"{}")
        type(self).seen_model.append(payload.get("model", ""))
        body = json.dumps({"choices": [{"message": {"content": "pong-from-gateway"}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        type(self).logs.append(fmt % args if args else fmt)


@pytest.fixture
def gateway_server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _GatewayStub)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]
    yield GatewayConfig(f"http://127.0.0.1:{port}/v1")
    srv.shutdown()


def test_preuve_traversante_reelle(gateway_server):
    _GatewayStub.seen_model.clear()
    wiring = wire_brick("rag-worker", "chat", "glm-4.6", gateway_server)
    # conformité d'abord…
    assert assert_via_gateway([wiring], gateway_server) == []
    # …puis PREUVE : appel réel brique → gateway → réponse non vide
    result = prove_traversal(wiring, "jeton-interne-gateway")
    assert result.ok and result.light == "GREEN"
    assert _GatewayStub.seen_model == ["glm-4.6"]  # le gateway a bien reçu le modèle câblé


def test_traversal_avec_transport_injecte():
    tr = _GreenTransport()
    wiring = wire_brick("b", "chat", "m", GW)
    result = prove_traversal(wiring, "gw-key", transport=tr)
    assert result.ok
    assert tr.calls[0]["url"].startswith(GW.base_url)  # a bien tapé le gateway
    assert tr.calls[0]["headers"]["Authorization"] == "Bearer gw-key"  # jeton gateway


# ---------- e2e CLI : add-cloud → set-url → wire → verify ----------

def test_cli_gateway_flux_complet(tmp_path, gateway_server, monkeypatch, capsys):
    from forgeai.cli import main
    home = tmp_path / "models"
    registre = tmp_path / "reg.jsonl"
    endpoint = gateway_server.base_url          # sert de fournisseur (add-cloud) ET de gateway
    monkeypatch.setenv("K", "sk-provider-secret-XYZ")
    monkeypatch.setenv("P", "pp")

    # 1) route cloud (test réel GREEN contre le stub local)
    assert main(["model", "add-cloud", "--name", "r-chat", "--provenance", "direct",
                 "--base-url", endpoint, "--model-id", "glm-4.6",
                 "--api-key-env", "K", "--passphrase-env", "P",
                 "--home", str(home), "--registre", str(registre)]) == 0
    # 2) gateway unique
    assert main(["gateway", "set-url", "--url", endpoint, "--home", str(home),
                 "--registre", str(registre)]) == 0
    # 3) câblage brique (rôle chat → route r-chat)
    assert main(["gateway", "wire", "--brick", "rag-worker", "--role", "chat",
                 "--route", "r-chat", "--home", str(home), "--registre", str(registre)]) == 0
    # 4) invariant vérifié
    assert main(["gateway", "verify", "--home", str(home)]) == 0
    out = capsys.readouterr().out
    assert "invariant gateway OK" in out

    # persistance : aucune clé fournisseur nulle part ; le câblage référence la clé GATEWAY
    wirings = (home / "wirings.json").read_text()
    assert "sk-provider-secret-XYZ" not in wirings
    assert "${FORGEAI_GATEWAY_KEY}" in wirings
    assert "sk-provider-secret-XYZ" not in registre.read_text()
