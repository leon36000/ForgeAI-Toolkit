"""FAI-0001 (#109) — le serveur web n'a ni contrôle d'origine ni jeton : toute page (site
malveillant via CSRF/DNS-rebinding) ou toute machine du réseau (si bind non-loopback) peut
déclencher les routes mutantes (/api/deploy → subprocess, /api/nodes → ssh, /api/nodes/prepare).

Spécification d'un garde sur les requêtes MUTANTES (POST) :
- rejet 403 si l'en-tête `Origin` est présent et n'est pas la même origine (loopback/hôte lié) → anti-CSRF ;
- rejet 403 si l'en-tête `Host` n'est pas loopback/hôte lié → anti DNS-rebinding ;
- si `FORGEAI_WEB_TOKEN` est défini, exiger `Authorization: Bearer <token>` sur les routes mutantes.
La même origine (l'UI servie par le serveur) DOIT continuer à fonctionner.

RED avant correctif : aucun garde → une requête POST cross-origin/rebinding est traitée (pas de 403).
"""
import json
import secrets
import threading
import urllib.error
import urllib.request

import pytest

import forgeai.web.server as web_server
from forgeai.web.server import authorize_mutation, build_server, _normalize_host


@pytest.fixture()
def live(monkeypatch):
    # déploiement neutralisé : le garde doit rejeter AVANT tout traitement, mais par sécurité
    # on ne veut aucun subprocess réel si le garde laissait passer.
    monkeypatch.setattr("forgeai.web.server._DEPLOY_CMD", ["python3", "-c", "pass"], raising=False)
    srv = build_server("127.0.0.1", 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]
    yield f"http://127.0.0.1:{port}", port
    srv.shutdown(); srv.server_close()


@pytest.fixture()
def live_non_loopback():
    """Serveur lié publiquement, joint via loopback uniquement pour le socket de test."""
    srv = build_server("0.0.0.0", 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]
    yield f"http://127.0.0.1:{port}"
    srv.shutdown(); srv.server_close()


def _post(base, path, headers, body=None):
    data = json.dumps(body or {}).encode()
    req = urllib.request.Request(base + path, data=data, method="POST",
                                 headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def test_post_origine_croisee_rejetee(live):
    """CSRF : un POST avec Origin d'un site tiers → 403 (jamais traité)."""
    base, _ = live
    code, _ = _post(base, "/api/deploy", {"Origin": "http://evil.example"},
                    {"stack": "agentique", "backend": "compose", "confirm": "FORCER"})
    assert code == 403, f"origine croisée doit être refusée, reçu {code}"


def test_post_host_rebinding_rejete(live):
    """DNS-rebinding : un POST avec Host non-loopback → 403."""
    base, _ = live
    code, _ = _post(base, "/api/deploy", {"Host": "evil.example"},
                    {"stack": "agentique", "backend": "compose", "confirm": "FORCER"})
    assert code == 403, f"Host de rebinding doit être refusé, reçu {code}"


def test_post_cross_site_sans_origin_rejete(live):
    """Défense en profondeur (revue Gemini) : une requête cross-site (Sec-Fetch-Site: cross-site)
    doit être refusée MÊME si l'en-tête Origin est absent — on ne saute jamais le contrôle."""
    base, _ = live
    code, _ = _post(base, "/api/deploy", {"Sec-Fetch-Site": "cross-site"},
                    {"stack": "agentique", "backend": "compose", "confirm": "FORCER"})
    assert code == 403, f"cross-site sans Origin doit être refusé, reçu {code}"


def test_post_meme_origine_passe_le_garde(live):
    """L'UI servie (même origine, Host loopback) n'est PAS bloquée par le garde (≠ 403)."""
    base, port = live
    code, _ = _post(base, "/api/deploy",
                    {"Origin": f"http://127.0.0.1:{port}", "Host": f"127.0.0.1:{port}"},
                    {"stack": "agentique", "backend": "compose"})
    assert code != 403, "la même origine ne doit jamais être refusée par le garde"


def test_jeton_exige_si_defini(monkeypatch):
    """Si FORGEAI_WEB_TOKEN est défini, une route mutante sans jeton → 401 ; avec le bon jeton → pas 401."""
    configured_token = secrets.token_urlsafe(32)
    monkeypatch.setattr(web_server, "_WEB_TOKEN", configured_token)
    server = build_server("127.0.0.1", 0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_address[1]
    base = f"http://127.0.0.1:{port}"
    try:
        hdr_ok_origin = {"Origin": base, "Host": f"127.0.0.1:{port}"}
        code_sans, _ = _post(base, "/api/deploy", hdr_ok_origin, {"stack": "agentique"})
        code_avec, _ = _post(
            base,
            "/api/deploy",
            {**hdr_ok_origin, "Authorization": f"Bearer {configured_token}"},
            {"stack": "agentique"},
        )
    finally:
        server.shutdown()
        server.server_close()

    assert code_sans == 401, f"sans jeton → 401, reçu {code_sans}"
    assert code_avec != 401, "le bon jeton ne doit pas être refusé"


@pytest.mark.parametrize("path", ["/api/deploy", "/api/nodes", "/api/nodes/prepare", "/api/models"])
def test_bind_non_loopback_exige_bearer_meme_avec_host_loopback(live_non_loopback, path):
    """Le bind public exige un Bearer, même si le client joint le socket via loopback."""
    code, _ = _post(live_non_loopback, path, {"Host": "127.0.0.1"}, {})
    assert code == 401, f"bind non-loopback sans Bearer doit être refusé, reçu {code}"


def test_authorize_mutation_bind_non_loopback_exige_bearer_sans_jeton_configure():
    assert authorize_mutation(
        origin=None,
        host="127.0.0.1",
        auth_header=None,
        bind_host="0.0.0.0",
        token=None,
    ) == (False, 401)


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("127.0.0.2", True),
        ("::1", True),
        ("localhost", True),
        ("LOCALHOST", True),
        ("0.0.0.0", False),
        ("::", False),
        ("network.example", False),
        ("*", False),
    ],
)
def test_classification_loopback_du_bind(host, expected):
    assert web_server._is_loopback_host(host) is expected


def test_deux_serveurs_concurrents_conservent_leurs_politiques(monkeypatch):
    """Un second serveur ne doit pas remplacer le bind ou le jeton du premier."""
    monkeypatch.setattr(web_server, "_WEB_TOKEN", None)
    loopback_server = build_server("127.0.0.1", 0)

    network_token = secrets.token_urlsafe(32)
    monkeypatch.setattr(web_server, "_WEB_TOKEN", network_token)
    network_server = build_server("0.0.0.0", 0)

    servers = (loopback_server, network_server)
    for server in servers:
        threading.Thread(target=server.serve_forever, daemon=True).start()

    loopback_base = f"http://127.0.0.1:{loopback_server.server_address[1]}"
    network_base = f"http://127.0.0.1:{network_server.server_address[1]}"
    try:
        loopback_code, _ = _post(
            loopback_base,
            "/api/deploy",
            {"Host": "127.0.0.1"},
            {"stack": "agentique"},
        )
        network_code_without_auth, _ = _post(
            network_base,
            "/api/deploy",
            {"Host": "127.0.0.1"},
            {"stack": "agentique"},
        )
        network_code_with_auth, _ = _post(
            network_base,
            "/api/deploy",
            {
                "Host": "127.0.0.1",
                "Authorization": f"Bearer {network_token}",
            },
            {"stack": "agentique"},
        )
    finally:
        for server in servers:
            server.shutdown()
            server.server_close()

    assert loopback_code != 401
    assert network_code_without_auth == 401
    assert network_code_with_auth != 401


# --- Tests unitaires de la fonction pure (branches : IPv6, hôte lié, Host absent, jeton) ---
def test_authorize_mutation_branches():
    def am(**kw):
        base = dict(origin=None, host="127.0.0.1", auth_header=None,
                    bind_host="127.0.0.1", token=None)
        return authorize_mutation(**{**base, **kw})

    assert am(origin="http://127.0.0.1:8765", host="127.0.0.1:8765") == (True, 0)  # même origine
    assert am(host="[::1]:8765") == (True, 0)  # IPv6 loopback
    assert am(origin="http://evil.test", host="127.0.0.1:8765") == (False, 403)  # CSRF
    assert am(host="attacker.test") == (False, 403)  # rebinding
    assert am(host=None) == (False, 403)  # Host absent
    assert am(host="192.168.1.5:8765", bind_host="192.168.1.5") == (False, 401)  # Bearer-only
    assert am(token="t") == (False, 401)  # jeton manquant
    assert am(auth_header="Bearer t", token="t") == (True, 0)  # bon jeton
    assert am(auth_header="Bearer x", token="t") == (False, 401)  # mauvais jeton
    assert am(sec_fetch_site="cross-site") == (False, 403)  # cross-site sans Origin
    assert am(sec_fetch_site="same-site") == (False, 403)  # cross-port local
    assert am(sec_fetch_site="same-origin") == (True, 0)  # UI même origine
    assert am(sec_fetch_site="none") == (True, 0)  # navigation directe


def test_normalize_host():
    assert _normalize_host("127.0.0.1:8765") == "127.0.0.1"
    assert _normalize_host("[::1]:8765") == "::1"
    assert _normalize_host("::1") == "::1"
    assert _normalize_host("LocalHost") == "localhost"
    assert _normalize_host(None) is None
    assert _normalize_host("") is None


# --- FAI-0001b — le jeton valide prime sur Host/Origin/Sec-Fetch-Site (accès distant authentifié) ---
def test_authorize_mutation_jeton_prioritaire():
    """FAI-0001b : un Bearer valide autorise immédiatement, même hors loopback (ROUGE avant correctif)."""
    def am(**kw):
        base = dict(origin=None, host="127.0.0.1", auth_header=None,
                    bind_host="127.0.0.1", token=None)
        return authorize_mutation(**{**base, **kw})

    # accès distant authentifié : Host hors de `allowed` (bind 0.0.0.0) mais Bearer valide → autorisé
    assert authorize_mutation(origin=None, host="192.168.1.5:8765", auth_header="Bearer t",
                              bind_host="0.0.0.0", token="t", sec_fetch_site=None) == (True, 0)
    # le jeton prime sur Sec-Fetch-Site cross-site
    assert authorize_mutation(origin=None, host="127.0.0.1:8765", auth_header="Bearer t",
                              bind_host="127.0.0.1", token="t", sec_fetch_site="cross-site") == (True, 0)
    # le jeton prime sur un Origin cross-origin
    assert am(origin="http://evil.test", host="127.0.0.1:8765",
              auth_header="Bearer t", token="t") == (True, 0)
    # jeton défini mais absent, même en loopback → 401
    assert am(host="127.0.0.1:8765", auth_header=None, token="t") == (False, 401)
    # jeton défini mais invalide, même en loopback → 401
    assert am(host="127.0.0.1:8765", auth_header="Bearer x", token="t") == (False, 401)
    # sans jeton configuré, aucun contournement réintroduit : les contrôles actuels s'appliquent
    assert am(host="192.168.1.5:8765", bind_host="0.0.0.0") == (False, 401)
    assert am(sec_fetch_site="cross-site") == (False, 403)


def test_live_distant_authentifie_passe(monkeypatch):
    """E2E FAI-0001b : POST « distant » (Host hors loopback, bind 0.0.0.0) + Bearer valide → pas 403."""
    configured_token = secrets.token_urlsafe(32)
    monkeypatch.setattr(web_server, "_WEB_TOKEN", configured_token)
    server = build_server("0.0.0.0", 0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        code, _ = _post(
            base,
            "/api/deploy",
            {
                "Host": "192.168.1.5:8765",
                "Authorization": f"Bearer {configured_token}",
            },
            {"stack": "agentique", "backend": "compose"},
        )
        code_sans, _ = _post(
            base,
            "/api/deploy",
            {"Host": "192.168.1.5:8765"},
            {"stack": "agentique", "backend": "compose"},
        )
    finally:
        server.shutdown()
        server.server_close()

    assert code != 403, f"accès distant authentifié ne doit pas être refusé par le garde, reçu {code}"
    # sans le jeton, le même POST distant reste refusé (anti-rebinding intact quand le jeton manque)
    assert code_sans == 401, f"jeton défini mais absent → 401, reçu {code_sans}"
