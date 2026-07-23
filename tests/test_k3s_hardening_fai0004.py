
"""Tests FAI-0004 — durcissement k3s : resources, securityContext, probes,
ServiceAccount, NetworkPolicy et ClusterIP pour services internes."""
import sys
from pathlib import Path

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
    assert out.count("kind: NetworkPolicy") == 1
    assert "name: forgeai-default" in out


def test_redis_clusterip_sans_nodeport():
    out = render_k3s(_plan(_redis()))
    # redis est un service interne -> ClusterIP
    assert "type: ClusterIP" in out
    assert "nodePort:" not in out


def test_redis_resources_et_hardening():
    out = render_k3s(_plan(_redis()))
    assert "requests:" in out
    assert "cpu: 100m" in out
    assert "memory: 128Mi" in out
    assert "limits:" in out
    assert 'cpu: "1"' in out
    assert "memory: 1Gi" in out
    assert "allowPrivilegeEscalation: false" in out
    assert "seccompProfile:" in out
    assert "RuntimeDefault" in out


def test_runAsNonRoot_absent():
    out = render_k3s(_plan(_redis()))
    assert "runAsNonRoot" not in out


def test_redis_probes_tcpSocket():
    out = render_k3s(_plan(_redis()))
    assert out.count("livenessProbe:") == 1
    assert out.count("readinessProbe:") == 1
    assert "tcpSocket:" in out
    assert "httpGet:" not in out


def test_http_service_probe_avec_httpGet_et_path():
    out = render_k3s(_plan(_qdrant_http()))
    assert "httpGet:" in out
    assert "path: /readyz" in out
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


def test_gpu_amd_passthrough_pas_de_hardening():
    amd = ServiceSpec(
        name="engine",
        image="img:latest",
        host_port=8000,
        container_port=8000,
        gpu=True,
        gpu_vendor="amd",
    )
    out = render_k3s(_plan(amd))
    assert "privileged: true" in out
    assert "/dev/kfd" in out
    assert "/dev/dri" in out
    assert "drop:" not in out
    assert "allowPrivilegeEscalation: false" not in out
    assert "nvidia.com/gpu" not in out
