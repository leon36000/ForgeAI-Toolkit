"""BUG-web-server-redondance (bloc B) — POST /api/deploy avec `adopt` appelait
`load_stack(stack_id)` DEUX FOIS avec le MÊME stack_id (le premier résultat était
jeté sans être utilisé). Preuve par COMPTE d'appels (spy), pas par supposition.

Isolation : ce fichier ne prouve QUE le bloc B (double load_stack). Le bloc A (N+1
sonder_noeud) est prouvé séparément dans tests/test_perf_receptacles_n1.py — aucun
mélange des deux preuves.
"""
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request

import pytest

from forgeai.web import server as server_module
from forgeai.stacks import load_stack as _vrai_load_stack


def _post_json(url: str, payload: dict):
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            return exc.code, json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return exc.code, {"raw": raw.decode("utf-8", errors="replace")}


@pytest.fixture
def base_url(tmp_path, monkeypatch):
    monkeypatch.setenv("FORGEAI_HOME", str(tmp_path))
    # Neutralise le SPAWN réel du wizard : seul le comptage d'appels à load_stack
    # nous intéresse ici, pas l'exécution du déploiement lui-même.
    monkeypatch.setattr(server_module, "_DEPLOY_CMD", ["python3", "-c", "print('simule')"])

    server = server_module.build_server("127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    yield f"http://{host}:{port}"
    server.shutdown()
    server.server_close()


def test_deploy_adopt_appelle_load_stack_une_seule_fois(base_url, monkeypatch):
    """PREUVE PAR COMPTE (bloc B) : un déploiement avec `adopt` valide, sur un stack_id
    donné, ne doit charger ce stack qu'UNE SEULE fois.

    AVANT correctif (RED) : `load_stack(stack_id)` est appelé une 1re fois pour vérifier
    l'existence du stack (résultat jeté), puis une 2e fois pour `deploy_ids(load_stack(...))`
    => 2 appels avec le MÊME stack_id => cette assertion échoue (2 != 1).
    APRÈS correctif (GREEN) : le 1er résultat est réutilisé => 1 seul appel.
    """
    appels: list[str] = []

    def _load_stack_spy(stack_id: str):
        appels.append(stack_id)
        return _vrai_load_stack(stack_id)

    monkeypatch.setattr(server_module, "load_stack", _load_stack_spy)

    status, body = _post_json(f"{base_url}/api/deploy", {
        "stack": "agentique",
        "backend": "compose",
        "confirm": "FORCER",
        "adopt": {"redis": "127.0.0.1:6379"},
    })

    assert status == 202, body
    assert appels == ["agentique"], (
        f"load_stack('agentique') appelé {len(appels)} fois ({appels}) au lieu de 1 — "
        "double chargement redondant du même stack_id non corrigé."
    )


def test_deploy_sans_adopt_appelle_load_stack_une_seule_fois(base_url, monkeypatch):
    """Non-régression : sans `adopt`, le chemin ne devait déjà charger le stack qu'une
    fois (seule la vérification d'existence) — reste vrai après le correctif."""
    appels: list[str] = []

    def _load_stack_spy(stack_id: str):
        appels.append(stack_id)
        return _vrai_load_stack(stack_id)

    monkeypatch.setattr(server_module, "load_stack", _load_stack_spy)

    status, body = _post_json(f"{base_url}/api/deploy", {
        "stack": "agentique",
        "backend": "compose",
        "confirm": "FORCER",
    })

    assert status == 202, body
    assert appels == ["agentique"], appels


def test_deploy_stack_inconnu_reste_404(base_url, monkeypatch):
    """Non-régression : un stack_id inexistant doit toujours produire 404 (le correctif
    ne doit pas changer ce comportement observable), et n'appelle load_stack qu'1 fois."""
    appels: list[str] = []

    def _load_stack_spy(stack_id: str):
        appels.append(stack_id)
        return _vrai_load_stack(stack_id)

    monkeypatch.setattr(server_module, "load_stack", _load_stack_spy)

    status, body = _post_json(f"{base_url}/api/deploy", {
        "stack": "stack-qui-n-existe-pas-xyz",
        "backend": "compose",
        "confirm": "FORCER",
        "adopt": {"redis": "127.0.0.1:6379"},
    })

    assert status == 404, body
    assert body.get("error") == "stack not found"
    assert appels == ["stack-qui-n-existe-pas-xyz"], appels
