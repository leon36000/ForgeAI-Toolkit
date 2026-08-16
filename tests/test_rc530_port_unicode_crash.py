"""Issue #530 — `_valider_adopt` ne doit JAMAIS lever sur un port invalide.

Repro : `str.isdigit()` accepte des caractères Unicode « chiffre » (², ④, ①…) que `int()`
ne sait pas parser → `ValueError` non rattrapée qui remonte hors de `do_POST` : le thread de
connexion meurt sans écrire de réponse HTTP (déni de service par requête malformée). Le
contrat documenté de `_valider_adopt` est de TOUJOURS retourner une chaîne d'erreur (jamais
lever) pour un port invalide, quel qu'il soit.
"""

import json
import threading
import urllib.error
import urllib.request

import pytest

from forgeai.web.server import _valider_adopt, build_server


def _request(url: str, data: bytes | None = None, method: str | None = None) -> tuple[int, str]:
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        # 4xx/5xx font partie du contrat testé — retournés, pas levés
        return exc.code, exc.read().decode("utf-8")


@pytest.fixture
def server():
    srv = build_server("127.0.0.1", 0)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()
    srv.server_close()


def test_valider_adopt_port_chiffre_unicode_non_ascii_retourne_erreur():
    # Repro EXACT de l'issue #530 : « ² » (U+00B2, exposant deux) passe str.isdigit() mais
    # int() lève ValueError. _valider_adopt doit rendre une CHAÎNE d'erreur — si une exception
    # est levée ici, pytest fait échouer le test de lui-même (comportement par défaut).
    assert "²".isdigit()  # prérequis du repro : le caractère EST un « chiffre » pour isdigit
    resultat = _valider_adopt({"k3s": "localhost:²"}, {"k3s"})
    assert isinstance(resultat, str)
    assert "port" in resultat.lower()


def test_valider_adopt_port_ascii_valide_retourne_none():
    # Non-régression : un port ASCII normal doit continuer à passer la validation.
    assert _valider_adopt({"k3s": "localhost:8080"}, {"k3s"}) is None


def test_valider_adopt_port_hors_bornes_retourne_erreur():
    # Non-régression du contrôle 1-65535 existant.
    resultat = _valider_adopt({"k3s": "localhost:99999"}, {"k3s"})
    assert isinstance(resultat, str)
    assert "born" in resultat


def test_valider_adopt_port_non_numerique_ascii_retourne_erreur():
    # Non-régression du cas déjà couvert avant le correctif.
    resultat = _valider_adopt({"k3s": "localhost:abc"}, {"k3s"})
    assert isinstance(resultat, str)


def test_valider_adopt_autres_chiffres_unicode_non_ascii_aussi_couverts():
    # Autres caractères de la même CLASSE de bug que « ² » : ④ (U+2463, chiffre encerclé
    # quatre) et ① (U+2460, chiffre encerclé un) passent str.isdigit() mais font échouer
    # int() — les deux propriétés sont VÉRIFIÉES ci-dessous AVANT usage (comportement
    # documenté de la bibliothèque standard Python, pas des exemples inventés). Chacun doit
    # rendre une chaîne d'erreur, jamais lever.
    for caractere in ("④", "①"):
        assert caractere.isdigit(), f"{caractere!r} doit passer isdigit() pour reproduire le bug"
        with pytest.raises(ValueError):
            int(caractere)  # prémisse du bug : int() ne sait PAS parser ce « chiffre »
        resultat = _valider_adopt({"k3s": f"localhost:{caractere}"}, {"k3s"})
        assert isinstance(resultat, str)


def test_valider_adopt_via_serveur_http_reel_reponse_400_pas_de_crash(server):
    # Preuve de reproduction en conditions réelles (serveur HTTP démarré) : la requête
    # malformée doit recevoir un 400 propre — PAS une connexion tuée sans réponse
    # (RemoteDisconnected / timeout), PAS un 500. La validation échoue AVANT tout lancement
    # de sous-processus, donc la fixture fake_deploy n'est pas nécessaire.
    from forgeai.web.server import deploy_ids, load_stack

    noms = deploy_ids(load_stack("agentique"))  # nom de service RÉEL, lu — jamais deviné
    nom_service = next(iter(noms))
    payload = json.dumps(
        {
            "stack": "agentique",
            "backend": "compose",
            "confirm": "FORCER",
            "adopt": {nom_service: "localhost:²"},
        }
    ).encode("utf-8")
    status, body = _request(f"{server}/api/deploy", data=payload, method="POST")
    assert status == 400
    assert "error" in json.loads(body)
