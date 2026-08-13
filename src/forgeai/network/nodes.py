"""Story P2-F22 (état du cluster) — jonction prouvée : forgeai node status (codeur : fable).

Lit l'état réel des nœuds via kubectl (runner injectable), et scelle la preuve au
registre hash-chaîné : la « jonction prouvée » du manifeste phases.yaml est
l'observation vérifiable des nœuds Ready + l'intégrité de la chaîne de preuve.
"""
from __future__ import annotations

import json

from forgeai.core.runner import CommandRunner
from forgeai.i18n import t


class ClusterError(Exception):
    pass


def cluster_status(runner: CommandRunner) -> list[dict]:
    code, out = runner.run(["kubectl", "get", "nodes", "-o", "json"])
    if code != 0 or not out.strip():
        raise ClusterError(t("network.nodes.cluster_status.kubectl_echec", code=code))
    try:
        items = json.loads(out)["items"]
    except (json.JSONDecodeError, KeyError) as exc:
        raise ClusterError(t("network.nodes.cluster_status.sortie_illisible", detail=exc)) from exc
    nodes = []
    for item in items:
        conditions = {c["type"]: c["status"] for c in item["status"]["conditions"]}
        labels = item["metadata"].get("labels", {})
        roles = [k.rsplit("/", 1)[-1] for k in labels
                 if k.startswith("node-role.kubernetes.io/")]
        gpu = item["status"].get("allocatable", {}).get("nvidia.com/gpu", "0")
        # BUG-web-server-redondance (bloc A) : `kubectl get nodes -o json` (CET appel,
        # UNIQUE) renvoie déjà l'objet Node COMPLET par item — labels, capacité GPU par
        # vendeur et conditions détaillées y compris. `/api/nodes/receptacles` sondait
        # pourtant CHAQUE nœud une 2e fois via `sonder_noeud` (kubectl get node <nom>)
        # pour ré-extraire exactement ces mêmes champs : un N+1 pur. On les expose ici en
        # enrichissement LOCAL (zéro appel supplémentaire, même JSON déjà en mémoire) pour
        # que l'appelant construise l'état complet d'un nœud à partir de CETTE liste seule.
        # Champs additifs uniquement : "ready"/"gpu_allocatable"/"roles"/"version"
        # (contrat historique, consommé par /api/nodes/status et `forgeai node status`)
        # restent inchangés en sémantique et en valeur.
        capacity = item["status"].get("capacity", {})
        ready_status = conditions.get("Ready")
        if ready_status == "True":
            ready_tristate = True
        elif ready_status == "False":
            ready_tristate = False
        else:
            ready_tristate = None  # absent ou "Unknown" — même sémantique que sonder_noeud
        nodes.append({
            "name": item["metadata"]["name"],
            "ready": conditions.get("Ready") == "True",
            "roles": roles or ["worker"],
            "version": item["status"]["nodeInfo"]["kubeletVersion"],
            "gpu_allocatable": gpu,
            "labels": labels,
            "gpu_capacity_nvidia": int(capacity.get("nvidia.com/gpu", "0") or 0),
            "gpu_capacity_amd": int(capacity.get("amd.com/gpu", "0") or 0),
            "ready_tristate": ready_tristate,
            "arch": item["status"].get("nodeInfo", {}).get("architecture", ""),
        })
    if not nodes:
        raise ClusterError(t("network.nodes.cluster_status.aucun_noeud"))
    return nodes
