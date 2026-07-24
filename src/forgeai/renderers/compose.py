"""Story P1-S06 (rendu) — DeploymentPlan → docker-compose YAML (codeur : fable).

Sans dépendance YAML : le manifeste est émis par gabarit indenté, puis validé
par `docker compose config` dans les tests et au déploiement. Aucun secret dans
le manifeste : uniquement une référence env_file ; les variables de wiring sont
injectées via le bloc `environment:` à partir du plan.
"""
from __future__ import annotations

from forgeai.core.models import DeploymentPlan


def render_compose(plan: DeploymentPlan, project: str = "forgeai-minimal") -> str:
    lines = [
        f"# Généré par ForgeAI Toolkit — plan {plan.plan_id} (profil {plan.profile})",
        f"name: {project}",
        "# réseau par défaut : chaque service est joignable par son nom",
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
        if svc.env:
            lines.append("    environment:")
            for key, value in svc.env.items():
                # Valeur toujours entre guillemets : protège les caractères YAML
                # spéciaux (:, #, espaces) ; l'interpolation ${VAR} de compose
                # opère avant le parse YAML, donc reste effective ici.
                safe = str(value).replace("\\", "\\\\").replace('"', '\\"')
                lines.append(f'      {key}: "{safe}"')
        if svc.depends:
            lines.append("    depends_on:")
            for dep in svc.depends:
                lines.append(f"      - {dep}")
        if svc.command:
            lines.append("    command:")
            for arg in svc.command:
                lines.append(f"      - \"{arg}\"")
        if svc.volumes:
            lines.append("    volumes:")
            for volume in svc.volumes:
                lines.append(f"      - {volume}")
                source = volume.split(":", 1)[0]
                # Seuls les volumes NOMMÉS se déclarent en haut ; un bind mount
                # (chemin hôte commençant par . ou /) ne se déclare jamais.
                if not source.startswith((".", "/")):
                    volumes.add(source)
        if svc.gpu:
            vendor = svc.gpu_vendor or "nvidia"
            if vendor == "amd":
                # ROCm : accès direct aux devices noyau (pas de driver compose nvidia)
                lines += ["    devices:", "      - /dev/kfd", "      - /dev/dri"]
            elif vendor == "intel":
                lines += ["    devices:", "      - /dev/dri"]
            else:  # nvidia (défaut, rétrocompatible)
                lines += [
                    "    deploy:",
                    "      resources:",
                    "        reservations:",
                    "          devices:",
                    "            - driver: nvidia",
                    "              count: 1",
                    "              capabilities: [gpu]",
                ]
        # openbao (production) : mlock -> cap_add IPC_LOCK ; healthcheck = coffre DESCELLÉ
        # (`bao status` : 0 unsealed / 2 scellé) -> support de depends_on service_healthy (S4).
        if svc.name == "openbao":
            lines += [
                "    cap_add:",
                "      - IPC_LOCK",
                "    healthcheck:",
                '      test: ["CMD", "bao", "status", "-address=http://127.0.0.1:8200"]',
                "      interval: 10s",
                "      timeout: 3s",
                "      retries: 30",
            ]
    if volumes:
        lines.append("volumes:")
        for volume in sorted(volumes):
            lines.append(f"  {volume}:")
    return "\n".join(lines) + "\n"
