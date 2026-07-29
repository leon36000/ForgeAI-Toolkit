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


# ---------------------------------------------------------------------------
# PLACE-011 / FAI-U-011 — le placement est validé contre un INVENTAIRE réel avant rendu.
# Jusqu'ici aucun inventaire n'était consulté : un workload NVIDIA épinglé sur un nœud
# CPU-only produisait un manifeste parfaitement valide, envoyé à kubectl, qui échouait au
# scheduling. L'utilisateur découvrait l'incompatibilité en production.
# ---------------------------------------------------------------------------
import pytest

from forgeai.core.models import NodeInventaire, PlacementError


def _plan(services) -> DeploymentPlan:
    """Plan portant exactement les services fournis (le fichier n'a que `_plan_minimal`,
    qui assemble depuis un overlay et ne convient pas pour ces cas ciblés)."""
    return DeploymentPlan(plan_id="place011", profile="minimal-gpu-cuda",
                          target=RenderTarget.K3S, services=tuple(services),
                          model="m", embed_model="e")


def _inventaire():
    """Inventaire de référence : un nœud NVIDIA 8 Go, un nœud AMD 16 Go, un nœud CPU-only."""
    return (
        NodeInventaire(hostname="n-nvidia", gpu_vendor="nvidia", vram_mib=8192),
        NodeInventaire(hostname="n-amd", gpu_vendor="amd", vram_mib=16384),
        NodeInventaire(hostname="n-cpu", gpu_vendor=None, vram_mib=0),
    )


def _svc_gpu(vendor="nvidia", node=None, vram_requise=None):
    return ServiceSpec(name="ollama", image="ollama/ollama:latest", host_port=21434,
                       container_port=11434, gpu=True, gpu_vendor=vendor, node=node,
                       vram_min_mib=vram_requise)


def test_nvidia_ne_peut_pas_etre_epingle_sur_un_noeud_cpu_only():
    """Critère 1. Le manifeste serait syntaxiquement valide et échouerait au scheduling :
    l'erreur doit survenir AVANT kubectl, avec sa cause."""
    with pytest.raises(PlacementError) as exc:
        render_k3s(_plan([_svc_gpu(node="n-cpu")]), inventaire=_inventaire())
    message = str(exc.value)
    assert "n-cpu" in message and "nvidia" in message.lower(), \
        f"l'erreur doit nommer le nœud ET le vendor attendu : {message}"


def test_vendor_incompatible_refuse():
    """Critère 2. AMD/Intel portent une contrainte vérifiable : un workload AMD sur un nœud
    NVIDIA est refusé — un GPU n'est pas un GPU générique."""
    with pytest.raises(PlacementError) as exc:
        render_k3s(_plan([_svc_gpu(vendor="amd", node="n-nvidia")]), inventaire=_inventaire())
    assert "amd" in str(exc.value).lower() and "nvidia" in str(exc.value).lower()


def test_vram_insuffisante_produit_une_erreur_causale():
    """Critère 3. Le nœud a bien un GPU du bon vendor, mais pas assez de VRAM : l'échec ne
    doit pas se manifester par un OOM au chargement du modèle, en production."""
    with pytest.raises(PlacementError) as exc:
        render_k3s(_plan([_svc_gpu(node="n-nvidia", vram_requise=12288)]), inventaire=_inventaire())
    message = str(exc.value)
    assert "12288" in message and "8192" in message, \
        f"l'erreur doit donner la VRAM demandée ET la VRAM disponible : {message}"


def test_placement_compatible_accepte():
    """Contrôle positif : un placement valide passe et épingle bien le nœud demandé."""
    out = render_k3s(_plan([_svc_gpu(node="n-nvidia", vram_requise=4096)]), inventaire=_inventaire())
    assert "kubernetes.io/hostname: n-nvidia" in out


def test_mode_auto_choisit_uniquement_un_noeud_qualifie():
    """Critère 4. Sans nœud imposé, la sélection automatique ne doit retenir qu'un nœud
    qualifié — jamais le nœud CPU-only, jamais un vendor incompatible."""
    out = render_k3s(_plan([_svc_gpu(vendor="amd", node=None)]), inventaire=_inventaire())
    assert "kubernetes.io/hostname: n-amd" in out
    assert "n-cpu" not in out and "n-nvidia" not in out


def test_mode_auto_sans_noeud_qualifie_refuse():
    """Contrôle négatif du mode auto : aucun nœud ne convient -> refus explicite, jamais un
    placement au hasard ni un manifeste voué à l'échec."""
    inventaire_sans_intel = _inventaire()
    with pytest.raises(PlacementError) as exc:
        render_k3s(_plan([_svc_gpu(vendor="intel", node=None)]), inventaire=inventaire_sans_intel)
    assert "intel" in str(exc.value).lower()


def test_sans_inventaire_le_comportement_reste_inchange():
    """Rétro-compatibilité : sans inventaire fourni, aucune validation n'est possible et le
    rendu reste celui d'avant — la validation est une capacité ajoutée, pas une rupture."""
    out = render_k3s(_plan([_svc_gpu(node="n-cpu")]))
    assert "kubernetes.io/hostname: n-cpu" in out


def test_service_cpu_ignore_l_inventaire_gpu():
    """Contrôle négatif : un service sans GPU n'est jamais contraint par le vendor d'un nœud."""
    cpu_only = ServiceSpec(name="redis", image="redis:7", host_port=26379, container_port=6379,
                           node="n-cpu", resource_class="db")
    out = render_k3s(_plan([cpu_only]), inventaire=_inventaire())
    assert "kubernetes.io/hostname: n-cpu" in out


# --- Objections de la revue scellée (3/3 APPROVE, sceau 258d2f6d1de2) -----------------
def test_codes_d_erreur_de_l_inventaire_sont_specifiques():
    """Les TROIS vendors ont relevé indépendamment le même défaut : `NodeInventaire` utilisait
    `ERR_PLACE_VENDOR_INCONNU` pour signaler un hostname vide ou une VRAM négative — des cas qui
    n'ont rien à voir avec un vendor. Un code d'erreur trompeur envoie l'utilisateur chercher au
    mauvais endroit ; c'est exactement ce que les codes stables sont censés éviter."""
    with pytest.raises(ValueError, match="ERR_PLACE_HOSTNAME_INVALIDE"):
        NodeInventaire(hostname="")
    with pytest.raises(ValueError, match="ERR_PLACE_VRAM_INVALIDE"):
        NodeInventaire(hostname="n1", gpu_vendor="nvidia", vram_mib=-1)
    with pytest.raises(ValueError, match="ERR_PLACE_VENDOR_INCONNU"):
        NodeInventaire(hostname="n1", gpu_vendor="matrox")


def test_noeud_absent_de_l_inventaire_est_refuse():
    """Objection de Grok : ce cas était prouvé dans COMPORTEMENT.txt mais aucun test ne le
    couvrait. Un comportement démontré une fois n'est pas un comportement protégé."""
    with pytest.raises(PlacementError) as exc:
        render_k3s(_plan([_svc_gpu(node="n-fantome")]), inventaire=_inventaire())
    message = str(exc.value)
    assert "ERR_PLACE_NOEUD_INCONNU" in message
    assert "n-fantome" in message and "n-nvidia" in message, \
        "l'erreur doit nommer le nœud demandé ET lister les hostnames connus"


def test_inventaire_vide_explicite_n_est_pas_une_absence_d_inventaire():
    """Objection de DeepSeek : un tuple vide passait pour « pas d'inventaire » et court-circuitait
    toute validation. Or fournir un inventaire SANS AUCUN nœud n'est pas la même chose que ne pas
    en fournir : c'est affirmer qu'aucun nœud n'est disponible. Un service GPU ne peut donc y être
    placé, et le dire vaut mieux que de rendre un manifeste."""
    with pytest.raises(PlacementError) as exc:
        render_k3s(_plan([_svc_gpu(node=None)]), inventaire=())
    assert "ERR_PLACE_AUCUN_NOEUD_QUALIFIE" in str(exc.value)


# ---------------------------------------------------------------------------
# PLACE-026B / FAI-U-026 — diagnostic service -> nœud -> raison.
# Constat de reproduction : les critères 1 et 2 (sélecteur correct, service `auto` non
# épinglé) sont DÉJÀ satisfaits — héritage de PLACE-026A. Ils sont néanmoins verrouillés
# par des tests ci-dessous : un comportement prouvé n'est pas un comportement protégé
# (leçon de la revue PLACE-011). Le critère 3 manquait entièrement.
# ---------------------------------------------------------------------------
from forgeai.cluster import placement_diagnostic


def _svcs_placement():
    return [
        ServiceSpec(name="pin", image="i:1", host_port=1, container_port=1, node="n-a"),
        ServiceSpec(name="libre", image="i:2", host_port=2, container_port=2, node="auto"),
        ServiceSpec(name="herite", image="i:3", host_port=3, container_port=3),
    ]


def test_service_epingle_recoit_son_selecteur():
    """Critère 1 — verrouillage d'un comportement existant (PLACE-026A)."""
    import yaml
    out = render_k3s(_plan(_svcs_placement()), node="n-global")
    sels = {d["metadata"]["name"]: (d["spec"]["template"]["spec"].get("nodeSelector") or {})
            for d in yaml.safe_load_all(out) if d and d.get("kind") == "Deployment"}
    assert sels["pin"] == {"kubernetes.io/hostname": "n-a"}


def test_service_auto_n_est_jamais_epingle():
    """Critère 2 — `auto` signifie « laisse le scheduler décider ». L'épingler par
    inadvertance annulerait la tolérance aux pannes que l'utilisateur a demandée."""
    import yaml
    out = render_k3s(_plan(_svcs_placement()), node="n-global")
    sels = {d["metadata"]["name"]: (d["spec"]["template"]["spec"].get("nodeSelector") or {})
            for d in yaml.safe_load_all(out) if d and d.get("kind") == "Deployment"}
    assert sels["libre"] == {}, "un service 'auto' ne doit porter AUCUN nodeSelector"
    assert sels["herite"] == {"kubernetes.io/hostname": "n-global"}, "sans node, le global s'applique"


def test_diagnostic_rend_service_noeud_raison():
    """Critère 3 — le diagnostic doit dire, pour CHAQUE service, où il ira ET pourquoi.
    Sans cela, un utilisateur dont le déploiement se place mal n'a aucun moyen de comprendre
    quelle décision a produit ce placement."""
    lignes = placement_diagnostic(_plan(_svcs_placement()), node_global="n-global")
    par_service = {d["service"]: d for d in lignes}
    assert set(par_service) == {"pin", "libre", "herite"}
    assert par_service["pin"]["node"] == "n-a"
    assert "explicite" in par_service["pin"]["raison"].lower()
    assert par_service["libre"]["node"] is None
    assert "auto" in par_service["libre"]["raison"].lower()
    assert par_service["herite"]["node"] == "n-global"
    assert "global" in par_service["herite"]["raison"].lower()


def test_diagnostic_expose_la_validation_contre_l_inventaire():
    """Critère 3 (suite) — « exposer la décision ET SA VALIDATION ». Le diagnostic doit dire
    si le nœud choisi a été confronté à l'inventaire, et avec quel résultat."""
    inv = (NodeInventaire(hostname="n-a", gpu_vendor="nvidia", vram_mib=8192),
           NodeInventaire(hostname="n-global"))
    gpu = ServiceSpec(name="ollama", image="o:1", host_port=9, container_port=9,
                      gpu=True, gpu_vendor="nvidia", node="n-a")
    lignes = placement_diagnostic(_plan([gpu]), node_global=None, inventaire=inv)
    d = lignes[0]
    assert d["node"] == "n-a"
    assert d["validation"] == "OK", f"placement compatible -> validation OK : {d}"


def test_diagnostic_signale_un_placement_invalide_sans_lever():
    """Un diagnostic doit DIAGNOSTIQUER, pas planter : un placement incompatible est rapporté
    avec sa cause, pour que l'utilisateur voie TOUTES les lignes d'un coup plutôt que la
    première erreur seule."""
    inv = (NodeInventaire(hostname="n-cpu"),)
    gpu = ServiceSpec(name="ollama", image="o:1", host_port=9, container_port=9,
                      gpu=True, gpu_vendor="nvidia", node="n-cpu")
    lignes = placement_diagnostic(_plan([gpu]), node_global=None, inventaire=inv)
    d = lignes[0]
    assert d["validation"] != "OK"
    assert "ERR_PLACE_CPU_ONLY" in d["validation"], f"la cause doit être citée : {d}"
