"""Tests RC1-580 (#580) : agrégateur stable du contexte requis "tests".

Deux volets : (1) ``scripts/governance/verifier_agregat_tests.py`` — la
logique de vérification des dépendances CI, testée comme un module Python
ordinaire ; (2) la STRUCTURE de ``.github/workflows/gates.yml`` — vérifie que
le job agrégateur existe réellement, dépend de TOUS les gates bloquants
actuels, et ne peut jamais être silencieusement skip. Ce second volet lit le
VRAI fichier du dépôt (même motif déjà établi par
``tests/test_reg029b_ancrage.py::test_g11_le_gate_ci_appelle_reellement_les_controles``)
: un garde-fou testé mais absent du fichier réel serait vert partout et
n'aurait aucun effet.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parents[1]
GATES = RACINE / ".github" / "workflows" / "gates.yml"
SCRIPT = RACINE / "scripts" / "governance" / "verifier_agregat_tests.py"

spec = importlib.util.spec_from_file_location("verifier_agregat_tests", SCRIPT)
assert spec is not None and spec.loader is not None
vat = importlib.util.module_from_spec(spec)
sys.modules["verifier_agregat_tests"] = vat
spec.loader.exec_module(vat)


def _needs(**resultats: str) -> dict[str, dict[str, str]]:
    """Construit un contexte `needs` factice : {job: {"result": "..."}}."""
    return {nom: {"result": resultat} for nom, resultat in resultats.items()}


# --- gates_en_echec() : logique pure -----------------------------------


def test_gates_en_echec_tout_succes_retourne_vide() -> None:
    assert vat.gates_en_echec(_needs(a="success", b="success")) == {}


def test_gates_en_echec_une_defaillance_est_signalee() -> None:
    assert vat.gates_en_echec(_needs(a="success", b="failure")) == {"b": "failure"}


def test_gates_en_echec_un_skip_est_signale() -> None:
    """Cas CRITIQUE : un job skip compte comme succès pour GitHub, jamais ici."""
    assert vat.gates_en_echec(_needs(a="success", b="skipped")) == {"b": "skipped"}


def test_gates_en_echec_une_annulation_est_signalee() -> None:
    assert vat.gates_en_echec(_needs(a="success", b="cancelled")) == {"b": "cancelled"}


def test_gates_en_echec_plusieurs_defaillances_toutes_listees() -> None:
    resultat = vat.gates_en_echec(_needs(a="failure", b="skipped", c="success"))
    assert resultat == {"a": "failure", "b": "skipped"}


# --- main() : intégration via variable d'environnement -----------------


def test_main_tout_succes_retourne_zero(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("RESULTATS_NEEDS", json.dumps(_needs(a="success", b="success")))

    assert vat.main([]) == 0
    assert "OK" in capsys.readouterr().out


def test_main_une_defaillance_retourne_un(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("RESULTATS_NEEDS", json.dumps(_needs(a="success", b="failure")))

    assert vat.main([]) == 1
    assert "b" in capsys.readouterr().err


def test_main_un_skip_retourne_un(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("RESULTATS_NEEDS", json.dumps(_needs(a="success", b="skipped")))

    assert vat.main([]) == 1
    assert "skipped" in capsys.readouterr().err


def test_main_variable_absente_retourne_un(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("RESULTATS_NEEDS", raising=False)

    assert vat.main([]) == 1
    assert "absent" in capsys.readouterr().err


def test_main_variable_vide_retourne_un(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("RESULTATS_NEEDS", "")

    assert vat.main([]) == 1
    assert "absent" in capsys.readouterr().err


def test_main_json_invalide_retourne_un(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("RESULTATS_NEEDS", "{ceci n'est pas du JSON")

    assert vat.main([]) == 1
    assert "JSON" in capsys.readouterr().err


def test_main_json_liste_au_lieu_dobjet_retourne_un(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("RESULTATS_NEEDS", json.dumps(["success", "failure"]))

    assert vat.main([]) == 1
    assert "objet JSON" in capsys.readouterr().err


def test_main_objet_vide_retourne_un(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("RESULTATS_NEEDS", "{}")

    assert vat.main([]) == 1
    assert "objet JSON" in capsys.readouterr().err


# --- structure de gates.yml : pas de dérive silencieuse -----------------


def _charger_jobs_gates() -> dict:
    yaml = pytest.importorskip("yaml", reason="pyyaml est installé par le job `tests` de la CI")
    return yaml.safe_load(GATES.read_text(encoding="utf-8"))["jobs"]


def test_agregateur_tests_existe_avec_name_tests() -> None:
    jobs = _charger_jobs_gates()
    portant_name_tests = [jid for jid, j in jobs.items() if j.get("name") == "tests"]

    assert len(portant_name_tests) == 1, (
        "exactement un job doit porter name: tests (le contexte requis par la "
        "protection de branche) — jamais zéro, jamais plusieurs"
    )


def test_agregateur_tests_a_if_always() -> None:
    """Sans if: always(), l'agrégateur serait SKIPPED (donc compté SUCCÈS par
    GitHub) dès qu'une dépendance échoue — inverserait tout le correctif."""
    jobs = _charger_jobs_gates()
    aggregateur = next(j for j in jobs.values() if j.get("name") == "tests")

    assert aggregateur.get("if") == "always()"


def test_agregateur_tests_couvre_tous_les_gates_bloquants_de_gates_yml() -> None:
    """Garde-fou anti-dérive : si un futur gate bloquant est ajouté à
    gates.yml sans être ajouté aux needs: de l'agrégateur, ce test échoue —
    exactement le défaut racine que #580 corrige (un gate rouge invisible du
    contexte requis "tests")."""
    jobs = _charger_jobs_gates()
    aggregateur_id, aggregateur = next(
        (jid, j) for jid, j in jobs.items() if j.get("name") == "tests"
    )

    bloquants_attendus = {
        jid
        for jid, j in jobs.items()
        if jid != aggregateur_id and j.get("continue-on-error") is not True
    }
    needs = set(aggregateur.get("needs") or [])

    manquants = bloquants_attendus - needs
    assert not manquants, (
        f"gates bloquants absents de needs: de l'agrégateur : {sorted(manquants)}"
    )


def test_agregateur_tests_needs_ne_reference_aucun_job_inexistant() -> None:
    jobs = _charger_jobs_gates()
    aggregateur = next(j for j in jobs.values() if j.get("name") == "tests")
    needs = aggregateur.get("needs") or []

    inconnus = [n for n in needs if n not in jobs]
    assert not inconnus, f"needs: référence des jobs inexistants : {inconnus}"


def test_agregateur_tests_exclut_explicitement_rapport_composants() -> None:
    """rapport-composants (round #454) est délibérément non bloquant
    (continue-on-error: true) — vérifie qu'il n'est PAS dans needs: (sinon
    l'agrégateur bloquerait sur un gate qui n'a jamais dû bloquer)."""
    jobs = _charger_jobs_gates()
    aggregateur = next(j for j in jobs.values() if j.get("name") == "tests")

    assert jobs["rapport-composants"].get("continue-on-error") is True
    assert "rapport-composants" not in (aggregateur.get("needs") or [])


def test_agregateur_tests_invoque_le_script_de_verification() -> None:
    jobs = _charger_jobs_gates()
    aggregateur = next(j for j in jobs.values() if j.get("name") == "tests")
    commandes = " ".join(
        str(etape.get("run", "")) for etape in aggregateur.get("steps", [])
    )

    assert "verifier_agregat_tests.py" in commandes


def test_job_matriciel_tests_existant_garde_son_id_inchange() -> None:
    """Le job matriciel historique `tests` (id, pas name:) ne doit PAS être
    renommé — ses checks "tests (3.10)" etc. restent des noms stables,
    indépendants de ce nouvel agrégateur (id différent)."""
    jobs = _charger_jobs_gates()

    assert "tests" in jobs
    assert jobs["tests"].get("strategy", {}).get("matrix", {}).get("python-version")
    assert jobs["tests"].get("name") is None, (
        "le job matriciel historique ne doit pas avoir de name: -- sinon ses "
        "checks perdraient leur suffixe de matrice habituel"
    )
