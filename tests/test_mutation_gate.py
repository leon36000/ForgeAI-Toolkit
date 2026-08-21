from __future__ import annotations

from pathlib import Path

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
