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


def _deployment(svc: ServiceSpec, node: str | None = None,
                node_port: int | None = None) -> str:
    gpu_limits = """
          resources:
            limits:
              nvidia.com/gpu: "1"ifgpu""".replace("ifgpu", "") if svc.gpu else ""
    node_selector = (f"""
      nodeSelector:
        kubernetes.io/hostname: {node}""" if node else "")
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
  type: NodePort
  selector: {{app: {svc.name}}}
  ports:
    - port: {svc.container_port}
      targetPort: {svc.container_port}
      nodePort: {node_port if node_port is not None else node_port_for(svc)}
"""


def render_k3s(plan: DeploymentPlan, node: str | None = None) -> str:
    """`node` épingle les pods sur un hôte (profil Minimal = single-node par contrat)."""
    parts = [f"""# Généré par ForgeAI Toolkit — plan {plan.plan_id} (profil {plan.profile})
apiVersion: v1
kind: Namespace
metadata:
  name: {NAMESPACE}
"""]
    used: set[int] = set()
    parts += [_deployment(svc, node, node_port_for(svc, used)) for svc in plan.services]
    return "".join(parts)
