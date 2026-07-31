"""WEB-015 : normalisation des erreurs inattendues sans fuite d'exception interne.

Chaque test vérifie que le client HTTP ne reçoit qu'un message générique "erreur interne"
lorsqu'une exception inattendue se produit dans les routes /api/detect,
/api/stacks/recommended, /api/bricks ; l'opérateur garde la trace complète sur stderr.
"""
import json
import threading
import urllib.error
import urllib.request

import pytest

import forgeai.web.server as web_server
from forgeai.web.server import build_server


# ---------------------------------------------------------------------------
# Fixtures (style test_web_auth.py)
# ---------------------------------------------------------------------------

@pytest.fixture()
def live():
    """Serveur lié sur loopback, port aléatoire, threadé."""
    srv = build_server("127.0.0.1", 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]
    yield f"http://127.0.0.1:{port}", port
    srv.shutdown()
    srv.server_close()


def _get(base, path):
    """GET helper, retourne (status, body_bytes)."""
    req = urllib.request.Request(base + path, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_detect_erreur_ne_fuite_pas(live, monkeypatch):
    """GET /api/detect avec exception interne → 500, secret absent de la réponse."""
    secret = "api_key=" + "a" * 32  # proof:allow (secret factice de test sans impact)
    monkeypatch.setattr(
        web_server,
        "hardware_json",
        lambda: (_ for _ in ()).throw(RuntimeError(f"chemin /home/u/.secret/x {secret}")),
    )
    base, _ = live
    status, body = _get(base, "/api/detect")
    assert status == 500
    payload = json.loads(body)
    # OPS-031D : le corps peut porter en plus `request_id` — jeton OPAQUE généré par le serveur,
    # qui ne divulgue rien de l'exception. La garantie WEB-015 est donc exprimée en INVARIANT DE
    # CLÉS (aucune clé hors de cet ensemble) plutôt qu'en égalité stricte.
    assert set(payload) <= {"error", "request_id"}, f"clé inattendue dans le corps : {payload}"
    assert payload["error"] == "erreur interne"
    body_str = body.decode()
    assert "api_key" not in body_str, "FUITE: api_key dans la réponse"
    assert ("a" * 32) not in body_str, "FUITE: secret longueur 32"
    assert "/home/u/.secret" not in body_str, "FUITE: chemin fichier"
    assert "RuntimeError" not in body_str, "FUITE: type d'exception"


def test_stacks_recommended_erreur_ne_fuite_pas(live, monkeypatch):
    """GET /api/stacks/recommended avec erreur → 500, secret absent."""
    secret = "token=" + "b" * 40  # proof:allow
    monkeypatch.setattr(
        web_server,
        "hardware_json",
        lambda: (_ for _ in ()).throw(IOError(f"/etc/secret.conf {secret}")),
    )
    base, _ = live
    status, body = _get(base, "/api/stacks/recommended")
    assert status == 500
    payload = json.loads(body)
    # OPS-031D : le corps peut porter en plus `request_id` — jeton OPAQUE généré par le serveur,
    # qui ne divulgue rien de l'exception. La garantie WEB-015 est donc exprimée en INVARIANT DE
    # CLÉS (aucune clé hors de cet ensemble) plutôt qu'en égalité stricte.
    assert set(payload) <= {"error", "request_id"}, f"clé inattendue dans le corps : {payload}"
    assert payload["error"] == "erreur interne"
    body_str = body.decode()
    assert secret not in body_str
    assert "/etc/secret.conf" not in body_str


def test_discover_erreur_ne_fuite_pas(live, monkeypatch):
    """GET /api/discover?node=local avec erreur interne (inventaire) → 500, secret absent."""
    secret = "password=" + "c" * 50  # proof:allow
    def _lever(*args, **kwargs):
        raise ValueError(f"DB /var/run/secrets/db {secret}")
    monkeypatch.setattr(web_server, "inventaire", _lever)
    base, _ = live
    status, body = _get(base, "/api/discover?node=local")
    assert status == 500
    payload = json.loads(body)
    # OPS-031D : le corps peut porter en plus `request_id` — jeton OPAQUE généré par le serveur,
    # qui ne divulgue rien de l'exception. La garantie WEB-015 est donc exprimée en INVARIANT DE
    # CLÉS (aucune clé hors de cet ensemble) plutôt qu'en égalité stricte.
    assert set(payload) <= {"error", "request_id"}, f"clé inattendue dans le corps : {payload}"
    assert payload["error"] == "erreur interne"
    body_str = body.decode()
    assert secret not in body_str
    assert "/var/run/secrets/db" not in body_str
    assert "ValueError" not in body_str


def test_message_generique_exact(live, monkeypatch):
    """La réponse d'erreur ne porte que le message générique (+ l'identifiant opaque OPS-031D)."""
    monkeypatch.setattr(web_server, "hardware_json", lambda: 1 / 0)  # ZeroDivisionError
    base, _ = live
    status, body = _get(base, "/api/detect")
    assert status == 500
    data = json.loads(body)
    assert set(data) <= {"error", "request_id"}, f"clé inattendue dans le corps : {data}"
    assert data["error"] == "erreur interne", f"message non générique : {data}"
    if "request_id" in data:
        # OPS-031D : le seul champ additionnel toléré est un identifiant OPAQUE (alphabet restreint),
        # jamais un détail interne — on le vérifie plutôt que de le prendre pour acquis.
        from forgeai.web.server import _REQUEST_ID_RE
        assert _REQUEST_ID_RE.match(data["request_id"]), (
            f"request_id non opaque/conforme : {data['request_id']!r}"
        )


def test_trace_operateur_sur_stderr(live, monkeypatch, capfd):
    """L'opérateur (stderr) reçoit la traceback complète même si le client non."""
    monkeypatch.setattr(web_server, "hardware_json", lambda: 1 / 0)
    base, _ = live
    _get(base, "/api/detect")
    captured = capfd.readouterr()
    assert "ZeroDivisionError" in captured.err, (
        "Traceback absente de stderr, l'opérateur perd le diagnostic"
    )


def test_cluster_status_detail_redige(live, monkeypatch):
    """GET /api/nodes/status : ClusterError encapsule un {exc} interne → le detail exposé
    (200 mode dégradé) est rédigé (secret absent), sans fuite via str(exc)."""
    from forgeai.network.nodes import ClusterError
    secret = "api_key=" + "d" * 32  # proof:allow
    def _lever(_runner):
        raise ClusterError(f"sortie kubectl illisible : {secret}")
    monkeypatch.setattr(web_server, "cluster_status", _lever)
    base, _ = live
    status, body = _get(base, "/api/nodes/status")
    assert status == 200
    payload = json.loads(body)
    assert payload["nodes"] == []
    assert secret not in body.decode(), "FUITE: secret dans detail ClusterError"
    assert "«REDACTED»" in payload["detail"]  # rédaction appliquée


def test_detect_nominal_200(live):
    """Sans erreur, la route /api/detect renvoie 200 (non-régression)."""
    base, _ = live
    status, body = _get(base, "/api/detect")
    assert status == 200
    assert json.loads(body)  # JSON valide, ne lève pas
