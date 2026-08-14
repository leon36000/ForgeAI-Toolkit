"""BUG-web-server-redondance (bloc A) — /api/nodes/receptacles appelait `sonder_noeud`
(un `kubectl get node <hostname> -o json` DISTINCT, potentiellement coûteux pour un nœud
distant) UNE FOIS PAR NŒUD, en boucle après un premier `cluster_status` qui avait déjà
sondé TOUT le cluster en un seul `kubectl get nodes -o json`. Un cluster à N nœuds
déclenchait donc 1 + N appels kubectl au lieu de 1.

Preuve par COMPTE RÉEL d'appels sous-processus (spy au niveau du `CommandRunner`
injecté, PAS une supposition) : on intercepte `SubprocessRunner` à l'endroit où le
serveur le construit et on compte les invocations `argv` réellement soumises — le test
exerce donc le VRAI `cluster_status` (network/nodes.py) et le VRAI handler HTTP, de bout
en bout, sans mocker les fonctions métier elles-mêmes.

Isolation : ce fichier ne prouve QUE le bloc A (redondance N+1). Le bloc B (double
`load_stack`) est prouvé séparément dans tests/test_web_deploy_load_stack_once.py —
aucun mélange des deux preuves.
"""
from __future__ import annotations

import json
import threading
import urllib.request

import pytest

from forgeai.web import server as server_module


def _get_json(url: str):
    with urllib.request.urlopen(url, timeout=5) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))


@pytest.fixture
def base_url():
    server = server_module.build_server("127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    yield f"http://{host}:{port}"
    server.shutdown()
    server.server_close()


def _node_item(
    name: str,
    ready_status: str | None,
    *,
    nvidia_cap: int = 0,
    amd_cap: int = 0,
    labels: dict | None = None,
    arch: str = "amd64",
) -> dict:
    """Objet Node kubectl RÉALISTE (mêmes clés qu'une vraie sortie `kubectl get nodes
    -o json`) : `sonder_noeud` ET `cluster_status` lisent tous deux ces mêmes champs
    depuis ce même objet — la preuve porte donc sur des données authentiques, pas
    inventées pour faire passer le test."""
    conditions = []
    if ready_status is not None:
        conditions.append({"type": "Ready", "status": ready_status})
    capacity = {}
    if nvidia_cap:
        capacity["nvidia.com/gpu"] = str(nvidia_cap)
    if amd_cap:
        capacity["amd.com/gpu"] = str(amd_cap)
    return {
        "metadata": {"name": name, "labels": labels or {}},
        "status": {
            "conditions": conditions,
            "capacity": capacity,
            "allocatable": dict(capacity),
            "nodeInfo": {"architecture": arch, "kubeletVersion": "v1.30.0"},
        },
    }


class _SpyRunner:
    """Remplace `SubprocessRunner` : n'exécute RIEN de réel, journalise chaque `argv`
    et répond avec les fixtures de nœuds construites en mémoire."""

    def __init__(self, items: list[dict]):
        self._items = items
        self.calls: list[list[str]] = []

    def run(self, argv: list[str]):
        self.calls.append(list(argv))
        if argv == ["kubectl", "get", "nodes", "-o", "json"]:
            return 0, json.dumps({"items": self._items})
        if (
            len(argv) == 6 and argv[0] == "kubectl" and argv[1] == "get"
            and argv[2] == "node" and argv[4] == "-o" and argv[5] == "json"
        ):
            hostname = argv[3]
            for item in self._items:
                if item["metadata"]["name"] == hostname:
                    return 0, json.dumps(item)
            return 1, ""
        if argv and argv[0] == "helm":
            return 0, ""
        if len(argv) >= 2 and argv[0] == "kubectl" and argv[1] == "label":
            return 0, ""
        return 127, ""


def _appels_par_noeud(calls: list[list[str]]) -> list[str]:
    """Extrait les hostnames des appels `kubectl get node <hostname> -o json` (la
    signature EXACTE de `sonder_noeud`) parmi tous les appels journalisés."""
    return [
        argv[3] for argv in calls
        if len(argv) == 6 and argv[0] == "kubectl" and argv[1] == "get"
        and argv[2] == "node" and argv[4] == "-o" and argv[5] == "json"
    ]


def test_receptacles_zero_appel_kubectl_par_noeud(base_url, monkeypatch):
    """PREUVE PAR COMPTE (bloc A) : pour 3 nœuds, AUCUN appel `kubectl get node <nom>`
    individuel ne doit être émis — toute l'info doit venir de l'UNIQUE `kubectl get
    nodes` déjà exécuté par `cluster_status`.

    AVANT correctif (RED) : la boucle par nœud émet 1 `kubectl get node <nom>` par
    nœud => 3 appels individuels détectés => échec (3 != 0).
    APRÈS correctif (GREEN) : 0 appel individuel, 1 seul appel total (la liste).
    """
    items = [
        _node_item("node-gpu", "True", nvidia_cap=2,
                   labels={"forgeai/receptacle": "pret", "nvidia.com/gpu.present": "true"}),
        _node_item("node-cpu", "True"),
        _node_item("node-unknown", "Unknown"),
    ]
    spy = _SpyRunner(items)
    monkeypatch.setattr(server_module, "SubprocessRunner", lambda *a, **k: spy)

    status, body = _get_json(f"{base_url}/api/nodes/receptacles")

    assert status == 200
    assert len(body["nodes"]) == 3, body
    par_noeud = _appels_par_noeud(spy.calls)
    assert par_noeud == [], (
        f"appel(s) kubectl PAR NŒUD détecté(s) : {par_noeud} (attendu : aucun) — "
        "N+1 non corrigé : /api/nodes/receptacles re-sonde chaque nœud individuellement "
        "alors que cluster_status l'a déjà fait en un seul appel liste."
    )
    assert spy.calls == [["kubectl", "get", "nodes", "-o", "json"]], (
        f"total d'appels sous-processus attendu = 1 (la liste seule), obtenu {spy.calls}"
    )


def test_receptacles_appels_bornes_a_un_quel_que_soit_n(base_url, monkeypatch):
    """Variante à N=6 nœuds : le total d'appels kubectl doit rester à 1, PAS croître
    linéairement avec N (signature du N+1)."""
    items = [_node_item(f"node-{i}", "True") for i in range(6)]
    spy = _SpyRunner(items)
    monkeypatch.setattr(server_module, "SubprocessRunner", lambda *a, **k: spy)

    status, body = _get_json(f"{base_url}/api/nodes/receptacles")

    assert status == 200
    assert len(body["nodes"]) == 6, body
    assert len(spy.calls) == 1, (
        f"6 nœuds => {len(spy.calls)} appel(s) kubectl ({spy.calls}), attendu 1 (borné, "
        "indépendant de N) : le N+1 ferait croître ce compte à 7 (1 liste + 6 par nœud)."
    )


def test_receptacles_valeurs_correctes_apres_appel_unique(base_url, monkeypatch):
    """Preuve de NON-RÉGRESSION FONCTIONNELLE : en plus du compte d'appels, les valeurs
    renvoyées par nœud doivent rester EXACTEMENT celles qu'aurait produites l'ancien
    chemin (sonder_noeud + plan_preparation), y compris le cas ready=None (nœud
    'Unknown' : sonder_noeud renvoyait `ready=None`, PAS `False` — un cluster_status
    naïf qui réduirait à un booléen romprait cette distinction observable de l'API)."""
    items = [
        _node_item("node-gpu", "True", nvidia_cap=2,
                   labels={"forgeai/receptacle": "pret", "nvidia.com/gpu.present": "true"}),
        _node_item("node-cpu", "True"),
        _node_item("node-unknown", "Unknown"),
    ]
    spy = _SpyRunner(items)
    monkeypatch.setattr(server_module, "SubprocessRunner", lambda *a, **k: spy)

    status, body = _get_json(f"{base_url}/api/nodes/receptacles")
    assert status == 200
    par_hostname = {n["hostname"]: n for n in body["nodes"]}

    gpu = par_hostname["node-gpu"]
    assert gpu["ready"] is True
    assert gpu["gpu_nvidia"] == 2
    assert gpu["gpu_amd"] == 0
    assert gpu["receptacle_actuel"] == "pret"
    assert gpu["pret"] is True
    assert gpu["etapes_restantes"] == 1  # label-pret a une commande ; verifier-gpu non

    cpu = par_hostname["node-cpu"]
    assert cpu["ready"] is True
    assert cpu["gpu_nvidia"] == 0
    assert cpu["gpu_amd"] == 0
    assert cpu["receptacle_actuel"] is None
    assert cpu["pret"] is False
    assert cpu["etapes_restantes"] == 1  # label-cpu a une commande

    inconnu = par_hostname["node-unknown"]
    assert inconnu["ready"] is None, (
        "un nœud 'Unknown' doit garder ready=None (tri-état de sonder_noeud), "
        f"pas être aplati en False — obtenu {inconnu['ready']!r}"
    )
    assert inconnu["receptacle_actuel"] is None
    assert inconnu["pret"] is False
    assert inconnu["etapes_restantes"] == 0  # diagnostic : commande=None, rien à compter
