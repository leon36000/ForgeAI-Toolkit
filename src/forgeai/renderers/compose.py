"""Story P1-S06 (rendu) — DeploymentPlan → docker-compose YAML (codeur : fable).

Sans dépendance YAML : le manifeste est émis par gabarit indenté, puis validé
par `docker compose config` dans les tests et au déploiement. Aucun secret dans
le manifeste : uniquement une référence env_file ; les variables de wiring sont
injectées via le bloc `environment:` à partir du plan.
"""
from __future__ import annotations

from forgeai.core.models import DeploymentPlan, ProbeType
from forgeai.renderers._openbao import UNSEAL_SCRIPT


def _healthcheck_lines(svc) -> list[str]:
    """Retourne les lignes du bloc healthcheck: pour un service Docker Compose.
    Retourne une liste vide si aucune sonde exploitable n'est configurée.
    Indentation: 4 espaces pour 'healthcheck:', 6 espaces pour ses clés."""
    lines = []

    # Vérifier si une sonde est exploitable
    if svc.probe_type is ProbeType.NONE or (svc.probe_type is None and not svc.healthcheck_url):
        return []

    # Déterminer le test selon le type de sonde
    if svc.probe_type is ProbeType.EXEC:
        # Utilisation de CMD (et non CMD-SHELL) pour éviter l'injection de commande : on passe un tableau d'arguments,
        # jamais une chaîne interprétée par le shell. Le shell est dangereux car il peut exécuter des sous-commandes.
        test_entry = f'test: ["CMD", {", ".join(f'"{arg}"' for arg in svc.probe_target)}]'
    elif svc.probe_type is ProbeType.HTTP:
        # Sonde HTTP via curl : vérifie que le serveur répond avec un code 2xx/3xx.
        test_entry = f'test: ["CMD", "curl", "-fsS", "http://127.0.0.1:{int(svc.container_port)}{svc.probe_target}"]'
    elif svc.probe_type is ProbeType.TCP:
        # Sonde TCP via netcat : vérifie que le port est ouvert et accepte les connexions.
        test_entry = f'test: ["CMD", "nc", "-z", "127.0.0.1", "{int(svc.container_port)}"]'
    else:
        # Fallback : probe_type est None mais healthcheck_url est renseigné (comportement hérité).
        # On utilise l'URL telle quelle, sans reconstruction.
        test_entry = f'test: ["CMD", "curl", "-fsS", "{svc.healthcheck_url}"]'

    # Remplir les paramètres de la sonde avec conversion en entiers
    interval = int(svc.health_interval_s)
    timeout = int(svc.health_timeout_s)
    retries = int(svc.health_retries)
    start_period = interval * retries  # correspond à la fenêtre de démarrage tolérée

    lines.append("    healthcheck:")
    lines.append(f"      {test_entry}")
    lines.append(f"      interval: {interval}s")
    lines.append(f"      timeout: {timeout}s")
    lines.append(f"      retries: {retries}")
    # start_period équivaut à startupProbe Kubernetes : les échecs pendant cette période ne comptent pas comme
    # une indisponibilité, permettant au service de démarrer lentement.
    lines.append(f"      start_period: {start_period}s")

    return lines


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
        # Durcissement universel : empêche toute élévation de privilèges via setuid/sudo/cap.
        # Équivalent Compose de allowPrivilegeEscalation:false du renderer k3s
        # (voir renderers/k3s.py::_security_block). Consciemment limité à cette option car
        # cap_drop:[ALL] / read_only / user cassent certaines images à état (prouvé runtime).
        "    security_opt:",
        "      - no-new-privileges:true",
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
    # docker compose INTERPOLE $VAR / ${VAR} dans le fichier compose AVANT de le passer au conteneur :
    # chaque `$` du script shell est échappé en `$$` (compose recolle `$$` -> `$`) pour que le script
    # reçoive ses variables intactes (sinon $i, $ADDR, ${BAO_ADDR:-…} deviendraient vides). Le sidecar
    # k3s n'a PAS besoin de cet échappement (k8s ne fait qu'une expansion `$(VAR)` d'env connues).
    out += [f"        {line.replace('$', '$$')}" for line in UNSEAL_SCRIPT.strip("\n").splitlines()]
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
            # Durcissement universel : empêche toute élévation de privilèges via setuid/sudo/cap.
            # Équivalent Compose de allowPrivilegeEscalation:false du renderer k3s
            # (voir renderers/k3s.py::_security_block). Consciemment limité à cette option car
            # cap_drop:[ALL] / read_only / user cassent certaines images à état (prouvé runtime).
            "    security_opt:",
            "      - no-new-privileges:true",
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
        # HEALTH-028B : sonde fonctionnelle par service. Sans elle, un service est réputé
        # disponible dès que Compose l'a démarré — un port ouvert ne prouve pas qu'une base
        # accepte des requêtes.
        lines.extend(_healthcheck_lines(svc))
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
        # openbao (production) : healthcheck = coffre DESCELLÉ (`bao status` : 0 unsealed / 2 scellé)
        # -> support de depends_on service_healthy (S4). PAS de cap_add IPC_LOCK : l'image lance `bao`
        # en non-root sans file-cap, la capability n'entre jamais dans le set EFFECTIVE (mlock inopérant,
        # prouvé e2e S6) ; le coffre tourne avec disable_mlock (openbao.hcl) + swap-off au nœud.
        if svc.name == "openbao":
            lines += [
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
