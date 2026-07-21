"""Story P1-S07 (rendu) — DeploymentPlan → manifestes K3s (codeur : grok/fable).

Un fichier YAML multi-documents : Namespace + (Deployment + Service) par brique.
Ports exposés en NodePort sur le port hôte alloué du plan (plage 30000-32767 de
Kubernetes : le port hôte est décalé dans la plage NodePort de façon déterministe).
"""
from __future__ import annotations

from forgeai.core.models import DeploymentPlan, ServiceSpec

NAMESPACE = "forgeai-minimal"
_NODEPORT_SPAN = 2768  # 30000..32767
# Le renderer ne fait pas confiance à son appelant : `service_type` est restreint à ces valeurs
# (interpolé brut au manifeste ; une valeur arbitraire injecterait du YAML). Le wizard le contraint
# par argparse, mais render_k3s est une API publique -> allowlist ici (finding Sentinelle).
_SERVICE_TYPES = frozenset({"NodePort", "LoadBalancer"})


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
                node_port: int | None = None, service_type: str = "NodePort") -> str:
    name = _safe(svc.name, "name")
    image = _safe(svc.image, "image")
    # GPU par vendor (S3) : nvidia -> ressource device-plugin ; amd/intel -> passthrough hostPath
    # des devices noyau + privileged (marche sur un nœud NU, sans device-plugin installé).
    vendor = (svc.gpu_vendor or "nvidia") if svc.gpu else None
    resources_block, security_block, gpu_mounts, gpu_vols = "", "", [], []
    if vendor == "nvidia":
        resources_block = """
          resources:
            limits:
              nvidia.com/gpu: "1\""""
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
    # Fusion volume data + devices GPU en UN bloc volumeMounts et UN bloc volumes (sinon clé YAML
    # dupliquée). mounts: (claim, mountPath) ; vols: (claim, hostPath|None) — None => emptyDir data.
    mounts, vols = [], []
    if svc.volumes:
        parts = svc.volumes[0].split(":", 1)
        if len(parts) != 2:  # format attendu 'nom:chemin' -> erreur claire (pas d'IndexError)
            raise ValueError(f"volume mal formé (attendu 'nom:chemin') : {svc.volumes[0]!r}")
        claim, mount_path = _safe(parts[0], "volume-claim"), _safe(parts[1], "volume-path")
        mounts.append((claim, mount_path))
        vols.append((claim, None))
    for claim, path in gpu_mounts:
        mounts.append((claim, path))
    for claim, path in gpu_vols:
        vols.append((claim, path))
    volume_mount = ""
    if mounts:
        items = "".join(
            f"\n            - name: {c}\n              mountPath: {m}" for c, m in mounts)
        volume_mount = f"\n          volumeMounts:{items}"
    volume_def = ""
    if vols:
        items = ""
        for claim, hostpath in vols:
            if hostpath is None:
                items += f"\n        - name: {claim}\n          emptyDir: {{}}"
            else:
                items += (f"\n        - name: {claim}"
                          f"\n          hostPath:\n            path: {hostpath}")
        volume_def = f"\n      volumes:{items}"
    # command → args k8s (parité avec le renderer compose) ; chaque arg passé par _safe (injection).
    command_block = ""
    if svc.command:
        items = "".join(f"\n            - \"{_safe(str(a), 'arg')}\"" for a in svc.command)
        command_block = f"\n          args:{items}"
    container_extra = f"{command_block}{resources_block}{security_block}{volume_mount}{volume_def}"
    return f"""---
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
               service_type: str = "NodePort") -> str:
    """Manifestes Kubernetes STANDARD (valables k3s ET k8s — même API). `node` épingle les pods
    sur un hôte (profil Minimal = single-node) ; `svc.node == "auto"` laisse le scheduler décider.
    `service_type` : NodePort (défaut, portable partout, k3s/edge) ou LoadBalancer (cloud/k8s)."""
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
        parts.append(_deployment(svc, effective_node, node_port_for(svc, used), service_type))
    return "".join(parts)
