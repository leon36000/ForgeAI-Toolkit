"""Story RC1-031 (#459) — découpage de `_deployment()` en `_volumes_et_mounts()` et
`_command_et_env_blocks()`, zéro changement de sortie.

Non-régression : chaque cas ci-dessous a été comparé BYTE-À-BYTE entre le rendu du code
d'origine (une seule fonction `_deployment()` de 248 lignes) et le rendu post-découpage —
diff vide, confirmé en session avant ce commit. Ces assertions ciblées couvrent les branches
qui traversent maintenant les deux fonctions extraites (volumes bind-mount/PVC/openbao,
GPU multi-vendor, command/env avec référence secret), pour que toute régression future
fasse rougir ce fichier plutôt qu'être découverte ailleurs.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from forgeai.core.models import ServiceSpec
from forgeai.renderers.k3s import _command_et_env_blocks, _deployment, _volumes_et_mounts


def _svc(**kw):
    d = dict(name="svc", image="img:1", host_port=8080, container_port=8080)
    d.update(kw)
    return ServiceSpec(**d)


def test_deployment_minimal_inchange():
    r = _deployment(_svc())
    assert "kind: Deployment" in r and "kind: Service" in r
    assert "image: img:1" in r


def test_deployment_volumes_bind_mount_et_pvc_et_node_fixe():
    r = _deployment(
        _svc(name="svc-b", container_port=9000, host_port=9000,
             volumes=("data-claim:/data", "./cfg.yaml:/etc/cfg.yaml:ro")),
        effective_node="node-1", node_port=30500, service_type="NodePort",
        config_files={"cfg.yaml": "key: value\n"},
    )
    assert "kind: ConfigMap" in r and "kind: PersistentVolumeClaim" in r
    assert "kubernetes.io/hostname: node-1" in r
    assert "mountPath: /etc/cfg.yaml" in r and "readOnly: true" in r
    assert "mountPath: /data" in r


def test_deployment_openbao_sidecar_et_secret_volume():
    r = _deployment(_svc(name="openbao", image="openbao/openbao:2", container_port=8200,
                          host_port=8200), service_type="ClusterIP")
    assert "openbao-keys" in r  # volume Secret des clés d'unseal
    assert "secretName: forgeai-openbao-keys" in r
    assert "defaultMode: 288" in r and "optional: true" in r


def test_deployment_gpu_nvidia_et_amd_ressources_distinctes():
    r_nvidia = _deployment(_svc(name="svc-gpu", container_port=8000, host_port=8000,
                                 gpu=True, gpu_vendor="nvidia"))
    r_amd = _deployment(_svc(name="svc-gpu-amd", container_port=8001, host_port=8001,
                              gpu=True, gpu_vendor="amd"))
    assert "nvidia.com/gpu" in r_nvidia
    assert "amd.com/gpu" in r_amd
    assert "amd.com/gpu" not in r_nvidia and "nvidia.com/gpu" not in r_amd


def test_deployment_command_et_env_avec_reference_secret():
    r = _deployment(_svc(
        name="svc-c", container_port=7000, host_port=7000,
        command=("python", "-m", "app", "--flag=a b"),
        env={"FOO": "${FORGEAI_API_KEY}", "BAR": "plain-value",
             "BAZ": "prefix-${FORGEAI_TOKEN}-suffix"},
    ), service_type="LoadBalancer")
    assert '"python"' in r and '"-m"' in r
    assert "secretKeyRef" in r and "key: FORGEAI_API_KEY" in r
    assert "value: \"plain-value\"" in r
    assert "$(FORGEAI_TOKEN)" in r  # réécriture inline, pas secretKeyRef pur


def test_deployment_service_interne_force_clusterip():
    r = _deployment(_svc(name="redis", image="redis:7", container_port=6379, host_port=6379),
                     service_type="NodePort")  # demandé NodePort, mais redis est interne
    assert "type: ClusterIP" in r


def test_volumes_et_mounts_isole_retourne_le_bon_tuple():
    """Le nouveau point d'extraction est directement appelable et documente son contrat."""
    from forgeai.renderers.k3s import _profil_securite
    svc = _svc(volumes=("data-claim:/data",))
    profil = _profil_securite(svc.name)
    volume_mount, volume_def, configmap_docs, pvc_docs = _volumes_et_mounts(
        svc, profil, gpu_actif=False, config_files=None)
    assert "mountPath: /data" in volume_mount
    assert "claimName: data-claim" in volume_def
    assert configmap_docs == []
    assert len(pvc_docs) == 1 and "kind: PersistentVolumeClaim" in pvc_docs[0]


def test_command_et_env_blocks_isole_retourne_le_bon_tuple():
    svc = _svc(command=("echo", "hi"), env={"X": "y"})
    command_block, env_block = _command_et_env_blocks(svc)
    assert '"echo"' in command_block and '"hi"' in command_block
    assert 'name: X' in env_block and 'value: "y"' in env_block
