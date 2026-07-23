"""Story P1-S07 (rendu) — DeploymentPlan → manifestes K3s (codeur : grok/fable).

Un fichier YAML multi-documents : Namespace + (Deployment + Service) par brique.
Ports exposés en NodePort sur le port hôte alloué du plan (plage 30000-32767 de
Kubernetes : le port hôte est décalé dans la plage NodePort de façon déterministe).
"""
from __future__ import annotations

import os
import re
import textwrap

from forgeai.core.models import DeploymentPlan, ServiceSpec

NAMESPACE = "forgeai-minimal"
_NODEPORT_SPAN = 2768  # 30000..32767
_DEFAULT_PVC_SIZE = "10Gi"
# Le renderer ne fait pas confiance à son appelant : `service_type` est restreint à ces valeurs
# (interpolé brut au manifeste ; une valeur arbitraire injecterait du YAML). Le wizard le contraint
# par argparse, mais render_k3s est une API publique -> allowlist ici (finding Sentinelle).
_SERVICE_TYPES = frozenset({"NodePort", "LoadBalancer"})

_SECRET_NAME = "forgeai-secrets"
_SECRET_REF = re.compile(r"\$\{(FORGEAI_[A-Za-z0-9_]+)\}")


def _safe(value: str, field: str) -> str:
    """Refuse une valeur interpolée au YAML si elle porte un caractère de contrôle/newline
    (injection de manifeste, finding Sentinelle). Les valeurs légitimes (noms k8s RFC 1123,
    images, hostnames, chemins) n'en portent jamais ; on refuse le reste (défense en profondeur).
    Vérif par point de code (pas de regex de contrôle) pour rester lisible et sans surprise."""
    if any(ord(ch) < 0x20 or ord(ch) == 0x7f for ch in value):
        raise ValueError(f"valeur non sûre pour un manifeste Kubernetes ({field}) : {value!r}")
    return value


def node_port_for(svc: ServiceSpec, used: set[int] | None = None) -> int:
    """Mappe le port hôte vers la plage NodePort (30000-32767), sans collision :
    en cas de conflit de modulo entre services, incrémente jusqu'au port libre
    (objection majeure levée en revue de code P1, corrigée)."""
    port = 30000 + (svc.host_port % _NODEPORT_SPAN)
    if used is not None:
        if len(used) >= _NODEPORT_SPAN:  # plage saturée -> erreur bornée, jamais de boucle infinie
            raise RuntimeError(
                f"plage NodePort (30000-32767) saturée : plus de {_NODEPORT_SPAN} services exposés")
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


def _deployment(svc: ServiceSpec, effective_node: str | None = None,
                node_port: int | None = None, service_type: str = "NodePort",
                config_files: dict[str, str] | None = None) -> str:
    name = _safe(svc.name, "name")
    image = _safe(svc.image, "image")
    # GPU par vendor (S3) : nvidia -> ressource device-plugin ; amd/intel -> passthrough hostPath
    # des devices noyau + privileged (marche sur un nœud NU, sans device-plugin installé).
    vendor = (svc.gpu_vendor or "nvidia") if svc.gpu else None
    resources_block, security_block, gpu_mounts, gpu_vols = "", "", [], []
    if vendor == "nvidia":
        resources_block = (
            "\n          resources:"
            "\n            limits:"
            '\n              nvidia.com/gpu: "1"'
        )
    elif vendor == "amd":
        security_block = """
          securityContext:
            privileged: true"""
        gpu_mounts = [("dev-kfd", "/dev/kfd"), ("dev-dri", "/dev/dri")]
        gpu_vols = list(gpu_mounts)
    elif vendor == "intel":
        security_block = """
          securityContext:
            privileged: true"""
        gpu_mounts = [("dev-dri", "/dev/dri")]
        gpu_vols = list(gpu_mounts)
    node_selector = ""
    if effective_node and effective_node != "auto":
        node_selector = f"""
      nodeSelector:
        kubernetes.io/hostname: {_safe(effective_node, 'node')}"""
    # Fusion volume data + devices GPU + fichiers config (ConfigMap) en UN bloc volumeMounts
    # et UN bloc volumes (sinon clé YAML dupliquée).
    # mounts: (name, mountPath, subPath|None, readOnly)
    # vols:   (name, payload, kind) avec kind dans {"pvc", "hostPath", "configMap"}
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
                raise ValueError(
                    f"bind-mount de fichier config non fourni dans config_files : {source!r}")
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
            raise ValueError(
                f"volume mal formé (attendu 'nom:chemin' ou './fichier:chemin:mode') : {volume!r}")
    for claim, path in gpu_mounts:
        mounts.append((claim, path, None, False))
    for claim, path in gpu_vols:
        vols.append((claim, path, "hostPath"))
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
            elif kind == "hostPath":
                items += (f"\n        - name: {claim}"
                          f"\n          hostPath:\n            path: {payload}")
            elif kind == "configMap":
                items += (f"\n        - name: {claim}"
                          f"\n          configMap:\n            name: {payload}")
        volume_def = f"\n      volumes:{items}"
    # command → args k8s (parité avec le renderer compose) ; chaque arg passé par _safe (injection).
    command_block = ""
    if svc.command:
        items = "".join(f"\n            - \"{_safe(str(a), 'arg')}\"" for a in svc.command)
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
                items += (
                    f"\n            - name: {_safe(str(k), 'env-key')}"
                    f"\n              value: \"{_safe(rewritten, 'env-val')}\""
                )
            else:
                items += (
                    f"\n            - name: {_safe(str(k), 'env-key')}"
                    f"\n              value: \"{_safe(str(v), 'env-val')}\""
                )
        env_block = f"\n          env:{items}"
    container_extra = (command_block + env_block + resources_block
                       + security_block + volume_mount + volume_def)
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
    spec:{node_selector}
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
  type: {service_type}
  selector: {{app: {name}}}
  ports:{_service_ports(svc, service_type, node_port)}
"""


def render_k3s(plan: DeploymentPlan, node: str | None = None,
               service_type: str = "NodePort",
               config_files: dict[str, str] | None = None) -> str:
    """Manifestes Kubernetes STANDARD (valables k3s ET k8s — même API). `node` épingle les pods
    sur un hôte (profil Minimal = single-node) ; `svc.node == "auto"` laisse le scheduler décider.
    `service_type` : NodePort (défaut, portable partout, k3s/edge) ou LoadBalancer (cloud/k8s).
    `config_files` : mapping {basename: contenu} pour les bind-mounts de fichiers de config
    (ex. litellm-config.yaml) émis comme ConfigMap et montés via subPath."""
    if service_type not in _SERVICE_TYPES:
        raise ValueError(
            f"service_type invalide : {service_type!r} (attendu {sorted(_SERVICE_TYPES)})")
    parts = [f"""# Généré par ForgeAI Toolkit — plan {plan.plan_id} (profil {plan.profile})
apiVersion: v1
kind: Namespace
metadata:
  name: {NAMESPACE}
"""]
    used: set[int] = set()
    for svc in plan.services:
        effective_node = svc.node if svc.node is not None else node
        parts.append(_deployment(svc, effective_node, node_port_for(svc, used), service_type,
                                 config_files))
    return "".join(parts)
