"""Story P1-S06 (rendu) — DeploymentPlan → docker-compose YAML (codeur : fable).

Sans dépendance YAML : le manifeste est émis par gabarit indenté, puis validé
par `docker compose config` dans les tests et au déploiement. Aucun secret dans
le manifeste : uniquement une référence env_file.
"""
from __future__ import annotations

from forgeai.core.models import DeploymentPlan


def render_compose(plan: DeploymentPlan, project: str = "forgeai-minimal") -> str:
    lines = [
        f"# Généré par ForgeAI Toolkit — plan {plan.plan_id} (profil {plan.profile})",
        f"name: {project}",
        "services:",
    ]
    volumes: set[str] = set()
    for svc in plan.services:
        lines += [
            f"  {svc.name}:",
            f"    image: {svc.image}",
            "    restart: unless-stopped",
            "    env_file: .env",
            "    ports:",
            f"      - \"127.0.0.1:{svc.host_port}:{svc.container_port}\"",
        ]
        if svc.volumes:
            lines.append("    volumes:")
            for volume in svc.volumes:
                lines.append(f"      - {volume}")
                volumes.add(volume.split(":", 1)[0])
        if svc.gpu:
            lines += [
                "    deploy:",
                "      resources:",
                "        reservations:",
                "          devices:",
                "            - driver: nvidia",
                "              count: 1",
                "              capabilities: [gpu]",
            ]
    if volumes:
        lines.append("volumes:")
        for volume in sorted(volumes):
            lines.append(f"  {volume}:")
    return "\n".join(lines) + "\n"
