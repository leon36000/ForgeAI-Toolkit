"""Durcissement du renderer k3s/k8s — findings Sentinelle (majeures) sur render_k3s.

Traite 3 trous de robustesse latents (le renderer les portait avant K-CHOICE) :
  1. node_port_for : plage NodePort saturée -> erreur claire, JAMAIS de boucle infinie (DoS) ;
  2. volume mal formé (sans ':') -> ValueError explicite, pas d'IndexError ;
  3. valeurs interpolées au manifeste (name/image/node/volume) : refus des caractères qui
     casseraient/injecteraient le YAML (newline, contrôle) — défense en profondeur.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from forgeai.core.models import DeploymentPlan, RenderTarget, ServiceSpec
from forgeai.renderers.k3s import node_port_for, render_k3s


def _svc(**kw):
    d = dict(name="ollama", image="ollama/ollama:latest", host_port=21434, container_port=11434)
    d.update(kw)
    return ServiceSpec(**d)


def _plan(services):
    return DeploymentPlan(plan_id="t", profile="minimal-cpu", target=RenderTarget.K3S,
                          services=tuple(services), model="m", embed_model="e")


# 1) saturation de la plage NodePort -> erreur bornée, pas de boucle infinie
def test_node_port_for_plage_saturee_leve_erreur():
    used = set(range(30000, 32768))  # les 2768 ports occupés
    with pytest.raises(RuntimeError):
        node_port_for(_svc(), used)


def test_node_port_for_normal_ok():
    used: set = set()
    p1 = node_port_for(_svc(host_port=21434), used)
    p2 = node_port_for(_svc(host_port=24202), used)  # collision de modulo -> réassigné
    assert p1 != p2 and 30000 <= p1 <= 32767 and 30000 <= p2 <= 32767


# 2) volume mal formé -> ValueError claire (pas d'IndexError)
def test_volume_sans_deux_points_leve_valueerror():
    with pytest.raises(ValueError):
        render_k3s(_plan([_svc(volumes=("volume-sans-chemin",))]))


def test_volume_bien_forme_ok():
    out = render_k3s(_plan([_svc(volumes=("data:/root/.ollama",))]))
    assert "name: data" in out and "mountPath: /root/.ollama" in out


# 3) injection YAML : une valeur avec newline/contrôle est refusée
@pytest.mark.parametrize("champ", ["name", "image"])
def test_valeur_avec_newline_refusee(champ):
    with pytest.raises(ValueError):
        render_k3s(_plan([_svc(**{champ: "ok\n      hostPID: true"})]))


def test_node_avec_newline_refuse():
    with pytest.raises(ValueError):
        render_k3s(_plan([_svc()]), node="node\nmalicious: true")


# 4) service_type : le renderer ne fait pas confiance à son appelant -> allowlist stricte
def test_service_type_invalide_refuse():
    with pytest.raises(ValueError):
        render_k3s(_plan([_svc()]), service_type="NodePort\n  hostNetwork: true")
    with pytest.raises(ValueError):
        render_k3s(_plan([_svc()]), service_type="Bidon")


def test_service_types_valides_ok():
    for st in ("NodePort", "LoadBalancer"):
        out = render_k3s(_plan([_svc()]), service_type=st)
        assert f"type: {st}" in out


# ---------------------------------------------------------------------------
# K8S-022 / FAI-U-022 — le profil Pod Security Standards « restricted » est le DÉFAUT.
# Validateur réel des règles PSS restricted (k8s >= 1.25) appliqué aux manifests rendus,
# et non une simple recherche de sous-chaîne : chaque conteneur de chaque Deployment est vérifié.
# ---------------------------------------------------------------------------
import yaml

# Volumes autorisés par PSS restricted (les autres, dont hostPath, sont refusés).
_PSS_VOLUMES_OK = frozenset({
    "configMap", "csi", "downwardAPI", "emptyDir", "ephemeral",
    "persistentVolumeClaim", "projected", "secret",
})


def _deployments(manifest: str) -> list[dict]:
    return [d for d in yaml.safe_load_all(manifest) if d and d.get("kind") == "Deployment"]


def violations_pss_restricted(manifest: str) -> list[str]:
    """Retourne la liste des écarts au profil PSS `restricted`. Vide = conforme."""
    out: list[str] = []
    for dep in _deployments(manifest):
        pod = dep["spec"]["template"]["spec"]
        psc = pod.get("securityContext") or {}
        who = dep["metadata"]["name"]
        for champ in ("hostNetwork", "hostPID", "hostIPC"):
            if pod.get(champ):
                out.append(f"{who}: {champ} activé")
        for vol in pod.get("volumes") or []:
            kinds = [k for k in vol if k != "name"]
            for kind in kinds:
                if kind not in _PSS_VOLUMES_OK:
                    out.append(f"{who}: type de volume interdit par restricted : {kind}")
        for cont in pod.get("containers") or []:
            csc = cont.get("securityContext") or {}
            cible = f"{who}/{cont['name']}"
            if csc.get("privileged"):
                out.append(f"{cible}: privileged")
            if csc.get("allowPrivilegeEscalation") is not False:
                out.append(f"{cible}: allowPrivilegeEscalation != false")
            drop = ((csc.get("capabilities") or {}).get("drop")) or []
            if "ALL" not in drop:
                out.append(f"{cible}: capabilities.drop ne contient pas ALL")
            add = ((csc.get("capabilities") or {}).get("add")) or []
            if [c for c in add if c != "NET_BIND_SERVICE"]:
                out.append(f"{cible}: capabilities.add interdites : {add}")
            if not (csc.get("runAsNonRoot") or psc.get("runAsNonRoot")):
                out.append(f"{cible}: runAsNonRoot absent (ni pod ni conteneur)")
            seccomp = (csc.get("seccompProfile") or psc.get("seccompProfile") or {}).get("type")
            if seccomp not in ("RuntimeDefault", "Localhost"):
                out.append(f"{cible}: seccompProfile.type = {seccomp!r}")
    return out


def test_profil_restricted_est_le_defaut():
    """Un service ordinaire (sans exception déclarée) est rendu conforme PSS restricted."""
    out = render_k3s(_plan([_svc(name="service-quelconque", image="exemple/app:1.0")]))
    assert violations_pss_restricted(out) == []


def test_root_filesystem_en_lecture_seule_par_defaut():
    out = render_k3s(_plan([_svc(name="service-quelconque", image="exemple/app:1.0")]))
    dep = _deployments(out)[0]
    cont = dep["spec"]["template"]["spec"]["containers"][0]
    assert cont["securityContext"]["readOnlyRootFilesystem"] is True
    # readOnlyRootFilesystem sans /tmp inscriptible casse la plupart des runtimes -> emptyDir explicite
    montages = {m["mountPath"] for m in cont.get("volumeMounts") or []}
    assert "/tmp" in montages
