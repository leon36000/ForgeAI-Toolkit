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
