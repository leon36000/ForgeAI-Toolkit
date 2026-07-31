"""REL-038B — unicité de la préparation par hôte + réconciliation idempotente.

Deux POST concurrents sur le MÊME hôte ne doivent lancer qu'UNE préparation (409 pour le second),
tandis que des hôtes DIFFÉRENTS restent parallélisables. Et parce que REL-038A fait survivre l'état
au redémarrage, une entrée « en cours » restaurée doit être réconciliée en état terminal — sinon la
garde d'unicité verrouillerait cet hôte définitivement.
"""

import json
import threading
import time
import urllib.error
import urllib.request

import pytest

from forgeai.web import server
from forgeai.web.server import build_server


def _post_json(url: str, payload: dict):
    """POST JSON ; retourne (code, corps_dict). urlopen LÈVE sur 4xx → on capture."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, method="POST", headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.getcode(), json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def _get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=5) as resp:
        return json.loads(resp.read().decode("utf-8"))


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    """Isole l'état MODULE (état + ensemble actif) et redirige forgeai_home hors du home réel."""
    monkeypatch.setattr(server, "forgeai_home", lambda: tmp_path)
    server._PREPARE_STATE.clear()
    server._PREPARE_ACTIVE.clear()
    yield
    server._PREPARE_STATE.clear()
    server._PREPARE_ACTIVE.clear()


@pytest.fixture()
def live():
    srv = build_server("127.0.0.1", 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    host, port = srv.server_address
    yield f"http://{host}:{port}"
    srv.shutdown()
    srv.server_close()


def _attendre_done(base: str, hote: str, essais: int = 50) -> dict:
    """Attend (borné) que l'état de `hote` soit terminal."""
    for _ in range(essais):
        etat = _get_json(f"{base}/api/nodes/prepare/{hote}")
        if etat.get("done") is True:
            return etat
        time.sleep(0.1)
    pytest.fail(f"état 'done' jamais atteint pour {hote}")


def test_g1_meme_hote_rejete_et_travail_unique(live, monkeypatch):
    """CA1 : second POST sur le même hôte → 409, et la préparation n'a lieu QU'UNE fois."""
    barriere = threading.Event()
    compteur = {"n": 0}

    def faux_preparer(runner, hote, *, appliquer, helm_present):
        compteur["n"] += 1
        barriere.wait(timeout=5)
        return {"status": "ok"}

    monkeypatch.setattr(server, "preparer_noeud", faux_preparer)
    hote = "n1.local"

    code1, _ = _post_json(f"{live}/api/nodes/prepare", {"host": hote})
    assert code1 == 202
    time.sleep(0.2)  # laisse le thread entrer dans la préparation

    code2, corps2 = _post_json(f"{live}/api/nodes/prepare", {"host": hote})
    assert code2 == 409, f"attendu 409 pour un doublon, reçu {code2}"
    assert "cours" in corps2.get("error", "").lower()

    barriere.set()
    _attendre_done(live, hote)
    assert compteur["n"] == 1, f"la préparation a été exécutée {compteur['n']} fois au lieu d'une"


def test_g2_hotes_distincts_parallelisables(live, monkeypatch):
    """CA2 : deux hôtes DIFFÉRENTS ne se bloquent pas (usage multi-nœuds préservé)."""
    barriere = threading.Event()

    def faux_preparer(runner, hote, *, appliquer, helm_present):
        barriere.wait(timeout=5)
        return {"status": "ok"}

    monkeypatch.setattr(server, "preparer_noeud", faux_preparer)

    code_a, _ = _post_json(f"{live}/api/nodes/prepare", {"host": "n1.local"})
    time.sleep(0.2)
    code_b, _ = _post_json(f"{live}/api/nodes/prepare", {"host": "n2.local"})
    barriere.set()

    assert code_a == 202
    assert code_b == 202, f"un hôte distinct ne doit pas être bloqué, reçu {code_b}"


def test_g3_hote_libere_apres_la_fin(live, monkeypatch):
    """CA2 : une fois la préparation terminée, un nouveau POST sur le même hôte est accepté."""
    def faux_preparer(runner, hote, *, appliquer, helm_present):
        return {"status": "ok"}

    monkeypatch.setattr(server, "preparer_noeud", faux_preparer)
    hote = "n1.local"

    assert _post_json(f"{live}/api/nodes/prepare", {"host": hote})[0] == 202
    _attendre_done(live, hote)
    assert server._PREPARE_ACTIVE == set(), "l'hôte n'a pas été libéré"

    code2, _ = _post_json(f"{live}/api/nodes/prepare", {"host": hote})
    assert code2 == 202, f"hôte non libéré après la fin, reçu {code2}"


def test_g4_hote_libere_meme_sur_exception_non_rattrapee(live, monkeypatch):
    """CA2 : le `finally` libère l'hôte même sur une exception qui ÉCHAPPE aux gardes internes.

    Détecteur réel : `preparer_noeud` est déjà entouré d'un `except Exception` qui convertit la
    panne en message d'erreur — une RuntimeError ne prouverait donc RIEN du `finally` (elle est
    absorbée avant). On lève une `KeyboardInterrupt` (BaseException), qui traverse `except
    Exception` : seule la clause `finally` peut alors libérer l'hôte.
    """
    def faux_preparer_qui_echappe(runner, hote, *, appliquer, helm_present):
        raise KeyboardInterrupt("interruption non rattrapée")

    monkeypatch.setattr(server, "preparer_noeud", faux_preparer_qui_echappe)
    hote = "n1.local"

    assert _post_json(f"{live}/api/nodes/prepare", {"host": hote})[0] == 202

    for _ in range(50):  # attente bornée de la mort du thread
        if server._PREPARE_ACTIVE == set():
            break
        time.sleep(0.1)
    assert server._PREPARE_ACTIVE == set(), "l'hôte reste verrouillé après une exception échappée"

    code2, _ = _post_json(f"{live}/api/nodes/prepare", {"host": hote})
    assert code2 == 202, "l'hôte doit rester préparable après un échec brutal"


def test_g5_reconciliation_etat_en_cours_restaure(live, monkeypatch, tmp_path):
    """CA3 : une entrée « en cours » persistée devient TERMINALE au chargement, et l'hôte
    redevient préparable (sans quoi la garde d'unicité le verrouillerait à vie)."""
    def faux_preparer(runner, hote, *, appliquer, helm_present):
        return {"status": "ok"}

    monkeypatch.setattr(server, "preparer_noeud", faux_preparer)
    hote = "n1.local"

    chemin = server._prepare_state_path()
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(
        json.dumps({
            "version": server._PREPARE_STATE_VERSION,
            "hosts": {hote: {"done": False, "resultat": None, "erreur": None}},
        }),
        encoding="utf-8",
    )

    server._PREPARE_STATE.clear()
    server._load_prepare_state()

    etat = server._PREPARE_STATE[hote]
    assert etat["done"] is True, "une entrée « en cours » restaurée doit devenir terminale"
    assert "redémarrage" in (etat["erreur"] or ""), f"erreur non explicite : {etat['erreur']!r}"

    code, _ = _post_json(f"{live}/api/nodes/prepare", {"host": hote})
    assert code == 202, f"l'hôte doit redevenir préparable, reçu {code}"


def test_g6_reconciliation_idempotente(tmp_path):
    """CA3 : ré-appliquer la réconciliation ne change plus rien (point fixe)."""
    hote = "n1.local"
    chemin = server._prepare_state_path()
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(
        json.dumps({
            "version": server._PREPARE_STATE_VERSION,
            "hosts": {hote: {"done": False, "resultat": None, "erreur": None}},
        }),
        encoding="utf-8",
    )

    server._PREPARE_STATE.clear()
    server._load_prepare_state()
    premier = dict(server._PREPARE_STATE[hote])

    server._load_prepare_state()  # 2e application
    second = dict(server._PREPARE_STATE[hote])

    assert premier == second, f"réconciliation non idempotente : {premier} → {second}"


def test_g7_ensemble_actif_jamais_persiste(live, monkeypatch, tmp_path):
    """CA3 : `_PREPARE_ACTIVE` est runtime-only — il n'apparaît dans aucun fichier persisté."""
    def faux_preparer(runner, hote, *, appliquer, helm_present):
        return {"status": "ok"}

    monkeypatch.setattr(server, "preparer_noeud", faux_preparer)
    hote = "n1.local"
    assert _post_json(f"{live}/api/nodes/prepare", {"host": hote})[0] == 202
    _attendre_done(live, hote)

    contenu = server._prepare_state_path().read_text(encoding="utf-8")
    assert "_PREPARE_ACTIVE" not in contenu
    assert "active" not in json.loads(contenu), "l'ensemble actif ne doit pas être persisté"
