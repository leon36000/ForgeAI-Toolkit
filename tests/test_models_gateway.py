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
    GatewayStore,
    assert_via_gateway,
    prove_traversal,
    wire_all,
    wire_brick,
)
from forgeai.models.routes import RouteError, RouteStore

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


def test_gateway_refuse_hote_fournisseur_avec_point_final():
    """Bug hunt : un FQDN absolu avec point final (forme standard, transparente pour la
    résolution DNS et tout client HTTP réel) contournait la garde — urlparse() conserve ce
    point ('api.openai.com.' != 'api.openai.com' en tant que chaîne Python) alors que c'est
    exactement le même hôte réel."""
    with pytest.raises(GatewayError):
        GatewayConfig("https://openrouter.ai./api/v1")


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


def test_wire_all_route_introuvable_dans_le_store():
    """I18N-031 : `wire_all` propage un GatewayError bilingue (`route_role_introuvable`)
    quand le nom de route existe dans le role_mapping mais pas dans le RouteStore."""
    store = RouteStore.__new__(RouteStore)

    def _echoue(name):
        raise RouteError(f"route '{name}' inconnue")

    store.get = _echoue
    with pytest.raises(GatewayError, match="r-absente"):
        wire_all([("b1", "chat")], {"chat": "r-absente"}, store, GW)


def test_gateway_store_get_gateway_non_configure(tmp_path):
    """I18N-031 : `GatewayStore.get_gateway()` sur un home sans gateway.json lève un
    GatewayError bilingue (`non_configure`), jamais un texte français codé en dur."""
    store = GatewayStore(tmp_path / "aucun-gateway-ici")
    with pytest.raises(GatewayError, match="gateway"):
        store.get_gateway()


# --- RC1-456-iter3 : même famille que #482/#492/#527/#528 — gateway.json/wirings.json sont dans
# portability.py::SETUP_FILES (import_setup les copie sans validation de structure interne, seul
# routes.json est validé en profondeur) — un fichier édité à la main ou importé depuis un bundle
# corrompu ne doit jamais faire lever TypeError, seulement une erreur bilingue explicite. ---
def test_get_gateway_json_non_dict_leve_gatewayerror_pas_typeerror(tmp_path):
    """RC1-456-iter3 : gateway.json contenant un JSON valide mais top-level non-dict (ex. une
    liste) fait actuellement lever `TypeError: models.gateway.GatewayConfig() argument after **
    must be a mapping, not list` au lieu d'un GatewayError explicite."""
    home = tmp_path / "models"
    home.mkdir(parents=True)
    (home / "gateway.json").write_text("[1, 2, 3]", encoding="utf-8")
    store = GatewayStore(home)
    with pytest.raises(GatewayError):
        store.get_gateway()


def test_load_wirings_element_non_dict_leve_gatewayerror_pas_typeerror(tmp_path):
    """RC1-456-iter3 : wirings.json contenant une liste dont un élément n'est pas un dict (ex.
    fusion accidentelle de deux exports, ou édition manuelle) fait actuellement lever TypeError
    au lieu d'un GatewayError explicite lors de `GatewayStore.wirings()`."""
    home = tmp_path / "models"
    home.mkdir(parents=True)
    (home / "wirings.json").write_text(json.dumps([{"brick_id": "b1", "role": "chat"}, None]),
                                        encoding="utf-8")
    store = GatewayStore(home)
    with pytest.raises(GatewayError):
        store.wirings()


def test_gateway_store_wire_route_introuvable(tmp_path):
    """I18N-031 : `GatewayStore.wire()` propage un GatewayError bilingue
    (`route_introuvable`) quand la route nommée n'existe pas dans le RouteStore persisté."""
    home = tmp_path / "models"
    store = GatewayStore(home)
    store.set_gateway(GW)
    with pytest.raises(GatewayError, match="route-jamais-ajoutee"):
        store.wire("b1", "chat", "route-jamais-ajoutee")


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


def test_assert_detecte_brique_pointant_fournisseur_avec_point_final():
    """Même contournement que ci-dessus, sur la 2e garde INDÉPENDANTE (audit des câblages
    déjà écrits, assert_via_gateway::host in _PROVIDER_HOSTS) — les deux gardes doivent être
    insensibles au point final d'un FQDN absolu.

    Isolation de la garde précisément (pas juste « une violation quelconque », que la garde
    générale « base != gateway.base_url » produirait de toute façon) : on filtre les
    violations sur le message SPÉCIFIQUE de la détection d'hôte fournisseur.
    """
    rogue = BrickWiring("rogue2", "chat", {
        "OPENAI_API_BASE": "https://api.openai.com./v1",  # point final = même hôte réel
        "OPENAI_API_KEY": "${FORGEAI_GATEWAY_KEY}", "OPENAI_MODEL": "gpt"})
    violations = assert_via_gateway([rogue], GW)
    hote_violations = [v for v in violations if "hôte fournisseur" in v]
    assert hote_violations, (
        f"la garde host in _PROVIDER_HOSTS doit détecter le point final, violations={violations!r}"
    )


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


def test_assert_brique_fournisseur_et_cle_en_clair():
    rogue = BrickWiring(
        brick_id="rogue",
        role="chat",
        env={
            "OPENAI_API_BASE": "https://api.openai.com/v1",
            "OPENAI_API_KEY": "cle-en-clair-interdite",
            "OPENAI_MODEL": "m",
        },
    )
    violations = assert_via_gateway([rogue], GW)
    has_provider = any(
        "fournisseur" in v.lower() or "api.openai.com" in v.lower() for v in violations
    )
    has_clear = any("clair" in v.lower() for v in violations)
    assert has_provider, violations
    assert has_clear, violations
    assert len(violations) >= 2, violations
