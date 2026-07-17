import json
import sys
from pathlib import Path

import pytest

# Ajoute le répertoire racine au path pour pouvoir importer scripts.plugin_gate
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.plugin_gate import (PluginError, REQUIRED_FIELDS, default_existence_check,
                                 validate_plugin, load_plugin, main)


def _valid_plugin():
    return {
        "id": "test-plugin",
        "name": "Test Plugin",
        "source_url": "https://github.com/user/repo",
        "license": "MIT",
        "healthcheck": {"type": "http", "url": "https://example.com/health"}
    }


def test_plugin_valide_accepte():
    result = validate_plugin(_valid_plugin(), existence_check=lambda u: True)
    assert result == []


def test_sans_healthcheck_refuse():
    p = _valid_plugin()
    del p["healthcheck"]
    result = validate_plugin(p)
    assert any("healthcheck" in v for v in result)


def test_sans_licence_refuse():
    p = _valid_plugin()
    del p["license"]
    result = validate_plugin(p)
    assert any("license" in v for v in result)


def test_source_url_non_https_refuse():
    p = _valid_plugin()
    p["source_url"] = "http://x"
    result = validate_plugin(p)
    assert any("source_url invalide" in v for v in result)


def test_existence_github_fausse_refuse():
    p = _valid_plugin()
    result = validate_plugin(p, existence_check=lambda u: False)
    assert any("source GitHub introuvable" in v for v in result)


def test_healthcheck_dict_sans_type_refuse():
    p = _valid_plugin()
    p["healthcheck"] = {"url": "x"}
    result = validate_plugin(p)
    assert any("healthcheck sans type" in v for v in result)


def test_main_retourne_1_sur_plugin_invalide(tmp_path):
    p = tmp_path / "plugin.json"
    p.write_text(json.dumps({}))
    rc = main(["--plugin", str(p), "--offline"])
    assert rc == 1


def test_main_offline_plugin_valide(tmp_path):
    p = tmp_path / "plugin.json"
    p.write_text(json.dumps(_valid_plugin()))
    rc = main(["--plugin", str(p), "--offline"])
    assert rc == 0
