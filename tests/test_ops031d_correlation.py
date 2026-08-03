"""OPS-031D — identifiants de corrélation de bout en bout.

WEB-015 rend les erreurs client GÉNÉRIQUES (la trace part sur stderr) : sans identifiant, un
signalement « j'ai eu erreur interne » ne désigne aucune des tracebacks du flux. Ces tests
verrouillent la corrélation (en-tête ↔ corps ↔ stderr) ET l'anti-injection de logs sur l'en-tête
`X-Request-Id` fourni par le client, qui est une entrée NON FIABLE.
"""

import json
import threading
import urllib.error
import urllib.request

import pytest

import forgeai.web.server as server
from forgeai.web.server import build_server, _REQUEST_ID_RE, _valider_request_id


@pytest.fixture()
def live():
    srv = build_server("127.0.0.1", 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()
    srv.server_close()


def _get(base, path, headers=None):
    req = urllib.request.Request(base + path, method="GET", headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.read(), dict(r.headers)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), dict(exc.headers)


def test_g1_toute_reponse_porte_un_identifiant(live):
    """CA1 : l'en-tête X-Request-Id est présent et conforme, y compris sur une 404."""
    for chemin in ("/api/health", "/chemin/inexistant"):
        _code, _corps, entetes = _get(live, chemin)
        cid = entetes.get("X-Request-Id")
        assert cid, f"X-Request-Id absent sur {chemin}"
        assert _REQUEST_ID_RE.match(cid), f"identifiant non conforme à l'allowlist : {cid!r}"


def test_g2_identifiant_client_valide_est_repris(live):
    """CA1 : un X-Request-Id VALIDE fourni en amont est repris tel quel (corrélation proxy)."""
    fourni = "trace-amont_42.AB"
    assert _REQUEST_ID_RE.match(fourni), "le cas de test doit être conforme à l'allowlist"
    _code, _corps, entetes = _get(live, "/api/health", {"X-Request-Id": fourni})
    assert entetes.get("X-Request-Id") == fourni


@pytest.mark.parametrize(
    "hostile",
    [
        "abc",                       # trop court
        "x" * 65,                    # trop long
        "id avec espaces",           # caractère hors allowlist
        "id;rm -rf /",               # métacaractères
        "",                          # vide
    ],
)
def test_g3_identifiant_client_hostile_est_remplace(live, hostile):
    """CA2 : une valeur hostile est REMPLACÉE (jamais tronquée ni nettoyée) et n'apparaît nulle part."""
    _code, corps, entetes = _get(live, "/api/health", {"X-Request-Id": hostile})
    cid = entetes.get("X-Request-Id")

    assert cid != hostile, f"la valeur hostile {hostile!r} a été acceptée"
    assert _REQUEST_ID_RE.match(cid), f"identifiant de remplacement non conforme : {cid!r}"
    fragment = hostile.strip().splitlines()[0] if hostile.strip() else None
    if fragment and len(fragment) > 4:
        assert fragment not in corps.decode(errors="replace"), "fragment hostile réfléchi dans le corps"


def test_g3b_validateur_unitaire():
    """CA2 : le validateur accepte l'allowlist et rejette tout le reste."""
    assert _valider_request_id("abcdefgh") == "abcdefgh"
    assert _valider_request_id("A-1_2.3xyz") == "A-1_2.3xyz"
    for mauvais in (None, "", "court", "x" * 65, "a b c d", "cr\r\nlf-inject", "é" * 10):
        assert _valider_request_id(mauvais) is None, f"{mauvais!r} aurait dû être rejeté"


def test_g4_g5_erreur_generique_correle_entete_corps_et_stderr(live, monkeypatch, capfd):
    """CA3 : même identifiant en en-tête, dans le corps d'erreur et devant la trace stderr,
    sans qu'aucun détail interne ne fuie (garantie WEB-015 préservée)."""
    fragment_interne = "chemin /home/u/.prive/x"  # chemin interne, PAS un identifiant
    monkeypatch.setattr(
        server, "hardware_json",
        lambda: (_ for _ in ()).throw(RuntimeError(fragment_interne)),
    )

    code, corps, entetes = _get(live, "/api/detect")
    assert code == 500
    charge = json.loads(corps)

    # WEB-015 : rien d'interne ne fuit
    assert charge["error"] == "erreur interne"
    assert "RuntimeError" not in corps.decode()
    assert "/home/u/.prive" not in corps.decode()

    # OPS-031D : l'identifiant est présent et cohérent en-tête ↔ corps
    cid = entetes.get("X-Request-Id")
    assert charge.get("request_id") == cid, "corps et en-tête doivent porter le MÊME identifiant"
    assert _REQUEST_ID_RE.match(cid)

    # ... et il précède la trace côté opérateur
    capture = capfd.readouterr()
    assert cid in capture.err, "l'identifiant doit accompagner la trace sur stderr"
    assert "RuntimeError" in capture.err, "l'opérateur doit garder la trace complète"


def test_g6_identifiants_distincts_entre_requetes(live):
    """CA1 : deux requêtes sans en-tête client obtiennent des identifiants distincts."""
    _c1, _b1, e1 = _get(live, "/api/health")
    _c2, _b2, e2 = _get(live, "/api/health")
    assert e1.get("X-Request-Id") != e2.get("X-Request-Id")


def test_g3c_tentative_de_contrebande_crlf_par_socket_brut(live):
    """CA2 : la tentative RÉELLE d'injection CRLF (socket brut) ne produit aucun identifiant hostile.

    Un client HTTP correct REFUSE d'émettre un en-tête contenant CRLF (`http.client` lève
    `ValueError`) : le vecteur n'est donc atteignable qu'en fabriquant la requête à la main, ce que
    fait ce test. Côté serveur, le CRLF termine la ligne d'en-tête : seul « inject » subsiste comme
    valeur — 6 caractères, donc sous le minimum de l'allowlist → REMPLACÉ. C'est bien la validation
    (longueur + alphabet) qui ferme le vecteur, pas la politesse du client.
    """
    import socket as _socket
    from urllib.parse import urlsplit

    parts = urlsplit(live)
    brute = (
        "GET /api/health HTTP/1.1\r\n"
        f"Host: {parts.hostname}:{parts.port}\r\n"
        "X-Request-Id: inject\r\nFAUSSE-ENTREE: 1\r\n"
        "Connection: close\r\n\r\n"
    ).encode()

    with _socket.create_connection((parts.hostname, parts.port), timeout=10) as sock:
        sock.sendall(brute)
        morceaux = []
        while True:
            bloc = sock.recv(4096)
            if not bloc:
                break
            morceaux.append(bloc)
    reponse = b"".join(morceaux).decode(errors="replace")

    entete = [l for l in reponse.splitlines() if l.lower().startswith("x-request-id:")]
    assert entete, f"aucun X-Request-Id dans la réponse brute : {reponse[:200]!r}"
    valeur = entete[0].split(":", 1)[1].strip()
    assert _REQUEST_ID_RE.match(valeur), f"identifiant émis non conforme : {valeur!r}"
    assert valeur != "inject", "le fragment tronqué par le CRLF ne doit pas être adopté"
    assert "FAUSSE-ENTREE" not in valeur


def test_g7_identifiant_remis_a_zero_entre_requetes_dune_meme_instance():
    """CA1 : l'identifiant est remis à zéro à CHAQUE requête, même instance de handler réutilisée.

    `BaseHTTPRequestHandler.handle()` boucle sur `handle_one_request()` en réutilisant l'instance
    tant que la connexion reste ouverte. Le défaut est aujourd'hui LATENT — CPython n'honore
    `Connection: keep-alive` que si `protocol_version >= HTTP/1.1`, or le serveur est en HTTP/1.0,
    donc la connexion se ferme après chaque requête et l'instance n'est jamais réutilisée. Il
    deviendrait ACTIF ET SILENCIEUX au moindre passage en HTTP/1.1 : on teste donc le mécanisme de
    remise à zéro directement, sans dépendre d'une condition que la configuration actuelle interdit.
    """
    handler = server.ForgeAIHandler.__new__(server.ForgeAIHandler)
    handler.headers = {}          # aucune valeur client : identifiant généré
    handler._correlation_id = None

    premier = handler.correlation_id
    assert _REQUEST_ID_RE.match(premier)
    assert handler.correlation_id == premier, "l'identifiant doit être stable DANS une requête"

    # Simule le début de la requête suivante sur la MÊME instance (ce que fait handle_one_request).
    handler._correlation_id = None
    second = handler.correlation_id

    assert second != premier, (
        "identifiant réutilisé d'une requête à l'autre sur la même instance de handler"
    )


def test_g7b_handle_one_request_remet_bien_a_zero():
    """CA1 : c'est `handle_one_request` — la seule frontière exacte d'une requête — qui remet à zéro."""
    import inspect
    source = inspect.getsource(server.ForgeAIHandler.handle_one_request)
    assert "_correlation_id = None" in source, (
        "la remise à zéro doit avoir lieu dans handle_one_request (frontière de requête)"
    )
