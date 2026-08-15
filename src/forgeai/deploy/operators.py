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
from forgeai.i18n import t


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


def fetch_releases_helm(runner: CommandRunner) -> list:
    """Un SEUL appel `helm list -A -o json`, résultat parsé réutilisable par plusieurs
    detect()/plan() (PERF — trouvé en session : `_operators()` dans cli.py bouclait sur les 3
    opérateurs du châssis et rappelait cette commande IDENTIQUE une fois par opérateur, alors
    qu'elle liste déjà TOUTES les releases de TOUS les namespaces indépendamment du nom visé).
    Retourne [] si la commande échoue, ne renvoie rien d'exploitable, si le JSON est invalide ou
    si le JSON valide ne représente pas une liste — dans tous ces cas detect() retombe sur le
    fallback CRD, exactement comme avant."""
    code, out = runner.run(["helm", "list", "-A", "-o", "json"])
    if code == 0 and out.strip():
        try:
            releases = json.loads(out)
            return releases if isinstance(releases, list) else []
        except (ValueError, TypeError):
            return []
    return []


def detect(name: str, runner: CommandRunner, releases_helm: list | None = None) -> OperatorStatus:
    """Détecte un opérateur : release Helm présente (avec sa version de chart) ou CRD signature.

    releases_helm : résultat déjà obtenu de fetch_releases_helm(runner), pour éviter un appel
    `helm list` redondant quand plusieurs opérateurs sont vérifiés dans la même invocation (voir
    _operators() dans cli.py). None (défaut) -> comportement historique inchangé : un appel
    `helm list` propre à CET appel de detect() — compatibilité totale pour un usage isolé
    (ex. `forgeai operators --name <x>`, ou tout appelant externe à (name, runner))."""
    spec = OPERATORS[name]
    releases = releases_helm if releases_helm is not None else fetch_releases_helm(runner)
    for rel in releases:
        if rel.get("name") == spec.release:
            return OperatorStatus(name, True, "helm", rel.get("chart"))
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


def plan(name: str, runner: CommandRunner, releases_helm: list | None = None) -> dict:
    """Décision Discovery/Adoption : présent -> ADOPTER (aucune commande) ; absent -> installer.

    releases_helm : voir detect() — transmis tel quel, None par défaut (compatibilité)."""
    if name not in OPERATORS:
        raise KeyError(t("deploy.operators.plan.operateur_inconnu", name=name, connus=sorted(OPERATORS)))
    status = detect(name, runner, releases_helm)
    if status.present:
        return {"action": "adopt", "status": status, "commands": []}
    return {"action": "install", "status": status, "commands": install_argv(name)}
