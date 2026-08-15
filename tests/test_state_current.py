from __future__ import annotations

import hashlib
import importlib.util
import json
import pathlib
import socket
import subprocess
import sys
import urllib.request
from typing import Any

import jsonschema
import pytest

_MODULE_PATH = (
    pathlib.Path(__file__).resolve().parents[1]
    / "scripts"
    / "governance"
    / "state_current.py"
)
_spec = importlib.util.spec_from_file_location("state_current", _MODULE_PATH)
state_current = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(state_current)

REPO = pathlib.Path(__file__).resolve().parents[1]


def _write_json(path: pathlib.Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _catalogue_digest(catalogue_path: pathlib.Path) -> str:
    return hashlib.sha256(
        catalogue_path.read_bytes().replace(b"\r\n", b"\n")
    ).hexdigest()


def _write_catalogue(repo_root: pathlib.Path, entries: list[dict[str, str]]) -> None:
    catalogue_path = repo_root / "src" / "forgeai" / "data" / "catalogue.json"
    _write_json(catalogue_path, {"entries": entries})
    catalogue_path.with_suffix(".json.sha256").write_text(
        _catalogue_digest(catalogue_path) + "\n",
        encoding="utf-8",
    )


def _write_observations(
    repo_root: pathlib.Path,
    observations: list[dict[str, Any]] | None = None,
) -> None:
    _write_json(
        repo_root / "governance" / "state-observations.json",
        observations
        if observations is not None
        else [
            {
                "id": "fixture-observation",
                "value": "fixture",
                "display": "Observation de fixture",
                "observed_at": "2025-01-01T00:00:00Z",
                "source": "fixture locale",
                "evidence": "governance/state-observations.json",
                "sealed": False,
                "command": "fixture",
            }
        ],
    )


def _write_fixture_repo(tmp_path: pathlib.Path) -> pathlib.Path:
    (tmp_path / "src" / "forgeai" / "data").mkdir(parents=True)
    (tmp_path / "tests").mkdir()
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / "coordination").mkdir()

    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "forgeai"
version = "9.9.9"
requires-python = ">=3.11"
dependencies = ["alpha>=1", "beta>=2"]
""".lstrip(),
        encoding="utf-8",
    )
    (tmp_path / "src" / "forgeai" / "__init__.py").write_text(
        '__version__ = "9.9.9"\n',
        encoding="utf-8",
    )
    _write_catalogue(
        tmp_path,
        [
            {
                "name": "brique-a",
                "description_en": "Première brique de fixture.",
                "category": "base",
            },
            {
                "name": "brique-b",
                "description_en": "Deuxième brique de fixture.",
                "category": "base",
            },
            {
                "name": "brique-c",
                "description_en": "Troisième brique de fixture.",
                "category": "avancée",
            },
        ],
    )
    (tmp_path / "tests" / "test_alpha.py").write_text(
        """
def test_alpha_un():
    assert 1 == 1


def test_alpha_deux():
    assert 2 == 2


def test_alpha_trois():
    assert 3 == 3
""".lstrip(),
        encoding="utf-8",
    )
    (tmp_path / "tests" / "test_beta.py").write_text(
        """
def test_beta_un():
    assert "a" == "a"


def test_beta_deux():
    assert "b" == "b"
""".lstrip(),
        encoding="utf-8",
    )
    (tmp_path / ".github" / "workflows" / "checks.yml").write_text(
        """
name: Checks
on: [push]
jobs:
  unit:
    runs-on: ubuntu-latest
    steps:
      - run: python -m pytest
  lint:
    runs-on: ubuntu-latest
    steps:
      - run: python -m compileall src
""".lstrip(),
        encoding="utf-8",
    )
    _write_json(
        tmp_path / "coordination" / "work-packages.json",
        [{"id": "wp-a"}, {"id": "wp-b"}],
    )
    _write_json(
        tmp_path / "coordination" / "active-claims.json",
        [{"id": "claim-a", "concurrency": "catalogue"}],
    )
    _write_observations(tmp_path)
    return tmp_path


def _write_state_files(repo_root: pathlib.Path) -> dict[str, Any]:
    state = state_current.build_state(repo_root)
    _write_json(repo_root / "governance" / "STATE-CURRENT.json", state)
    (repo_root / "governance" / "STATE-CURRENT.md").write_text(
        state_current.render(state),
        encoding="utf-8",
    )
    return state


def _assert_no_forbidden_time_keys(value: Any) -> None:
    if isinstance(value, dict):
        forbidden = {"generated_at", "timestamp", "head_commit", "generated_on"}
        assert not (set(value) & forbidden)
        for child in value.values():
            _assert_no_forbidden_time_keys(child)
    elif isinstance(value, list):
        for child in value:
            _assert_no_forbidden_time_keys(child)


def test_deux_generations_identiques() -> None:
    first = state_current.build_state(REPO)
    second = state_current.build_state(REPO)

    assert first == second
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_aucun_horodatage_dans_le_bloc_deterministe() -> None:
    deterministic = state_current.collect(REPO)

    _assert_no_forbidden_time_keys(deterministic)
    assert deterministic["_schema"] == "state-current-v1"


def test_aucun_acces_reseau(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden_network(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("réseau interdit")

    monkeypatch.setattr(socket, "socket", forbidden_network)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden_network)

    deterministic = state_current.collect(REPO)
    state = state_current.build_state(REPO)

    assert deterministic["_schema"] == "state-current-v1"
    assert state["deterministe"] == deterministic


def test_aucun_subprocess(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden_subprocess(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("subprocess interdit")

    monkeypatch.setattr(subprocess, "run", forbidden_subprocess)
    monkeypatch.setattr(subprocess, "Popen", forbidden_subprocess)

    deterministic = state_current.collect(REPO)
    state = state_current.build_state(REPO)

    assert deterministic["_schema"] == "state-current-v1"
    assert state["deterministe"] == deterministic


def test_valeurs_correctes_sur_etat_connu(tmp_path: pathlib.Path) -> None:
    repo_root = _write_fixture_repo(tmp_path)

    state = state_current.collect(repo_root)

    assert state["package"] == {
        "name": "forgeai",
        "version": "9.9.9",
        "version_pyproject": "9.9.9",
        "requires_python": ">=3.11",
        "runtime_dependencies": ["alpha>=1", "beta>=2"],
    }
    assert state["catalogue"]["entries_total"] == 3
    assert state["catalogue"]["sha256_recomputed_ok"] is True
    assert state["catalogue"]["descriptions_en_missing"] == 0
    assert state["catalogue"]["categories_total"] == 2
    assert state["tests"]["python_files"] == 2
    assert state["tests"]["python_functions_declared"] == 5
    assert state["tests"]["js_files"] == 0
    assert state["ci"]["workflows"] == 1
    assert state["ci"]["jobs_total"] == 2
    assert state["coordination"]["work_packages_total"] == 2
    assert state["coordination"]["active_claims_total"] == 1
    assert state["coordination"]["concurrency_total"] == 1


def test_version_divergente_pyproject_init_rejetee(tmp_path: pathlib.Path) -> None:
    repo_root = _write_fixture_repo(tmp_path)
    (repo_root / "pyproject.toml").write_text(
        """
[project]
name = "forgeai"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = []
""".lstrip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError) as raised:
        state_current.collect(repo_root)

    message = str(raised.value)
    assert "pyproject.toml" in message
    assert "__init__.py" in message
    assert "0.1.0" in message
    assert "9.9.9" in message


def test_catalogue_sha256_non_conforme_signale(tmp_path: pathlib.Path) -> None:
    repo_root = _write_fixture_repo(tmp_path)
    sidecar = repo_root / "src" / "forgeai" / "data" / "catalogue.json.sha256"
    sidecar.write_text("0" * 64 + "\n", encoding="utf-8")

    state = state_current.collect(repo_root)

    assert state["catalogue"]["sha256_recomputed_ok"] is False


def test_chemin_hors_depot_rejete(tmp_path: pathlib.Path) -> None:
    repo_root = _write_fixture_repo(tmp_path)

    with pytest.raises(ValueError) as raised:
        state_current._within_repo(repo_root, repo_root / "../../etc/passwd")

    assert "hors" in str(raised.value).lower()


def test_rendu_markdown_contient_lentete_ne_pas_editer(tmp_path: pathlib.Path) -> None:
    state = state_current.build_state(_write_fixture_repo(tmp_path))

    markdown = state_current.render(state)

    assert (
        "NE PAS ÉDITER À LA MAIN — généré par "
        "scripts/governance/state_current.py --render"
    ) in markdown


def test_rendu_marque_les_observations_comme_non_scellees(
    tmp_path: pathlib.Path,
) -> None:
    state = state_current.build_state(_write_fixture_repo(tmp_path))

    markdown = state_current.render(state)

    assert "observation horodatée, non scellée — hors chaîne de preuve du dépôt" in markdown
    assert "Observation de fixture" in markdown


def test_injection_remplace_la_valeur_entre_marqueurs() -> None:
    text = "Le total est <!-- state:catalogue.entries_total -->999<!-- /state --> aujourd'hui."
    state = {"deterministe": {"catalogue": {"entries_total": 3}}, "observations": []}

    rendered, replacements = state_current.inject(text, state, "document.md")

    assert ">3<" in rendered
    assert ">999<" not in rendered
    assert replacements == ["catalogue.entries_total : 999 -> 3"]


def test_injection_preserve_le_reste_du_fichier() -> None:
    prefix = "Préfixe exact.\n"
    suffix = "\nSuffixe exact, accents inclus : é.\n"
    text = (
        prefix
        + "<!-- state:catalogue.entries_total -->999<!-- /state -->"
        + suffix
    )
    state = {"deterministe": {"catalogue": {"entries_total": 3}}, "observations": []}

    rendered, replacements = state_current.inject(text, state, "document.md")

    assert rendered.startswith(prefix)
    assert rendered.endswith(suffix)
    assert replacements == ["catalogue.entries_total : 999 -> 3"]


def test_injection_marqueur_observations_resout_par_id() -> None:
    state = {
        "deterministe": {},
        "observations": [{"id": "coverage.global", "display": "94"}],
    }

    rendered, _ = state_current.inject(
        "Couverture <!-- state:observations.coverage.global -->92<!-- /state --> %.",
        state,
        "test.md",
    )

    assert (
        rendered
        == "Couverture <!-- state:observations.coverage.global -->94<!-- /state --> %."
    )
    assert ">94<" in rendered
    assert ">92<" not in rendered


def test_injection_chemin_inconnu_leve() -> None:
    text = "<!-- state:nexiste.pas -->ancienne<!-- /state -->"
    state = {"deterministe": {}, "observations": []}

    with pytest.raises(KeyError) as raised:
        state_current.inject(text, state, "document.md")

    assert "nexiste.pas" in str(raised.value)


def test_injection_marqueurs_desequilibres_leve() -> None:
    text = "Valeur <!-- state:catalogue.entries_total -->ancienne"
    state = {"deterministe": {"catalogue": {"entries_total": 3}}, "observations": []}

    with pytest.raises(ValueError) as raised:
        state_current.inject(text, state, "document.md")

    assert "marqueur" in str(raised.value).lower()


def test_format_value_totale() -> None:
    assert state_current.format_value(3) == "3"
    assert state_current.format_value("x") == "x"
    with pytest.raises(TypeError):
        state_current.format_value(3.5)
    with pytest.raises(TypeError):
        state_current.format_value(None)


def test_derive_de_compteur_detectee(tmp_path: pathlib.Path) -> None:
    repo_root = _write_fixture_repo(tmp_path)
    _write_state_files(repo_root)
    _write_catalogue(
        repo_root,
        [
            {
                "name": "brique-a",
                "description_en": "Première brique de fixture.",
                "category": "base",
            },
            {
                "name": "brique-b",
                "description_en": "Deuxième brique de fixture.",
                "category": "base",
            },
            {
                "name": "brique-c",
                "description_en": "Troisième brique de fixture.",
                "category": "avancée",
            },
            {
                "name": "brique-d",
                "description_en": "Quatrième brique de fixture.",
                "category": "avancée",
            },
        ],
    )

    ok, errors = state_current.check(repo_root)

    assert not ok
    assert any("catalogue.entries_total" in error for error in errors)
    assert errors[-1] == "corriger par : python3 scripts/governance/state_current.py --render"


def test_derive_sans_changement_de_compteur_detectee(tmp_path: pathlib.Path) -> None:
    repo_root = _write_fixture_repo(tmp_path)
    _write_state_files(repo_root)
    _write_catalogue(
        repo_root,
        [
            {
                "name": "brique-renommee",
                "description_en": "Première brique de fixture.",
                "category": "base",
            },
            {
                "name": "brique-b",
                "description_en": "Deuxième brique de fixture.",
                "category": "base",
            },
            {
                "name": "brique-c",
                "description_en": "Troisième brique de fixture.",
                "category": "avancée",
            },
        ],
    )

    ok, errors = state_current.check(repo_root)

    assert not ok
    assert any("inputs" in error for error in errors)
    assert errors[-1] == "corriger par : python3 scripts/governance/state_current.py --render"


def test_rendu_markdown_desynchronise_rejete(tmp_path: pathlib.Path) -> None:
    repo_root = _write_fixture_repo(tmp_path)
    _write_state_files(repo_root)
    (repo_root / "governance" / "STATE-CURRENT.md").write_text(
        "# Modification manuelle\n",
        encoding="utf-8",
    )

    ok, errors = state_current.check(repo_root)

    assert not ok
    assert any("STATE-CURRENT.md" in error or "rendu" in error for error in errors)


def test_etat_reel_du_depot_passe_le_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [str(_MODULE_PATH), "--repo-root", str(REPO), "--render"],
    )

    rendered = state_current.main()
    ok, errors = state_current.check(REPO)

    assert rendered == 0
    assert ok
    assert errors == []


def test_state_current_valide_contre_son_schema() -> None:
    schema = json.loads(
        (REPO / "governance" / "state-current.schema.json").read_text(
            encoding="utf-8"
        )
    )
    data = json.loads(
        (REPO / "governance" / "STATE-CURRENT.json").read_text(encoding="utf-8")
    )

    jsonschema.Draft202012Validator(schema).validate(data)


def test_subcommands_by_group_compte_node_a_sept() -> None:
    state = state_current.collect(REPO)

    assert state["cli"]["subcommands_by_group"]["node"] == 7


def test_observation_sans_provenance_rejetee(tmp_path: pathlib.Path) -> None:
    observations_path = tmp_path / "state-observations.json"
    _write_json(
        observations_path,
        [
            {
                "id": "sans-date",
                "value": "x",
                "display": "Sans date",
                "source": "fixture locale",
                "evidence": "preuve",
                "sealed": False,
                "command": "fixture",
            }
        ],
    )

    with pytest.raises(ValueError) as raised:
        state_current.load_observations(observations_path)

    assert "observed_at" in str(raised.value)


def test_observation_reseau_doit_etre_non_scellee(tmp_path: pathlib.Path) -> None:
    observations_path = tmp_path / "state-observations.json"
    _write_json(
        observations_path,
        [
            {
                "id": "reseau",
                "value": "x",
                "display": "Observation réseau",
                "observed_at": "2025-01-01T00:00:00Z",
                "source": "gh api repos/example/project",
                "evidence": "réponse distante",
                "sealed": True,
                "command": "gh api repos/example/project",
            }
        ],
    )

    with pytest.raises(ValueError) as raised:
        state_current.load_observations(observations_path)

    assert "scell" in str(raised.value).lower()


def test_observation_ancienne_nempeche_pas_ok(tmp_path: pathlib.Path) -> None:
    repo_root = _write_fixture_repo(tmp_path)
    _write_observations(
        repo_root,
        [
            {
                "id": "ancienne",
                "value": "x",
                "display": "Observation ancienne de fixture",
                "observed_at": "2024-01-01T00:00:00Z",
                "source": "fixture locale",
                "evidence": "archive locale",
                "sealed": False,
                "command": "fixture",
            }
        ],
    )
    _write_state_files(repo_root)

    ok, errors = state_current.check(repo_root)

    assert ok
    assert errors == []


def test_main_render_docs_reecrit_le_document(tmp_path: pathlib.Path) -> None:
    repo_root = _write_fixture_repo(tmp_path)
    document = repo_root / "doc.md"
    document.write_text(
        "Total: <!-- state:catalogue.entries_total -->999<!-- /state --> briques.\n",
        encoding="utf-8",
    )
    arguments = ["--repo-root", str(repo_root), "--render", "--docs", "doc.md"]

    assert state_current.main(arguments) == 0
    first_content = document.read_text(encoding="utf-8")

    assert ">3<" in first_content
    assert ">999<" not in first_content

    assert state_current.main(arguments) == 0
    assert document.read_text(encoding="utf-8") == first_content


def test_main_render_puis_check_sur_vrai_depot(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(REPO)
    monkeypatch.setattr(sys, "argv", [str(_MODULE_PATH), "--render"])

    rendered = state_current.main()
    output_rendered = capsys.readouterr()

    monkeypatch.setattr(sys, "argv", [str(_MODULE_PATH)])

    checked = state_current.main()
    output_checked = capsys.readouterr()

    assert rendered == 0
    assert checked == 0
    assert output_rendered.err == ""
    assert output_checked.err == ""
