"""Tests E1a — châssis déployable et branché (socle CPU)."""
from __future__ import annotations

import json
from pathlib import Path

from forgeai.core.models import DeploymentPlan, RenderTarget, ServiceSpec
from forgeai.planner.assemble import assemble_plan, _load_deploy_specs
from forgeai.renderers.compose import render_compose


SOCLE_BRICKS = (
    "litellm",
    "redis",
    "qdrant",
    "text-embeddings-inference-tei",
    "immudb",
    "openbao",
)


def _minimal_overlay(tmp_path: Path) -> Path:
    """Fournit un overlay minimal utilisable par assemble_plan."""
    try:
        from importlib.resources import files

        ref = files("forgeai.data") / "deploy-minimal.json"
        if ref.is_file():
            return Path(str(ref))
    except Exception:
        pass

    overlay = tmp_path / "deploy-minimal.json"
    overlay.write_text(
        json.dumps(
            {
                "models": {
                    "llm": "llama3.1:8b",
                    "embed": "nomic-embed-text:latest",
                },
                "services": [
                    {
                        "name": "ollama",
                        "image": "ollama/ollama:latest",
                        "container_port": 11434,
                        "volume": None,
                        "healthcheck_path": None,
                        "gpu_capable": True,
                    },
                    {
                        "name": "qdrant",
                        "image": "qdrant/qdrant:v1.18.3",
                        "container_port": 6333,
                        "volume": "forgeai-qdrant-data:/qdrant/storage",
                        "healthcheck_path": "/readyz",
                        "gpu_capable": False,
                    },
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return overlay


# Valeurs de healthcheck VÉRIFIÉES contre la réalité (endpoints canoniques) :
# - litellm /health/liveliness : confirmé HTTP 200 sur le conteneur en marche
#   (berriai/litellm) — la graphie "liveliness" est l'endpoint officiel, pas un typo.
# - qdrant /readyz, TEI /health, openbao /v1/sys/health : endpoints documentés.
# redis et immudb n'exposent pas de HTTP → health_path null (sonde par port/TCP).
HEALTH_PATHS_ATTENDUS = {
    "litellm": "/health/liveliness",
    "redis": None,
    "qdrant": "/readyz",
    "text-embeddings-inference-tei": "/health",
    "immudb": None,
    "openbao": "/v1/sys/health",
}


def test_specs_socle_present():
    specs = _load_deploy_specs()
    for brick in SOCLE_BRICKS:
        assert brick in specs, f"brique {brick} absente de deploy-specs.json"
        spec = specs[brick]
        assert "image" in spec, f"{brick} : champ image manquant"
        assert "container_port" in spec, f"{brick} : champ container_port manquant"
        assert ":" in spec["image"], f"{brick} : image sans tag"


def test_specs_health_path_exacts():
    """Verrouille la VALEUR exacte de chaque health_path (pas juste sa présence)."""
    specs = _load_deploy_specs()
    for brick, attendu in HEALTH_PATHS_ATTENDUS.items():
        spec = specs[brick]
        assert "health_path" in spec, f"{brick} : champ health_path manquant"
        assert spec["health_path"] == attendu, (
            f"{brick} : health_path={spec['health_path']!r}, attendu {attendu!r}"
        )


def test_assemble_consomme_env_depends(tmp_path: Path):
    overlay = _minimal_overlay(tmp_path)
    plan = assemble_plan(
        profile="minimal-cpu",
        deploy_overlay=overlay,
        extra_bricks=("litellm", "redis", "qdrant"),
    )
    by_name = {s.name: s for s in plan.services}

    assert "litellm" in by_name
    litellm = by_name["litellm"]
    assert litellm.env, "litellm doit avoir des variables d'environnement"
    assert "LITELLM_MASTER_KEY" in litellm.env
    # ollama fait partie du socle minimal, donc la dépendance est conservée.
    assert "ollama" in litellm.depends
    # Les dépendances absentes du plan doivent être filtrées.
    assert "inexistant" not in litellm.depends

    assert "redis" in by_name
    assert "qdrant" in by_name


def test_compose_emet_environment_depends():
    plan = DeploymentPlan(
        plan_id="test-env-dep",
        profile="minimal-cpu",
        target=RenderTarget.COMPOSE,
        services=(
            ServiceSpec(
                name="svc",
                image="busybox:latest",
                host_port=18080,
                container_port=80,
                env={"K": "v"},
                depends=("redis",),
            ),
            ServiceSpec(
                name="redis",
                image="redis:7.4.9",
                host_port=16379,
                container_port=6379,
            ),
        ),
        model="llama3.1:8b",
        embed_model="nomic-embed-text:latest",
    )
    yaml = render_compose(plan)

    assert "environment:" in yaml
    # Valeur entre guillemets (protège les caractères YAML spéciaux).
    assert 'K: "v"' in yaml
    assert "depends_on:" in yaml
    assert "- redis" in yaml


def test_compose_socle_branché(tmp_path: Path):
    overlay = _minimal_overlay(tmp_path)
    plan = assemble_plan(
        profile="minimal-cpu",
        deploy_overlay=overlay,
        extra_bricks=("litellm", "redis", "qdrant"),
    )
    yaml = render_compose(plan)

    assert "image: ghcr.io/berriai/litellm:main-stable" in yaml
    assert "image: redis:7.4.9" in yaml
    assert "image: qdrant/qdrant:v1.18.3" in yaml
    assert "depends_on:" in yaml
    assert "- ollama" in yaml
    # Le secret de wiring est une référence env quotée, jamais une valeur en clair.
    assert 'LITELLM_MASTER_KEY: "${FORGEAI_LITELLM_KEY}"' in yaml


def test_depends_ordre_independant(tmp_path: Path, monkeypatch):
    """Une dépendance vers une brique traitée PLUS TARD survit au filtrage."""
    from forgeai.planner import assemble as asm

    fake_specs = {
        # alpha (traité en premier) dépend de beta (ajouté après lui).
        "alpha": {"image": "alpha:1", "container_port": 9001, "depends": ["beta"]},
        "beta": {"image": "beta:1", "container_port": 9002, "depends": []},
    }
    monkeypatch.setattr(asm, "_load_deploy_specs", lambda: fake_specs)
    overlay = _minimal_overlay(tmp_path)
    plan = asm.assemble_plan(
        profile="minimal-cpu",
        deploy_overlay=overlay,
        extra_bricks=("alpha", "beta"),
    )
    by_name = {s.name: s for s in plan.services}
    assert "alpha" in by_name and "beta" in by_name
    # La dépendance alpha→beta n'est PAS perdue malgré l'ordre de traitement.
    assert "beta" in by_name["alpha"].depends


def test_retrocompat_minimal(tmp_path: Path):
    overlay = _minimal_overlay(tmp_path)
    plan = assemble_plan(
        profile="minimal-cpu",
        deploy_overlay=overlay,
    )
    names = {s.name for s in plan.services}

    assert "ollama" in names
    assert "vector-store" in names  # nom du service qdrant dans l'overlay minimal
    assert "litellm" not in names
    assert "redis" not in names
