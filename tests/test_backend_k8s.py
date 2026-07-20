"""Story K-CHOICE — l'utilisateur choisit k3s OU k8s (+ type de service).

Spec exécutable (TDAD, AVANT le code). k3s et k8s partagent l'API Kubernetes (kubectl, manifestes
identiques) ; la différence utile = l'exposition des services. On ajoute :
  - le backend `k8s` (à côté de compose/k3s), activé quand kubectl+cluster sont joignables ;
  - `render_k3s(plan, service_type=...)` : NodePort (défaut, portable) ou LoadBalancer (cloud).
Le manifeste rendu reste du Kubernetes standard, validé par `kubectl apply --dry-run` (e2e).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from forgeai.core.models import DeploymentPlan, RenderTarget, ServiceSpec
from forgeai.preflight import OK, Check, available_backends
from forgeai.renderers.k3s import render_k3s


def _plan():
    return DeploymentPlan(
        plan_id="p1-test", profile="minimal-cpu", target=RenderTarget.K3S,
        services=(ServiceSpec(name="ollama", image="ollama/ollama:latest", host_port=21434,
                              container_port=11434),),
        model="m", embed_model="e")


# --- service type : NodePort par défaut ---
def test_render_defaut_nodeport():
    out = render_k3s(_plan())
    assert "type: NodePort" in out
    assert "nodePort:" in out


# --- service type : LoadBalancer (k8s cloud) ---
def test_render_loadbalancer():
    out = render_k3s(_plan(), service_type="LoadBalancer")
    assert "type: LoadBalancer" in out
    assert "type: NodePort" not in out
    # un service LoadBalancer expose port/targetPort ; pas de nodePort figé
    assert "nodePort:" not in out
    assert "port: 11434" in out and "targetPort: 11434" in out


def test_render_loadbalancer_reste_du_kubernetes_valide():
    out = render_k3s(_plan(), service_type="LoadBalancer")
    assert "apiVersion: apps/v1" in out and "kind: Deployment" in out
    assert "kind: Service" in out and "kind: Namespace" in out


# --- preflight : kubectl OK -> k3s ET k8s disponibles ---
def test_available_backends_inclut_k8s_si_kubectl():
    checks = [Check("docker", OK, "ok", "compose"), Check("kubectl", OK, "ok", "kube")]
    backends = available_backends(checks)
    assert "k3s" in backends and "k8s" in backends and "compose" in backends


def test_available_backends_sans_kubectl_pas_de_k8s():
    from forgeai.preflight import MISSING
    checks = [Check("docker", OK, "ok", "compose"), Check("kubectl", MISSING, "absent", "x")]
    backends = available_backends(checks)
    assert "k8s" not in backends and "k3s" not in backends and "compose" in backends
