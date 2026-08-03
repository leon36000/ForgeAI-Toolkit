"""Story B-10 (DM-5b) — stratégie modèle Cerveau/Équipe/Hybride.

Prouve : le choix détermine le nombre de slots ; écrit au canon ; tout changement produit
un diff explicite et n'est jamais appliqué silencieusement (le CLI exige --confirm).
"""
from __future__ import annotations

import json

import pytest

from forgeai.models.strategy import (
    StrategyError,
    StrategyStore,
    diff_specs,
    resolve_spec,
)


def test_cerveau_unique_un_seul_slot():
    spec = resolve_spec("cerveau-unique")
    assert spec.slot_count == 1 and spec.slots == ("generaliste",)


def test_equipe_multi_slots():
    spec = resolve_spec("equipe")
    assert spec.slot_count >= 3 and "orchestrateur" in spec.slots


def test_hybride_mixte():
    spec = resolve_spec("hybride")
    assert spec.slot_count >= 2 and any("local" in s for s in spec.slots)


def test_roles_personnalises():
    spec = resolve_spec("cerveau-unique", ["a", "a", " a "])  # dédup + strip
    assert spec.slots == ("a",)


def test_cerveau_unique_refuse_plusieurs_roles():
    with pytest.raises(StrategyError):
        resolve_spec("cerveau-unique", ["x", "y"])


def test_strategie_inconnue():
    with pytest.raises(StrategyError):
        resolve_spec("mega-brain")


def test_diff_ajout_retrait_conserve():
    old = resolve_spec("equipe")                       # 4 slots
    new = resolve_spec("cerveau-unique")               # 1 slot
    d = diff_specs(old, new)
    assert d.is_change
    assert "generaliste" in d.added
    assert "orchestrateur" in d.removed


def test_diff_identique_pas_de_changement():
    spec = resolve_spec("hybride")
    assert diff_specs(spec, spec).is_change is False


# ---------- canon du projet + reconfiguration ----------

def test_store_roundtrip_et_premiere_config(tmp_path):
    store = StrategyStore(tmp_path)
    assert store.get() is None
    new = resolve_spec("equipe")
    diff = store.plan_change(new)                       # première config = tout ajouté
    assert diff.added == new.slots and diff.removed == ()
    store.save(new)
    got = store.get()
    assert got == new
    # écrit au canon (fichier), slots lisibles
    data = json.loads((tmp_path / "strategy.json").read_text())
    assert data["strategy"] == "equipe" and data["slots"] == list(new.slots)


def test_plan_change_detecte_reconfiguration(tmp_path):
    store = StrategyStore(tmp_path)
    store.save(resolve_spec("equipe"))
    diff = store.plan_change(resolve_spec("cerveau-unique"))
    assert diff.is_change and diff.removed  # slots à retirer explicités


def test_cli_changement_jamais_silencieux(tmp_path, capsys):
    """CLI : 1re config OK ; changement SANS --confirm refusé (diff montré) ; AVEC --confirm appliqué."""
    from forgeai.cli import main
    home, reg = tmp_path / "m", tmp_path / "r.jsonl"

    # 1) première configuration : appliquée
    assert main(["strategy", "set", "--strategy", "equipe",
                 "--home", str(home), "--registre", str(reg)]) == 0
    assert StrategyStore(home).get().strategy == "equipe"

    # 2) changement SANS --confirm : refusé, diff affiché, stratégie INCHANGÉE
    rc = main(["strategy", "set", "--strategy", "cerveau-unique",
               "--home", str(home), "--registre", str(reg)])
    assert rc == 10
    err = capsys.readouterr().err
    assert "Reconfiguration" in err and "generaliste" in err
    assert StrategyStore(home).get().strategy == "equipe"   # non modifié (jamais silencieux)

    # 3) changement AVEC --confirm : appliqué
    assert main(["strategy", "set", "--strategy", "cerveau-unique", "--confirm",
                 "--home", str(home), "--registre", str(reg)]) == 0
    assert StrategyStore(home).get().strategy == "cerveau-unique"


def test_roles_perso_mauvais_nombre_rejete():
    with pytest.raises(StrategyError):
        resolve_spec("equipe", ["a", "b", "c"])
    with pytest.raises(StrategyError):
        resolve_spec("hybride", ["x", "y"])


def test_roles_perso_bon_nombre_ok():
    assert resolve_spec("equipe", ["a", "b", "c", "d"]).slots == ("a", "b", "c", "d")
    assert resolve_spec("hybride", ["p", "q", "r"]).slot_count == 3
