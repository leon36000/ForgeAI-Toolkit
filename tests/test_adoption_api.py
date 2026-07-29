"""Tests de l'endpoint /api/deploy : validation du paramètre `adopt`.

Ces tests figent le comportement de la validation côté serveur : une entrée
mal formée NE DOIT JAMAIS produire un 500. Une faute de saisie utilisateur
reste une erreur 4xx avec un message explicite.
"""
from __future__ import annotations

import io
import json
import os
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator

import pytest

# Isoler les artefacts avant tout import du serveur.
os.environ.setdefault("FORGEAI_HOME", "/tmp/forgeai_test_home")

import forgeai.web.server as srv  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers HTTP
# ---------------------------------------------------------------------------

def _post_json(port: int, payload: dict) -> tuple[int, dict]:
    """POST /api/deploy, retourne (status, body_json)."""
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/deploy",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            raw = resp.read()
            return resp.status, json.loads(raw.decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            data = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            data = {"raw": raw.decode("utf-8", errors="replace")}
        return exc.code, data


# ---------------------------------------------------------------------------
# Fixture : serveur démarré sur port éphémère, FORGEAI_HOME pointé sur tmp.
# ---------------------------------------------------------------------------

@pytest.fixture
def server(tmp_path, monkeypatch) -> Iterator[int]:
    """Démarre un serveur HTTP sur port 0 et neutralise le vrai déploiement."""
    monkeypatch.setenv("FORGEAI_HOME", str(tmp_path))
    # Neutralise l'exécution de la commande de déploiement.
    monkeypatch.setattr(srv, "_DEPLOY_CMD", ["python3", "-c", "print('simule')"])

    httpd = srv.build_server("127.0.0.1", 0)
    port = httpd.server_address[1]

    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield port
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=2)


# ---------------------------------------------------------------------------
# 1. Types invalides pour `adopt` (liste, str, int)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "bad_adopt",
    [
        ["redis"],          # liste
        "redis:6379",       # chaîne
        42,                # entier
    ],
    ids=["list", "str", "int"],
)
def test_adopt_type_invalide_400(server, bad_adopt):
    status, body = _post_json(server, {
        "stack": "agentique",
        "backend": "compose",
        "confirm": "FORCER",
        "adopt": bad_adopt,
    })
    assert status == 400, f"un type invalide doit donner 400, pas {status}"
    msg = body.get("error", "")
    assert "adopt doit etre un objet" in msg, (
        f"message attendu sur la nature dict-de-adopt, obtenu : {msg!r}"
    )


# ---------------------------------------------------------------------------
# 2. Clé de service inconnue
# ---------------------------------------------------------------------------

def test_adopt_service_inconnu_400(server):
    status, body = _post_json(server, {
        "stack": "agentique",
        "backend": "compose",
        "confirm": "FORCER",
        "adopt": {"inexistant": "h:1"},
    })
    assert status == 400, f"service inconnu doit donner 400, pas {status}"
    msg = body.get("error", "")
    # Le message doit nommer la clé fautive.
    assert "inexistant" in msg, (
        f"le message doit citer la clé fautive, obtenu : {msg!r}"
    )
    assert "inconnu" in msg, (
        f"le message doit qualifier 'inconnu', obtenu : {msg!r}"
    )


# ---------------------------------------------------------------------------
# 3. Formes d'endpoint mal formées
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "endpoint,frag_attendu",
    [
        ("h:abc",    "port non numerique"),
        ("h:99999",  "port hors bornes"),
        ("h:0",      "port hors bornes"),
        ("pasdeport", "forme attendue 'hote:port'"),
        (":6379",    "hote invalide"),
    ],
    ids=["port_non_num", "port_hors_bornes", "port_zero", "pas_de_port", "hote_vide"],
)
def test_adopt_endpoint_malforme_400(server, endpoint, frag_attendu):
    status, body = _post_json(server, {
        "stack": "agentique",
        "backend": "compose",
        "confirm": "FORCER",
        "adopt": {"redis": endpoint},
    })
    assert status == 400, f"endpoint mal formé doit donner 400, pas {status}"
    msg = body.get("error", "")
    assert "redis" in msg, (
        f"le message doit citer le service fautif 'redis', obtenu : {msg!r}"
    )
    assert frag_attendu in msg, (
        f"message attendu contenant {frag_attendu!r}, obtenu : {msg!r}"
    )


# ---------------------------------------------------------------------------
# 4. Critère central : aucune entrée malformée ne doit produire un 500
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "payload,label",
    [
        ({"stack": "agentique", "backend": "compose", "confirm": "FORCER",
          "adopt": ["redis"]}, "adopt_liste"),
        ({"stack": "agentique", "backend": "compose", "confirm": "FORCER",
          "adopt": "redis:6379"}, "adopt_str"),
        ({"stack": "agentique", "backend": "compose", "confirm": "FORCER",
          "adopt": 42}, "adopt_int"),
        ({"stack": "agentique", "backend": "compose", "confirm": "FORCER",
          "adopt": {"inexistant": "h:1"}}, "service_inconnu"),
        ({"stack": "agentique", "backend": "compose", "confirm": "FORCER",
          "adopt": {"redis": "h:abc"}}, "port_non_num"),
        ({"stack": "agentique", "backend": "compose", "confirm": "FORCER",
          "adopt": {"redis": "h:99999"}}, "port_hors_bornes"),
        ({"stack": "agentique", "backend": "compose", "confirm": "FORCER",
          "adopt": {"redis": "pasdeport"}}, "pas_de_port"),
        ({"stack": "agentique", "backend": "compose", "confirm": "FORCER",
          "adopt": {"redis": ":6379"}}, "hote_vide"),
    ],
)
def test_aucune_reponse_500_sur_entree_malformee(server, payload, label):
    status, _ = _post_json(server, payload)
    assert status != 500, (
        f"[{label}] une entrée mal formée NE DOIT PAS produire un 500 "
        f"(status={status})"
    )
    # Et c'est bien une erreur server, pas un succès par hasard.
    assert 400 <= status < 500, (
        f"[{label}] attendu 4xx, obtenu {status}"
    )


# ---------------------------------------------------------------------------
# 5. Validation d'adopt ne doit pas masquer un 404 en 500
# ---------------------------------------------------------------------------

def test_stack_inconnu_reste_404(server):
    """Sans champ adopt, un stack inconnu reste un 404 — pas un 500."""
    status, body = _post_json(server, {
        "stack": "nexistepas",
        "backend": "compose",
        "confirm": "FORCER",
    })
    assert status == 404, (
        f"stack inconnu doit donner 404, pas {status} (body={body!r})"
    )
    msg = body.get("error", "")
    assert "stack not found" in msg, (
        f"message attendu 'stack not found', obtenu : {msg!r}"
    )


import json
import time


class _FauxProc:
    """Process neutralisé : le spawn ne lance rien, mais le chemin de code est le VRAI."""

    def __init__(self, *a, **k):
        self.stdout = io.StringIO("")
        self.returncode = 0

    def poll(self):
        return 0

    def wait(self, timeout=None):
        return 0


@pytest.fixture()
def server_reel(tmp_path, monkeypatch):
    """Comme `server`, mais _DEPLOY_CMD reste None : le fichier de selection EST ecrit.

    Neutraliser _DEPLOY_CMD (comme la fixture `server`) court-circuite le bloc
    `if cmd is None:` qui contient l'ecriture du fichier — le test ne verifierait alors
    jamais le chemin reel. On neutralise donc le SPAWN, pas la commande.
    """
    monkeypatch.setenv("FORGEAI_HOME", str(tmp_path))
    monkeypatch.setattr(srv, "_DEPLOY_CMD", None)
    monkeypatch.setattr(srv.subprocess, "Popen", _FauxProc)
    httpd = srv.build_server("127.0.0.1", 0)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield port
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=2)


@pytest.mark.parametrize(
    ("adopt", "attendu"),
    [
        ({"": "127.0.0.1:6379"}, "nom de service invalide"),
        ({"redis": 123}, "doit etre une chaine"),
    ],
    ids=["cle_vide", "valeur_non_chaine"],
)
def test_adopt_cle_ou_valeur_invalide_400(server, adopt, attendu):
    """Clé vide et valeur non-chaîne : deux formes que JSON permet et que l'API doit refuser.

    Ces deux cas sont atteignables depuis le réseau (JSON autorise une clé "" et une valeur
    numérique) : ils méritent donc un test HTTP, pas seulement une vérification unitaire.
    """
    status, body = _post_json(server, {
        "stack": "agentique",
        "backend": "compose",
        "confirm": "FORCER",
        "adopt": adopt,
    })
    assert status == 400, f"attendu 400, obtenu {status}"
    assert attendu in body.get("error", ""), (
        f"message attendu contenant {attendu!r}, obtenu {body.get('error')!r}"
    )


def _selection(tmp_path):
    """Fichier de sélection écrit par le serveur (FORGEAI_HOME est redirigé par la fixture)."""
    return tmp_path / "deploy" / "selection-demande.json"


def _lire_selection(tmp_path, delai=3.0):
    """Le fichier est écrit avant le spawn ; on tolère un court délai puis on lit."""
    chemin = _selection(tmp_path)
    fin = time.monotonic() + delai
    while time.monotonic() < fin:
        if chemin.exists():
            return json.loads(chemin.read_text(encoding="utf-8"))
        time.sleep(0.05)
    return None


def test_adopt_valide_ecrit_dans_selection(server_reel, tmp_path):
    """CHEMIN NOMINAL : un adopt valide est transmis au wizard via le fichier de sélection."""
    status, _ = _post_json(server_reel, {
        "stack": "agentique", "backend": "compose", "confirm": "FORCER",
        "adopt": {"redis": "127.0.0.1:6379"},
    })
    assert status < 400, f"un adopt valide ne doit pas etre refuse (statut {status})"
    contenu = _lire_selection(tmp_path)
    assert contenu is not None, "le fichier de selection doit etre ecrit"
    assert contenu.get("adopt") == {"redis": "127.0.0.1:6379"}, (
        f"la cle adopt doit porter le dictionnaire transmis, obtenu {contenu!r}"
    )


def test_sans_adopt_aucune_cle_adopt_dans_selection(server_reel, tmp_path):
    """NON-REGRESSION : sans adopt, aucune cle adopt n'apparait dans la selection."""
    status, _ = _post_json(server_reel, {
        "stack": "agentique", "backend": "compose", "confirm": "FORCER",
        "bricks": ["redis"],
    })
    assert status < 400
    contenu = _lire_selection(tmp_path)
    if contenu is not None:
        assert "adopt" not in contenu, f"aucune cle adopt attendue, obtenu {contenu!r}"


def test_adopt_vide_traite_comme_absent(server_reel, tmp_path):
    """adopt={} vaut absence : pas d'adoption de rien."""
    status, _ = _post_json(server_reel, {
        "stack": "agentique", "backend": "compose", "confirm": "FORCER",
        "bricks": ["redis"], "adopt": {},
    })
    assert status < 400
    contenu = _lire_selection(tmp_path)
    if contenu is not None:
        assert "adopt" not in contenu, f"un adopt vide ne doit rien ecrire, obtenu {contenu!r}"
