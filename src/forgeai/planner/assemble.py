"""Story P1-S04 — assemblage du plan de déploiement Minimal (codeur : composer/fable).

Alloue des ports hôte LIBRES (la machine peut déjà héberger d'autres stacks —
le port préféré est essayé, sinon on scanne vers le haut), instancie les services
de l'overlay curé, et fige le tout en DeploymentPlan sérialisable.
"""
from __future__ import annotations

import importlib.resources
import json
import socket
import uuid
from pathlib import Path

from forgeai.catalogue.loader import minimal_stack
from forgeai.core.models import DeploymentPlan, RenderTarget, ServiceSpec
from forgeai.stacks import deploy_ids

PREFERRED_PORT_OFFSET = 10000  # 11434 → 21434 : évite les stacks existantes
CHASSIS_PORT_START = 8100


def port_is_free(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
            return True
        except OSError:
            return False


def find_free_port(preferred: int, is_free=port_is_free) -> int:
    for port in range(preferred, preferred + 200):
        if is_free(port):
            return port
    raise RuntimeError(f"Aucun port libre entre {preferred} et {preferred + 200}")


def _next_chassis_port(used_ports: set[int], is_free=port_is_free) -> int:
    """Port libre suivant à partir de CHASSIS_PORT_START, en évitant les doublons."""
    for port in range(CHASSIS_PORT_START, CHASSIS_PORT_START + 200):
        if port in used_ports:
            continue
        if is_free(port):
            return port
    raise RuntimeError(f"Aucun port libre entre {CHASSIS_PORT_START} et {CHASSIS_PORT_START + 200}")


def _load_deploy_specs() -> dict[str, dict]:
    """Registre brique→conteneur embarqué (package-data)."""
    try:
        raw = json.loads(
            (importlib.resources.files("forgeai.data") / "deploy-specs.json")
            .read_text(encoding="utf-8")
        )
    except FileNotFoundError:
        return {}
    return {k: v for k, v in raw.items() if not k.startswith("_")}


def assemble_plan(
    profile: str,
    deploy_overlay: Path,
    *,
    target: RenderTarget = RenderTarget.COMPOSE,
    stack: dict | None = None,
    extra_bricks: tuple[str, ...] = (),
    is_free=port_is_free,
) -> DeploymentPlan:
    overlay = json.loads(deploy_overlay.read_text(encoding="utf-8"))
    services = []
    for svc in minimal_stack(deploy_overlay):
        host_port = find_free_port(svc["container_port"] + PREFERRED_PORT_OFFSET, is_free)
        services.append(ServiceSpec(
            name=svc["name"],
            image=svc["image"],
            host_port=host_port,
            container_port=svc["container_port"],
            volumes=(svc["volume"],) if svc.get("volume") else (),
            healthcheck_url=(
                f"http://127.0.0.1:{host_port}{svc['healthcheck_path']}"
                if svc.get("healthcheck_path") else None
            ),
            gpu=bool(svc.get("gpu_capable")) and profile == "minimal-gpu-cuda",
        ))

    if stack is not None or extra_bricks:
        specs = _load_deploy_specs()
        existing_names = {s.name for s in services}
        used_ports = {s.host_port for s in services}
        candidats = list(deploy_ids(stack)) if stack is not None else []
        # briques cochées par l'utilisateur (P0.3b) : même mécanique, dédupliquée
        candidats += [b for b in extra_bricks if b not in candidats]
        for brick_id in candidats:
            if brick_id in existing_names:
                continue
            spec = specs.get(brick_id)
            if spec is None:
                continue
            host_port = _next_chassis_port(used_ports, is_free)
            used_ports.add(host_port)
            health_path = spec.get("health_path")
            healthcheck_url = (
                f"http://127.0.0.1:{host_port}{health_path}"
                if health_path else None
            )
            services.append(ServiceSpec(
                name=brick_id,
                image=spec["image"],
                host_port=host_port,
                container_port=spec["container_port"],
                volumes=(),
                env={},
                healthcheck_url=healthcheck_url,
                gpu=False,
            ))

    return DeploymentPlan(
        plan_id=f"p1-{uuid.uuid4().hex[:8]}",
        profile=profile,
        target=target,
        services=tuple(services),
        model=overlay["models"]["llm"],
        embed_model=overlay["models"]["embed"],
    )
