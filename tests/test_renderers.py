"""Tests S06/S07 (rendu) et S08 (chunking) — parité des deux backends."""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from forgeai.core.models import DeploymentPlan, RenderTarget, ServiceSpec
from forgeai.rag.client import chunk_text
from forgeai.renderers.compose import render_compose
from forgeai.renderers.k3s import render_k3s


def _plan(gpu=True):
    return DeploymentPlan(
        plan_id="p1-test", profile="minimal-gpu-cuda" if gpu else "minimal-cpu",
        target=RenderTarget.COMPOSE,
        services=(
            ServiceSpec(name="ollama", image="ollama/ollama:latest", host_port=21434,
                        container_port=11434, volumes=("vol-a:/root/.ollama",),
                        healthcheck_url="http://127.0.0.1:21434/api/tags", gpu=gpu),
            ServiceSpec(name="vector-store", image="qdrant/qdrant:v1.13.4",
                        host_port=26333, container_port=6333,
                        volumes=("vol-b:/qdrant/storage",),
                        healthcheck_url="http://127.0.0.1:26333/readyz"),
        ),
        model="qwen2.5:0.5b", embed_model="nomic-embed-text",
    )


def test_compose_contient_services_ports_et_gpu():
    out = render_compose(_plan())
    assert "ollama/ollama:latest" in out
    assert '"127.0.0.1:21434:11434"' in out
    assert "driver: nvidia" in out
    assert "vol-a:" in out and "vol-b:" in out


def test_compose_cpu_sans_reservation_gpu():
    assert "nvidia" not in render_compose(_plan(gpu=False))


def test_parite_noms_de_services_compose_k3s():
    plan = _plan()
    compose, k3s = render_compose(plan), render_k3s(plan)
    for svc in plan.services:
        assert f"  {svc.name}:" in compose
        assert f"name: {svc.name}" in k3s


def test_k3s_nodeport_dans_la_plage():
    k3s = render_k3s(_plan())
    ports = [int(line.split(":")[1]) for line in k3s.splitlines()
             if "nodePort:" in line]
    # FAI-0004 : vector-store est un datastore interne -> ClusterIP (pas de nodePort) ;
    # seul ollama (non interne) reste exposé en NodePort.
    assert len(ports) == 1
    assert all(30000 <= p <= 32767 for p in ports)


def test_k3s_nodeports_sans_collision_de_modulo():
    plan = _plan()
    # 21434 et 24202 ont le même reste modulo 2768 → collision sans correctif
    colliding = tuple(
        ServiceSpec(name=f"svc{i}", image="img:1", host_port=port, container_port=80)
        for i, port in enumerate((21434, 24202))
    )
    plan = DeploymentPlan(plan_id="t", profile="minimal-cpu", target=plan.target,
                          services=colliding, model="m", embed_model="e")
    ports = [int(line.split(":")[1]) for line in render_k3s(plan).splitlines()
             if "nodePort:" in line]
    assert len(ports) == len(set(ports)) == 2


def test_aucun_secret_dans_les_manifestes():
    plan = _plan()
    for rendered in (render_compose(plan), render_k3s(plan)):
        assert "FORGEAI_API_TOKEN=" not in rendered
        # FAI-0004 : `automountServiceAccountToken` est un nom de champ (durcissement), pas un
        # secret — on le retire du filet naïf « token » qui cible les VALEURS de secret.
        assert "token" not in (rendered.lower()
                               .replace("env_file", "")
                               .replace("automountserviceaccounttoken", ""))


@pytest.mark.skipif(shutil.which("docker") is None,
                    reason="docker absent du CI, voir Registres/mission.jsonl (mock déclaré)")
def test_compose_valide_par_docker_compose_config(tmp_path):
    compose_file = tmp_path / "docker-compose.yaml"
    compose_file.write_text(render_compose(_plan()), encoding="utf-8")
    (tmp_path / ".env").write_text("FORGEAI_API_TOKEN=x\nQDRANT_SERVICE_KEY=y\n",
                                   encoding="utf-8")
    proc = subprocess.run(["docker", "compose", "-f", str(compose_file), "config"],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


# COMPOSE-025 (FAI-U-025) — durcissement conteneur par défaut.
# `no-new-privileges` est l'analogue compose de `allowPrivilegeEscalation:false` de k3s
# (renderers/k3s.py:_security_block) : universellement sûr (n'exige ni non-root, ni drop de
# capabilities), donc appliqué à TOUS les services par défaut. Preuve d'absence = défaut FAI-U-025.
def test_compose_durcissement_no_new_privileges_par_defaut():
    out = render_compose(_plan())
    # un bloc security_opt: no-new-privileges:true par service (2 services applicatifs)
    assert out.count("no-new-privileges:true") >= 2, out
    assert "security_opt:" in out


def test_compose_no_new_privileges_couvre_chaque_service():
    # Une directive no-new-privileges par service du plan (aucun openbao ici -> pas d'unsealer).
    plan = _plan()
    out = render_compose(plan)
    assert "openbao" not in {s.name for s in plan.services}
    # séquence RENDUE exacte : restart immédiatement suivi du bloc de durcissement, une fois/service
    sequence = "    restart: unless-stopped\n    security_opt:\n      - no-new-privileges:true"
    assert out.count(sequence) == len(plan.services), out
    assert out.count("no-new-privileges:true") == len(plan.services)


def test_chunking_regroupe_les_paragraphes():
    text = "\n\n".join(f"Paragraphe {i} " + "x" * 100 for i in range(10))
    chunks = chunk_text(text, max_chars=300)
    assert 3 <= len(chunks) <= 6
    assert all(chunks)
    assert "".join(chunks).count("Paragraphe") == 10


def test_chunking_texte_vide():
    assert chunk_text("   \n\n  ") == []


# ---------------------------------------------------------------------------
# RES-012B / FAI-U-012 — ressources rendues DEPUIS le ServiceSpec (ADR RES-012A).
# `_resources_block` codait en dur 100m/128Mi -> 1 CPU/1Gi pour TOUT service : un runtime
# d'inférence était plafonné comme un job d'init (OOMKill), un utilitaire réservait autant
# qu'une base. Le renderer doit désormais LIRE les valeurs résolues du spec.
# ---------------------------------------------------------------------------
def _plan_res(services) -> DeploymentPlan:
    """Plan portant EXACTEMENT les services fournis (le `_plan` du fichier prend un booléen
    gpu et fabrique ses propres services : il ne convient pas pour tester les classes)."""
    return DeploymentPlan(plan_id="res012b", profile="minimal-cpu", target=RenderTarget.K3S,
                          services=tuple(services), model="m", embed_model="e")


def _res_du_manifeste(manifeste: str, service: str) -> dict:
    """Extrait le bloc resources du conteneur `service` dans le manifeste rendu."""
    import yaml
    for doc in yaml.safe_load_all(manifeste):
        if doc and doc.get("kind") == "Deployment" and doc["metadata"]["name"] == service:
            return doc["spec"]["template"]["spec"]["containers"][0].get("resources") or {}
    raise AssertionError(f"Deployment {service} absent du manifeste")


def test_classe_llm_obtient_les_valeurs_de_sa_classe():
    """ADR §4 : un runtime d'inférence garde ses poids et son KV cache en RAM. Plafonné à 1Gi
    il est OOMKillé — constaté au déploiement réel lors de K8S-024."""
    svc = ServiceSpec(name="ollama", image="ollama/ollama:latest", host_port=21434,
                      container_port=11434, resource_class="llm")
    res = _res_du_manifeste(render_k3s(_plan_res([svc])), "ollama")
    assert res["requests"] == {"cpu": "1000m", "memory": "4Gi"}
    assert res["limits"]["cpu"] == "4000m" and res["limits"]["memory"] == "8Gi"


def test_classe_db_et_classe_utilitaire_different():
    """Une base stateful et un job d'init ne peuvent pas partager le même gabarit."""
    db = ServiceSpec(name="qdrant", image="qdrant/qdrant:v1.12.5", host_port=26333,
                     container_port=6333, resource_class="db")
    util = ServiceSpec(name="init", image="busybox:1", host_port=29999, container_port=9999)
    manifeste = render_k3s(_plan_res([db, util]))
    r_db, r_util = _res_du_manifeste(manifeste, "qdrant"), _res_du_manifeste(manifeste, "init")
    assert r_db["requests"] == {"cpu": "250m", "memory": "512Mi"}
    assert r_util["requests"] == {"cpu": "50m", "memory": "64Mi"}, "défaut = utilitaire (ADR §3.3)"
    assert r_db != r_util


def test_derogation_explicite_prime_sur_la_classe():
    """ADR §3.3 : `resources` explicite > `resource_class` > défaut."""
    svc = ServiceSpec(name="special", image="x:1", host_port=28000, container_port=8000,
                      resource_class="sidecar",
                      resources={"requests": {"cpu": "300m", "memory": "1Gi"},
                                 "limits": {"cpu": "2", "memory": "4Gi"}})
    res = _res_du_manifeste(render_k3s(_plan_res([svc])), "special")
    assert res["requests"] == {"cpu": "300m", "memory": "1Gi"}
    assert res["limits"]["memory"] == "4Gi", "la dérogation doit primer, pas fusionner"


def test_unite_invalide_refusee():
    """ADR §5.1 : la notation décimale et les suffixes hors Mi/Gi sont refusés à la source."""
    for mauvais in ({"cpu": "0.5", "memory": "1Gi"}, {"cpu": "500m", "memory": "1G"},
                    {"cpu": "500m", "memory": "1024Ki"}):
        with pytest.raises(ValueError, match="ERR_RES"):
            ServiceSpec(name="x", image="x:1", host_port=28001, container_port=8001,
                        resources={"requests": mauvais,
                                   "limits": {"cpu": "4", "memory": "8Gi"}})


def test_limits_inferieures_aux_requests_refusees():
    """ADR §5.2 : comparaison numérique normalisée ; l'égalité reste autorisée (QoS Guaranteed)."""
    with pytest.raises(ValueError, match="ERR_RES"):
        ServiceSpec(name="x", image="x:1", host_port=28002, container_port=8002,
                    resources={"requests": {"cpu": "2", "memory": "1Gi"},
                               "limits": {"cpu": "500m", "memory": "2Gi"}})
    with pytest.raises(ValueError, match="ERR_RES"):
        ServiceSpec(name="x", image="x:1", host_port=28003, container_port=8003,
                    resources={"requests": {"cpu": "500m", "memory": "2Gi"},
                               "limits": {"cpu": "500m", "memory": "1Gi"}})
    # égalité : autorisée
    ServiceSpec(name="ok", image="x:1", host_port=28004, container_port=8004,
                resources={"requests": {"cpu": "500m", "memory": "1Gi"},
                           "limits": {"cpu": "500m", "memory": "1Gi"}})


def test_derogation_partielle_refusee():
    """ADR §3.2 : règle tout-ou-rien — une fusion implicite non relue est une erreur de spec."""
    with pytest.raises(ValueError, match="ERR_RES"):
        ServiceSpec(name="x", image="x:1", host_port=28005, container_port=8005,
                    resources={"requests": {"cpu": "500m", "memory": "1Gi"}})


def test_classe_inconnue_refusee():
    """ADR §5.1 : défaut-deny sur l'enum."""
    with pytest.raises(ValueError, match="ERR_RES"):
        ServiceSpec(name="x", image="x:1", host_port=28006, container_port=8006,
                    resource_class="gigantesque")


def test_aucun_magic_number_ne_subsiste_dans_le_renderer():
    """ADR §6.2 + §8 : test structurel interdisant la réintroduction d'un littéral de ressource."""
    from pathlib import Path
    import forgeai.renderers.k3s as mod
    source = Path(mod.__file__).read_text(encoding="utf-8")
    for litteral in ("cpu: 100m", "memory: 128Mi", "memory: 1Gi", 'cpu: "1"'):
        assert litteral not in source, f"littéral de ressource réintroduit : {litteral!r}"


def test_branche_gpu_preservee():
    """ADR §4 : les accélérateurs ne sont JAMAIS dans les classes — la branche nvidia est
    orthogonale au schéma CPU/mémoire et reste inchangée."""
    svc = ServiceSpec(name="ollama", image="ollama/ollama:latest", host_port=21434,
                      container_port=11434, gpu=True, gpu_vendor="nvidia", resource_class="llm")
    res = _res_du_manifeste(render_k3s(_plan_res([svc])), "ollama")
    assert res["limits"]["nvidia.com/gpu"] in ("1", 1)
    assert res["limits"]["memory"] == "8Gi", "la classe llm gouverne toujours la RAM"


def test_compose_name_derive_du_plan_id():
    plan = _plan()
    out = render_compose(plan)
    assert f"name: {plan.plan_id}" in out
    assert "name: forgeai-minimal" not in out


def test_compose_deux_plans_identites_disjointes():
    plan_a = _plan()
    plan_b = DeploymentPlan(
        plan_id="p1-autre-plan", profile=plan_a.profile, target=plan_a.target,
        services=plan_a.services, model=plan_a.model, embed_model=plan_a.embed_model,
    )
    name_a = [l for l in render_compose(plan_a).splitlines() if l.startswith("name:")][0]
    name_b = [l for l in render_compose(plan_b).splitlines() if l.startswith("name:")][0]
    assert name_a != name_b


def test_compose_meme_plan_id_identite_stable():
    """Reprise sur état existant : re-rendre le MÊME plan (même plan_id) produit
    TOUJOURS la même identité — un `docker compose up` répété reconnecte la pile
    existante au lieu d'en créer une nouvelle sous un nom différent."""
    plan = _plan()
    name_1 = [l for l in render_compose(plan).splitlines() if l.startswith("name:")][0]
    name_2 = [l for l in render_compose(plan).splitlines() if l.startswith("name:")][0]
    assert name_1 == name_2


def test_compose_identite_rendu_correspond_a_celle_du_healthcheck():
    """Ferme la boucle rendu -> _etats_docker sans nécessiter de vrai daemon Docker :
    l'identité extraite du YAML rendu doit être EXACTEMENT celle que _etats_docker()
    interroge déjà via `-p str(plan.plan_id)` (#586)."""
    plan = _plan()
    name_line = [l for l in render_compose(plan).splitlines() if l.startswith("name:")][0]
    assert name_line == f"name: {plan.plan_id}"
