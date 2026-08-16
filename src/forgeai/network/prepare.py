from __future__ import annotations

import json
from typing import Any

from forgeai.core.runner import CommandRunner
from forgeai.i18n import t


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
                # RC1-456-iter3 : chemin purement diagnostique (message d'erreur) — un élément
                # non-dict, ou un `metadata`/`name` absent/`null` dans `items`, ne doit jamais
                # empêcher la levée de la PrepareError réelle ci-dessous, même famille que
                # #492/#527 (élément malformé ignoré, pas fatal ; .get() partout, pas
                # d'indexation directe).
                noms_bruts = [
                    (item.get("metadata") or {}).get("name")
                    for item in data.get("items", [])
                    if isinstance(item, dict)
                ]
                names = [n for n in noms_bruts if isinstance(n, str)]
            except json.JSONDecodeError:
                pass
        raise PrepareError(
            t("network.prepare.sonder_noeud.noeud_absent", hostname=hostname,
              noms=', '.join(names) or t("network.prepare.aucun"))
        )

    try:
        data = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise PrepareError(t("network.prepare.sonder_noeud.sortie_illisible",
                              hostname=hostname, detail=exc)) from exc

    status = data.get("status", {}) or {}
    ready = _ready_value(status.get("conditions", []) or [])
    # RC1-456-iter3 : `status.capacity`/`status.nodeInfo` peuvent être des clés PRÉSENTES avec
    # une valeur `null` explicite (nœud dont le kubelet n'a pas fini son initialisation) —
    # `.get(clé, défaut)` ne protège QUE l'absence de clé, jamais une valeur `null` présente.
    capacity = status.get("capacity") or {}
    gpu_nvidia = int(capacity.get("nvidia.com/gpu", "0") or 0)
    gpu_amd = int(capacity.get("amd.com/gpu", "0") or 0)
    arch = (status.get("nodeInfo") or {}).get("architecture", "")
    labels = (data.get("metadata") or {}).get("labels", {}) or {}

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
                "titre_en": "Reachability diagnostic",
                "action": "aucune",
                "commande": None,
                "pourquoi_fr": (
                    f"Le nœud '{hostname}' n'est pas Ready (état {ready!r}). "
                    "Résolvez la connexion réseau/kubelet avant de le préparer."
                ),
            }
        )
        return steps

    helm_cmds = {
        "nvidia": ["helm", "upgrade", "--install", "gpu-operator", "gpu-operator",
                   "--repo", "https://helm.ngc.nvidia.com/nvidia",
                   "-n", "gpu-operator", "--create-namespace"],
        "amd": ["helm", "upgrade", "--install", "amd-gpu-operator", "gpu-operator",
                "--repo", "https://rocm.github.io/gpu-operator",
                "-n", "kube-amd-gpu", "--create-namespace"],
    }
    # Symétrie stricte NVIDIA/AMD (objection unanime revue N3) :
    # exposé -> vérifier ; probable non exposé -> helm (ou note manuelle SANS étiquette prêt).
    vendors = (
        ("nvidia", gpu_nvidia, _nvidia_probable(labels)),
        ("amd", gpu_amd, _amd_probable(labels)),
    )
    installation_manuelle = False
    for vendor, exposes, probable in vendors:
        if exposes > 0:
            steps.append({
                "id": f"verifier-gpu-{vendor}",
                "titre_fr": f"Vérifier le GPU {vendor.upper()} déjà exposé",
                "titre_en": f"Check the already-exposed {vendor.upper()} GPU",
                "action": "verifier",
                "commande": None,
                "pourquoi_fr": (f"Le nœud expose déjà {exposes} GPU(s) {vendor.upper()} ; "
                                "aucun opérateur n'est nécessaire."),
            })
        elif probable:
            if helm_present:
                steps.append({
                    "id": f"helm-{vendor}",
                    "titre_fr": f"Installer {vendor.upper()} GPU Operator",
                    "titre_en": f"Install {vendor.upper()} GPU Operator",
                    "action": "helm",
                    "commande": helm_cmds[vendor],
                    "pourquoi_fr": (f"Un GPU {vendor.upper()} est détecté mais non exposé comme "
                                    "ressource kubernetes ; l'opérateur provisionne le device-plugin."),
                })
            else:
                installation_manuelle = True
                steps.append({
                    "id": f"helm-{vendor}-manuel",
                    "titre_fr": f"Installer {vendor.upper()} GPU Operator (helm manuel)",
                    "titre_en": f"Install {vendor.upper()} GPU Operator (manual helm)",
                    "action": "aucune",
                    "commande": None,
                    "pourquoi_fr": ("helm n'est pas installé localement. Commande à exécuter "
                                    "manuellement : " + " ".join(helm_cmds[vendor])),
                })

    gpu_present = any(exposes > 0 or probable for _, exposes, probable in vendors)
    if not gpu_present:
        steps.append({
            "id": "label-cpu",
            "titre_fr": "Étiqueter le nœud comme réceptacle CPU",
            "titre_en": "Label the node as a CPU receptacle",
            "action": "label",
            "commande": ["kubectl", "label", "node", hostname,
                         "forgeai/receptacle=pret-cpu", "--overwrite"],
            "pourquoi_fr": "Aucun GPU détecté ; le nœud est un réceptacle edge CPU valide.",
        })
    elif not installation_manuelle:
        steps.append({
            "id": "label-pret",
            "titre_fr": "Étiqueter le nœud comme réceptacle prêt",
            "titre_en": "Label the node as a ready receptacle",
            "action": "label",
            "commande": ["kubectl", "label", "node", hostname,
                         "forgeai/receptacle=pret", "--overwrite"],
            "pourquoi_fr": "Le nœud est prêt à accueillir des charges GPU.",
        })
    # installation manuelle en attente : PAS d'étiquette « prêt » (honnêteté du statut)

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
                # NOTE i18n : `pourquoi_fr` est un champ français-seul pré-existant
                # (mécanisme dédié titre_fr/titre_en de I18N-031, cli.py:824) — hors
                # périmètre de cette story (messages raise(), pas les champs d'affichage
                # de plan). Le seul texte traduit ici est l'enveloppe de l'exception.
                raise PrepareError(
                    t("network.prepare.preparer_noeud.preparation_impossible",
                      hostname=hostname, pourquoi=step['pourquoi_fr'])
                )
            etapes.append({**step, "statut": "sautee"})
            continue

        rc, stdout = runner.run(cmd)
        if rc == 0:
            etapes.append({**step, "statut": "ok"})
        else:
            etapes.append({**step, "statut": "echec", "rc": rc, "stdout": stdout})
            raise PrepareError(
                t("network.prepare.preparer_noeud.etape_echouee",
                  etape_id=step['id'], hostname=hostname, code=rc)
            )

    if etat["ready"] is not True:
        receptacle = "non"
    elif any(s["id"] == "label-cpu" for s in plan):
        receptacle = "pret-cpu"
    elif any(s["id"].endswith("-manuel") for s in plan):
        receptacle = "attente-installation"  # helm manquant : jamais « prêt » à tort
    else:
        receptacle = "pret"

    return {
        "hostname": hostname,
        "etat": etat,
        "etapes": etapes,
        "receptacle": receptacle,
    }
