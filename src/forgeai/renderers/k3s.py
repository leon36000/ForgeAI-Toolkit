"""Story P1-S07 (rendu) — DeploymentPlan → manifestes K3s (codeur : grok/fable).

Un fichier YAML multi-documents : Namespace + (Deployment + Service) par brique.
Ports exposés en NodePort sur le port hôte alloué du plan (plage 30000-32767 de
Kubernetes : le port hôte est décalé dans la plage NodePort de façon déterministe).
"""
from __future__ import annotations

import json

import os
import re
import textwrap
from typing import NamedTuple
from urllib.parse import urlsplit

from forgeai.core.models import DeploymentPlan, ServiceSpec, NodeInventaire, valider_placement, CapaciteCluster, QuotaError, ProbeType, GPU_VENDORS_CONNUS
from forgeai.i18n import t
from forgeai.renderers._openbao import UNSEAL_SCRIPT as _UNSEAL_SCRIPT


class AdoptionNonSupporteeK3s(Exception):
    """Rendu k3s refusé pour un plan contenant un service adopté (ERR_ADOPT_K3S_NON_SUPPORTE).

    L'inventaire ne rapporte aujourd'hui que 127.0.0.1:<port> — qui désigne le pod lui-même
    depuis un pod, pas le nœud hôte. Un Endpoints vers 127.0.0.1 produirait un manifeste
    syntaxiquement VALIDE et fonctionnellement FAUX : le dépendant se connecterait à lui-même.
    À retirer quand l'inventaire rapportera une IP de nœud joignable."""

NAMESPACE = "forgeai-minimal"
_NODEPORT_SPAN = 2768  # 30000..32767
_DEFAULT_PVC_SIZE = "10Gi"
# Le renderer ne fait pas confiance à son appelant : `service_type` est restreint à ces valeurs
# (interpolé brut au manifeste ; une valeur arbitraire injecterait du YAML). Le wizard le contraint
# par argparse, mais render_k3s est une API publique -> allowlist ici (finding Sentinelle).
_SERVICE_TYPES = frozenset({"NodePort", "LoadBalancer"})
# Services internes du profil Minimal : exposés en ClusterIP, pas en NodePort/LoadBalancer.
_INTERNAL_SERVICES = frozenset({"redis", "qdrant", "vector-store", "immudb", "openbao", "postgres", "tei"})

_SECRET_NAME = "forgeai-secrets"
_SECRET_REF = re.compile(r"\$\{(FORGEAI_[A-Za-z0-9_]+)\}")

# Ressource Kubernetes déclarée par le device plugin de chaque vendor. Demander la
# ressource est la SEULE façon d'obtenir l'accès au device : monter /dev/... en hostPath
# rend le fichier visible mais le cgroup devices en refuse l'usage (mesuré, LAB-033A).
_RESSOURCE_GPU_PAR_VENDOR = {
    "nvidia": "nvidia.com/gpu",
    "amd": "amd.com/gpu",
    "intel": "gpu.intel.com/i915",
}


def _safe(value: str, field: str) -> str:
    """Refuse une valeur interpolée au YAML si elle porte un caractère de contrôle/newline
    (injection de manifeste, finding Sentinelle). Les valeurs légitimes (noms k8s RFC 1123,
    images, hostnames, chemins) n'en portent jamais ; on refuse le reste (défense en profondeur).
    Vérif par point de code (pas de regex de contrôle) pour rester lisible et sans surprise."""
    if any(ord(ch) < 0x20 or ord(ch) == 0x7f for ch in value):
        raise ValueError(t("renderers.k3s.valeur_non_sure", field=field, value_repr=repr(value)))
    return value


def node_port_for(svc: ServiceSpec, used: set[int] | None = None) -> int:
    """Mappe le port hôte vers la plage NodePort (30000-32767), sans collision :
    en cas de conflit de modulo entre services, incrémente jusqu'au port libre
    (objection majeure levée en revue de code P1, corrigée)."""
    port = 30000 + (svc.host_port % _NODEPORT_SPAN)
    if used is not None:
        if len(used) >= _NODEPORT_SPAN:  # plage saturée -> erreur bornée, jamais de boucle infinie
            raise RuntimeError(t("renderers.k3s.nodeport_sature", nodeport_span=_NODEPORT_SPAN))
        while port in used:
            port = 30000 + ((port - 30000 + 1) % _NODEPORT_SPAN)
        used.add(port)
    return port


def _service_ports(svc: ServiceSpec, service_type: str, node_port: int | None) -> str:
    """Bloc `ports:` du Service selon le type. NodePort épingle un port hôte (k3s/edge) ;
    LoadBalancer expose port/targetPort et laisse le cluster/cloud assigner l'accès externe."""
    base = f"""
    - port: {svc.container_port}
      targetPort: {svc.container_port}"""
    if service_type == "NodePort":
        port = node_port if node_port is not None else node_port_for(svc)
        return base + f"\n      nodePort: {port}"
    return base


def _resources_block(svc: ServiceSpec, vendor: str | None) -> str:
    """Bloc resources rendu DEPUIS le spec ; plus aucun magic number.
    La validation (unités, cohérence) est dans models.py, pas ici.
    Ajoute la ressource du device plugin du vendor en limite si svc.gpu est vrai.
    """
    res = svc.ressources_effectives
    req = res["requests"]
    lim = res["limits"]

    # Indentation existante : chaque ligne est précédée de retours à la ligne et d'espaces
    block = "\n          resources:"
    block += "\n            requests:"
    block += f'\n              cpu: "{req["cpu"]}"'
    block += f'\n              memory: "{req["memory"]}"'
    block += "\n            limits:"
    block += f'\n              cpu: "{lim["cpu"]}"'
    block += f'\n              memory: "{lim["memory"]}"'

    # Accélérateurs orthogonaux : jamais dans les classes CPU/mémoire.
    # `vendor` est calculé par l'appelant : (svc.gpu_vendor or "nvidia") si svc.gpu, sinon None.
    if vendor is not None:
        ressource = _RESSOURCE_GPU_PAR_VENDOR.get(vendor)
        if ressource is not None:
            block += f'\n              {ressource}: "1"'

    return block


class ProfilSecurite(NamedTuple):
    """Profil de sécurité mesuré sur k3s v1.35.5 pour un service donné."""
    uid: int
    ro_rootfs: bool = True
    chemins_inscriptibles: tuple[str, ...] = ()
    preuve: str = ""


_PROFILS_SECURITE: dict[str, ProfilSecurite] = {
    "redis": ProfilSecurite(
        uid=999,
        preuve="redis:7-alpine READY en restricted complet ; en root + drop ALL : FAILED « chown: . : Operation not permitted »",
    ),
    "litellm": ProfilSecurite(
        uid=1000,
        preuve="ghcr.io/berriai/litellm:main-stable READY en restricted complet",
    ),
    "qdrant": ProfilSecurite(
        uid=1000,
        chemins_inscriptibles=("/qdrant/storage", "/qdrant/snapshots"),
        preuve="qdrant/qdrant:v1.12.5 : panic « Can't create Snapshots directory: PermissionDenied » "
               "sans /qdrant/snapshots ; et « Service internal error: Read-only file system (os error 30) » "
               "sans /qdrant/storage lorsque AUCUN volume de données n'est déclaré (mesuré e2e K8S-024). "
               "Si un PVC est monté sur ce chemin, l'emptyDir est écarté (garde anti-doublon de montage).",
    ),
    "postgres": ProfilSecurite(
        uid=999,
        chemins_inscriptibles=("/var/run/postgresql",),
        preuve="postgres:18.3-alpine : échec sans ce volume ; READY avec",
    ),
    "immudb": ProfilSecurite(
        uid=3322,
        preuve="codenotary/immudb:1.11.1 READY en restricted complet",
    ),
    "openbao": ProfilSecurite(
        uid=100,
        preuve="openbao/openbao:2.6.0 (USER nommé « openbao » = uid 100) : écriture de /openbao/file OK en restricted complet",
    ),
    "langfuse": ProfilSecurite(
        uid=1000,
        preuve="langfuse/langfuse:3 : écriture OK en restricted complet",
    ),
    "text-embeddings-inference-tei": ProfilSecurite(
        uid=1000,
        preuve="ghcr.io/huggingface/text-embeddings-inference:cpu-1.5 : écriture de /data OK en restricted complet",
    ),
    "ollama": ProfilSecurite(
        uid=1000,
        ro_rootfs=False,
        preuve="ollama/ollama:latest : « mkdir /home/ubuntu/.ollama: read-only file system » avec readOnlyRootFilesystem ; READY sans. Le HOME dépend de la distribution de base de l'image, inconnu au moment du rendu",
    ),
}

_PROFILS_SECURITE["vector-store"] = _PROFILS_SECURITE["qdrant"]
_PROFILS_SECURITE["text-embeddings-inference-reranker"] = _PROFILS_SECURITE["text-embeddings-inference-tei"]
_PROFILS_SECURITE["tei"] = _PROFILS_SECURITE["text-embeddings-inference-tei"]

_PROFIL_DEFAUT = ProfilSecurite(uid=1000, preuve="défaut pour service non mesuré")
_UID_MINIMAL_NON_ROOT = 1


def _profil_securite(nom: str) -> ProfilSecurite:
    """Retourne le profil mesuré d'un service, ou le profil par défaut."""
    profil = _PROFILS_SECURITE.get(nom, _PROFIL_DEFAUT)
    if profil.uid < _UID_MINIMAL_NON_ROOT:
        raise ValueError(t("renderers.k3s.profil_securite_uid",
                            nom_repr=repr(nom), profil_uid=profil.uid,
                            uid_minimal=_UID_MINIMAL_NON_ROOT))
    return profil


def _pod_security_block(profil: ProfilSecurite, gpu: bool) -> str:
    """Bloc securityContext au niveau pod ; dérogation GPU documentée."""
    if gpu:
        return (
            "\n      securityContext:"
            "\n        # forgeai: pod GPU — l'accès au device se fait par ressource de"
            "\n        # forgeai: device plugin du vendor. Le durcissement (non-root, racine"
            "\n        # forgeai: en lecture seule) n'a pas été mesuré par vendor ; reporté à"
            "\n        # forgeai: une story de durcissement dédiée."
            "\n        seccompProfile:"
            "\n          type: RuntimeDefault"
        )
    return (
        "\n      securityContext:"
        "\n        runAsNonRoot: true"
        f"\n        runAsUser: {profil.uid}"
        f"\n        runAsGroup: {profil.uid}"
        f"\n        fsGroup: {profil.uid}"
        "\n        seccompProfile:"
        "\n          type: RuntimeDefault"
    )


def _security_block(profil: ProfilSecurite, gpu: bool) -> str:
    """Bloc securityContext au niveau conteneur.

    `gpu` désactive AUSSI readOnlyRootFilesystem, et pas seulement l'identité non-root :
    les conteneurs GPU tournent actuellement sous une identité root et une racine
    inscriptible. Le durcissement (non-root, readOnlyRootFilesystem) n'a pas été mesuré
    par vendor après le passage au device plugin (LAB-033A) : il est reporté à une
    story de durcissement dédiée. Les trois contrôles mesurables restent émis
    (drop:[ALL], allowPrivilegeEscalation:false, seccomp).
    readOnlyRootFilesystem n'est pas une exigence du profil PSS restricted : le pod GPU ne
    déroge à restricted que par son identité root, pas par ce champ.
    """
    ro = profil.ro_rootfs and not gpu
    lines = ["\n          securityContext:"]
    if gpu:
        lines.extend([
            "\n            # forgeai: pod GPU — l'accès au device se fait par ressource de",
            "\n            # forgeai: device plugin du vendor. Le durcissement (non-root, racine",
            "\n            # forgeai: en lecture seule) n'a pas été mesuré par vendor ; reporté à",
            "\n            # forgeai: une story de durcissement dédiée.",
        ])
    lines.extend([
        "\n            allowPrivilegeEscalation: false",
        "\n            capabilities:",
        "\n              drop:",
        "\n                - ALL",
        f"\n            readOnlyRootFilesystem: {'true' if ro else 'false'}",
        "\n            seccompProfile:",
        "\n              type: RuntimeDefault",
    ])
    return "".join(lines)


def _volumes_inscriptibles(profil: ProfilSecurite, gpu: bool) -> list[tuple[str, str]]:
    """Liste les emptyDir nécessaires quand la racine est en lecture seule."""
    ro = profil.ro_rootfs and not gpu
    if not ro:
        return []
    chemins = ["/tmp"] + list(profil.chemins_inscriptibles)

    def _nom(chemin: str) -> str:
        return "inscriptible-" + chemin.lstrip("/").replace("/", "-").lower()

    return [(_nom(c), c) for c in chemins]


_PROFIL_SIDECAR_OPENBAO = ProfilSecurite(
    uid=100, ro_rootfs=False,
    preuve="side-car d'unseal : `bao operator unseal` peut écrire un fichier de jeton dans "
           "$HOME ; comportement NON mesuré en racine lecture seule -> readOnlyRootFilesystem "
           "non activé. Le reste du profil restricted (drop ALL, seccomp, no-escalation) est conservé.",
)


def _probes_block(svc) -> str:
    """Génère le bloc YAML des trois sondes K3s (startup/readiness/liveness).

    Les trois sondes ont des rôles distincts :
    - startupProbe : protège un démarrage LENT (échecs tolérés longtemps).
    - readinessProbe : retire le pod du Service quand il ne peut pas répondre,
      SANS le tuer.
    - livenessProbe : redémarre le conteneur quand il est réellement bloqué.

    startupProbe.failureThreshold est strictement supérieur à celui de
    livenessProbe : c'est précisément ce qui distingue un démarrage lent d'une
    panne. Si l'on inversait les valeurs, un service qui démarre simplement
    lentement serait tué en boucle par la livenessProbe (faux positif de panne).

    Retourne une chaîne VIDE si aucune sonde n'est exploitable.
    """
    # Pas de sonde exploitable -> bloc vide (le manifeste reste valide).
    if svc.probe_type == ProbeType.NONE:
        return ""

    port = svc.container_port
    health_url = getattr(svc, "healthcheck_url", None) or ""

    # Les trois sondes partagent en général le MÊME handler ; openbao est la seule
    # exception, et elle est indispensable (voir ci-dessous).
    if svc.name == "openbao" and health_url:
        # openbao démarre SCELLÉ en production : /v1/sys/health renvoie 503 (scellé)
        # ou 501 (non initialisé) tant qu'un opérateur ne l'a pas descellé.
        # Une liveness stricte tuerait donc le conteneur EN BOUCLE avant même que
        # l'unseal soit possible — le coffre de secrets ne démarrerait jamais.
        # D'où : liveness et startup TOLÉRANTES (le processus vit même scellé),
        # readiness STRICTE (les consommateurs attendent réellement le descellement).
        # Choix délibéré : ne pas supprimer cette branche par simplification.
        chemin_base = _safe(urlsplit(health_url).path or "/", "healthcheck-path")
        chemin_tolerant = _safe(
            f"{chemin_base}?standbyok=true&sealedcode=200&uninitcode=200", "liveness-path")
        handler_liveness = (f"httpGet:\n              path: {json.dumps(chemin_tolerant, ensure_ascii=False)}"
                            f"\n              port: {port}")
        handler_startup = handler_liveness
        handler_readiness = (f"httpGet:\n              path: {json.dumps(chemin_base, ensure_ascii=False)}"
                             f"\n              port: {port}")
    elif svc.probe_type == ProbeType.HTTP:
        path = svc.probe_target if svc.probe_target is not None else "/"
        # Même classe de défaut que les arguments EXEC : un chemin contenant `: `, `#` ou `*`
        # serait réinterprété par le parseur YAML et la sonde viserait une autre URL.
        handler_liveness = (
            f"httpGet:\n              path: {json.dumps(str(path), ensure_ascii=False)}"
            f"\n              port: {port}")
        handler_startup = handler_readiness = handler_liveness
    elif svc.probe_type == ProbeType.TCP:
        handler_liveness = f"tcpSocket:\n              port: {port}"
        handler_startup = handler_readiness = handler_liveness
    elif svc.probe_type == ProbeType.EXEC:
        # Exec : argv listé ligne par ligne, JAMAIS via une chaîne shell.
        argv = svc.probe_target or ()
        # Échappement par json.dumps, comme dans le renderer Compose : un argument contenant
        # `: `, `#`, `*`, `[` ou `{` serait sinon RÉINTERPRÉTÉ par le parseur YAML — mesuré :
        # "a: b" devient un dictionnaire, " #c" devient None, "*ref" corrompt le document.
        # La sonde exécuterait alors autre chose que demandé, SANS erreur. Une altération
        # silencieuse est pire qu'un échec bruyant.
        cmd_lines = "\n".join(
            f"              - {json.dumps(str(arg), ensure_ascii=False)}" for arg in argv)
        handler_liveness = f"exec:\n              command:\n{cmd_lines}"
        handler_startup = handler_readiness = handler_liveness
    elif health_url:
        # Dérivation depuis healthcheck_url, traitée comme du HTTP.
        path = _safe(urlsplit(health_url).path or "/", "healthcheck-path")
        # Dérivation depuis healthcheck_url : MÊME échappement que les autres branches.
        handler_liveness = (f"httpGet:\n              path: {json.dumps(str(path), ensure_ascii=False)}"
                            f"\n              port: {port}")
        handler_startup = handler_readiness = handler_liveness
    else:
        # REPLI HISTORIQUE — sans lui, un service comme redis n'aurait AUCUNE sonde et
        # Kubernetes ne pourrait plus détecter qu'il est bloqué : il ne le redémarrerait
        # jamais. Seul `ProbeType.NONE` explicite (traité plus haut) supprime les sondes.
        handler_liveness = f"tcpSocket:\n              port: {port}"
        handler_startup = handler_readiness = handler_liveness

    # Conversion en entiers : le YAML K3s exige des entiers pour ces champs,
    # et les valeurs du modèle peuvent être des flottants.
    interval = int(svc.health_interval_s)
    timeout = int(svc.health_timeout_s)
    liveness_failure_threshold = 3
    # startupProbe DOIT tolérer plus d'échecs que la livenessProbe : sinon un
    # démarrage lent tue le conteneur (faux positif de panne).
    startup_failure_threshold = max(int(svc.health_retries), liveness_failure_threshold + 1)

    return (
        f"\n          startupProbe:\n            {handler_startup}"
        f"\n            periodSeconds: {interval}"
        f"\n            timeoutSeconds: {timeout}"
        f"\n            failureThreshold: {startup_failure_threshold}"
        f"\n          readinessProbe:\n            {handler_readiness}"
        f"\n            periodSeconds: {interval}"
        f"\n            timeoutSeconds: {timeout}"
        f"\n            failureThreshold: {liveness_failure_threshold}"
        f"\n          livenessProbe:\n            {handler_liveness}"
        f"\n            periodSeconds: {interval}"
        f"\n            timeoutSeconds: {timeout}"
        f"\n            failureThreshold: {liveness_failure_threshold}"
        f"\n            initialDelaySeconds: 0"
    )

def _openbao_sidecar_block(image: str) -> str:
    """2e conteneur du POD openbao : re-descelle le coffre depuis la clé montée (Secret RO).
    Même image openbao (binaire `bao`) ; ne monte QUE `openbao-keys` (jamais les données ni
    le root). Item de `containers:` (indent 8). _UNSEAL_SCRIPT injecté dans
    un block scalar YAML `|` (indent 14 espaces)."""
    script = textwrap.indent(_UNSEAL_SCRIPT, " " * 14).rstrip("\n")
    return (
        "\n        - name: openbao-unsealer"
        f"\n          image: {_safe(image, 'image')}"
        "\n          command:"
        "\n            - /bin/sh"
        "\n            - -c"
        "\n            - |"
        f"\n{script}"
        "\n          volumeMounts:"
        "\n            - name: openbao-keys"
        "\n              mountPath: /keys"
        "\n              readOnly: true"
        + _security_block(_PROFIL_SIDECAR_OPENBAO, gpu=False)
    )


def _deployment(svc: ServiceSpec, effective_node: str | None = None,
                node_port: int | None = None, service_type: str = "NodePort",
                config_files: dict[str, str] | None = None) -> str:
    name = _safe(svc.name, "name")
    image = _safe(svc.image, "image")

    # Vérification explicite du vendor GPU avant tout rendu du bloc GPU. Défense en
    # profondeur : `ServiceSpec.__post_init__` (core/models.py, BUG-servicespec-validation)
    # refuse déjà tout gpu_vendor hors GPU_VENDORS_CONNUS dès la construction, donc cette
    # branche est normalement inatteignable — conservée pour ne pas dépendre implicitement
    # de l'invariant amont si un ServiceSpec venait à être construit autrement.
    if svc.gpu and svc.gpu_vendor is not None and svc.gpu_vendor not in GPU_VENDORS_CONNUS:
        raise ValueError(t("renderers.k3s.vendor_gpu_non_supporte", gpu_vendor=svc.gpu_vendor))
    # GPU par vendor : chaque vendor reçoit sa ressource de device plugin
    # (LAB-033A). Le passthrough hostPath est supprimé car le cgroup devices
    # refuse l'accès aux char devices montés en hostPath.
    vendor = (svc.gpu_vendor or "nvidia") if svc.gpu else None

    # K8S-022 : profil PSS restricted par service (uid mesuré) ; `svc.gpu` = seule dérogation.
    profil = _profil_securite(svc.name)
    gpu_actif = bool(svc.gpu)
    resources_block = _resources_block(svc, vendor)
    security_block = _security_block(profil, gpu_actif)
    probes_block = _probes_block(svc)
    node_selector = ""
    if effective_node and effective_node != "auto":
        node_selector = f"""
      nodeSelector:
        kubernetes.io/hostname: {_safe(effective_node, 'node')}"""
    effective_type = "ClusterIP" if svc.name in _INTERNAL_SERVICES else service_type
    # Fusion volume data + fichiers config (ConfigMap) en UN bloc volumeMounts
    # et UN bloc volumes (sinon clé YAML dupliquée).
    # mounts: (name, mountPath, subPath|None, readOnly)
    # vols:   (name, payload, kind) avec kind dans {"pvc", "configMap", "emptyDir", "secret"}
    mounts, vols, configmap_docs, pvc_docs = [], [], [], []
    for volume in svc.volumes:
        segs = volume.split(":")
        if len(segs) == 3 and segs[0].startswith(("./", "/")):
            source, target, mode = segs[0], segs[1], segs[2]
            source = _safe(source, "config-source")
            target = _safe(target, "config-target")
            mode = _safe(mode, "config-mode")
            basename = os.path.basename(source)
            if config_files is None or basename not in config_files:
                raise ValueError(t("renderers.k3s.bind_mount_non_fourni",
                                    source_repr=repr(source)))
            cm_name = basename.rsplit(".", 1)[0].lower().replace(".", "-")
            content = config_files[basename]
            indented = textwrap.indent(content, "    ")
            if not indented.endswith("\n"):
                indented += "\n"
            configmap_docs.append(
                f"---\n"
                f"apiVersion: v1\n"
                f"kind: ConfigMap\n"
                f"metadata:\n"
                f"  name: {cm_name}\n"
                f"  namespace: {NAMESPACE}\n"
                f"data:\n"
                f"  {basename}: |\n"
                f"{indented}"
            )
            mounts.append((cm_name, target, basename, mode == "ro"))
            vols.append((cm_name, cm_name, "configMap"))
        elif len(segs) == 2:
            claim, mount_path = _safe(segs[0], "volume-claim"), _safe(segs[1], "volume-path")
            mounts.append((claim, mount_path, None, False))
            vols.append((claim, None, "pvc"))
            pvc_docs.append(
                f"---\n"
                f"apiVersion: v1\n"
                f"kind: PersistentVolumeClaim\n"
                f"metadata:\n"
                f"  name: {claim}\n"
                f"  namespace: {NAMESPACE}\n"
                f"spec:\n"
                f"  accessModes:\n"
                f"    - ReadWriteOnce\n"
                f"  resources:\n"
                f"    requests:\n"
                f"      storage: {_DEFAULT_PVC_SIZE}\n"
            )
        else:
            raise ValueError(t("renderers.k3s.volume_mal_forme", volume_repr=repr(volume)))
    # K8S-022 : readOnlyRootFilesystem impose des emptyDir explicites pour les chemins que le
    # service écrit hors de ses volumes de données (chemins MESURÉS, cf. _PROFILS_SECURITE).
    # Un chemin déjà monté (PVC, ConfigMap…) n'est jamais monté deux fois : mountPath dupliqué
    # = spec de pod invalide.
    deja_montes = {chemin for _, chemin, _, _ in mounts}
    for nom_volume, chemin in _volumes_inscriptibles(profil, gpu_actif):
        if chemin in deja_montes:
            continue
        deja_montes.add(chemin)
        mounts.append((nom_volume, chemin, None, False))
        vols.append((nom_volume, None, "emptyDir"))
    # openbao : volume Secret des clés d'unseal — ajouté aux `vols` du POD (donc au bloc volumes:)
    # MAIS PAS aux `mounts` (le conteneur principal ne monte JAMAIS les clés ; seul le sidecar
    # de re-unseal les monte, cf. _openbao_sidecar_block).
    if svc.name == "openbao":
        vols.append(("openbao-keys", "forgeai-openbao-keys", "secret"))
    volume_mount = ""
    if mounts:
        items = ""
        for claim, mount_path, sub_path, read_only in mounts:
            items += f"\n            - name: {claim}\n              mountPath: {mount_path}"
            if sub_path:
                items += f"\n              subPath: {sub_path}"
            if read_only:
                items += "\n              readOnly: true"
        volume_mount = f"\n          volumeMounts:{items}"
    volume_def = ""
    if vols:
        items = ""
        for claim, payload, kind in vols:
            if kind == "pvc":
                items += (f"\n        - name: {claim}"
                          f"\n          persistentVolumeClaim:"
                          f"\n            claimName: {claim}")
            elif kind == "emptyDir":
                items += (f"\n        - name: {claim}"
                          f"\n          emptyDir: {{}}")
            elif kind == "configMap":
                items += (f"\n        - name: {claim}"
                          f"\n          configMap:\n            name: {payload}")
            elif kind == "secret":
                # openbao : Secret des clés d'unseal ; `optional: true` -> le POD démarre même si le
                # Secret pas encore peuplé (le flux de déploiement le pré-crée, S5). `items`
                # -> seul unseal_key est exposé au sidecar (jamais le root token).
                items += (f"\n        - name: {claim}"
                          f"\n          secret:"  # proof:allow — kind de volume k8s (pas un secret en dur)
                          f"\n            secretName: {payload}"
                          # defaultMode 0o440 (= 288 décimal, k8s exige le décimal) : lecture
                          # owner+groupe seulement — équivalent k3s du 0640+groupe hôte côté
                          # compose (ADR SECRET-020A §7.4, story SECRET-020B).
                          f"\n            defaultMode: 288"
                          f"\n            optional: true"
                          f"\n            items:"
                          f"\n              - key: unseal_key"
                          f"\n                path: unseal_key")
        volume_def = f"\n      volumes:{items}"
    # command → args k8s (parité avec le renderer compose) ; chaque arg passé par _safe (injection).
    command_block = ""
    if svc.command:
        # Échappement par json.dumps (même motif que _probes_block/EXEC ci-dessus) : un
        # guillemet dans la valeur casserait sinon le YAML généré — _safe() ne rejette que
        # les caractères de contrôle, jamais un guillemet (mesuré : ScannerError sur une
        # valeur du type 'a"b: c').
        items = "".join(
            f"\n            - {json.dumps(_safe(str(a), 'arg'), ensure_ascii=False)}"
            for a in svc.command
        )
        command_block = f"\n          args:{items}"
    # env → bloc env k8s (parité compose) ; ${FORGEAI_*} devient secretKeyRef ou $(VAR).
    env_block = ""
    if svc.env:
        items = ""
        # 1. clés auxiliaires pour références embarquées, dans l'ordre d'apparition, sans doublon
        aux_keys: list[str] = []
        seen_aux: set[str] = set()
        for _, v in svc.env.items():
            val = str(v).strip()
            if _SECRET_REF.fullmatch(val):
                continue
            for m in _SECRET_REF.finditer(val):
                key = m.group(1)
                if key not in seen_aux:
                    seen_aux.add(key)
                    aux_keys.append(key)
        # 2. variables auxiliaires émises en premier
        for key in aux_keys:
            items += (
                f"\n            - name: {_safe(key, 'env-key')}"
                f"\n              valueFrom:"
                f"\n                secretKeyRef:"
                f"\n                  name: {_safe(_SECRET_NAME, 'secret-name')}"
                f"\n                  key: {_safe(key, 'secret-key')}"
            )
        # 3. variables réelles
        for k, v in svc.env.items():
            val = str(v).strip()
            m = _SECRET_REF.fullmatch(val)
            if m:
                key = m.group(1)
                items += (
                    f"\n            - name: {_safe(str(k), 'env-key')}"
                    f"\n              valueFrom:"
                    f"\n                secretKeyRef:"
                    f"\n                  name: {_safe(_SECRET_NAME, 'secret-name')}"
                    f"\n                  key: {_safe(key, 'secret-key')}"
                )
            elif _SECRET_REF.search(val):
                rewritten = _SECRET_REF.sub(lambda match: f"$({match.group(1)})", str(v))
                # Échappement par json.dumps — même motif que command_block/_probes_block :
                # un guillemet dans la valeur casserait sinon le YAML généré.
                items += (
                    f"\n            - name: {_safe(str(k), 'env-key')}"
                    f"\n              value: {json.dumps(_safe(rewritten, 'env-val'), ensure_ascii=False)}"
                )
            else:
                items += (
                    f"\n            - name: {_safe(str(k), 'env-key')}"
                    f"\n              value: {json.dumps(_safe(str(v), 'env-val'), ensure_ascii=False)}"
                )
        env_block = f"\n          env:{items}"
    # openbao : le sidecar s'insère ENTRE le conteneur principal (volume_mount, indent 10)
    # et le bloc `volumes:` du POD (volume_def, indent 6) — sinon le 2e conteneur tomberait après
    # `volumes:` = YAML invalide.
    sidecar_block = _openbao_sidecar_block(image) if svc.name == "openbao" else ""
    container_extra = (command_block + env_block + resources_block + security_block
                       + probes_block + volume_mount + sidecar_block + volume_def)
    sa_block = ("\n      serviceAccountName: forgeai-sa"
                "\n      automountServiceAccountToken: false"
                + _pod_security_block(profil, gpu_actif))
    return "".join(configmap_docs) + "".join(pvc_docs) + f"""---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {name}
  namespace: {NAMESPACE}
spec:
  replicas: 1
  selector:
    matchLabels: {{app: {name}}}
  template:
    metadata:
      labels: {{app: {name}}}
    spec:{node_selector}{sa_block}
      containers:
        - name: {name}
          image: {image}
          ports:
            - containerPort: {svc.container_port}{container_extra}
---
apiVersion: v1
kind: Service
metadata:
  name: {name}
  namespace: {NAMESPACE}
spec:
  type: {effective_type}
  selector: {{app: {name}}}
  ports:{_service_ports(svc, effective_type, node_port)}
"""


_PSA_VERSION = "v1.25"


def _namespace_block(plan: DeploymentPlan) -> str:
    """Émet le Namespace avec les étiquettes Pod Security Admission.

    Sans ces étiquettes, le durcissement des pods reste purement déclaratif :
    le cluster n'applique aucune politique de sécurité aux pods déployés.
    """
    # forgeai (LAB-033A) : un plan GPU n'émet plus aucun volume hostPath (accès par ressource de
    # device plugin). K8S-024 avait mesuré que baseline refusait le pod GPU À CAUSE de ces
    # hostPath ; ils ont disparu, et baseline l'ACCEPTE désormais (mesuré sur k3s v1.35.5).
    # restricted reste hors d'atteinte tant que le pod GPU garde l'identité root
    # (restricted exige runAsNonRoot: true) — durcissement reporté à une story dédiée.
    enforce = "baseline" if any(svc.gpu for svc in plan.services) else "restricted"

    comments = ""
    if enforce == "baseline":
        comments = (
            "# forgeai: (LAB-033A) le niveau enforce est abaissé à baseline car le plan "
            "demande un service GPU. L'accès au device se fait par ressource de device plugin ; "
            "aucun volume hostPath n'est émis. restricted reste hors d'atteinte tant que le pod "
            "GPU garde l'identité root (runAsNonRoot: true requis par restricted).\n"
            "# forgeai: audit et warn restent à restricted pour signaler l'écart d'identité.\n"
        )

    return (
        "apiVersion: v1\n"
        "kind: Namespace\n"
        f"{comments}"
        "metadata:\n"
        f"  name: {NAMESPACE}\n"
        "  labels:\n"
        f"    pod-security.kubernetes.io/enforce: {enforce}\n"
        f"    pod-security.kubernetes.io/enforce-version: {_PSA_VERSION}\n"
        "    pod-security.kubernetes.io/audit: restricted\n"
        f"    pod-security.kubernetes.io/audit-version: {_PSA_VERSION}\n"
        "    pod-security.kubernetes.io/warn: restricted\n"
        f"    pod-security.kubernetes.io/warn-version: {_PSA_VERSION}\n"
    )


def _network_policies(plan: DeploymentPlan) -> str:
    """Construit les NetworkPolicies du profil Minimal.

    POURQUOI : refus par défaut sur Ingress ET Egress (sinon un pod compromis exfiltre, et tout
    pod du namespace peut en joindre n'importe quel autre), puis ouverture EXCLUSIVEMENT des
    flux qu'une dépendance déclarée du plan justifie, plus DNS vers kube-system pour ne pas
    casser la résolution de noms sans rouvrir l'Internet en 0.0.0.0/0.
    """
    parts: list[str] = []

    # 1) Refus par défaut : on déclare Ingress+Egress et on n'émet ni règle ingress ni règle
    # egress -> Kube interprète « tout refuser ». Ne pas écrire `ingress: []` (règle vide).
    parts.append("---\n")
    parts.append("apiVersion: networking.k8s.io/v1\n")
    parts.append("kind: NetworkPolicy\n")
    parts.append("metadata:\n")
    parts.append("  name: forgeai-default-deny\n")
    parts.append(f"  namespace: {NAMESPACE}\n")
    parts.append("spec:\n")
    parts.append("  podSelector: {}\n")
    parts.append("  policyTypes:\n")
    parts.append("    - Ingress\n")
    parts.append("    - Egress\n")

    # 2) DNS : on rouvre UNIQUEMENT UDP/53 et TCP/53 vers kube-system.
    # Aucun ipBlock : sans cela, kube-proxy/CoreDNS joignables et Internet toujours bloqué.
    parts.append("---\n")
    parts.append("apiVersion: networking.k8s.io/v1\n")
    parts.append("kind: NetworkPolicy\n")
    parts.append("metadata:\n")
    parts.append("  name: forgeai-allow-dns\n")
    parts.append(f"  namespace: {NAMESPACE}\n")
    parts.append("spec:\n")
    parts.append("  podSelector: {}\n")
    parts.append("  policyTypes:\n")
    parts.append("    - Egress\n")
    parts.append("  egress:\n")
    parts.append("    - to:\n")
    parts.append("        - namespaceSelector:\n")
    parts.append("            matchLabels:\n")
    parts.append("              kubernetes.io/metadata.name: kube-system\n")
    parts.append("      ports:\n")
    parts.append("        - protocol: UDP\n")
    parts.append("          port: 53\n")
    parts.append("        - protocol: TCP\n")
    parts.append("          port: 53\n")

    # 3) Une politique par service CIBLE d'au moins une dépendance.
    # Indexation par nom pour O(1) et conservation de l'ordre d'apparition du plan.
    by_name: dict[str, ServiceSpec] = {svc.name: svc for svc in plan.services}
    seen_targets: dict[str, list[str]] = {}  # cible -> dépendants (ordre du plan, sans doublon)

    for dependant in plan.services:
        for dep_name in dependant.depends:
            cible = by_name.get(dep_name)
            # Dépendance pointant un service absent du plan : ignorée silencieusement.
            # Le plan peut référencer une brique non déployée ; on n'ouvre pas de flux.
            if cible is None:
                continue
            if cible.name not in seen_targets:
                seen_targets[cible.name] = []
            if dependant.name not in seen_targets[cible.name]:
                seen_targets[cible.name].append(dependant.name)

    # Ordre déterministe : ordre d'apparition des cibles dans plan.services.
    for svc in plan.services:
        dependants = seen_targets.get(svc.name)
        if not dependants:
            continue  # Contrôle négatif : personne ne dépend -> aucune politique, aucun flux.

        target_name = _safe(svc.name, "service.name")
        parts.append("---\n")
        parts.append("apiVersion: networking.k8s.io/v1\n")
        parts.append("kind: NetworkPolicy\n")
        parts.append("metadata:\n")
        parts.append(f"  name: forgeai-allow-{target_name}\n")
        parts.append(f"  namespace: {NAMESPACE}\n")
        parts.append("spec:\n")
        parts.append("  podSelector:\n")
        parts.append("    matchLabels:\n")
        parts.append(f"      app: {target_name}\n")
        parts.append("  policyTypes:\n")
        parts.append("    - Ingress\n")
        parts.append("  ingress:\n")
        parts.append("    - from:\n")
        for dep in dependants:
            dep_name = _safe(dep, "dependant.name")
            parts.append("        - podSelector:\n")
            parts.append("            matchLabels:\n")
            parts.append(f"              app: {dep_name}\n")
        parts.append("      ports:\n")
        parts.append("        - protocol: TCP\n")
        parts.append(f"          port: {svc.container_port}\n")

    # 4) Politiques d'egress symétriques : Kubernetes exige que la source autorise l'egress
    # ET la destination l'ingress pour qu'un flux passe. Mesuré sur cluster k3s réel : sans cette
    # politique, `litellm -> redis:6379` reste bloqué même si `forgeai-allow-redis` ouvre l'ingress.
    for dep_svc in plan.services:
        # Collecter les cibles (dans l'ordre du plan, sans doublon) dont dep_svc dépend effectivement
        cibles: list[str] = []
        for dep_name in dep_svc.depends:
            cible_svc = by_name.get(dep_name)
            if cible_svc is None:
                continue  # Dépendance pointant un service absent du plan : ignorée
            if cible_svc.name not in cibles:
                cibles.append(cible_svc.name)
        if not cibles:
            # Contrôle négatif : aucune dépendance présente -> pas de politique
            continue

        dep_name_safe = _safe(dep_svc.name, "dep.name")
        parts.append("---\n")
        parts.append("apiVersion: networking.k8s.io/v1\n")
        parts.append("kind: NetworkPolicy\n")
        parts.append("metadata:\n")
        parts.append(f"  name: forgeai-allow-{dep_name_safe}-egress\n")
        parts.append(f"  namespace: {NAMESPACE}\n")
        parts.append("spec:\n")
        parts.append("  podSelector:\n")
        parts.append("    matchLabels:\n")
        parts.append(f"      app: {dep_name_safe}\n")
        parts.append("  policyTypes:\n")
        parts.append("    - Egress\n")
        parts.append("  egress:\n")
        for cible_name in cibles:
            cible_safe = _safe(cible_name, "target.name")
            cible_svc = by_name[cible_name]  # Garanti présent car filtré plus haut
            container_port = cible_svc.container_port
            parts.append("    - to:\n")
            parts.append("        - podSelector:\n")
            parts.append("            matchLabels:\n")
            parts.append(f"              app: {cible_safe}\n")
            parts.append("      ports:\n")
            parts.append("        - protocol: TCP\n")
            parts.append(f"          port: {container_port}\n")


    return "".join(parts)


# Conversions CPU/mémoire : la somme du budget doit être NUMÉRIQUE. Additionner
# des chaînes comme "4000m" et "1" n'a aucun sens — Kubernetes accepte ces deux
# notations pour 4000 milliCPU, mais une addition Python donnerait "4000m1".
# On normalise donc tout en entiers (milliCPU, MiB) avant de sommer.
_MIB_PER_GIB = 1024


def _cpu_en_millicores(valeur: str) -> int:
    """Convertit une valeur CPU Kubernetes (``"250m"`` ou ``"2"``) en milliCPU."""
    valeur = valeur.strip()
    if valeur.endswith("m"):
        return int(valeur[:-1])
    # Forme décimale : "1" = 1 CPU = 1000 milliCPU.
    return int(float(valeur) * 1000)


def _memoire_en_mib(valeur: str) -> int:
    """Convertit une valeur mémoire Kubernetes (``"256Mi"`` ou ``"1Gi"``) en MiB."""
    valeur = valeur.strip()
    if valeur.endswith("Mi"):
        return int(valeur[:-2])
    if valeur.endswith("Gi"):
        return int(valeur[:-2]) * _MIB_PER_GIB
    raise ValueError(t("renderers.k3s.quota_memoire_invalide", valeur_repr=repr(valeur)))


def _budget_du_plan(plan: DeploymentPlan) -> dict:
    """Somme, pour chaque service du plan, ses ``requests`` et ``limits`` effectifs.

    Retourne un dictionnaire imbriqué compatible avec la sérialisation YAML :
    ``{"requests": {"cpu_m": int, "mem_mib": int},
       "limits":   {"cpu_m": int, "mem_mib": int}}``.

    Un budget faux en silence est PIRE qu'une erreur bruyante : ce budget devient un
    ``ResourceQuota``, et sous-compté il produirait un quota trop petit qui bloquerait le
    déploiement qu'il est censé encadrer. Toute ressource absente ou incomplète lève donc,
    plutôt que d'être ignorée (objection de revue scellée, Gemini-3.1-Pro).
    """
    budget = {
        "requests": {"cpu_m": 0, "mem_mib": 0},
        "limits": {"cpu_m": 0, "mem_mib": 0},
    }
    for svc in plan.services:
        res = getattr(svc, "ressources_effectives", None)
        if res is None:
            # On lève une erreur plutôt que de fausser le budget en silence
            raise ValueError(t("renderers.k3s.quota_ressources_absentes", svc_name=svc.name))
        for categorie in ("requests", "limits"):
            # `dict.get(cle, {})` ne protège que de l'absence de clé, pas d'une valeur
            # None explicite : sans le `or {}`, le .get() suivant lèverait AttributeError
            # — une trace technique opaque au lieu du ValueError qui nomme la cause.
            cpu = (res.get(categorie) or {}).get("cpu")
            memoire = (res.get(categorie) or {}).get("memory")
            if cpu is None or memoire is None:
                # On lève une erreur plutôt que de fausser le budget en silence
                raise ValueError(t("renderers.k3s.quota_ressources_incompletes",
                                    svc_name=svc.name,
                                    champ_manquant="cpu" if cpu is None else "memory",
                                    categorie=categorie))
            budget[categorie]["cpu_m"] += _cpu_en_millicores(cpu)
            budget[categorie]["mem_mib"] += _memoire_en_mib(memoire)
    return budget


# Valeurs utilitaires de la LimitRange : volontairement modestes. Elles ne
# décrivent pas le profil "LLM lourd" (qui a ses propres ressources_effectives)
# mais le conteneur "moyen" qui ne déclare rien. Sans LimitRange, ce conteneur
# silencieux échapperait au quota et pourrait, à lui seul, épuiser la capacité
# allouée au namespace.
_LIMITE_DEFAUT_CPU = "250m"
_LIMITE_DEFAUT_MEMOIRE = "256Mi"
_REQUETE_DEFAUT_CPU = "50m"
_REQUETE_DEFAUT_MEMOIRE = "64Mi"


def _quota_et_limites(plan: DeploymentPlan) -> str:
    """Émet un ``ResourceQuota`` et un ``LimitRange`` pour le namespace du plan.

    Le ``ResourceQuota`` vaut **exactement** le budget cumulé du plan :
    - ni plus (on ne gèlerait pas de la capacité inutilisée),
    - ni moins (un quota sous-alloué bloquerait le déploiement qu'il encadre
      en refusant la création des pods au-delà du quota).
    La ``LimitRange`` applique des défauts raisonnables à tout conteneur qui
    n'aurait pas déclaré ses propres ressources.
    """
    budget = _budget_du_plan(plan)

    cpu_req_m = budget["requests"]["cpu_m"]
    mem_req_mib = budget["requests"]["mem_mib"]
    cpu_lim_m = budget["limits"]["cpu_m"]
    mem_lim_mib = budget["limits"]["mem_mib"]

    parts: list[str] = []
    # ResourceQuota : couvre simultanément requests et limits pour CPU et mémoire.
    parts.append("---\n")
    parts.append("apiVersion: v1\n")
    parts.append("kind: ResourceQuota\n")
    parts.append("metadata:\n")
    parts.append("  name: forgeai-quota\n")
    parts.append(f"  namespace: {NAMESPACE}\n")
    parts.append("spec:\n")
    parts.append("  hard:\n")
    parts.append(f'    requests.cpu: "{cpu_req_m}m"\n')
    parts.append(f'    requests.memory: "{mem_req_mib}Mi"\n')
    parts.append(f'    limits.cpu: "{cpu_lim_m}m"\n')
    parts.append(f'    limits.memory: "{mem_lim_mib}Mi"\n')

    # LimitRange : un seul entrée de type Container, défauts requests/limits.
    # Sans elle, un pod sans resources serait accepté tel quel et pourrait
    # consommer à lui seul tout le quota du namespace.
    parts.append("---\n")
    parts.append("apiVersion: v1\n")
    parts.append("kind: LimitRange\n")
    parts.append("metadata:\n")
    parts.append("  name: forgeai-limits\n")
    parts.append(f"  namespace: {NAMESPACE}\n")
    parts.append("spec:\n")
    parts.append("  limits:\n")
    parts.append("    - type: Container\n")
    parts.append("      default:\n")
    parts.append(f'        cpu: "{_LIMITE_DEFAUT_CPU}"\n')
    parts.append(f'        memory: "{_LIMITE_DEFAUT_MEMOIRE}"\n')
    parts.append("      defaultRequest:\n")
    parts.append(f'        cpu: "{_REQUETE_DEFAUT_CPU}"\n')
    parts.append(f'        memory: "{_REQUETE_DEFAUT_MEMOIRE}"\n')

    return "".join(parts)


def _verifier_capacite(plan: DeploymentPlan, capacite: "CapaciteCluster | None") -> None:
    """Vérifie que le budget agrégé du plan tient dans la capacité déclarée.

    Rétro-compatibilité stricte : si ``capacite`` vaut ``None``, on ne peut
    rien vérifier (l'appelant n'a pas déclaré de cluster cible) et la fonction
    retourne silencieusement. Sinon, on compare les **limits** (et non les
    requests) car c'est le plafond absolu que Kubernetes appliquera au pod :
    si les limits dépassent la capacité, le pod sera de toute façon throttlé
    ou OOMKill, indépendamment du quota du namespace.

    Les deux contrôles (CPU, mémoire) sont indépendants : un dépassement
    uniquement mémoire reste un dépassement et doit être signalé.

    Pour les services GPU, si le cluster déclare explicitement ses ressources
    GPU (``ressources_gpu`` non vide), on exige que le device plugin du vendor
    soit présent avec une capacité suffisante. Si ``ressources_gpu`` est vide,
    l'appelant n'a pas renseigné l'information : on ne refuse pas le rendu.
    """
    if capacite is None:
        return

    budget = _budget_du_plan(plan)
    cpu_requis = budget["limits"]["cpu_m"]
    memoire_requise = budget["limits"]["mem_mib"]

    if cpu_requis > capacite.cpu_millicores:
        raise QuotaError(t("renderers.k3s.quota_cpu_depasse",
                            cpu_requis=cpu_requis, cpu_millicores=capacite.cpu_millicores))
    if memoire_requise > capacite.memoire_mib:
        raise QuotaError(t("renderers.k3s.quota_memoire_depassee",
                            memoire_requise=memoire_requise, memoire_mib=capacite.memoire_mib))

    # Vérification GPU uniquement si le cluster a déclaré ses ressources GPU.
    if not capacite.ressources_gpu:
        return

    demandes_gpu: dict[str, int] = {}
    for svc in plan.services:
        if not svc.gpu:
            continue
        vendor = svc.gpu_vendor or "nvidia"
        ressource = _RESSOURCE_GPU_PAR_VENDOR.get(vendor)
        if ressource is None:
            continue
        demandes_gpu[ressource] = demandes_gpu.get(ressource, 0) + 1

    for ressource, demande in demandes_gpu.items():
        disponible = capacite.ressources_gpu.get(ressource, 0)
        if disponible < demande:
            raise QuotaError(t("renderers.k3s.quota_gpu_plugin_absent",
                                demande=demande, ressource=ressource, disponible=disponible))


def render_k3s(plan: DeploymentPlan, node: str | None = None,
               service_type: str = "NodePort",
               config_files: dict[str, str] | None = None,
               inventaire: tuple[NodeInventaire, ...] | None = None,
               capacite: CapaciteCluster | None = None) -> str:
    """Manifestes Kubernetes STANDARD (valables k3s ET k8s — même API). `node` épingle les pods
    sur un hôte (profil Minimal = single-node) ; `svc.node == "auto"` laisse le scheduler décider.
    `service_type` : NodePort (défaut, portable partout, k3s/edge) ou LoadBalancer (cloud/k8s).
    `config_files` : mapping {basename: contenu} pour les bind-mounts de fichiers de config
    (ex. litellm-config.yaml) émis comme ConfigMap et montés via subPath."""

    # Garde adoption (k3s) : un service adopté porte l'endpoint "hôte:port" d'un service DÉJÀ
    # présent sur le nœud. Côté compose on omet le workload et le dépendant joint l'hôte via
    # host.docker.internal. Côté k3s la cible correcte serait un Service ClusterIP sans selector
    # + un Endpoints manuel, MAIS l'inventaire ne rapporte que 127.0.0.1:<port> — qui désigne le
    # pod lui-même depuis un pod, pas le nœud hôte. Rendre cela produirait un manifeste valide et
    # fonctionnellement FAUX : le dépendant se connecterait à lui-même. On REFUSE explicitement
    # plutôt que de rendre un câblage trompeur.
    _adoptes = [(sv.name, sv.adopted_endpoint) for sv in plan.services if sv.adopted_endpoint]
    if _adoptes:
        _detail = ", ".join(f"{nom} ({ep})" for nom, ep in _adoptes)
        raise AdoptionNonSupporteeK3s(t("renderers.k3s.adoption_non_supportee", detail=_detail))
    # K8S-027 : refuser AVANT de produire quoi que ce soit. Rendre puis échouer laisserait
    # l'utilisateur appliquer un manifeste dont les pods resteront Pending sans cause lisible.
    _verifier_capacite(plan, capacite)

    if service_type not in _SERVICE_TYPES:
        raise ValueError(t("renderers.k3s.service_type_invalide",
                            service_type_repr=repr(service_type),
                            service_types_valides=sorted(_SERVICE_TYPES)))
    parts = [f"""# Généré par ForgeAI Toolkit — plan {plan.plan_id} (profil {plan.profile})
{_namespace_block(plan)}---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: forgeai-sa
  namespace: {NAMESPACE}
automountServiceAccountToken: false
"""]
    # K8S-023 : refus par défaut Ingress ET Egress + allowlists dérivées des dépendances
    # DÉCLARÉES du plan. Remplace l'unique politique `forgeai-default`, qui laissait l'egress
    # totalement libre et autorisait un accès intra-namespace universel.
    # K8S-027 : quota et LimitRange dérivés du budget RÉEL du plan (somme des
    # ressources_effectives, RES-012B). Sans LimitRange, un conteneur ne déclarant aucune
    # ressource échapperait au quota et pourrait l'épuiser à lui seul.
    parts.append(_quota_et_limites(plan))
    parts.append(_network_policies(plan))
    used: set[int] = set()
    for svc in plan.services:
        effective_node = svc.node if svc.node is not None else node
        # PLACE-011 : valider le placement contre l'inventaire AVANT d'émettre le manifeste.
        # Sans inventaire, aucune validation n'est possible et le comportement reste inchangé
        # (rétro-compatibilité). Avec inventaire, un placement incompatible lève PlacementError
        # ici plutôt que de produire un manifeste qui échouera au scheduling, en production.
        # `is not None` et non `if inventaire` : un inventaire explicitement VIDE doit atteindre
        # la validation, qui saura dire qu'aucun nœud n'est disponible. `None` = « je ne sais
        # pas » ; `()` = « je sais, et il n'y a rien » (objection de revue, DeepSeek-V4-Pro).
        if inventaire is not None:
            effective_node = valider_placement(svc, inventaire, effective_node)
        parts.append(_deployment(svc, effective_node, node_port_for(svc, used), service_type,
                                 config_files))
    return "".join(parts)
