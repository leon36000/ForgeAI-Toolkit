from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from scripts import mutation_gate


def test_mutations_ciblent_un_site_unique_et_des_contrats_distincts() -> None:
    assert mutation_gate.MUTATIONS
    assert len({m.identifiant for m in mutation_gate.MUTATIONS}) == len(mutation_gate.MUTATIONS)
    assert all(m.fichier == "src/forgeai/web/ratelimit.py" for m in mutation_gate.MUTATIONS)
    assert len({m.contrat for m in mutation_gate.MUTATIONS}) == len(mutation_gate.MUTATIONS)


def test_campagne_reelle_tue_les_mutants_de_garde() -> None:
    racine = Path(__file__).resolve().parent.parent
    rapport = mutation_gate.campagne(racine)

    assert rapport["statut"] == "PASS"
    assert rapport["survivants"] == 0
    assert rapport["tues"] == rapport["total"]


def test_code_retour_runner_non_nul_n_est_pas_une_preuve_de_mutant_tue(monkeypatch) -> None:
    racine = Path(__file__).resolve().parent.parent
    monkeypatch.setattr(
        mutation_gate.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=2, stdout="", stderr="erreur interne pytest"
        ),
    )

    rapport = mutation_gate.executer_mutation(racine, mutation_gate.MUTATIONS[0])

    assert rapport["statut"] == "runner-error"
    assert rapport["disposition"] == "FAIL: erreur du runner pytest (2)"


def test_timeout_runner_est_conserve_comme_erreur_bloquante(monkeypatch) -> None:
    racine = Path(__file__).resolve().parent.parent

    def lever_timeout(*args, **kwargs):
        raise mutation_gate.subprocess.TimeoutExpired(cmd=args[0], timeout=kwargs["timeout"])

    monkeypatch.setattr(mutation_gate.subprocess, "run", lever_timeout)

    rapport = mutation_gate.executer_mutation(racine, mutation_gate.MUTATIONS[0])

    assert rapport["statut"] == "runner-error"
    assert rapport["disposition"] == "FAIL: délai dépassé du runner pytest"
    assert rapport["code_retour"] is None


def test_erreur_preparation_est_rapportee_comme_erreur_runner(monkeypatch) -> None:
    racine = Path(__file__).resolve().parent.parent

    def lever_erreur(*args, **kwargs):
        raise RuntimeError("site de mutation non unique")

    monkeypatch.setattr(mutation_gate, "executer_mutation", lever_erreur)

    rapport = mutation_gate.campagne(racine)

    assert rapport["statut"] == "FAIL"
    assert rapport["erreurs_runner"] == rapport["total"]
    assert all(m["statut"] == "runner-error" for m in rapport["mutants"])
