"""Tests FAI-0003 — volume data k3s rendu en PersistentVolumeClaim."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from forgeai.core.models import DeploymentPlan, RenderTarget, ServiceSpec
from forgeai.renderers.k3s import render_k3s


def _svc(**kw):
    d = dict(name="ollama", image="ollama/ollama:latest", host_port=21434, container_port=11434)
    d.update(kw)
    return ServiceSpec(**d)


def _plan(services):
    return DeploymentPlan(
        plan_id="t", profile="minimal-cpu", target=RenderTarget.K3S,
        services=tuple(services), model="m", embed_model="e"
    )


def _plan_redis():
    return _plan([
        _svc(
            name="redis",
            image="redis:7",
            host_port=26379,
            container_port=6379,
            volumes=("forgeai-redis-data:/data",),
        )
    ])


def _plan_litellm():
    return _plan([
        _svc(
            name="litellm",
            image="litellm/litellm:latest",
            host_port=24000,
            container_port=4000,
            volumes=("./litellm-config.yaml:/app/litellm-config.yaml:ro",),
            command=["litellm", "--config", "/app/litellm-config.yaml"],
        )
    ])


def test_pvc_emis_pour_volume_data():
    out = render_k3s(_plan_redis(), config_files=None)

    assert "kind: PersistentVolumeClaim" in out
    assert "name: forgeai-redis-data" in out
    assert "ReadWriteOnce" in out
    assert "storage: 10Gi" in out
    assert "persistentVolumeClaim" in out
    assert "claimName: forgeai-redis-data" in out
    # K8S-022 : le manifeste contient désormais des emptyDir de TRAVAIL (/tmp et chemins
    # d'écriture mesurés) rendus nécessaires par readOnlyRootFilesystem. L'intention de ce
    # test — le volume de DONNÉES est un PVC, jamais un volume éphémère — est donc vérifiée
    # précisément sur ce volume, au lieu de l'absence globale du mot « emptyDir ».
    bloc_volumes = out.split("\n      volumes:", 1)[1]
    volume_data = bloc_volumes.split("- name: forgeai-redis-data", 1)[1]
    volume_data = volume_data.split("\n        - name:", 1)[0]
    assert "persistentVolumeClaim" in volume_data
    assert "emptyDir" not in volume_data


def test_pvc_avant_deployment():
    out = render_k3s(_plan_redis(), config_files=None)

    assert out.find("kind: PersistentVolumeClaim") < out.find("kind: Deployment")


def test_volumemount_conserve():
    out = render_k3s(_plan_redis(), config_files=None)

    assert "mountPath: /data" in out
    assert "- name: forgeai-redis-data" in out


def test_non_regression_configmap():
    out = render_k3s(
        _plan_litellm(),
        config_files={"litellm-config.yaml": "x: 1\n"},
    )

    assert "kind: ConfigMap" in out
    assert "kind: PersistentVolumeClaim" not in out
