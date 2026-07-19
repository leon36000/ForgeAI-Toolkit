"""P1 — fusion templates→stacks (décision 2026-07-19) : un seul système de profils.

Les anciens templates B-13/B-14 sont des ALIAS rétro-compatibles vers les stacks ;
les JSON dupliqués (data/templates/) ont été retirés."""
from importlib import resources

import pytest

from forgeai.stacks import deploy_ids, list_stacks
from forgeai.templates import (
    LEGACY_ALIASES,
    TemplateError,
    list_templates,
    load_template,
    resolve_alias,
)


def test_alias_herites_pointent_sur_des_stacks_reels():
    stacks = set(list_stacks())
    assert set(LEGACY_ALIASES.values()) <= stacks
    assert LEGACY_ALIASES["dev-agentic"] == "agentique"
    assert LEGACY_ALIASES["rag-souverain"] == "assistant-entreprise"
    assert LEGACY_ALIASES["lab-fine-tuning"] == "mlops"
    assert LEGACY_ALIASES["production-souveraine"] == "tout-en-un"


def test_list_templates_est_la_liste_des_stacks():
    assert list_templates() == sorted(list_stacks())


def test_load_template_via_alias_ou_id_direct():
    via_alias = load_template("dev-agentic")
    direct = load_template("agentique")
    assert via_alias == direct
    assert len(deploy_ids(via_alias)) == 72


def test_nom_inconnu_leve_template_error():
    with pytest.raises(TemplateError):
        resolve_alias("template-fantome")


def test_json_dupliques_retires():
    """Le format concurrent n'existe plus : data/templates/ ne doit plus être packagé."""
    data_dir = resources.files("forgeai.data")
    entries = [p.name for p in data_dir.iterdir()]
    assert "templates" not in entries or not any(
        f.name.endswith(".json") for f in (data_dir / "templates").iterdir()
    )
