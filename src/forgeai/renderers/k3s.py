"""Story P1-S07 (rendu) — DeploymentPlan → manifestes K3s (codeur : grok/fable).

Un fichier YAML multi-documents : Namespace + (Deployment + Service) par brique.
Ports exposés en NodePort sur le port hôte alloué du plan (plage 30000-32767 de
Kubernetes : le port hôte est décalé dans la plage NodePort de façon déterministe).
"""
from __future__ import annotations

from forgeai.core.models import DeploymentPlan, ServiceSpec

NAMESPACE = "forgeai-minimal"


def node_port_for(svc: ServiceSpec, used: set[int] | None = None) -> int:
    """Mappe le port hôte vers la plage NodePort (30000-32767), sans collision :
    en cas de conflit de modulo entre services, incrémente jusqu'au port libre
    (objection majeure levée en revue de code P1, corrigée)."""
    port = 30000 + (svc.host_port % 2768)
    if used is not None:
        while port in used:
            port = 30000 + ((port - 30000 + 1) % 2768)
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
    gpu_limits = """
          resources:
            limits:
              nvidia.com/gpu: "1"ifgpu""".replace("ifgpu", "") if svc.gpu else ""
    node_selector = (f"""
      nodeSelector:
        kubernetes.io/hostname: {effective_node}"""
                   if effective_node and effective_node != "auto" else "")
    volume_mount, volume_def = "", ""
    if svc.volumes:
        claim = svc.volumes[0].split(":", 1)[0]
        mount_path = svc.volumes[0].split(":", 1)[1]
        volume_mount = f"""
          volumeMounts:
            - name: {claim}
              mountPath: {mount_path}"""
        volume_def = f"""
      volumes:
        - name: {claim}
          emptyDir: {{}}"""
    return f"""---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {svc.name}
  namespace: {NAMESPACE}
spec:
  replicas: 1
  selector:
    matchLabels: {{app: {svc.name}}}
  template:
    metadata:
      labels: {{app: {svc.name}}}
    spec:{node_selector}
      containers:
        - name: {svc.name}
          image: {svc.image}
          ports:
            - containerPort: {svc.container_port}{gpu_limits}{volume_mount}{volume_def}
---
apiVersion: v1
kind: Service
metadata:
  name: {svc.name}
  namespace: {NAMESPACE}
spec:
  type: {service_type}
  selector: {{app: {svc.name}}}
  ports:{_service_ports(svc, service_type, node_port)}
"""


def render_k3s(plan: DeploymentPlan, node: str | None = None,
               service_type: str = "NodePort") -> str:
    """Manifestes Kubernetes STANDARD (valables k3s ET k8s — même API). `node` épingle les pods
    sur un hôte (profil Minimal = single-node) ; `svc.node == "auto"` laisse le scheduler décider.
    `service_type` : NodePort (défaut, portable partout, k3s/edge) ou LoadBalancer (cloud/k8s)."""
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
