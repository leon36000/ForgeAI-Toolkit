"""Tests FAI-0004 — durcissement k3s : resources, securityContext, probes,
ServiceAccount, NetworkPolicy et ClusterIP pour services internes."""
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from forgeai.core.models import DeploymentPlan, RenderTarget, ServiceSpec
from forgeai.renderers.k3s import render_k3s


def _plan(*services):
    return DeploymentPlan(
        plan_id="p1-fai0004",
        profile="minimal",
        target=RenderTarget.K3S,
        services=services,
        model="m",
        embed_model="e",
    )


def _redis():
    return ServiceSpec(
        name="redis",
        image="redis:7",
        host_port=6379,
        container_port=6379,
        volumes=("forgeai-redis-data:/data",),
        # RES-012B : redis est déclaré `db` dans deploy-specs.json (brique stateful
        # mémoire-centric, ADR RES-012A §4). Le helper reflète cette réalité.
        resource_class="db",
    )


def _qdrant_http():
    return ServiceSpec(
        name="qdrant-http",
        image="qdrant/qdrant",
        host_port=6333,
        container_port=6333,
        healthcheck_url="http://127.0.0.1:6333/readyz",
    )


def test_serviceaccount_and_networkpolicy_emis_une_fois():
    out = render_k3s(_plan(_redis()))
    assert out.count("kind: ServiceAccount") == 1
    assert "name: forgeai-sa" in out
    assert out.count("automountServiceAccountToken: false") == 2  # SA + pod spec
    # K8S-023 : le renderer émet désormais PLUSIEURS NetworkPolicies par conception — refus par
    # défaut, DNS, puis une allowlist par service cible d'une dépendance déclarée. L'intention de
    # ce test — aucune duplication accidentelle — est préservée et vérifiée précisément : chaque
    # politique porte un nom unique, et le refus par défaut est émis exactement une fois.
    noms = [ligne.strip()[len("name: "):] for ligne in out.splitlines()
            if ligne.strip().startswith("name: forgeai-")]
    politiques = [n for n in noms if n.startswith("forgeai-default-deny")
                  or n.startswith("forgeai-allow-")]
    assert len(politiques) == len(set(politiques)), f"politique dupliquée : {politiques}"
    assert politiques.count("forgeai-default-deny") == 1


def test_redis_clusterip_sans_nodeport():
    out = render_k3s(_plan(_redis()))
    # redis est un service interne -> ClusterIP
    assert "type: ClusterIP" in out
    assert "nodePort:" not in out


def test_redis_resources_et_hardening():
    out = render_k3s(_plan(_redis()))
    assert "requests:" in out
    # RES-012B : les ressources ne sont plus des littéraux — redis relève de la classe `db`
    # (ADR RES-012A §4 : brique stateful mémoire-centric). L'intention du test — un bloc de
    # ressources est bien rendu pour ce service — est préservée et vérifiée sur les valeurs
    # de sa classe, au lieu du magic number que ce package supprime.
    assert 'cpu: "250m"' in out and 'memory: "512Mi"' in out
    assert "limits:" in out
    assert 'cpu: "1000m"' in out and 'memory: "2Gi"' in out
    assert "allowPrivilegeEscalation: false" in out
    assert "seccompProfile:" in out
    assert "RuntimeDefault" in out


def test_runAsNonRoot_present_desormais():
    """FAI-0004 documentait l'ABSENCE de runAsNonRoot (les images tournaient en root).
    SUPERSÉDÉ par FAI-U-022/K8S-022 : le profil PSS restricted est désormais le défaut, et la
    mesure runtime a établi que drop:[ALL] n'est viable QU'en non-root (root + drop ALL ->
    « chown: Operation not permitted » sur redis). L'assertion est donc inversée."""
    out = render_k3s(_plan(_redis()))
    assert "runAsNonRoot: true" in out
    assert "runAsUser: 999" in out  # uid mesuré de redis


def test_redis_probes_tcpSocket():
    out = render_k3s(_plan(_redis()))
    assert out.count("livenessProbe:") == 1
    assert out.count("readinessProbe:") == 1
    assert "tcpSocket:" in out
    assert "httpGet:" not in out


def test_http_service_probe_avec_httpGet_et_path():
    out = render_k3s(_plan(_qdrant_http()))
    assert "httpGet:" in out
    # HEALTH-028B : chemins ÉCHAPPÉS (json.dumps) — intention inchangée, forme quotée.
    assert 'path: "/readyz"' in out
    assert "port: 6333" in out


def test_pod_serviceAccountName():
    out = render_k3s(_plan(_redis()))
    assert "serviceAccountName: forgeai-sa" in out


def test_pvc_non_regression():
    out = render_k3s(_plan(_redis()))
    assert "kind: PersistentVolumeClaim" in out
    assert "name: forgeai-redis-data" in out


def test_service_non_interne_reste_nodeport():
    litellm = ServiceSpec(
        name="litellm",
        image="litellm",
        host_port=4000,
        container_port=4000,
    )
    out = render_k3s(_plan(litellm))
    assert "type: NodePort" in out
    assert "nodePort:" in out


def test_gpu_amd_device_plugin_avec_hardening():
    """LAB-033A : l'accès GPU AMD se fait par ressource de device plugin (amd.com/gpu).
    Le passthrough hostPath /dev/kfd+/dev/dri est supprimé car le cgroup devices refuse
    l'accès au char device (EPERM). Le securityContext durci reste appliqué."""
    amd = ServiceSpec(
        name="engine",
        image="img:latest",
        host_port=8000,
        container_port=8000,
        gpu=True,
        gpu_vendor="amd",
    )
    out = render_k3s(_plan(amd))
    assert 'amd.com/gpu: "1"' in out
    assert "privileged: true" not in out
    assert "allowPrivilegeEscalation: false" in out
    assert "nvidia.com/gpu" not in out
    # Vérification YAML : aucun volume ne porte la clé hostPath.
    for doc in yaml.safe_load_all(out):
        if doc and doc.get("kind") == "Deployment":
            for vol in doc["spec"]["template"]["spec"].get("volumes") or []:
                assert "hostPath" not in vol, f"volume hostPath interdit : {vol}"
