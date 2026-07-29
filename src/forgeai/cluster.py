"""Story S7 — vue cluster agrégée : consolide les sondes NodeProbe (registre type `node_hardware`)
en « quel vendor GPU sur quels nœuds », pour un déploiement multi-nœud vendor-aware.
Fonctions pures + lecteur registre.
"""
from __future__ import annotations

import json
from pathlib import Path
from forgeai.core.models import PlacementError, valider_placement


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


def placement_diagnostic(plan, node_global=None, inventaire=None) -> list[dict]:
    """Diagnostique le placement de chaque service du plan.

    Produit, pour chaque service, le nœud retenu et la raison du choix
    (explicite, héritage global, ou auto-scheduling), puis confronte ce
    choix à l'inventaire quand il est fourni.

    Cette fonction n'interrompt jamais : un diagnostic a vocation à
    remonter TOUTES les lignes d'un coup à l'utilisateur, y compris
    lorsqu'un placement est invalide ou qu'aucun inventaire n'est
    disponible. Lever ici masquerait les erreurs suivantes et priverait
    l'opérateur d'une vision complète de son plan.
    """
    lignes: list[dict] = []
    for svc in plan.services:
        # Décision de placement : on détermine d'abord le nœud retenu et
        # la justification, puis on valide séparément.
        if svc.node == "auto":
            node_retenu = None
            raison = (
                "placement auto : svc.node == 'auto', le scheduler "
                "k3s choisira le nœud"
            )
        elif svc.node is not None:
            # Hostname explicite demandé par le service : on respecte.
            node_retenu = svc.node
            raison = (
                f"placement explicite : svc.node == '{svc.node}', "
                "choix du service"
            )
        elif node_global is not None:
            # Pas de nœud propre, on hérite du nœud global du plan.
            node_retenu = node_global
            raison = (
                f"héritage global : svc.node absent, le service "
                f"reçoit le nœud du plan '{node_global}'"
            )
        else:
            # Ni svc.node, ni node_global : on laisse le scheduler décider.
            node_retenu = None
            raison = (
                "placement auto : aucun nœud explicite ni global, "
                "le scheduler choisira"
            )

        # Validation : séparée de la décision pour ne jamais interrompre
        # le diagnostic. Une erreur sur un service ne doit pas masquer
        # l'état des autres.
        if inventaire is None:
            validation = "non vérifié"
        else:
            try:
                valider_placement(svc, inventaire, node_retenu)
                validation = "OK"
            except PlacementError as exc:
                # Le message porte son code ERR_PLACE_* ; on le remonte
                # tel quel pour que l'utilisateur puisse le lire.
                validation = str(exc)

        lignes.append({
            "service": svc.name,
            "node": node_retenu,
            "raison": raison,
            "validation": validation,
        })
    return lignes
