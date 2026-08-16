"""Tests de persistance/reprise du flux de déploiement (FAI-0018 #139).

Le flux `/api/deploy` gardait `_DEPLOY_STATE` UNIQUEMENT en mémoire : un restart du backend
perdait le statut, et aucune trace n'était écrite au registre avant la fin du wizard (crash
mi-course = déploiement partiel sans trace). On vérifie ici : (1) trace `deploy_started` AVANT
le spawn, (2) persistance disque de l'état reportable, (3) rechargement au démarrage, (4) le
endpoint SSE reporte réellement l'état restauré après un restart.
"""

from __future__ import annotations

import json
import sys
import threading
import time
import urllib.request

import pytest
from forgeai.web import server


def _post_json(url: str, payload: dict) -> urllib.request.addinfourl:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    return urllib.request.urlopen(req, timeout=5)


def _start_server() -> tuple:
    srv = server.build_server("127.0.0.1", 0)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    host, port = srv.server_address
    return srv, f"http://{host}:{port}"


def _poll_deploy_done() -> None:
    for _ in range(50):
        with server._DEPLOY_STATE["lock"]:
            if server._DEPLOY_STATE["done"]:
                return
        time.sleep(0.1)
    pytest.fail("le déploiement factice ne s'est jamais terminé")


def _poll_state_file_done() -> dict:
    """Attend que le fichier de persistance reflète un déploiement TERMINÉ.

    `_reader` pose `done=True` (sous lock) PUIS appelle `_persist_deploy_state()` à la ligne
    suivante : lire le fichier dès que la mémoire dit `done` serait une course. On poll donc
    le FICHIER jusqu'à `done: True` — déterministe, sans flakiness.
    """
    path = server._deploy_state_path()
    for _ in range(50):
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                data = {}
            if data.get("done") is True:
                return data
        time.sleep(0.1)
    pytest.fail("le fichier de persistance n'a jamais reflété done=True")


@pytest.fixture(autouse=True)
def isolate_deploy_state(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "forgeai_home", lambda: tmp_path)
    monkeypatch.setattr(server, "load_stack", lambda stack_id: None)
    monkeypatch.setattr(server, "_DEPLOY_CMD", [sys.executable, "-c", "print('ok')"])
    with server._DEPLOY_STATE["lock"]:
        server._DEPLOY_STATE["proc"] = None
        server._DEPLOY_STATE["lines"].clear()
        server._DEPLOY_STATE["done"] = False
        server._DEPLOY_STATE["exit_code"] = None
        # Round 8 (#452) : manquait à cette liste — un test antérieur laissant
        # nettoyage_incertain=True polluait silencieusement l'ordre d'exécution suivant.
        server._DEPLOY_STATE["nettoyage_incertain"] = False
    yield


def test_deploy_trace_registre(monkeypatch, tmp_path) -> None:
    """Une trace `deploy_started` (actor=web, payload stack/backend/node) est écrite au registre."""
    registre_path = tmp_path / "mission.jsonl"
    monkeypatch.setattr(server, "_registre_path", lambda: registre_path)

    srv, base_url = _start_server()
    try:
        with _post_json(
            f"{base_url}/api/deploy",
            {"stack": "minimal", "backend": "compose", "confirm": "FORCER"},
        ) as resp:
            assert resp.status == 202

        _poll_deploy_done()

        assert registre_path.exists()
        entries = [
            json.loads(line)
            for line in registre_path.read_text(encoding="utf-8").splitlines()
        ]
        started = [e for e in entries if e.get("type") == "deploy_started"]
        assert len(started) == 1
        assert started[0]["actor"] == "web"
        attendu = {
            "stack": "minimal",
            "backend": "compose",
            "node": "local",
        }
        charge = started[0]["payload"]
        # OPS-031D : la trace porte EN PLUS `request_id`, qui rattache l'entrée d'audit à la requête
        # HTTP qui l'a provoquée. On vérifie donc l'INCLUSION des champs métier attendus + la
        # conformité de l'identifiant, plutôt qu'une égalité stricte devenue trop rigide.
        for cle, valeur in attendu.items():
            assert charge[cle] == valeur, f"champ {cle} altéré : {charge}"
        assert set(charge) <= set(attendu) | {"request_id"}, f"champ inattendu : {charge}"
        from forgeai.web.server import _REQUEST_ID_RE
        assert _REQUEST_ID_RE.match(charge["request_id"]), f"request_id non conforme : {charge}"
    finally:
        srv.shutdown()
        srv.server_close()


def test_deploy_state_persiste(tmp_path) -> None:
    """L'état reportable {done,exit_code,lines} est persisté sur disque (jamais proc/lock)."""
    srv, base_url = _start_server()
    try:
        with _post_json(
            f"{base_url}/api/deploy",
            {"stack": "minimal", "backend": "compose", "confirm": "FORCER"},
        ) as resp:
            assert resp.status == 202

        data = _poll_state_file_done()
        assert data["done"] is True
        assert data["exit_code"] == 0
        assert "ok" in data["lines"]
        assert "proc" not in data
        assert "lock" not in data
    finally:
        srv.shutdown()
        srv.server_close()


def test_deploy_state_rechargee_apres_restart(tmp_path) -> None:
    """Au démarrage, `_load_deploy_state` repeuple l'état depuis le disque (proc reste None)."""
    state_path = server._deploy_state_path()
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps({"done": True, "exit_code": 0, "lines": ["reprise"]}, ensure_ascii=False),
        encoding="utf-8",
    )

    server._load_deploy_state()

    with server._DEPLOY_STATE["lock"]:
        assert server._DEPLOY_STATE["done"] is True
        assert server._DEPLOY_STATE["exit_code"] == 0
        assert "reprise" in server._DEPLOY_STATE["lines"]
        assert server._DEPLOY_STATE["proc"] is None


def test_deploy_events_reporte_apres_restart(tmp_path) -> None:
    """Après restart, GET /api/deploy/events reporte l'état restauré (lignes + exit_code)."""
    state_path = server._deploy_state_path()
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(
            {"done": True, "exit_code": 0, "lines": ["ligne-restauree"]}, ensure_ascii=False
        ),
        encoding="utf-8",
    )

    srv, base_url = _start_server()
    try:
        with urllib.request.urlopen(f"{base_url}/api/deploy/events", timeout=5) as resp:
            body = resp.read().decode("utf-8")

        assert "data: ligne-restauree\n\n" in body
        assert 'event: end\ndata: {"exit_code": 0}' in body
    finally:
        srv.shutdown()
        srv.server_close()


def test_deploy_events_reporte_nettoyage_incertain_apres_restart(tmp_path) -> None:
    """Round 5 (#452) : quand nettoyage_incertain=True est restauré du disque, la clé DOIT
    apparaître dans la charge SSE (le mécanisme de visibilité reste fonctionnel — seul le
    chemin NOMINAL, sans nettoyage incertain, doit rester byte-identique à avant round 4)."""
    state_path = server._deploy_state_path()
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(
            {
                "done": True,
                "exit_code": -1,
                "lines": ["ligne-restauree"],
                "nettoyage_incertain": True,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    srv, base_url = _start_server()
    try:
        with urllib.request.urlopen(f"{base_url}/api/deploy/events", timeout=5) as resp:
            body = resp.read().decode("utf-8")

        assert "data: ligne-restauree\n\n" in body
        assert 'event: end\ndata: {"exit_code": -1, "nettoyage_incertain": true}' in body
    finally:
        srv.shutdown()
        srv.server_close()


def test_load_deploy_state_fichier_corrompu_ignore(tmp_path) -> None:
    """Un deploy-state.json corrompu / mal typé n'altère pas l'état ni ne crashe le démarrage."""
    state_path = server._deploy_state_path()
    state_path.parent.mkdir(parents=True, exist_ok=True)

    for contenu in (
        "{ceci n'est pas du json",              # JSONDecodeError -> except
        json.dumps(["une", "liste"]),           # pas un dict -> return
        json.dumps({"lines": "x", "done": "oui"}),  # types invalides -> return
    ):
        state_path.write_text(contenu, encoding="utf-8")
        server._load_deploy_state()  # ne doit jamais lever
        with server._DEPLOY_STATE["lock"]:
            # l'état reste celui de la fixture (aucune restauration depuis un fichier invalide)
            assert server._DEPLOY_STATE["done"] is False
            assert server._DEPLOY_STATE["lines"] == []


def test_deploy_trace_registre_echec_best_effort(monkeypatch, tmp_path) -> None:
    """Si l'append registre échoue, le déploiement continue et un avertissement est journalisé."""
    def _boom(*args, **kwargs):
        raise RuntimeError("registre indisponible")

    monkeypatch.setattr(server.registre, "append", _boom)

    srv, base_url = _start_server()
    try:
        with _post_json(
            f"{base_url}/api/deploy",
            {"stack": "minimal", "backend": "compose", "confirm": "FORCER"},
        ) as resp:
            assert resp.status == 202

        _poll_deploy_done()
        with server._DEPLOY_STATE["lock"]:
            lines = list(server._DEPLOY_STATE["lines"])
        assert any("échec traçage registre" in ln for ln in lines)
    finally:
        srv.shutdown()
        srv.server_close()


def test_persist_concurrent_pas_de_corruption(tmp_path) -> None:
    """20 threads persistent en boucle en concurrence : le fichier reste TOUJOURS un JSON valide.

    Régression de l'objection de revue (tour 1) : un `.tmp` à nom fixe corrompait le JSON quand un
    nouveau deploy persistait pendant que le `_reader` de l'ancien persistait encore. mkstemp donne
    un tmp unique par écriture → `os.replace` atomique, jamais de corruption.
    """
    errors: list = []
    stop = threading.Event()

    def writer() -> None:
        i = 0
        while not stop.is_set():
            with server._DEPLOY_STATE["lock"]:
                server._DEPLOY_STATE["done"] = (i % 2) == 0
                server._DEPLOY_STATE["exit_code"] = i % 5
                server._DEPLOY_STATE["lines"].append(f"line {i}")
                if len(server._DEPLOY_STATE["lines"]) > 50:
                    server._DEPLOY_STATE["lines"].pop(0)
            try:
                server._persist_deploy_state()
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)
            i += 1

    threads = [threading.Thread(target=writer) for _ in range(20)]
    for t in threads:
        t.start()
    time.sleep(0.5)
    stop.set()
    for t in threads:
        t.join(timeout=5)
        assert not t.is_alive(), "un thread writer ne s'est pas arrêté"

    assert not errors, f"persist a levé : {errors[:3]}"

    path = server._deploy_state_path()
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))  # ne doit JAMAIS lever (JSON valide)
    # Round 8 (#452, objection GPT-5.6-Terra-Pro majeure) : nettoyage_incertain n'est plus
    # sérialisé quand False (chemin nominal de ce test — le writer() ci-dessus ne le met
    # jamais à True) ; voir _persist_deploy_state(). Avant round 8, la clé apparaissait
    # toujours, même sur le chemin nominal — c'était précisément le défaut signalé.
    assert set(data) == {"done", "exit_code", "lines"}
    assert isinstance(data["lines"], list)
    assert isinstance(data["done"], bool)


def test_persist_deploy_state_echec_ecriture_ajoute_avertissement(monkeypatch) -> None:
    """Si l'écriture sur disque échoue, _persist_deploy_state ajoute un avertissement sans lever."""
    def _boom(*args, **kwargs):
        raise OSError("disque plein")

    monkeypatch.setattr(server.tempfile, "mkstemp", _boom)

    server._persist_deploy_state()

    with server._DEPLOY_STATE["lock"]:
        lines = list(server._DEPLOY_STATE["lines"])
    assert any(
        ln.startswith("avertissement: échec persistance état déploiement")
        for ln in lines
    )


def test_persist_deploy_state_exception_str_cassee_ne_leve_pas(monkeypatch) -> None:
    """Round 27 (#452) — objection GPT-5.6-Terra-Pro (revue scellée) : rien n'empêche
    exc.__str__() de lever lui-même (vérifié empiriquement) — sans str_exc_sur(), la
    construction du message f"...: {exc}" ferait échouer CE bloc best-effort au lieu d'ajouter
    un avertissement."""
    class _ExceptionStrCassee(OSError):
        def __str__(self) -> str:
            raise ValueError("str() cassé délibérément pour ce test")

    def _boom(*args, **kwargs):
        raise _ExceptionStrCassee()

    monkeypatch.setattr(server.tempfile, "mkstemp", _boom)

    server._persist_deploy_state()  # ne doit JAMAIS lever, même avec exc.__str__() cassé

    with server._DEPLOY_STATE["lock"]:
        lines = list(server._DEPLOY_STATE["lines"])
    assert any(
        ln.startswith("avertissement: échec persistance état déploiement") for ln in lines
    )


def test_load_deploy_state_echec_inattendu_journalise_stderr(monkeypatch, capsys) -> None:
    """Une exception inattendue lors du chargement journalise un message sur stderr sans lever."""
    state_path = server._deploy_state_path()
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text("{}", encoding="utf-8")

    def _boom(*args, **kwargs):
        raise OSError("erreur I/O inattendue")

    monkeypatch.setattr(server.Path, "read_text", _boom)

    server._load_deploy_state()

    captured = capsys.readouterr()
    assert "échec de restauration" in captured.err


def test_deploy_state_persiste_et_recharge_nettoyage_incertain(tmp_path) -> None:
    """Le flag nettoyage_incertain est persisté sur disque et restauré par _load_deploy_state."""
    with server._DEPLOY_STATE["lock"]:
        server._DEPLOY_STATE["done"] = True
        server._DEPLOY_STATE["exit_code"] = 1
        server._DEPLOY_STATE["lines"] = ["erreur"]
        server._DEPLOY_STATE["nettoyage_incertain"] = True

    server._persist_deploy_state()

    with server._DEPLOY_STATE["lock"]:
        server._DEPLOY_STATE["nettoyage_incertain"] = False

    server._load_deploy_state()

    with server._DEPLOY_STATE["lock"]:
        assert server._DEPLOY_STATE["nettoyage_incertain"] is True


def test_load_deploy_state_sans_nettoyage_incertain_par_defaut_false(tmp_path) -> None:
    """Un fichier d'état pré-correctif sans clé nettoyage_incertain charge False par défaut."""
    state_path = server._deploy_state_path()
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps({"done": True, "exit_code": 0, "lines": ["ok"]}, ensure_ascii=False),
        encoding="utf-8",
    )

    with server._DEPLOY_STATE["lock"]:
        server._DEPLOY_STATE["nettoyage_incertain"] = True

    server._load_deploy_state()

    with server._DEPLOY_STATE["lock"]:
        assert server._DEPLOY_STATE["nettoyage_incertain"] is False
