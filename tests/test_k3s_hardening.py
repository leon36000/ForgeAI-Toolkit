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


# ---------------------------------------------------------------------------
# K8S-024 / FAI-U-024 — Pod Security Admission : le Namespace rendu doit PORTER le niveau
# d'enforcement, sinon le profil restricted de K8S-022 n'est jamais APPLIQUÉ par le cluster.
# Le niveau enforce doit correspondre à ce que les manifests respectent réellement.
# ---------------------------------------------------------------------------
_PSA_PREFIXE = "pod-security.kubernetes.io/"


def _namespace(manifest: str) -> dict:
    for doc in yaml.safe_load_all(manifest):
        if doc and doc.get("kind") == "Namespace":
            return doc
    raise AssertionError("aucun Namespace dans le manifeste rendu")


def test_namespace_porte_l_admission_pod_security():
    """Sans ces étiquettes, le cluster n'applique RIEN : le durcissement reste déclaratif."""
    ns = _namespace(render_k3s(_plan([_svc(name="service-quelconque")])))
    labels = ns["metadata"].get("labels") or {}
    assert labels.get(_PSA_PREFIXE + "enforce") == "restricted"
    assert labels.get(_PSA_PREFIXE + "audit") == "restricted"
    assert labels.get(_PSA_PREFIXE + "warn") == "restricted"


def test_versions_d_admission_epinglees():
    """`latest` ferait dériver la politique au gré des montées de version du cluster : versions
    ÉPINGLÉES, comme les images le sont déjà (FAI-0011)."""
    ns = _namespace(render_k3s(_plan([_svc(name="service-quelconque")])))
    labels = ns["metadata"].get("labels") or {}
    for mode in ("enforce", "audit", "warn"):
        version = labels.get(f"{_PSA_PREFIXE}{mode}-version")
        assert version and version != "latest", f"{mode}-version doit être épinglée, vu : {version!r}"
        assert version.startswith("v1."), f"version k8s attendue (vX.Y), vu : {version!r}"


def test_enforce_correspond_aux_manifests_rendus():
    """Le niveau annoncé doit être TENU : un plan sans GPU est conforme restricted, donc enforce
    reste `restricted`. C'est le lien entre l'étiquette et la réalité du rendu."""
    out = render_k3s(_plan([_svc(name="service-quelconque")]))
    assert violations_pss_restricted(out) == []
    labels = _namespace(out)["metadata"].get("labels") or {}
    assert labels.get(_PSA_PREFIXE + "enforce") == "restricted"


def test_exception_gpu_degrade_enforce_et_reste_visible():
    """Un service GPU DÉROGE au profil restricted (mesure K8S-022 : non-root = 0/4 devices).
    Annoncer `enforce: restricted` sur un tel plan serait un mensonge : le cluster REFUSERAIT les
    pods au déploiement. Niveau réellement tenu, MESURÉ sur cluster k3s v1.35.5 avec le pod GPU réel :
      enforce=restricted -> REFUSÉ (« restricted volume type hostPath », « runAsNonRoot »)
      enforce=baseline    -> REFUSÉ (« hostPath volumes (volume "dri") »)
      enforce=privileged  -> ACCEPTÉ
    `baseline` interdit lui aussi hostPath : seul `privileged` admet le passthrough de devices.
    L'exception doit donc être VISIBLE : enforce descendu au seul niveau qui tient, audit ET warn
    MAINTENUS à restricted pour que l'API server continue de signaler chaque écart."""
    out = render_k3s(_plan([_svc(name="ollama", gpu=True, gpu_vendor="amd")]))
    labels = _namespace(out)["metadata"].get("labels") or {}
    assert labels.get(_PSA_PREFIXE + "enforce") == "privileged"
    assert labels.get(_PSA_PREFIXE + "audit") == "restricted"
    assert labels.get(_PSA_PREFIXE + "warn") == "restricted"
    assert "# forgeai:" in out.split("kind: Namespace")[1].split("---")[0]


def test_service_sans_volume_declare_garde_un_chemin_de_donnees_inscriptible():
    """Régression K8S-022 attrapée par l'E2E de K8S-024 : avec readOnlyRootFilesystem, un service
    dont le répertoire de données n'est PAS déclaré en volume ne peut plus le créer. Mesuré sur
    cluster réel : qdrant sans volume -> « Service internal error: Read-only file system (os error
    30) ». Le profil doit donc fournir un emptyDir de repli sur ce chemin."""
    out = render_k3s(_plan([_svc(name="qdrant", image="qdrant/qdrant:v1.12.5")]))
    cont = _deployments(out)[0]["spec"]["template"]["spec"]["containers"][0]
    montages = {m["mountPath"] for m in cont.get("volumeMounts") or []}
    assert "/qdrant/storage" in montages


def test_le_pvc_prime_sur_l_emptydir_de_repli():
    """Le repli ne doit JAMAIS masquer les données : quand un volume persistant est déclaré sur le
    même chemin, il est monté seul (un mountPath dupliqué rendrait d'ailleurs le pod invalide)."""
    out = render_k3s(_plan([_svc(name="qdrant", image="qdrant/qdrant:v1.12.5",
                                volumes=("forgeai-qdrant-data:/qdrant/storage",))]))
    pod = _deployments(out)[0]["spec"]["template"]["spec"]
    montages = [m["mountPath"] for m in pod["containers"][0].get("volumeMounts") or []]
    assert montages.count("/qdrant/storage") == 1
    volume = next(v for v in pod["volumes"] if v["name"] == "forgeai-qdrant-data")
    assert "persistentVolumeClaim" in volume and "emptyDir" not in volume
