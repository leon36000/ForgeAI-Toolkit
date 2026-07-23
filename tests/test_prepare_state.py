"""FAI-0013 (#119) — `_PREPARE_STATE` était un dict partagé SANS verrou, JAMAIS purgé :
course lecture/écriture (handler GET vs thread _run_prepare) + croissance mémoire non bornée
(un `POST /api/nodes/prepare` par hôte distinct ajoute une entrée jamais évincée).

Spécification : accès sérialisés par verrou, taille BORNÉE (éviction du plus ancien), et lecture
par COPIE défensive (le thread mutant ne peut corrompre ce que voit un lecteur). RED : helpers absents.
"""
import threading

from forgeai.web import server


def test_prepare_state_borne():
    with server._PREPARE_LOCK:
        server._PREPARE_STATE.clear()
    for i in range(server._PREPARE_MAX + 50):
        server._prepare_state_set(f"h{i}", {"done": True, "i": i})
    with server._PREPARE_LOCK:
        assert len(server._PREPARE_STATE) <= server._PREPARE_MAX, "état non borné"
    assert server._prepare_state_get("h0") == {"done": False}, "le plus ancien n'a pas été évincé"
    assert server._prepare_state_get(f"h{server._PREPARE_MAX + 49}")["done"] is True


def test_prepare_state_lecture_par_copie():
    server._prepare_state_set("node-x", {"done": False, "resultat": None})
    snap = server._prepare_state_get("node-x")
    snap["hacked"] = True  # muter la copie...
    assert "hacked" not in server._prepare_state_get("node-x"), "lecture non défensive (état partagé mutable)"


def test_prepare_state_concurrent():
    with server._PREPARE_LOCK:
        server._PREPARE_STATE.clear()

    def worker(i):
        for _ in range(50):
            server._prepare_state_set(f"h{i}", {"done": True, "i": i})
            server._prepare_state_get(f"h{i}")

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    with server._PREPARE_LOCK:
        assert len(server._PREPARE_STATE) <= server._PREPARE_MAX
    assert server._prepare_state_get("h9")["i"] == 9
