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


def test_probe_paths_filtre_services_hors_rag_ports():
    """Garde défensive : un service avec healthcheck mais absent de rag_ports est filtré,
    donc l'accès rag_ports[name] dans la boucle ne peut jamais lever de KeyError."""
    services = [
        ServiceSpec("ollama", "img", 21434, 11434,
                    healthcheck_url="http://127.0.0.1:21434/api/tags"),
        ServiceSpec("absent", "img", 29999, 9999,
                    healthcheck_url="http://127.0.0.1:29999/health"),
    ]
    paths = _k3s_probe_paths(_plan(services), rag_ports={"ollama": 30001})
    assert paths == {"ollama": "/api/tags"}
    assert "absent" not in paths
