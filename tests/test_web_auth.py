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
import threading
import urllib.error
import urllib.request

import pytest

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


def test_jeton_exige_si_defini(live, monkeypatch):
    """Si FORGEAI_WEB_TOKEN est défini, une route mutante sans jeton → 401 ; avec le bon jeton → pas 401."""
    monkeypatch.setattr("forgeai.web.server._WEB_TOKEN", "s3cr3t", raising=False)
    base, port = live
    hdr_ok_origin = {"Origin": f"http://127.0.0.1:{port}", "Host": f"127.0.0.1:{port}"}
    code_sans, _ = _post(base, "/api/deploy", hdr_ok_origin, {"stack": "agentique"})
    assert code_sans == 401, f"sans jeton → 401, reçu {code_sans}"
    code_avec, _ = _post(base, "/api/deploy",
                         {**hdr_ok_origin, "Authorization": "Bearer s3cr3t"}, {"stack": "agentique"})
    assert code_avec != 401, "le bon jeton ne doit pas être refusé"


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
    assert am(host="192.168.1.5:8765", bind_host="192.168.1.5") == (True, 0)  # hôte lié
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
