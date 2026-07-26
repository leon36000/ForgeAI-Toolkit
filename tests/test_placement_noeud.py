from __future__ import annotations

import json
import threading
from http.client import HTTPConnection

from forgeai.core.models import DeploymentPlan, RenderTarget, ServiceSpec
from forgeai.renderers.k3s import render_k3s
from forgeai.resources import catalogue_path
from forgeai.web.server import build_server


def _read_data_json(name: str) -> dict:
    from importlib import resources
    return json.loads((resources.files("forgeai.data") / name).read_text(encoding="utf-8"))


def test_servicespec_node_retrocompat() -> None:
    spec = ServiceSpec(name="svc", image="img:latest", host_port=8080, container_port=80)
    assert spec.node is None


def test_k3s_node_par_service() -> None:
    services = (
        ServiceSpec(name="svc-global", image="g", host_port=8001, container_port=80),
        ServiceSpec(name="svc-worker", image="w", host_port=8002, container_port=80, node="worker-2"),
        ServiceSpec(name="svc-auto", image="a", host_port=8003, container_port=80, node="auto"),
    )
    plan = DeploymentPlan(
        plan_id="placement-01",
        profile="minimal",
        target=RenderTarget.K3S,
        services=services,
        model="ollama",
        embed_model="ollama",
    )
    rendered = render_k3s(plan, node="global-1")

    assert "hostname: global-1" in rendered
    assert "hostname: worker-2" in rendered
    assert rendered.count("nodeSelector:") == 2

    sections = rendered.split("---")
    auto_section = next(s for s in sections if "svc-auto" in s)
    assert "nodeSelector:" not in auto_section


def test_registre_moteurs_ids_au_catalogue() -> None:
    moteurs = _read_data_json("moteurs-inference.json")
    catalogue = json.loads(catalogue_path().read_text(encoding="utf-8"))
    catalogue_ids = {entry["id"] for entry in catalogue.get("entries", [])}

    for moteur in moteurs["moteurs"]:
        assert moteur["id"] in catalogue_ids, f"{moteur['id']} absent du catalogue"


def test_api_engines() -> None:
    server = build_server("127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        conn = HTTPConnection(host, port)
        conn.request("GET", "/api/engines")
        response = conn.getresponse()
        assert response.status == 200
        data = json.loads(response.read().decode("utf-8"))

        assert len(data["moteurs"]) == 8
        llama = next(m for m in data["moteurs"] if m["id"] == "llama-cpp")
        assert "vulkan" in llama["backends"]
        assert "rocm" in llama["backends"]
        tensorrt = next(m for m in data["moteurs"] if m["id"] == "tensorrt-llm")
        assert tensorrt["gpu_vendors"] == ["nvidia"]
    finally:
        server.shutdown()
        server.server_close()


def test_api_engines_compatible_filtre_par_vendor() -> None:
    # S6 : le choix FILTRÉ exposé à l'UI — /api/engines/compatible?vendor=amd
    server = build_server("127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        conn = HTTPConnection(host, port)
        conn.request("GET", "/api/engines/compatible?vendor=amd")
        response = conn.getresponse()
        assert response.status == 200
        data = json.loads(response.read().decode("utf-8"))
        assert data["vendor"] == "amd"
        assert "llama-cpp" in data["moteurs"] and "vllm" in data["moteurs"]
        assert "tensorrt-llm" not in data["moteurs"]  # nvidia-only exclu du choix AMD
        # vendor nvidia : tensorrt-llm réapparaît
        conn.request("GET", "/api/engines/compatible?vendor=nvidia")
        nv = json.loads(conn.getresponse().read().decode("utf-8"))
        assert "tensorrt-llm" in nv["moteurs"]
    finally:
        server.shutdown()
        server.server_close()


def test_choix_jamais_impose() -> None:
    moteurs = _read_data_json("moteurs-inference.json")
    vendors: set[str] = set()
    for moteur in moteurs["moteurs"]:
        vendors.update(moteur["gpu_vendors"])
    assert {"nvidia", "amd", "cpu"} <= vendors


# PLACE-026A (FAI-U-026) — l'intention de placement par service doit être CÂBLÉE dans assemble_plan.
def _plan_minimal(**kw):
    from importlib import resources
    from pathlib import Path
    from forgeai.planner.assemble import assemble_plan
    overlay = Path(str(resources.files("forgeai.data") / "deploy-minimal.json"))
    return assemble_plan("minimal-cpu", overlay, **kw)


def test_placement_par_service_cable_depuis_decision_explicite():
    """`placement` explicite {service: noeud} -> ServiceSpec.node peuplé pour CE service seulement."""
    plan = _plan_minimal(placement={"vector-store": "node-rag"})
    par_nom = {s.name: s for s in plan.services}
    assert par_nom["vector-store"].node == "node-rag"
    assert par_nom["ollama"].node is None  # non ciblé -> inchangé


def test_rag_node_ne_deplace_que_les_services_rag():
    """`rag_node` ne relocalise QUE les services RAG définis, jamais tout le plan (défaut FAI-U-026)."""
    plan = _plan_minimal(rag_node="node-rag")
    par_nom = {s.name: s for s in plan.services}
    assert par_nom["vector-store"].node == "node-rag"   # service RAG -> déplacé
    assert par_nom["ollama"].node is None               # NON-RAG -> jamais relocalisé silencieusement


def test_plan_expose_la_raison_du_placement():
    """Le plan expose la RAISON de chaque placement (traçabilité, critère d'acceptation)."""
    plan = _plan_minimal(rag_node="node-rag")
    raisons = getattr(plan, "placement_reasons", None)
    assert raisons, "le plan n'expose aucune raison de placement"
    assert "vector-store" in raisons and "rag" in str(raisons["vector-store"]).lower()


def test_plan_sans_placement_reste_documente():
    """Sans placement explicite : node=None partout, aucune raison inventée (rétro-compat)."""
    plan = _plan_minimal()
    assert all(s.node is None for s in plan.services)
    assert not getattr(plan, "placement_reasons", {})
