import json
import pytest
from forgeai.resources import catalogue_path
from forgeai.templates import (
    TemplateError,
    list_templates,
    load_template,
    validate_template,
    resolve_template,
    deployable_bricks,
)


def load_catalogue_entries():
    data = json.loads(catalogue_path().read_text(encoding="utf-8"))
    return data["entries"]


def test_dev_agentic_a_37_briques():
    t = load_template("dev-agentic")
    assert len(t["bricks"]) == 37


def test_toutes_briques_au_catalogue_et_bilingues():
    entries = load_catalogue_entries()
    t = load_template("dev-agentic")
    violations = validate_template(t, entries)
    assert violations == [], f"Violations trouvées : {violations}"


def test_filtrage_hardware_inference():
    t = load_template("dev-agentic")
    ids_no_gpu = [b["id"] for b in resolve_template(t, has_gpu=False)]
    assert not any("vllm" in bid for bid in ids_no_gpu), "vllm présent sans GPU"
    assert any("ollama" in bid for bid in ids_no_gpu), "ollama absent sans GPU"

    ids_gpu = [b["id"] for b in resolve_template(t, has_gpu=True)]
    assert any("vllm" in bid for bid in ids_gpu), "vllm absent avec GPU"


def test_deployables_non_vide():
    t = load_template("dev-agentic")
    deps = deployable_bricks(t, has_gpu=False)
    assert len(deps) > 0, "Aucune brique déployable sans GPU"
    assert all(b.get("deployable") is True for b in deps)


def test_defauts_etoile_presents():
    t = load_template("dev-agentic")
    defaults = [b for b in t["bricks"] if b.get("default") is True]
    assert len(defaults) >= 5, f"Seulement {len(defaults)} brique(s) par défaut"


def test_template_inconnu_leve():
    with pytest.raises(TemplateError):
        load_template("inexistant")


def test_list_templates_contient_dev_agentic():
    templates = list_templates()
    assert "dev-agentic" in templates


def test_cli_template_list_show_resolve(tmp_path, capsys):
    """Chemin CLI : list, show (validation catalogue), resolve --no-gpu (filtrage inférence)."""
    from forgeai.cli import main

    assert main(["template", "list"]) == 0
    assert "dev-agentic" in capsys.readouterr().out

    assert main(["template", "show", "dev-agentic"]) == 0
    assert "conforme" in capsys.readouterr().out

    reg = tmp_path / "r.jsonl"
    assert main(["template", "resolve", "dev-agentic", "--no-gpu", "--registre", str(reg)]) == 0
    out = capsys.readouterr().out
    assert "ollama" in out and "vllm" not in out
    assert "template_resolve" in reg.read_text(encoding="utf-8")
