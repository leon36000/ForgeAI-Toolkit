"""Story P2-F22 (état du cluster) — jonction prouvée : forgeai node status (codeur : fable).

Lit l'état réel des nœuds via kubectl (runner injectable), et scelle la preuve au
registre hash-chaîné : la « jonction prouvée » du manifeste phases.yaml est
l'observation vérifiable des nœuds Ready + l'intégrité de la chaîne de preuve.
"""
from __future__ import annotations

import json

from forgeai.core.runner import CommandRunner


class ClusterError(Exception):
    pass


def cluster_status(runner: CommandRunner) -> list[dict]:
    code, out = runner.run(["kubectl", "get", "nodes", "-o", "json"])
    if code != 0 or not out.strip():
        raise ClusterError(f"kubectl get nodes a échoué (code {code}) — cluster joignable ?")
    try:
        items = json.loads(out)["items"]
    except (json.JSONDecodeError, KeyError) as exc:
        raise ClusterError(f"sortie kubectl illisible : {exc}") from exc
    nodes = []
    for item in items:
        conditions = {c["type"]: c["status"] for c in item["status"]["conditions"]}
        labels = item["metadata"].get("labels", {})
        roles = [k.rsplit("/", 1)[-1] for k in labels
                 if k.startswith("node-role.kubernetes.io/")]
        gpu = item["status"].get("allocatable", {}).get("nvidia.com/gpu", "0")
        nodes.append({
            "name": item["metadata"]["name"],
            "ready": conditions.get("Ready") == "True",
            "roles": roles or ["worker"],
            "version": item["status"]["nodeInfo"]["kubeletVersion"],
            "gpu_allocatable": gpu,
        })
    if not nodes:
        raise ClusterError("aucun nœud retourné par le cluster")
    return nodes
