"""Story S7 — vue cluster agrégée : consolide les sondes NodeProbe (registre type `node_hardware`)
en « quel vendor GPU sur quels nœuds », pour un déploiement multi-nœud vendor-aware.
Fonctions pures + lecteur registre.
"""
from __future__ import annotations

import json
from pathlib import Path


def node_vendors(hardware: dict) -> list[str]:
    """Vendors GPU DISTINCTS d'un nœud, dans l'ordre de première apparition (hardware['gpus'])."""
    seen: list[str] = []
    for gpu in hardware.get("gpus", []):
        vendor = gpu.get("vendor")
        if vendor and vendor not in seen:
            seen.append(vendor)
    return seen


def cluster_view(probes: list[dict]) -> dict:
    """Agrège une liste de sondes {node_host, profile, backends, hardware} en vue cluster :
    - `nodes` : un résumé par nœud (node, profile, vendors, backends) ;
    - `vendors` : index inversé vendor -> [nœuds] (le « quel vendor où »)."""
    nodes: list[dict] = []
    vendors: dict[str, list[str]] = {}
    for probe in probes:
        host = probe.get("node_host", "?")
        vs = node_vendors(probe.get("hardware", {}))
        nodes.append({
            "node": host,
            "profile": probe.get("profile", ""),
            "vendors": vs,
            "backends": list(probe.get("backends", [])),
        })
        for vendor in vs:
            bucket = vendors.setdefault(vendor, [])
            if host not in bucket:
                bucket.append(host)
    return {"nodes": nodes, "vendors": vendors}


def read_probes(registre_path: str | Path) -> list[dict]:
    """Lit les sondes `node_hardware` d'un registre JSONL ; garde la PLUS RÉCENTE par node_host
    (le registre est chronologique : la dernière écrase). Lignes illisibles ignorées."""
    latest: dict[str, dict] = {}
    path = Path(registre_path)
    if not path.exists():
        return []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if entry.get("type") == "node_hardware":
            payload = entry.get("payload", {})
            latest[payload.get("node_host")] = payload
    return list(latest.values())
