"""Tests de non‑régression du rendu openbao production (k3s & compose)."""
from __future__ import annotations

from forgeai.core.models import DeploymentPlan, ServiceSpec
from forgeai.renderers.compose import render_compose
from forgeai.renderers.k3s import render_k3s

openbao_svc = ServiceSpec(
    name="openbao",
    image="openbao/openbao:latest",
    container_port=8200,
    host_port=8200,
    healthcheck_url="http://127.0.0.1:8200/v1/sys/health",
    volumes=[
        "forgeai-openbao-data:/openbao/data",
        "./openbao.hcl:/openbao/config/openbao.hcl:ro",
    ],
    command=["server", "-config=/openbao/config/openbao.hcl"],
    env={},
)
redis_svc = ServiceSpec(
    name="redis",
    image="redis:7-alpine",
    container_port=6379,
    host_port=6379,
    healthcheck_url="",          # pas d'URL → probe TCP
    env={},
)

plan = DeploymentPlan(
    plan_id="test-openbao",
    profile="minimal",
    target="k3s",
    services=[openbao_svc, redis_svc],
    model="qwen2.5:0.5b",
    embed_model="bge-m3",
)


class TestOpenbaoK3s:
    manifest = render_k3s(
        plan,
        config_files={"openbao.hcl": 'storage "file" {\n  path = "/openbao/data"\n}'},
    )

    def test_openbao_liveness_has_sealedcode(self):
        live = (
            "livenessProbe:\n            httpGet:\n              path: "
            "/v1/sys/health?standbyok=true&sealedcode=200&uninitcode=200"
        )
        assert live in self.manifest

    def test_openbao_readiness_is_strict(self):
        ready = "readinessProbe:\n            httpGet:\n              path: /v1/sys/health"
        assert ready in self.manifest
        # On vérifie qu'il n'y a PAS de query params sur la readiness
        assert ready + "?" not in self.manifest

    def test_openbao_has_ipc_lock(self):
        assert "IPC_LOCK" in self.manifest

    def test_openbao_configmap_mounted(self):
        assert "configMap:\n            name: openbao" in self.manifest

    def test_openbao_pvc(self):
        # Le volume `forgeai-openbao-data:/openbao/data` (2 segments) est rendu en PVC nommé.
        assert "kind: PersistentVolumeClaim" in self.manifest
        assert "name: forgeai-openbao-data" in self.manifest

    def test_openbao_command(self):
        assert "server" in self.manifest
        assert "-config=/openbao/config/openbao.hcl" in self.manifest

    def test_openbao_no_dev_root_token(self):
        assert "BAO_DEV_ROOT_TOKEN_ID" not in self.manifest

    def test_redis_probes_are_identical(self):
        idx_live = self.manifest.index("redis")
        redis_section = self.manifest[idx_live:]
        idx_liveness = redis_section.index("livenessProbe:")
        idx_readiness = redis_section.index("readinessProbe:")
        after_live = redis_section[idx_liveness:]
        after_read = redis_section[idx_readiness:]
        # Extrait les paths (tcpSocket dans le cas de redis sans healthcheck)
        # On vérifie simplement que le bloc liveness et le bloc readiness contiennent la même sonde
        liveness_socket = "tcpSocket:\n              port: 6379" in after_live
        readiness_socket = "tcpSocket:\n              port: 6379" in after_read
        assert liveness_socket and readiness_socket, "Les probes redis doivent être identiques"
        # Pas d'IPC_LOCK pour redis
        assert "IPC_LOCK" not in redis_section


class TestOpenbaoCompose:
    output = render_compose(plan)

    def test_openbao_cap_add_ipc_lock(self):
        idx = self.output.index("openbao:")
        openbao_block = self.output[idx:]
        assert "cap_add:" in openbao_block
        assert "IPC_LOCK" in openbao_block

    def test_openbao_healthcheck_bao_status(self):
        assert 'test: ["CMD", "bao", "status", "-address=http://127.0.0.1:8200"]' in self.output

    def test_openbao_bind_mount_openbao_hcl(self):
        assert "./openbao.hcl:/openbao/config/openbao.hcl:ro" in self.output

    def test_openbao_named_volume(self):
        assert "forgeai-openbao-data:" in self.output

    def test_openbao_command(self):
        expected = 'command:\n      - "server"\n      - "-config=/openbao/config/openbao.hcl"'
        assert expected in self.output

    def test_openbao_no_dev_root_token(self):
        assert "BAO_DEV_ROOT_TOKEN_ID" not in self.output

    def test_redis_no_ipc_lock_and_no_healthcheck(self):
        idx = self.output.index("redis:")
        redis_block = self.output[idx:]
        assert "IPC_LOCK" not in redis_block
        assert "healthcheck:" not in redis_block
