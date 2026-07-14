"""Story P1-S04 — assemblage du plan de déploiement Minimal (codeur : composer/fable).

Alloue des ports hôte LIBRES (la machine peut déjà héberger d'autres stacks —
le port préféré est essayé, sinon on scanne vers le haut), instancie les services
de l'overlay curé, et fige le tout en DeploymentPlan sérialisable.
"""
from __future__ import annotations

import json
import socket
import uuid
from pathlib import Path

from forgeai.catalogue.loader import minimal_stack
from forgeai.core.models import DeploymentPlan, RenderTarget, ServiceSpec

PREFERRED_PORT_OFFSET = 10000  # 11434 → 21434 : évite les stacks existantes


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


def assemble_plan(
    profile: str,
    deploy_overlay: Path,
    target: RenderTarget = RenderTarget.COMPOSE,
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
    return DeploymentPlan(
        plan_id=f"p1-{uuid.uuid4().hex[:8]}",
        profile=profile,
        target=target,
        services=tuple(services),
        model=overlay["models"]["llm"],
        embed_model=overlay["models"]["embed"],
    )
