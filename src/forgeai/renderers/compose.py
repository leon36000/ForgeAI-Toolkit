"""Story P1-S06 (rendu) — DeploymentPlan → docker-compose YAML (codeur : fable).

Sans dépendance YAML : le manifeste est émis par gabarit indenté, puis validé
par `docker compose config` dans les tests et au déploiement. Aucun secret dans
le manifeste : uniquement une référence env_file ; les variables de wiring sont
injectées via le bloc `environment:` à partir du plan.
"""
from __future__ import annotations

from forgeai.core.models import DeploymentPlan
from forgeai.renderers._openbao import UNSEAL_SCRIPT


def _openbao_unsealer_block(image: str) -> list[str]:
    """Service compose openbao-unsealer : re-descelle openbao à travers le réseau, clés en bind-mount
    hôte RO. `depends_on` openbao en condition service_STARTED (PAS service_healthy : le healthcheck
    openbao = coffre descellé, or c'est CE service qui descelle — service_healthy créerait un
    interblocage). BAO_ADDR pointe le nom réseau compose (pas localhost, conteneur séparé).
    Réutilise le MÊME script que le sidecar k3s (source unique forgeai.renderers._openbao)."""
    out = [
        "  openbao-unsealer:",
        f"    image: {image}",  # même image openbao (binaire `bao` présent)
        "    restart: unless-stopped",
        "    depends_on:",
        "      openbao:",
        "        condition: service_started",
        "    environment:",
        '      BAO_ADDR: "http://openbao:8200"',
        "    volumes:",
        # key-store hôte SÉPARÉ, LECTURE SEULE (l'item unseal_key est peuplé par le flux de
        # déploiement en S5 ; le unsealer ne voit jamais le root token).
        "      - ./openbao-keys:/keys:ro",
        "    command:",
        "      - /bin/sh",
        "      - -c",
        "      - |",
    ]
    # Corps du block scalar `|` : indenté à 8 espaces (strictement > la colonne du `-` à 6).
    out += [f"        {line}" for line in UNSEAL_SCRIPT.strip("\n").splitlines()]
    return out


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
            # Le healthcheck openbao (mode prod) ne passe QUE coffre descellé -> un consommateur
            # d'openbao doit attendre `service_healthy`. Compose interdit de mêler forme liste et
            # forme map : dès qu'openbao est une dépendance, tout le bloc passe en forme map
            # (openbao -> service_healthy ; les autres -> service_started, équivalent de la liste).
            if "openbao" in svc.depends:
                for dep in svc.depends:
                    cond = "service_healthy" if dep == "openbao" else "service_started"
                    lines.append(f"      {dep}:")
                    lines.append(f"        condition: {cond}")
            else:
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
    # openbao présent -> ajouter le service compagnon openbao-unsealer (2e "conteneur" en compose =
    # service séparé ; l'équivalent du sidecar k3s de S3). Émis APRÈS la boucle des services du plan.
    openbao_svc = next((s for s in plan.services if s.name == "openbao"), None)
    if openbao_svc is not None:
        lines += _openbao_unsealer_block(openbao_svc.image)
    if volumes:
        lines.append("volumes:")
        for volume in sorted(volumes):
            lines.append(f"  {volume}:")
    return "\n".join(lines) + "\n"
