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
