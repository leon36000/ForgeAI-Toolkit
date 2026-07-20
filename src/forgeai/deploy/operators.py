"""Opérateurs Kubernetes du châssis (mode K8s) — détection + ADOPTION ou installation Helm.

Aligné sur la capacité Discovery/Adoption : le Toolkit **détecte** un opérateur déjà présent sur le
cluster et l'**ADOPTE** (jamais réinstaller/écraser l'infra existante de l'utilisateur) ; il ne
l'installe (via Helm) que s'il est **absent**. Zéro dépendance : on shelle `helm`/`kubectl` via le
CommandRunner, exactement comme le reste de forgeai shelle `docker`/`kubectl`.

Opérateurs couverts : external-secrets (coffre -> Secrets k8s, complète openbao E3b), argo-cd
(GitOps), kserve (serving de modèles). Détection : release Helm présente OU CRD signature présent.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from forgeai.core.runner import CommandRunner


@dataclass(frozen=True)
class OperatorSpec:
    release: str          # nom de la release Helm
    namespace: str
    repo_name: str
    repo_url: str
    chart: str            # repo/chart
    crd: str              # CRD signature (détection alternative)


@dataclass(frozen=True)
class OperatorStatus:
    name: str
    present: bool
    source: str | None    # "helm" | "crd" | None
    version: str | None


OPERATORS: dict[str, OperatorSpec] = {
    "external-secrets-operator": OperatorSpec(
        release="external-secrets", namespace="external-secrets",
        repo_name="external-secrets", repo_url="https://charts.external-secrets.io",
        chart="external-secrets/external-secrets", crd="externalsecrets.external-secrets.io"),
    "argo-cd": OperatorSpec(
        release="argocd", namespace="argocd",
        repo_name="argo", repo_url="https://argoproj.github.io/argo-helm",
        chart="argo/argo-cd", crd="applications.argoproj.io"),
    "kserve": OperatorSpec(
        release="kserve", namespace="kserve",
        repo_name="kserve", repo_url="https://kserve.github.io/charts",
        chart="kserve/kserve", crd="inferenceservices.serving.kserve.io"),
}


def detect(name: str, runner: CommandRunner) -> OperatorStatus:
    """Détecte un opérateur : release Helm présente (avec sa version de chart) ou CRD signature."""
    spec = OPERATORS[name]
    code, out = runner.run(["helm", "list", "-A", "-o", "json"])
    if code == 0 and out.strip():
        try:
            for rel in json.loads(out):
                if rel.get("name") == spec.release:
                    return OperatorStatus(name, True, "helm", rel.get("chart"))
        except (ValueError, TypeError):
            pass
    code, out = runner.run(["kubectl", "get", "crd", spec.crd, "-o", "name"])
    if code == 0 and out.strip():
        return OperatorStatus(name, True, "crd", None)
    return OperatorStatus(name, False, None, None)


def install_argv(name: str) -> list[list[str]]:
    """Commandes Helm pour INSTALLER un opérateur absent (repo add/update + upgrade --install)."""
    spec = OPERATORS[name]
    return [
        ["helm", "repo", "add", spec.repo_name, spec.repo_url],
        ["helm", "repo", "update", spec.repo_name],
        ["helm", "upgrade", "--install", spec.release, spec.chart,
         "-n", spec.namespace, "--create-namespace", "--wait"],
    ]


def plan(name: str, runner: CommandRunner) -> dict:
    """Décision Discovery/Adoption : présent -> ADOPTER (aucune commande) ; absent -> installer."""
    if name not in OPERATORS:
        raise KeyError(f"opérateur inconnu : {name} (connus : {sorted(OPERATORS)})")
    status = detect(name, runner)
    if status.present:
        return {"action": "adopt", "status": status, "commands": []}
    return {"action": "install", "status": status, "commands": install_argv(name)}
