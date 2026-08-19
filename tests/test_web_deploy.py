import json
import sys
import threading
import time
import types
import urllib.error
import urllib.request

import pytest

from forgeai.web import server as srv_mod
from forgeai.web.server import _DEPLOY_STATE, build_server


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


@pytest.fixture
def fake_deploy(monkeypatch):
    cmd = [
        sys.executable,
        "-u",
        "-c",
        "print('etape 1/3 detection'); print('etape 2/3 plan'); print('etape 3/3 sante OK')",
    ]
    monkeypatch.setattr("forgeai.web.server._DEPLOY_CMD", cmd)

    with _DEPLOY_STATE["lock"]:
        proc = _DEPLOY_STATE["proc"]
        _DEPLOY_STATE["proc"] = None
        _DEPLOY_STATE["lines"].clear()
        _DEPLOY_STATE["done"] = False
        _DEPLOY_STATE["exit_code"] = None
    if proc is not None and proc.poll() is None:
        proc.terminate()
        proc.wait()

    yield

    with _DEPLOY_STATE["lock"]:
        proc = _DEPLOY_STATE["proc"]
        _DEPLOY_STATE["proc"] = None
    if proc is not None and proc.poll() is None:
        proc.terminate()
        proc.wait()


def test_summary(server):
    status, body = _request(f"{server}/api/summary?stack=agentique")
    assert status == 200
    data = json.loads(body)
    assert data["stack"]["n_deploy"] == 72
    assert isinstance(data["backends"], list)
    assert "cpu_model" in data["hardware"]


def test_summary_stack_inconnu(server):
    status, _ = _request(f"{server}/api/summary?stack=xyz")
    assert status == 404
    status, _ = _request(f"{server}/api/summary")
    assert status == 400


def test_deploy_friction_forcer(server, fake_deploy):
    payload = json.dumps({"stack": "agentique", "backend": "compose", "confirm": "oui"}).encode("utf-8")
    status, body = _request(f"{server}/api/deploy", data=payload, method="POST")
    assert status == 400
    assert "FORCER" in body
    assert _DEPLOY_STATE["proc"] is None


def test_deploy_et_sse(server, fake_deploy):
    payload = json.dumps({"stack": "agentique", "backend": "compose", "confirm": "FORCER"}).encode("utf-8")
    status, body = _request(f"{server}/api/deploy", data=payload, method="POST")
    assert status == 202
    assert json.loads(body)["started"] is True

    req = urllib.request.Request(f"{server}/api/deploy/events")
    with urllib.request.urlopen(req, timeout=15) as resp:
        stream = resp.read().decode("utf-8")

    assert "etape 1/3 detection" in stream
    assert "etape 3/3 sante OK" in stream
    assert "event: end" in stream
    assert '"exit_code": 0' in stream


def test_deploy_deja_en_cours(server, fake_deploy, monkeypatch):
    monkeypatch.setattr(
        "forgeai.web.server._DEPLOY_CMD",
        [sys.executable, "-u", "-c", "import time; time.sleep(3)"],
    )

    payload = json.dumps({"stack": "agentique", "backend": "compose", "confirm": "FORCER"}).encode("utf-8")
    status, _ = _request(f"{server}/api/deploy", data=payload, method="POST")
    assert status == 202

    status2, body2 = _request(f"{server}/api/deploy", data=payload, method="POST")
    assert status2 == 409
    assert "déploiement déjà en cours" in body2


def test_non_regression(server):
    for path in ("/api/stacks", "/api/models", "/api/nodes/status"):
        status, _ = _request(f"{server}{path}")
        assert status == 200, path


def test_deploy_popen_echoue_renvoie_500_generique(server, fake_deploy, monkeypatch):
    def fake_popen(*a, **k):
        raise OSError("spawn impossible")

    monkeypatch.setattr(srv_mod.subprocess, "Popen", fake_popen)

    payload = json.dumps({"stack": "agentique", "backend": "compose", "confirm": "FORCER"}).encode("utf-8")
    status, body = _request(f"{server}/api/deploy", data=payload, method="POST")

    assert status == 500
    data = json.loads(body)
    assert "error" in data
    assert "spawn impossible" not in data["error"]  # WEB-015 : pas de détail interne au client

    with _DEPLOY_STATE["lock"]:
        assert _DEPLOY_STATE["proc"] is None
        assert _DEPLOY_STATE["done"] is True
        assert _DEPLOY_STATE["exit_code"] == -1


def test_deploy_popen_echoue_puis_nouveau_deploy_reussit(server, fake_deploy, monkeypatch):
    real_popen = srv_mod.subprocess.Popen

    def fake_popen(*a, **k):
        raise OSError("spawn impossible")

    monkeypatch.setattr(srv_mod.subprocess, "Popen", fake_popen)
    payload = json.dumps({"stack": "agentique", "backend": "compose", "confirm": "FORCER"}).encode("utf-8")
    status, _ = _request(f"{server}/api/deploy", data=payload, method="POST")
    assert status == 500

    # Ré-applique setattr (pas monkeypatch.undo()) : `fake_deploy` partage la même instance
    # `monkeypatch` (fixture function-scoped) et a déjà patché `_DEPLOY_CMD` — un `.undo()`
    # global annulerait aussi CE patch et ferait fuir la vraie commande wizard dans le test.
    monkeypatch.setattr(srv_mod.subprocess, "Popen", real_popen)
    status2, body2 = _request(f"{server}/api/deploy", data=payload, method="POST")
    assert status2 == 202
    assert json.loads(body2)["started"] is True


class _WfileBloquant:
    """wfile factice : write() bloque jusqu'à ce que l'événement soit levé — simule un
    client SSE lent (backpressure) sans dépendre d'un vrai socket réseau."""
    def __init__(self, event_debloque):
        self.event_debloque = event_debloque
        self.ecrits = []
        self.flushes = 0

    def write(self, data):
        self.event_debloque.wait(timeout=5)
        self.ecrits.append(data)

    def flush(self):
        self.flushes += 1


def test_sse_ecriture_bloquante_ne_bloque_pas_deploy_resume():
    """#589 — reproduction exacte du défaut : _deploy_resume() (/api/status) doit terminer
    rapidement MÊME si le flux SSE est encore bloqué en écriture réseau."""
    with _DEPLOY_STATE["lock"]:
        _DEPLOY_STATE["proc"] = None
        _DEPLOY_STATE["lines"] = ["etape 1"]
        _DEPLOY_STATE["done"] = True
        _DEPLOY_STATE["exit_code"] = 0
        _DEPLOY_STATE["nettoyage_incertain"] = False

    event_debloque = threading.Event()
    fake_self = types.SimpleNamespace(wfile=_WfileBloquant(event_debloque))

    thread_stream = threading.Thread(
        target=srv_mod.ForgeAIHandler._deploy_events_stream, args=(fake_self,), daemon=True
    )
    thread_stream.start()
    time.sleep(0.2)  # laisse le stream entrer dans write() (bloqué)

    resume_termine = threading.Event()
    resultat = {}

    def _appeler_resume():
        resultat["valeur"] = srv_mod._deploy_resume()
        resume_termine.set()

    thread_resume = threading.Thread(target=_appeler_resume, daemon=True)
    thread_resume.start()

    try:
        assert resume_termine.wait(timeout=1.0), (
            "_deploy_resume() est resté bloqué par le verrou SSE"
        )
        assert resultat["valeur"]["done"] is True
    finally:
        event_debloque.set()
        thread_stream.join(timeout=5)
        thread_resume.join(timeout=5)


def test_sse_stream_envoie_toutes_les_lignes_et_termine(fake_deploy):
    """Non-régression : le contenu et l'ordre du flux SSE restent inchangés après le
    déplacement de l'écriture hors du verrou (même scénario que test_deploy_et_sse)."""
    with _DEPLOY_STATE["lock"]:
        _DEPLOY_STATE["proc"] = None
        _DEPLOY_STATE["lines"] = ["ligne 1", "ligne 2", "ligne 3"]
        _DEPLOY_STATE["done"] = True
        _DEPLOY_STATE["exit_code"] = 0
        _DEPLOY_STATE["nettoyage_incertain"] = False

    fake_self = types.SimpleNamespace(wfile=_WfileBloquant(threading.Event()))
    fake_self.wfile.event_debloque.set()  # jamais bloqué dans ce test

    srv_mod.ForgeAIHandler._deploy_events_stream(fake_self)

    sortie = b"".join(fake_self.wfile.ecrits).decode("utf-8")
    assert "data: ligne 1" in sortie
    assert "data: ligne 2" in sortie
    assert "data: ligne 3" in sortie
    assert sortie.index("ligne 1") < sortie.index("ligne 2") < sortie.index("ligne 3")
    assert "event: end" in sortie
    assert '"exit_code": 0' in sortie
