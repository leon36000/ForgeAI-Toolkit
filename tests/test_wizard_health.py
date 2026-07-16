"""Corrective (finding Sentinelle) : le health-check K3s du wizard dérive les chemins de
probe DU PLAN, jamais d'un dict codé en dur — plus de KeyError sur un service inconnu."""
from forgeai.core.models import DeploymentPlan, ServiceSpec, RenderTarget
from forgeai.cli import _k3s_probe_paths


def _plan(services):
    return DeploymentPlan(plan_id="t", profile="minimal-cpu", target=RenderTarget.COMPOSE,
                          services=tuple(services), model="m", embed_model="e")


def test_probe_paths_derive_du_plan_sans_keyerror():
    services = [
        ServiceSpec("ollama", "img", 21434, 11434,
                    healthcheck_url="http://127.0.0.1:21434/api/tags"),
        ServiceSpec("vector-store", "img", 26333, 6333,
                    healthcheck_url="http://127.0.0.1:26333/readyz"),
        # service supplémentaire SANS healthcheck : plantait `probes[name]` (KeyError) avant
        ServiceSpec("orchestrator", "img", 28080, 8080),
    ]
    paths = _k3s_probe_paths(_plan(services))
    assert paths == {"ollama": "/api/tags", "vector-store": "/readyz"}
    assert "orchestrator" not in paths


def test_probe_paths_service_avec_healthcheck_inclus():
    services = [ServiceSpec("brique-x", "img", 29000, 9000,
                            healthcheck_url="http://127.0.0.1:29000/health")]
    assert _k3s_probe_paths(_plan(services)) == {"brique-x": "/health"}
