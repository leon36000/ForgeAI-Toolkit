"""Story P1-S04 — assemblage du plan de déploiement Minimal (codeur : composer/fable).

Alloue des ports hôte LIBRES (la machine peut déjà héberger d'autres stacks —
le port préféré est essayé, sinon on scanne vers le haut), instancie les services
de l'overlay curé, et fige le tout en DeploymentPlan sérialisable.
"""
from __future__ import annotations

import dataclasses
import importlib.resources
import json
import socket
import uuid
from pathlib import Path

from forgeai.catalogue.loader import minimal_stack
from forgeai.catalogue.supply import verify_brick_before_exec, load_catalog_index
from forgeai.core.models import DeploymentPlan, RenderTarget, ServiceSpec
from forgeai.stacks import deploy_ids

PREFERRED_PORT_OFFSET = 10000  # 11434 → 21434 : évite les stacks existantes
CHASSIS_PORT_START = 8100

# Profils GPU → vendor pour la réservation (S2). cpu/inconnu → pas de vendor.
_GPU_PROFILES = {"minimal-gpu-cuda", "minimal-gpu-rocm", "minimal-gpu-intel"}
_PROFILE_VENDOR = {
    "minimal-gpu-cuda": "nvidia",
    "minimal-gpu-rocm": "amd",
    "minimal-gpu-intel": "intel",
}

# Services RAG connus : définition explicite du périmètre relocalisable par rag_node.
_RAG_SERVICES = frozenset({
    "vector-store",
    "rag",
    "rag-hardened",
    "tei-embed",
    "tei-rerank",
    "embeddings",
})


def _profile_vendor(profile: str) -> str | None:
    """Vendor GPU d'un profil de déploiement (None hors profil GPU)."""
    return _PROFILE_VENDOR.get(profile)


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


def _node_for(
    name: str,
    placement: dict[str, str] | None,
    rag_node: str | None,
) -> tuple[str | None, str | None]:
    """Détermine le nœud cible d'un service et la raison du placement."""
    if placement is not None and name in placement:
        return placement[name], "placement explicite"
    if rag_node is not None and name in _RAG_SERVICES:
        return rag_node, "service RAG relocalisé via rag_node"
    return None, None


def _attach_placement_reasons(plan: DeploymentPlan, reasons: dict[str, str]) -> None:
    """Attache le dict de traçabilité au plan, y compris quand il est vide."""
    if dataclasses.is_dataclass(plan) and plan.__dataclass_params__.frozen:
        object.__setattr__(plan, "placement_reasons", reasons)
    else:
        plan.placement_reasons = reasons  # type: ignore[attr-defined]


def assemble_plan(
    profile: str,
    deploy_overlay: Path,
    *,
    target: RenderTarget = RenderTarget.COMPOSE,
    stack: dict | None = None,
    extra_bricks: tuple[str, ...] = (),
    is_free=port_is_free,
    placement: dict[str, str] | None = None,
    rag_node: str | None = None,
) -> DeploymentPlan:
    overlay = json.loads(deploy_overlay.read_text(encoding="utf-8"))
    services = []
    placement_reasons: dict[str, str] = {}

    # Garde de chaîne d'approvisionnement (SUPPLY-018) : chaque brique doit être
    # épinglée (digest), vérifiée et licenciée AVANT tout déploiement — fail-closed.
    catalog_index = load_catalog_index()

    for svc in minimal_stack(deploy_overlay):
        verify_brick_before_exec(svc["brick_id"], svc["image"], catalog_index)
        host_port = find_free_port(svc["container_port"] + PREFERRED_PORT_OFFSET, is_free)
        svc_gpu = bool(svc.get("gpu_capable")) and profile in _GPU_PROFILES
        node, reason = _node_for(svc["name"], placement, rag_node)
        if node is not None:
            placement_reasons[svc["name"]] = reason
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
            gpu=svc_gpu,
            gpu_vendor=_profile_vendor(profile) if svc_gpu else None,
            # LAB-033N : classe de ressources déclarée dans l'overlay pour éviter
            # le défaut utilitaire (OOM du moteur LLM constaté sur le banc).
            resource_class=svc.get("resource_class", "utilitaire"),
            node=node,
        ))

    if stack is not None or extra_bricks:
        specs = _load_deploy_specs()
        existing_names = {s.name for s in services}
        used_ports = {s.host_port for s in services}
        candidats = list(deploy_ids(stack)) if stack is not None else []
        # briques cochées par l'utilisateur (P0.3b) : même mécanique, dédupliquée
        candidats += [b for b in extra_bricks if b not in candidats]
        # Ensemble FINAL des noms du plan (préexistants + briques à venir ayant
        # une spec). Filtrer les dépendances contre lui rend le résultat
        # indépendant de l'ordre de traitement des briques.
        planned_names = set(existing_names) | {b for b in candidats if b in specs}
        for brick_id in candidats:
            if brick_id in existing_names:
                continue
            spec = specs.get(brick_id)
            if spec is None:
                continue
            verify_brick_before_exec(brick_id, spec["image"], catalog_index)
            host_port = _next_chassis_port(used_ports, is_free)
            used_ports.add(host_port)
            health_path = spec.get("health_path")
            healthcheck_url = (
                f"http://127.0.0.1:{host_port}{health_path}"
                if health_path else None
            )
            # On ne conserve que les dépendances réellement présentes dans le
            # plan final (indépendant de l'ordre de traitement des briques).
            depends = tuple(d for d in spec.get("depends", []) if d in planned_names)
            brick_gpu = bool(spec.get("gpu", False))
            node, reason = _node_for(brick_id, placement, rag_node)
            if node is not None:
                placement_reasons[brick_id] = reason
            services.append(ServiceSpec(
                name=brick_id,
                image=spec["image"],
                host_port=host_port,
                container_port=spec["container_port"],
                volumes=tuple(spec.get("volumes", [])),
                env=spec.get("env", {}),
                healthcheck_url=healthcheck_url,
                depends=depends,
                command=tuple(spec.get("command", [])),
                gpu=brick_gpu,
                gpu_vendor=_profile_vendor(profile) if brick_gpu else None,
                # LAB-033N : même propagation pour les briques ajoutées au plan.
                resource_class=spec.get("resource_class", "utilitaire"),
                node=node,
            ))
            existing_names.add(brick_id)

    plan = DeploymentPlan(
        plan_id=f"p1-{uuid.uuid4().hex[:8]}",
        profile=profile,
        target=target,
        services=tuple(services),
        model=overlay["models"]["llm"],
        embed_model=overlay["models"]["embed"],
    )
    _attach_placement_reasons(plan, placement_reasons)
    return plan
