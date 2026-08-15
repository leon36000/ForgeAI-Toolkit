from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "governance" / "capabilities.py"
_spec = importlib.util.spec_from_file_location("capabilities", SCRIPT)
capabilities = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(capabilities)


def _by_name(items: list[dict], name: str) -> dict:
    return next(item for item in items if item["name"] == name)


def test_python3_available_si_version_suffisante() -> None:
    item = _by_name(capabilities.probe_capabilities(env={}), "python3")
    assert sys.version_info >= (3, 10)
    assert item["status"] == "AVAILABLE"


def test_git_blocked_si_absent(monkeypatch) -> None:
    monkeypatch.setattr(capabilities.shutil, "which", lambda name: None if name == "git" else "/bin/tool")

    item = _by_name(capabilities.probe_capabilities(env={}), "git")

    assert item["status"] == "BLOCKED"


def test_pre_commit_local_optional_si_binaire_pre_commit_absent(monkeypatch) -> None:
    # Régression revue scellée RC1-003-PR489-v3 (objection mineure DeepSeek-V4-Pro) :
    # ggshield et ruff présents mais le binaire `pre-commit` lui-même absent doit toujours
    # rapporter OPTIONAL (pre-commit install échouerait sinon silencieusement).
    monkeypatch.setattr(
        capabilities.shutil,
        "which",
        lambda name: None if name == "pre-commit" else "/bin/tool",
    )

    item = _by_name(capabilities.probe_capabilities(env={}), "pre-commit local (ggshield+ruff)")

    assert item["status"] == "OPTIONAL"
    assert "pre-commit" in item["howto"]


def test_pytest_optional_et_seul_gate_tests_affecte(monkeypatch) -> None:
    class Result:
        returncode = 1
        stdout = ""
        stderr = ""

    monkeypatch.setattr(capabilities, "_run_available", lambda command: False if "pytest" in command else True)

    item = _by_name(capabilities.probe_capabilities(env={}), "pytest")

    assert item["status"] == "OPTIONAL"
    assert "tests" in item["enables"]
    assert "no-stub-scan" not in item["enables"]
    assert "registres" not in item["enables"]


def test_revue_scellee_optional_si_env_incomplet() -> None:
    item = _by_name(
        capabilities.probe_capabilities(env={}),
        "revue aveugle scellée (outillage externe)",
    )

    assert item["status"] == "OPTIONAL"


def test_revue_scellee_available_si_les_3_signaux_presents(monkeypatch) -> None:
    monkeypatch.setattr(capabilities.Path, "home", classmethod(lambda cls: Path("/tmp/home")))
    original_exists = capabilities.Path.exists

    def exists(path: Path) -> bool:
        if str(path).endswith("proof-method/scripts/civ_review.py"):
            return True
        return original_exists(path)

    monkeypatch.setattr(capabilities.Path, "exists", exists)
    item = _by_name(
        capabilities.probe_capabilities(
            env={
                "LITELLM_API_KEY": "peu-importe",
                "LITELLM_BASE_URL": "http://localhost:4000",
            }
        ),
        "revue aveugle scellée (outillage externe)",
    )

    assert item["status"] == "AVAILABLE"


def test_revue_scellee_optional_si_path_home_leve_runtimeerror(monkeypatch) -> None:
    # Régression revue scellée RC1-003-PR489-v2 : Path.home() lève RuntimeError si HOME est
    # absent et qu'aucune base d'utilisateurs n'est résoluble — le diagnostic ne doit jamais
    # planter, seulement rapporter la capacité comme OPTIONAL.
    def raise_runtime_error(cls):
        raise RuntimeError("impossible de déterminer le répertoire personnel")

    monkeypatch.setattr(capabilities.Path, "home", classmethod(raise_runtime_error))

    item = _by_name(
        capabilities.probe_capabilities(env={}),
        "revue aveugle scellée (outillage externe)",
    )

    assert item["status"] == "OPTIONAL"


def test_aucune_valeur_de_secret_dans_la_sortie() -> None:
    env = {
        "LITELLM_API_KEY": "VALEUR_SENTINELLE_INTERDITE_XYZ",
        "LITELLM_BASE_URL": "http://localhost:4000",
    }
    found = capabilities.probe_capabilities(env=env)
    rendered = capabilities.render_report(found)
    rendered_json = json.dumps(found)

    assert "VALEUR_SENTINELLE_INTERDITE_XYZ" not in rendered
    assert "VALEUR_SENTINELLE_INTERDITE_XYZ" not in rendered_json
    assert "docker inspect" not in rendered
    assert "sed -n" not in rendered


def test_hooks_git_globaux_jamais_bloquant(monkeypatch) -> None:
    class Absent:
        returncode = 1
        stdout = ""
        stderr = ""

    class Present:
        returncode = 0
        stdout = "/hooks\n"
        stderr = ""

    monkeypatch.setattr(capabilities.subprocess, "run", lambda *args, **kwargs: Absent())
    absent = _by_name(capabilities.probe_capabilities(env={}), "hooks git globaux")
    monkeypatch.setattr(capabilities.subprocess, "run", lambda *args, **kwargs: Present())
    present = _by_name(capabilities.probe_capabilities(env={}), "hooks git globaux")

    assert absent["status"] != "BLOCKED"
    assert present["status"] != "BLOCKED"


def test_render_report_stable_et_lisible() -> None:
    items = [
        {
            "name": "alpha",
            "status": "AVAILABLE",
            "enables": "fonction alpha",
            "howto": "aucune action",
        },
        {
            "name": "beta",
            "status": "OPTIONAL",
            "enables": "fonction beta",
            "howto": "installez beta",
        },
    ]

    rendered = capabilities.render_report(items)

    assert rendered
    assert "alpha" in rendered
    assert "beta" in rendered


def test_main_json_mode_produit_un_json_valide(monkeypatch, capsys) -> None:
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), "--json"])

    rc = capabilities.main()

    assert rc == 0
    assert isinstance(json.loads(capsys.readouterr().out), list)


def test_main_exit_code_toujours_zero(monkeypatch) -> None:
    monkeypatch.setattr(
        capabilities,
        "probe_capabilities",
        lambda: [
            {
                "name": "python3",
                "status": "BLOCKED",
                "enables": "gates",
                "howto": "installez python",
            }
        ],
    )
    monkeypatch.setattr(sys, "argv", [str(SCRIPT)])

    assert capabilities.main() == 0
