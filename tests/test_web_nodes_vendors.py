"""Story S6b — /api/nodes/status enrichi du vendor GPU par nœud (dropdown moteur filtré).

Deux preuves EN PROCESS (comptées par la couverture, cf. piège SonarCloud sous-process) :
  1. helper pur `_node_vendors_by_host` : corrèle hôte -> vendors depuis les sondes
     `node_hardware` du registre (S7 read_probes/node_vendors) ;
  2. serveur web réel : chaque nœud porte son/ses vendor(s), un nœud SANS sonde => vendors:[].
Zéro mock de commande — `cluster_status` monkeypatché (pas de cluster local), registre réel seedé.
"""
from __future__ import annotations

import json
import threading
import urllib.request
from pathlib import Path

import pytest

from forgeai.web import server as server_module


def _get_json(url: str):
    with urllib.request.urlopen(url) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))


def _node_hardware_entry(host: str, vendors: list[str]) -> str:
    return json.dumps({
        "type": "node_hardware",
        "payload": {
            "node_host": host,
            "profile": "minimal-gpu-rocm",
            "backends": [],
            "hardware": {"gpus": [{"vendor": v} for v in vendors]},
        },
    })


def _seed_registre(path: Path, entries: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(entries) + "\n", encoding="utf-8")


def test_node_vendors_by_host_pur(tmp_path):
    """Helper pur EN PROCESS : hôte -> vendors distincts ; registre absent => {} sans exception."""
    reg = tmp_path / "mission.jsonl"
    _seed_registre(reg, [
        _node_hardware_entry("pc-amd", ["amd", "amd"]),      # dédup attendu
        _node_hardware_entry("pc-mix", ["nvidia", "amd"]),
    ])
    mapping = server_module._node_vendors_by_host(reg)
    assert mapping["pc-amd"] == ["amd"]                       # distincts, ordre de 1re apparition
    assert mapping["pc-mix"] == ["nvidia", "amd"]
    assert "inconnu" not in mapping

    # registre absent => mapping vide, jamais d'exception
    assert server_module._node_vendors_by_host(tmp_path / "absent.jsonl") == {}


@pytest.fixture
def base_url_seeded(monkeypatch, tmp_path):
    reg = tmp_path / "Registres" / "mission.jsonl"
    _seed_registre(reg, [
        _node_hardware_entry("worker-amd", ["amd"]),
        _node_hardware_entry("worker-nv", ["nvidia"]),
    ])
    monkeypatch.setattr(server_module, "_REGISTRE_PATH", reg)

    def fake_cluster_status(runner):
        return [
            {"name": "worker-amd", "ready": True, "roles": ["worker"]},
            {"name": "worker-nv", "ready": True, "roles": ["worker"]},
            {"name": "worker-sans-sonde", "ready": True, "roles": ["worker"]},
        ]

    monkeypatch.setattr(server_module, "cluster_status", fake_cluster_status)

    server = server_module.build_server("127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    yield f"http://{host}:{port}"
    server.shutdown()
    server.server_close()


def test_nodes_status_enrichit_vendors(base_url_seeded):
    status, body = _get_json(f"{base_url_seeded}/api/nodes/status")
    assert status == 200
    nodes = {n["name"]: n for n in body["nodes"]}
    assert nodes["worker-amd"]["vendors"] == ["amd"]
    assert nodes["worker-nv"]["vendors"] == ["nvidia"]
    # nœud réel du cluster mais AUCUNE sonde au registre => liste vide (jamais absent, jamais None)
    assert nodes["worker-sans-sonde"]["vendors"] == []
