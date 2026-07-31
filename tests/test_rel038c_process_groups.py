"""REL-038C — groupes de processus du déploiement web et nettoyage des orphelins.

Le chemin CLI était déjà traité (CLI-036). Ici on verrouille le chemin WEB : le sous-processus de
déploiement doit tourner dans SON PROPRE groupe (sinon un Ctrl-C destiné au serveur le tue), et il
ne doit jamais survivre à l'arrêt du serveur (orphelin non supervisé).
"""

import io
import os
import subprocess
import sys
import time

import pytest

import forgeai.web.server as server


@pytest.fixture(autouse=True)
def _reset_deploy_state():
    """`_DEPLOY_STATE` est un état MODULE : le remettre à zéro isole chaque test."""
    with server._DEPLOY_STATE["lock"]:
        server._DEPLOY_STATE["proc"] = None
    yield
    with server._DEPLOY_STATE["lock"]:
        proc = server._DEPLOY_STATE["proc"]
        server._DEPLOY_STATE["proc"] = None
    if proc is not None and proc.poll() is None:  # filet : ne jamais laisser fuir un processus
        try:
            server.kill_tree(proc, 0.2)
        except (OSError, subprocess.SubprocessError) as exc:
            # Jamais silencieux : un filet de nettoyage qui échoue doit se voir dans la sortie
            # du test (sinon un processus fuité resterait invisible).
            print(f"REL-038C : nettoyage du filet impossible pour le PID {proc.pid} : {exc}")


def _spawn_dormeur():
    """Lance un vrai sous-processus de longue durée dans son propre groupe (comme le déploiement)."""
    return subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )


def test_g1_deploiement_reel_lance_dans_son_propre_groupe(monkeypatch):
    """CA1 : le Popen du DÉPLOIEMENT DE PRODUCTION reçoit start_new_session=True.

    Traverse le VRAI chemin (POST /api/deploy → do_POST → subprocess.Popen) au lieu d'appeler le
    faux Popen depuis le test — sans quoi l'assertion serait tautologique (on vérifierait son propre
    appel, pas celui du serveur).
    """
    import json as _json
    import threading as _threading
    import urllib.error as _uerr
    import urllib.request as _ureq

    vus = {}

    class PopenEnregistreur:
        def __init__(self, cmd, **kwargs):
            vus["cmd"] = cmd
            vus.update(kwargs)
            self.pid = 4242
            self.stdout = io.StringIO("")

        def poll(self):
            return 0

        def wait(self, timeout=None):
            return 0

    monkeypatch.setattr(server.subprocess, "Popen", PopenEnregistreur)

    srv = server.build_server("127.0.0.1", 0)
    _threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        corps = _json.dumps(
            {"stack": "agentique", "backend": "compose", "confirm": "FORCER", "dry_run": True}
        ).encode()
        req = _ureq.Request(
            f"{base}/api/deploy", data=corps, method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            _ureq.urlopen(req, timeout=10).read()
        except _uerr.HTTPError as exc:
            exc.read()  # un 4xx applicatif est acceptable : on n'assert que sur le Popen
    finally:
        srv.shutdown()
        srv.server_close()

    assert vus, "le déploiement n'a jamais atteint subprocess.Popen"
    if os.name == "posix":
        assert vus.get("start_new_session") is True, (
            "le déploiement web doit être lancé dans SON PROPRE groupe de processus "
            f"(kwargs reçus : {sorted(k for k in vus if k != 'cmd')})"
        )
    else:
        # Sous Windows `start_new_session` est accepté mais IGNORÉ : l'isolation passe par
        # CREATE_NEW_PROCESS_GROUP (même convention que CLI-036).
        assert vus.get("creationflags") == subprocess.CREATE_NEW_PROCESS_GROUP, (
            f"isolation de groupe absente sous Windows (kwargs : {sorted(k for k in vus if k != 'cmd')})"
        )


@pytest.mark.skipif(os.name != "posix", reason="groupes de processus POSIX")
def test_g2_orphelin_termine_a_l_arret():
    """CA2 : un déploiement encore actif est bien TUÉ par le nettoyage (pas d'orphelin)."""
    proc = _spawn_dormeur()
    with server._DEPLOY_STATE["lock"]:
        server._DEPLOY_STATE["proc"] = proc

    assert proc.poll() is None, "le dormeur doit être vivant avant le nettoyage"
    server._terminate_active_deploy(grace_seconds=0.3)

    for _ in range(50):  # attente bornée de la mort effective
        if proc.poll() is not None:
            break
        time.sleep(0.1)
    assert proc.poll() is not None, "le sous-processus a survécu à l'arrêt du serveur (orphelin)"


@pytest.mark.skipif(os.name != "posix", reason="groupes de processus POSIX")
def test_g3_semantique_start_new_session_isole_bien_le_groupe():
    """CA1 (support) : vérifie la SÉMANTIQUE sur laquelle repose la garde — `start_new_session`
    place bien le fils dans un groupe distinct, de sorte qu'un signal au serveur ne l'atteint pas.

    Ce test ne prouve PAS que la production l'utilise (c'est le rôle de G1, qui traverse le vrai
    chemin) : il documente et verrouille la propriété système dont dépend la décision.
    """
    proc = _spawn_dormeur()
    try:
        assert os.getpgid(proc.pid) != os.getpgid(0), (
            "sans groupe dédié, un signal au serveur frapperait aussi le déploiement"
        )
    finally:
        server.kill_tree(proc, 0.2)


def test_g4_sans_deploiement_actif_est_un_noop():
    """CA3 : sans déploiement actif, le nettoyage ne lève pas (best-effort)."""
    with server._DEPLOY_STATE["lock"]:
        server._DEPLOY_STATE["proc"] = None
    server._terminate_active_deploy(grace_seconds=0.1)  # ne doit pas lever


@pytest.mark.skipif(os.name != "posix", reason="groupes de processus POSIX")
def test_g4b_deploiement_deja_termine_est_un_noop():
    """CA3 : un processus DÉJÀ terminé n'est pas re-tué et ne fait pas lever le nettoyage."""
    proc = subprocess.Popen([sys.executable, "-c", "pass"], start_new_session=True)
    proc.wait(timeout=10)
    with server._DEPLOY_STATE["lock"]:
        server._DEPLOY_STATE["proc"] = proc
    server._terminate_active_deploy(grace_seconds=0.1)  # ne doit pas lever


def test_g5_serve_nettoie_meme_sur_interruption(monkeypatch):
    """CA2 : `serve()` emprunte bien son `finally` — le nettoyage a lieu même sur KeyboardInterrupt."""
    appels = {"n": 0}

    class FauxServeur:
        server_address = ("127.0.0.1", 0)
        forgeai_tls = False

        def serve_forever(self):
            raise KeyboardInterrupt

        def shutdown(self):
            return None

        def server_close(self):
            return None

    monkeypatch.setattr(server, "build_server", lambda host, port: FauxServeur())
    monkeypatch.setattr(server, "_terminate_active_deploy", lambda *a, **k: appels.__setitem__("n", appels["n"] + 1))

    server.serve("127.0.0.1", 0, open_browser=False)
    assert appels["n"] == 1, "le nettoyage anti-orphelin doit être appelé à l'arrêt"


def test_g6_kill_tree_est_public():
    """CA3 : `kill_tree` est exposé publiquement (réutilisation de CLI-036, sans import privé)."""
    from forgeai.core.proc import kill_tree as public_kill_tree
    assert callable(public_kill_tree)
