"""Story P1-S06 (rendu) — DeploymentPlan → docker-compose YAML (codeur : fable).

Sans dépendance YAML : le manifeste est émis par gabarit indenté, puis validé
par `docker compose config` dans les tests et au déploiement. Aucun secret dans
le manifeste : uniquement une référence env_file ; les variables de wiring sont
injectées via le bloc `environment:` à partir du plan.
"""
from __future__ import annotations

import re
import json
from urllib.parse import urlsplit

from forgeai.core.models import DeploymentPlan, ProbeType
from forgeai.i18n import t
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
        # Échappement par json.dumps : un argument contenant un guillemet double
        # corromprait le tableau YAML si on interpolait naïvement. Un contenu de
        # configuration ne doit jamais pouvoir casser le manifeste rendu.
        argv = ["CMD", *(str(a) for a in svc.probe_target)]
        test_entry = f'test: {json.dumps(argv, ensure_ascii=False)}'
    elif svc.probe_type is ProbeType.HTTP:
        # Sonde HTTP via curl : vérifie que le serveur répond avec un code 2xx/3xx.
        cible = f"http://127.0.0.1:{int(svc.container_port)}{svc.probe_target}"
        test_entry = f'test: {json.dumps(["CMD", "curl", "-fsS", cible], ensure_ascii=False)}'
    elif svc.probe_type is ProbeType.TCP:
        # Sonde TCP via netcat : vérifie que le port est ouvert et accepte les connexions.
        test_entry = f'test: {json.dumps(["CMD", "nc", "-z", "127.0.0.1", str(int(svc.container_port))], ensure_ascii=False)}'
    else:
        # Fallback : probe_type est None mais healthcheck_url est renseigné (comportement hérité).
        # `healthcheck_url` porte le port HÔTE — c'est le contrat du consommateur hôte
        # (deploy/compose.py, qui sonde depuis l'ORCHESTRATEUR après déploiement). Cette sonde
        # Docker Compose, elle, s'exécute DANS le conteneur : réutiliser l'URL telle quelle visait
        # 127.0.0.1:<port hôte> depuis l'intérieur du conteneur, jamais joignable puisque le
        # service écoute sur `container_port`. Défaut MESURÉ (text-embeddings-inference-tei et
        # -reranker) : `docker inspect` rapportait `curl: (7) Failed to connect to
        # 127.0.0.1:<port hôte>` en boucle -> conteneur `unhealthy` en permanence bien que le
        # service réponde 200 sur le port hôte depuis l'extérieur. On ne réutilise donc QUE le
        # chemin de l'URL héritée, reconstruit avec le port INTERNE (même stratégie que le repli
        # équivalent de renderers/k3s.py, qui n'a jamais cette classe de défaut car un probe K8s
        # httpGet cible toujours container_port, jamais l'URL brute).
        chemin = urlsplit(str(svc.healthcheck_url)).path or "/"
        cible = f"http://127.0.0.1:{int(svc.container_port)}{chemin}"
        test_entry = f'test: {json.dumps(["CMD", "curl", "-fsS", cible], ensure_ascii=False)}'

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


def _openbao_unsealer_block(image: str, openbao_gid: int | None = None) -> list[str]:
    """Service compose openbao-unsealer : re-descelle openbao à travers le réseau, clés en bind-mount
    hôte RO. `depends_on` openbao en condition service_STARTED (PAS service_healthy : le healthcheck
    openbao = coffre descellé, or c'est CE service qui descelle — service_healthy créerait un
    interblocage). BAO_ADDR pointe le nom réseau compose (pas localhost, conteneur séparé).
    Réutilise le MÊME script que le sidecar k3s (source unique forgeai.renderers._openbao).

    `openbao_gid` : GID du groupe dédié forgeai-openbao, résolu DYNAMIQUEMENT par l'appelant
    via resolve_openbao_gid() (source unique de décision, ADR SECRET-020A §8).
    - non-None : insère `group_add: ["<gid>"]` pour que l'unsealer non-root lise la clé 0640
      (valeur QUOTÉE : compose exige des chaînes pour les GID numériques).
    - None : aucune ligne group_add (repli 0644 sans groupe — comportement historique prouvé
      e2e S6). Cohérence OBLIGATOIRE avec le mode fichier (FileKeyStore.write) : c'est le MÊME
      gid qui pilote les deux — un 0640 sans group_add = re-unseal cassé (régression e2e S6)."""
    out = [
        "  openbao-unsealer:",
        f"    image: {image}",  # même image openbao (binaire `bao` présent)
        "    restart: unless-stopped",
    ]
    if openbao_gid is not None:
        # ADR SECRET-020A §7.1 : quand le groupe dédié existe sur l'hôte, l'unsealer doit en
        # être membre pour lire la clé 0640. Même resolve_openbao_gid() pilote le mode fichier.
        out.extend([
            "    group_add:",
            f'      - "{openbao_gid}"',
        ])
    out.extend([
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
    ])
    # Corps du block scalar `|` : indenté à 8 espaces (strictement > la colonne du `-` à 6).
    # docker compose INTERPOLE $VAR / ${VAR} dans le fichier compose AVANT de le passer au conteneur :
    # chaque `$` du script shell est échappé en `$$` (compose recolle `$$` -> `$`) pour que le script
    # reçoive ses variables intactes (sinon $i, $ADDR, ${BAO_ADDR:-…} deviendraient vides). Le sidecar
    # k3s n'a PAS besoin de cet échappement (k8s ne fait qu'une expansion `$(VAR)` d'env connues).
    out += [f"        {line.replace('$', '$$')}" for line in UNSEAL_SCRIPT.strip("\n").splitlines()]
    return out


class RienADeployerError(Exception):
    """Rendu Compose refusé : tous les services du plan sont déjà adoptés (ERR_ADOPT_RIEN_A_DEPLOYER).

    Un plan dont chaque service porte un adopted_endpoint non None décrit un état où rien n'est
    à déployer : tout est déjà présent sur le nœud. Émettre un fichier sans aucune entrée
    `services:` produit un artefact rejeté par `docker compose up`, avec un message qui ne dit
    pas la vraie cause. Ce n'est PAS une erreur de l'utilisateur, mais un état à lui signaler."""


def render_compose(plan: DeploymentPlan, project: str | None = None) -> str:
    # #586 : l'identité de projet Compose DOIT dériver de plan.plan_id — un défaut codé en
    # dur ("forgeai-minimal") faisait collisionner tous les plans entre eux (rendu) ET
    # divergeait de `_etats_docker()` qui interroge déjà `-p plan.plan_id` (health-check).
    # `project` reste surchageable explicitement (tests, cas d'usage futurs), mais son défaut
    # est maintenant l'identité canonique du plan, jamais une constante.
    if project is None:
        project = plan.plan_id
    # Rien à déployer : tous les services sont déjà présents sur le nœud. On refuse AVANT de
    # construire quoi que ce soit — un compose sans section `services` est rejeté par Docker
    # avec un message qui masque la vraie cause.
    if plan.services and all(sv.adopted_endpoint is not None for sv in plan.services):
        _adoptes = [f"{sv.name} -> {sv.adopted_endpoint}" for sv in plan.services]
        raise RienADeployerError(
            t("renderers.compose.render_compose.rien_a_deployer",
              plan_id=plan.plan_id, adoptes=', '.join(_adoptes))
        )
    lines = [
        f"# Généré par ForgeAI Toolkit — plan {plan.plan_id} (profil {plan.profile})",
        f"name: {project}",
        "# réseau par défaut : chaque service est joignable par son nom",
        "services:",
    ]
    volumes: set[str] = set()
    adopted_names: set[str] = {s.name for s in plan.services if s.adopted_endpoint is not None}
    # Recablage des deps adoptes : pour chaque service adopte, on prepare le motif qui matche
    # son nom en position d'hote (precede de `//`, `@` ou debut de valeur) suivi de :PORT.
    # Le port substitue est le port DECOUVERT (extrait de l'endpoint H:P), pas celui du
    # catalogue -- l'existant prime. Si le plan n'a aucun service adopte, cette liste reste
    # vide et la sortie est strictement identique.
    adopted_patterns: list[tuple[re.Pattern, int]] = []
    for s in plan.services:
        if s.adopted_endpoint is not None:
            # Pas de try/except ici : adopted_endpoint est validé à la construction de
            # ServiceSpec (forme hôte:port, port numérique 1..65535). Un except silencieux
            # serait un chemin mort qui, le jour où la validation changerait, avalerait le
            # défaut et laisserait le dépendant orphelin sans aucun message.
            _, port_str = s.adopted_endpoint.rsplit(':', 1)
            port = int(port_str)
            pattern = re.compile(
                r'(?:(?<=//)|(?<=@)|^)' + re.escape(s.name) + r':\d+'
            )
            adopted_patterns.append((pattern, port))
    for svc in plan.services:
        # Service adopté : déjà présent sur le nœud, on s'y branche — pas d'entrée dans services:.
        if svc.adopted_endpoint is not None:
            continue
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
                str_value = str(value)
                # Recablage : pour chaque service adopte, rediriger N:PORT vers
                # host.docker.internal:PORT_DECOUVERT. Le motif n'agit QUE quand N est
                # en position d'hote (//, @, debut) suivi de :PORT -- jamais sur une
                # sous-chaine (myN, N_backup, etc.).
                for pattern, port in adopted_patterns:
                    str_value = pattern.sub(
                        f'host.docker.internal:{port}', str_value
                    )
                # Valeur toujours entre guillemets : protège les caractères YAML
                # spéciaux (:, #, espaces) ; l'interpolation ${VAR} de compose
                # opère avant le parse YAML, donc reste effective ici.
                safe = str_value.replace("\\", "\\\\").replace('"', '\\"')
                lines.append(f'      {key}: "{safe}"')
        # HEALTH-028B : sonde fonctionnelle par service. Sans elle, un service est réputé
        # disponible dès que Compose l'a démarré — un port ouvert ne prouve pas qu'une base
        # accepte des requêtes.
        lines.extend(_healthcheck_lines(svc))
        # adopted_endpoint != None -> service non déployé par nous ; le référencer dans
        # depends_on rendrait le compose invalide. On filtre la liste, et tout service qui
        # s'y branchait reçoit extra_hosts (host.docker.internal -> host-gateway) pour
        # atteindre le service de l'hôte depuis le conteneur.
        depends_adopted = [d for d in svc.depends if d in adopted_names]
        if svc.depends:
            filtered_depends = [d for d in svc.depends if d not in adopted_names]
            if filtered_depends:
                lines.append("    depends_on:")
                # Le healthcheck openbao (mode prod) ne passe QUE coffre descellé -> un consommateur
                # d'openbao doit attendre `service_healthy`. Compose interdit de mêler forme liste et
                # forme map : dès qu'openbao est une dépendance, tout le bloc passe en forme map
                # (openbao -> service_healthy ; les autres -> service_started, équivalent de la liste).
                if "openbao" in filtered_depends:
                    for dep in filtered_depends:
                        cond = "service_healthy" if dep == "openbao" else "service_started"
                        lines.append(f"      {dep}:")
                        lines.append(f"        condition: {cond}")
                else:
                    for dep in filtered_depends:
                        lines.append(f"      - {dep}")
        if depends_adopted:
            lines += [
                "    extra_hosts:",
                '      - "host.docker.internal:host-gateway"',
            ]
        if svc.command:
            lines.append("    command:")
            for arg in svc.command:
                # Même échappement que le bloc environment: ci-dessus : un guillemet dans
                # la valeur casserait sinon le YAML généré (mesuré : ScannerError sur une
                # valeur du type 'a"b: c').
                safe_arg = str(arg).replace("\\", "\\\\").replace('"', '\\"')
                lines.append(f'      - "{safe_arg}"')
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
    # BUG (trouvé en session, jamais couvert par l'audit v7.1) : si openbao est ADOPTÉ
    # (adopted_endpoint renseigné), la boucle principale ci-dessus l'exclut déjà de `services:`
    # (même motif que `adopted_names` L162/L183/L220) — mais ce bloc-ci ne vérifiait pas
    # adopted_endpoint et émettait quand même le sidecar unsealer, dont le depends_on référence
    # un service "openbao" jamais déclaré. Preuve : `docker compose config` échoue avec
    # "service openbao-unsealer depends on undefined service openbao: invalid compose project".
    openbao_svc = next((s for s in plan.services if s.name == "openbao"), None)
    if openbao_svc is not None and openbao_svc.adopted_endpoint is None:
        # SECRET-020B : la MÊME source (resolve_openbao_gid) pilote le mode fichier de la clé
        # (FileKeyStore.write : 0640 si groupe, 0644 sinon) ET le group_add du manifeste —
        # jamais l'un sans l'autre (un 0640 sans group_add = re-unseal cassé, e2e S6).
        # Import LOCAL : renderers ne dépend pas de deploy au niveau module (pas de cycle,
        # dépendance visible au seul point d'usage).
        from forgeai.deploy.openbao_flow import resolve_openbao_gid

        lines += _openbao_unsealer_block(openbao_svc.image, openbao_gid=resolve_openbao_gid())
    if volumes:
        lines.append("volumes:")
        for volume in sorted(volumes):
            lines.append(f"  {volume}:")
    return "\n".join(lines) + "\n"
