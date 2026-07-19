from __future__ import annotations

import json
from typing import Any

from forgeai.core.runner import CommandRunner


class PrepareError(Exception):
    """Erreur de préparation d'un nœud en réceptacle."""


def _ready_value(conditions: list[dict[str, Any]]) -> bool | None:
    for cond in conditions:
        if cond.get("type") == "Ready":
            status = cond.get("status", "")
            if status == "True":
                return True
            if status == "False":
                return False
            return None
    return None


def _nvidia_probable(labels: dict[str, str]) -> bool:
    return (
        labels.get("nvidia.com/gpu.present") == "true"
        or labels.get("feature.node.kubernetes.io/pci-10de.present") == "true"
    )


def _amd_probable(labels: dict[str, str]) -> bool:
    return (
        labels.get("amd.com/gpu.present") == "true"
        or labels.get("feature.node.kubernetes.io/pci-1002.present") == "true"
    )


def sonder_noeud(runner: CommandRunner, hostname: str) -> dict:
    """Interroge kubectl pour obtenir l'état d'un nœud."""
    argv = ["kubectl", "get", "node", hostname, "-o", "json"]
    rc, stdout = runner.run(argv)
    if rc != 0:
        # Liste les nœuds connus pour aider au diagnostic.
        list_rc, list_stdout = runner.run(["kubectl", "get", "nodes", "-o", "json"])
        names: list[str] = []
        if list_rc == 0:
            try:
                data = json.loads(list_stdout)
                names = [item["metadata"]["name"] for item in data.get("items", [])]
            except (json.JSONDecodeError, KeyError):
                pass
        raise PrepareError(
            f"nœud '{hostname}' absent ou injoignable. Nœuds connus : {', '.join(names) or '(aucun)'}"
        )

    try:
        data = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise PrepareError(f"sortie kubectl illisible pour {hostname} : {exc}") from exc

    status = data.get("status", {})
    ready = _ready_value(status.get("conditions", []))
    capacity = status.get("capacity", {})
    gpu_nvidia = int(capacity.get("nvidia.com/gpu", "0") or 0)
    gpu_amd = int(capacity.get("amd.com/gpu", "0") or 0)
    arch = status.get("nodeInfo", {}).get("architecture", "")
    labels = data.get("metadata", {}).get("labels", {})

    return {
        "hostname": hostname,
        "ready": ready,
        "gpu_nvidia": gpu_nvidia,
        "gpu_amd": gpu_amd,
        "arch": arch,
        "labels": labels,
    }


def plan_preparation(etat: dict, helm_present: bool) -> list[dict]:
    """Construit le plan de préparation d'un nœud sans l'exécuter."""
    hostname = etat["hostname"]
    ready = etat.get("ready")
    gpu_nvidia = etat.get("gpu_nvidia", 0)
    gpu_amd = etat.get("gpu_amd", 0)
    labels = etat.get("labels", {})

    steps: list[dict] = []

    if ready is not True:
        steps.append(
            {
                "id": "diagnostic",
                "titre_fr": "Diagnostic de joignabilité",
                "action": "aucune",
                "commande": None,
                "pourquoi_fr": (
                    f"Le nœud '{hostname}' n'est pas Ready (état {ready!r}). "
                    "Résolvez la connexion réseau/kubelet avant de le préparer."
                ),
            }
        )
        return steps

    if gpu_nvidia > 0:
        steps.append(
            {
                "id": "verifier-gpu",
                "titre_fr": "Vérifier le GPU NVIDIA déjà exposé",
                "action": "verifier",
                "commande": None,
                "pourquoi_fr": (
                    f"Le nœud expose déjà {gpu_nvidia} GPU(s) NVIDIA ; "
                    "aucun opérateur n'est nécessaire."
                ),
            }
        )
    elif _nvidia_probable(labels) and gpu_nvidia == 0:
        helm_cmd = [
            "helm",
            "upgrade",
            "--install",
            "gpu-operator",
            "gpu-operator",
            "--repo",
            "https://helm.ngc.nvidia.com/nvidia",
            "-n",
            "gpu-operator",
            "--create-namespace",
        ]
        if helm_present:
            steps.append(
                {
                    "id": "helm-nvidia",
                    "titre_fr": "Installer NVIDIA GPU Operator",
                    "action": "helm",
                    "commande": helm_cmd,
                    "pourquoi_fr": (
                        "Un GPU NVIDIA est détecté mais n'est pas exposé comme ressource "
                        "kubernetes ; l'opérateur provisionne le device-plugin."
                    ),
                }
            )
        else:
            steps.append(
                {
                    "id": "helm-nvidia-manuel",
                    "titre_fr": "Installer NVIDIA GPU Operator (helm manuel)",
                    "action": "aucune",
                    "commande": None,
                    "pourquoi_fr": (
                        "helm n'est pas installé localement. Commande à exécuter manuellement : "
                        + " ".join(helm_cmd)
                    ),
                }
            )

    if gpu_amd > 0:
        helm_cmd = [
            "helm",
            "upgrade",
            "--install",
            "amd-gpu-operator",
            "gpu-operator",
            "--repo",
            "https://rocm.github.io/gpu-operator",
            "-n",
            "kube-amd-gpu",
            "--create-namespace",
        ]
        if helm_present:
            steps.append(
                {
                    "id": "helm-amd",
                    "titre_fr": "Installer AMD GPU Operator",
                    "action": "helm",
                    "commande": helm_cmd,
                    "pourquoi_fr": (
                        f"Le nœud déclare {gpu_amd} GPU(s) AMD ; l'opérateur AMD est requis."
                    ),
                }
            )
        else:
            steps.append(
                {
                    "id": "helm-amd-manuel",
                    "titre_fr": "Installer AMD GPU Operator (helm manuel)",
                    "action": "aucune",
                    "commande": None,
                    "pourquoi_fr": (
                        "helm n'est pas installé localement. Commande à exécuter manuellement : "
                        + " ".join(helm_cmd)
                    ),
                }
            )

    # Déterminer l'étiquette finale.
    if gpu_nvidia > 0 or _nvidia_probable(labels) or gpu_amd > 0 or _amd_probable(labels):
        steps.append(
            {
                "id": "label-pret",
                "titre_fr": "Étiqueter le nœud comme réceptacle prêt",
                "action": "label",
                "commande": [
                    "kubectl",
                    "label",
                    "node",
                    hostname,
                    "forgeai/receptacle=pret",
                    "--overwrite",
                ],
                "pourquoi_fr": "Le nœud est prêt à accueillir des charges GPU.",
            }
        )
    else:
        steps.append(
            {
                "id": "label-cpu",
                "titre_fr": "Étiqueter le nœud comme réceptacle CPU",
                "action": "label",
                "commande": [
                    "kubectl",
                    "label",
                    "node",
                    hostname,
                    "forgeai/receptacle=pret-cpu",
                    "--overwrite",
                ],
                "pourquoi_fr": "Aucun GPU détecté ; le nœud est un réceptacle edge CPU valide.",
            }
        )

    return steps


def preparer_noeud(
    runner: CommandRunner, hostname: str, *, appliquer: bool, helm_present: bool
) -> dict:
    """Sonde un nœud, construit un plan et optionnellement l'applique."""
    etat = sonder_noeud(runner, hostname)
    plan = plan_preparation(etat, helm_present)

    etapes: list[dict] = []
    for step in plan:
        if not appliquer:
            etapes.append({**step, "statut": "planifiee"})
            continue

        cmd = step.get("commande")
        if cmd is None:
            if step["id"] == "diagnostic":
                etapes.append({**step, "statut": "echec"})
                raise PrepareError(
                    f"Préparation impossible sur '{hostname}' : {step['pourquoi_fr']}"
                )
            etapes.append({**step, "statut": "sautee"})
            continue

        rc, stdout = runner.run(cmd)
        if rc == 0:
            etapes.append({**step, "statut": "ok"})
        else:
            etapes.append({**step, "statut": "echec", "rc": rc, "stdout": stdout})
            raise PrepareError(
                f"Échec de l'étape '{step['id']}' sur '{hostname}' (code {rc})"
            )

    if etat["ready"] is not True:
        receptacle = "non"
    elif any(s["id"] == "label-cpu" for s in plan):
        receptacle = "pret-cpu"
    else:
        receptacle = "pret"

    return {
        "hostname": hostname,
        "etat": etat,
        "etapes": etapes,
        "receptacle": receptacle,
    }
