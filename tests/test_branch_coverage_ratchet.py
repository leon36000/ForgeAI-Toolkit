from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import branch_coverage_ratchet  # noqa: E402
import gate_git_ref  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ecrire_json(chemin: Path, data: dict) -> None:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _categories_deux() -> dict:
    return {
        "orchestrateurs": {
            "description": "Orchestration",
            "chemins": ["src/forgeai/cli.py", "src/forgeai/deploy/**"],
        },
        "securite": {
            "description": "Securite",
            "chemins": ["src/forgeai/secrets/**", "src/forgeai/models/vault*.py"],
        },
    }


def _baseline_deux(seuils: dict | None = None) -> dict:
    return {
        "_schema": "branch-coverage-baseline-v1",
        "seuil_global_initial_branches_pct": 90.0,
        "seuils_par_categorie": seuils if seuils is not None else {"orchestrateurs": 80.0, "securite": 80.0},
    }


def _rapport(files: dict) -> dict:
    return {"files": files}


def _fichier_summary(num: int, missing: int) -> dict:
    return {"summary": {"num_branches": num, "missing_branches": missing}}


def _ecrire_categories(racine: Path, data: dict) -> None:
    _ecrire_json(racine / "governance" / "branch-coverage-categories.json", data)


def _ecrire_baseline(racine: Path, data: dict) -> None:
    _ecrire_json(racine / "governance" / "branch-coverage-baseline.json", data)


def _ecrire_rapport_fichier(racine: Path, data: dict, nom: str = "branch-coverage.json") -> Path:
    chemin = racine / nom
    _ecrire_json(chemin, data)
    return chemin


def _reference_absente(*args: object, **kwargs: object) -> tuple[None, str]:
    return None, "reference absente"


# ---------------------------------------------------------------------------
# calculer_couverture_par_categorie
# ---------------------------------------------------------------------------

def test_calculer_agregation_plusieurs_fichiers_meme_categorie() -> None:
    categories = {
        "orchestrateurs": {"description": "x", "chemins": ["src/forgeai/deploy/**"]},
    }
    donnees = _rapport({
        "src/forgeai/deploy/a.py": _fichier_summary(10, 2),
        "src/forgeai/deploy/b.py": _fichier_summary(20, 4),
    })
    cov = branch_coverage_ratchet.calculer_couverture_par_categorie(donnees, categories)
    assert cov["orchestrateurs"]["num_branches"] == 30
    assert cov["orchestrateurs"]["missing_branches"] == 6
    assert cov["orchestrateurs"]["percent_branches_covered"] == pytest.approx(80.0)
    assert sorted(cov["orchestrateurs"]["fichiers"]) == ["src/forgeai/deploy/a.py", "src/forgeai/deploy/b.py"]


def test_calculer_fichier_ne_matchant_aucun_glob_exclu() -> None:
    categories = {
        "securite": {"description": "x", "chemins": ["src/forgeai/secrets/**"]},
    }
    donnees = _rapport({
        "src/forgeai/secrets/a.py": _fichier_summary(10, 1),
        "src/forgeai/other/b.py": _fichier_summary(100, 0),
    })
    cov = branch_coverage_ratchet.calculer_couverture_par_categorie(donnees, categories)
    assert cov["securite"]["num_branches"] == 10
    assert cov["securite"]["missing_branches"] == 1
    assert cov["securite"]["fichiers"] == ["src/forgeai/secrets/a.py"]


def test_calculer_categorie_sans_fichier_matche_vaut_100() -> None:
    categories = {
        "securite": {"description": "x", "chemins": ["src/forgeai/secrets/**"]},
    }
    donnees = _rapport({
        "src/forgeai/other/b.py": _fichier_summary(10, 5),
    })
    cov = branch_coverage_ratchet.calculer_couverture_par_categorie(donnees, categories)
    assert cov["securite"]["num_branches"] == 0
    assert cov["securite"]["missing_branches"] == 0
    assert cov["securite"]["percent_branches_covered"] == pytest.approx(100.0)
    assert cov["securite"]["fichiers"] == []


def test_calculer_matching_glob_double_etoile_dossier_entier() -> None:
    categories = {
        "orchestrateurs": {"description": "x", "chemins": ["src/forgeai/deploy/**"]},
    }
    donnees = _rapport({
        "src/forgeai/deploy/sub/nested.py": _fichier_summary(4, 1),
        "src/forgeai/deploy/a.py": _fichier_summary(6, 0),
    })
    cov = branch_coverage_ratchet.calculer_couverture_par_categorie(donnees, categories)
    assert cov["orchestrateurs"]["num_branches"] == 10
    assert cov["orchestrateurs"]["missing_branches"] == 1
    assert len(cov["orchestrateurs"]["fichiers"]) == 2


def test_calculer_matching_motif_fichier_simple_vault_etoile() -> None:
    categories = {
        "securite": {"description": "x", "chemins": ["src/forgeai/models/vault*.py"]},
    }
    donnees = _rapport({
        "src/forgeai/models/vault.py": _fichier_summary(10, 2),
        "src/forgeai/models/vault_utils.py": _fichier_summary(10, 0),
        "src/forgeai/models/other.py": _fichier_summary(10, 0),
    })
    cov = branch_coverage_ratchet.calculer_couverture_par_categorie(donnees, categories)
    assert cov["securite"]["num_branches"] == 20
    assert cov["securite"]["missing_branches"] == 2
    assert "src/forgeai/models/other.py" not in cov["securite"]["fichiers"]
    assert sorted(cov["securite"]["fichiers"]) == ["src/forgeai/models/vault.py", "src/forgeai/models/vault_utils.py"]


def test_calculer_fichiers_sans_summary_ignores() -> None:
    categories = {
        "orchestrateurs": {"description": "x", "chemins": ["src/forgeai/deploy/**"]},
    }
    donnees = _rapport({
        "src/forgeai/deploy/a.py": {"summary": {"num_branches": "bad", "missing_branches": 0}},
        "src/forgeai/deploy/b.py": _fichier_summary(10, 2),
    })
    cov = branch_coverage_ratchet.calculer_couverture_par_categorie(donnees, categories)
    assert cov["orchestrateurs"]["num_branches"] == 10
    assert cov["orchestrateurs"]["fichiers"] == ["src/forgeai/deploy/b.py"]


# ---------------------------------------------------------------------------
# _valider_categories
# ---------------------------------------------------------------------------

def test_valider_categories_chemins_vide_leve() -> None:
    with pytest.raises(ValueError, match="chemins doit être une liste non vide"):
        branch_coverage_ratchet._valider_categories(
            {"cat": {"description": "x", "chemins": []}}, "categories"
        )


def test_valider_categories_doublon_glob_leve() -> None:
    with pytest.raises(ValueError, match="doublons"):
        branch_coverage_ratchet._valider_categories(
            {"cat": {"description": "x", "chemins": ["a/**", "a/**"]}}, "categories"
        )


def test_valider_categories_description_vide_leve() -> None:
    with pytest.raises(ValueError, match="description doit être une chaîne non vide"):
        branch_coverage_ratchet._valider_categories(
            {"cat": {"description": "", "chemins": ["a/**"]}}, "categories"
        )


def test_valider_categories_aucune_categorie_leve() -> None:
    with pytest.raises(ValueError, match="aucune catégorie"):
        branch_coverage_ratchet._valider_categories({}, "categories")


def test_valider_categories_glob_invalide_leve() -> None:
    with pytest.raises(ValueError, match="glob invalide"):
        branch_coverage_ratchet._valider_categories(
            {"cat": {"description": "x", "chemins": [""]}}, "categories"
        )


def test_valider_categories_ignore_cles_underscore() -> None:
    data = {
        "_comment": "ignore",
        "cat": {"description": "x", "chemins": ["a/**"]},
    }
    result = branch_coverage_ratchet._valider_categories(data, "categories")
    assert "cat" in result
    assert "_comment" not in result


# ---------------------------------------------------------------------------
# _valider_baseline
# ---------------------------------------------------------------------------

def test_valider_baseline_schema_incorrect_leve() -> None:
    with pytest.raises(ValueError, match="_schema doit être"):
        branch_coverage_ratchet._valider_baseline(
            {"_schema": "mauvais", "seuils_par_categorie": {"a": 80}}, "baseline"
        )


def test_valider_baseline_seuil_hors_intervalle_leve() -> None:
    with pytest.raises(ValueError, match="entre 0 et 100"):
        branch_coverage_ratchet._valider_baseline(
            {"_schema": "branch-coverage-baseline-v1", "seuils_par_categorie": {"a": 150}}, "baseline"
        )
    with pytest.raises(ValueError, match="entre 0 et 100"):
        branch_coverage_ratchet._valider_baseline(
            {"_schema": "branch-coverage-baseline-v1", "seuils_par_categorie": {"a": -1}}, "baseline"
        )


def test_valider_baseline_seuils_vide_leve() -> None:
    with pytest.raises(ValueError, match="ne doit pas être vide"):
        branch_coverage_ratchet._valider_baseline(
            {"_schema": "branch-coverage-baseline-v1", "seuils_par_categorie": {}}, "baseline"
        )


def test_valider_baseline_seuil_non_nombre_leve() -> None:
    with pytest.raises(ValueError, match="doit être un nombre"):
        branch_coverage_ratchet._valider_baseline(
            {"_schema": "branch-coverage-baseline-v1", "seuils_par_categorie": {"a": "80"}}, "baseline"
        )


def test_valider_baseline_seuil_booleen_leve() -> None:
    with pytest.raises(ValueError, match="doit être un nombre"):
        branch_coverage_ratchet._valider_baseline(
            {"_schema": "branch-coverage-baseline-v1", "seuils_par_categorie": {"a": True}}, "baseline"
        )


def test_valider_baseline_seuils_absent_leve() -> None:
    with pytest.raises(ValueError, match="seuils_par_categorie doit être un objet"):
        branch_coverage_ratchet._valider_baseline(
            {"_schema": "branch-coverage-baseline-v1"}, "baseline"
        )


# ---------------------------------------------------------------------------
# main — nominal, régression, incohérences, référence git, régénération
# ---------------------------------------------------------------------------

def test_main_nominal_toutes_categories_au_dessus_du_seuil(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _ecrire_categories(tmp_path, _categories_deux())
    _ecrire_baseline(tmp_path, _baseline_deux({"orchestrateurs": 50.0, "securite": 50.0}))
    _ecrire_rapport_fichier(tmp_path, _rapport({
        "src/forgeai/deploy/a.py": _fichier_summary(10, 1),
        "src/forgeai/secrets/b.py": _fichier_summary(10, 1),
        "src/forgeai/models/vault.py": _fichier_summary(10, 1),
    }))
    monkeypatch.setattr(gate_git_ref, "charger_base_reference_git", _reference_absente)
    code = branch_coverage_ratchet.main(["--racine", str(tmp_path), "--sortie-json", str(tmp_path / "branch-coverage.json")])
    assert code == 0
    out = capsys.readouterr().out
    assert "OK" in out


def test_main_regression_locale_une_categorie_sous_seuil(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _ecrire_categories(tmp_path, _categories_deux())
    _ecrire_baseline(tmp_path, _baseline_deux({"orchestrateurs": 90.0, "securite": 90.0}))
    _ecrire_rapport_fichier(tmp_path, _rapport({
        "src/forgeai/deploy/a.py": _fichier_summary(10, 5),
        "src/forgeai/secrets/b.py": _fichier_summary(10, 0),
    }))
    monkeypatch.setattr(gate_git_ref, "charger_base_reference_git", _reference_absente)
    code = branch_coverage_ratchet.main(["--racine", str(tmp_path), "--sortie-json", str(tmp_path / "branch-coverage.json")])
    assert code == 1
    err = capsys.readouterr().err
    assert "orchestrateurs" in err
    assert "régression" in err


def test_main_incoherence_categorie_dans_categories_absente_baseline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _ecrire_categories(tmp_path, _categories_deux())
    _ecrire_baseline(tmp_path, _baseline_deux({"orchestrateurs": 80.0}))
    _ecrire_rapport_fichier(tmp_path, _rapport({
        "src/forgeai/deploy/a.py": _fichier_summary(10, 0),
    }))
    monkeypatch.setattr(gate_git_ref, "charger_base_reference_git", _reference_absente)
    code = branch_coverage_ratchet.main(["--racine", str(tmp_path), "--sortie-json", str(tmp_path / "branch-coverage.json")])
    assert code == 1


def test_main_incoherence_categorie_dans_baseline_absente_categories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    categories = {
        "orchestrateurs": {"description": "x", "chemins": ["src/forgeai/deploy/**"]},
    }
    _ecrire_categories(tmp_path, categories)
    _ecrire_baseline(tmp_path, _baseline_deux({"orchestrateurs": 80.0, "securite": 80.0}))
    _ecrire_rapport_fichier(tmp_path, _rapport({
        "src/forgeai/deploy/a.py": _fichier_summary(10, 0),
    }))
    monkeypatch.setattr(gate_git_ref, "charger_base_reference_git", _reference_absente)
    code = branch_coverage_ratchet.main(["--racine", str(tmp_path), "--sortie-json", str(tmp_path / "branch-coverage.json")])
    assert code == 1


def test_main_reference_git_regression_seuil_baisse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _ecrire_categories(tmp_path, _categories_deux())
    _ecrire_baseline(tmp_path, _baseline_deux({"orchestrateurs": 70.0, "securite": 70.0}))
    _ecrire_rapport_fichier(tmp_path, _rapport({
        "src/forgeai/deploy/a.py": _fichier_summary(10, 1),
        "src/forgeai/secrets/b.py": _fichier_summary(10, 1),
    }))

    def _ref_haute(racine: Path, chemin_base: Path, ref: str, valider):
        base_ref = _baseline_deux({"orchestrateurs": 90.0, "securite": 90.0})
        return valider(base_ref, "base de reference git"), ""

    monkeypatch.setattr(gate_git_ref, "charger_base_reference_git", _ref_haute)
    code = branch_coverage_ratchet.main(["--racine", str(tmp_path), "--sortie-json", str(tmp_path / "branch-coverage.json")])
    assert code == 1
    err = capsys.readouterr().err
    assert "ne peut pas baisser silencieusement" in err


def test_main_reference_git_ok_pas_de_regression(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _ecrire_categories(tmp_path, _categories_deux())
    _ecrire_baseline(tmp_path, _baseline_deux({"orchestrateurs": 80.0, "securite": 80.0}))
    _ecrire_rapport_fichier(tmp_path, _rapport({
        "src/forgeai/deploy/a.py": _fichier_summary(10, 1),
        "src/forgeai/secrets/b.py": _fichier_summary(10, 1),
    }))

    def _ref_basse(racine: Path, chemin_base: Path, ref: str, valider):
        base_ref = _baseline_deux({"orchestrateurs": 70.0, "securite": 70.0})
        return valider(base_ref, "base de reference git"), ""

    monkeypatch.setattr(gate_git_ref, "charger_base_reference_git", _ref_basse)
    code = branch_coverage_ratchet.main(["--racine", str(tmp_path), "--sortie-json", str(tmp_path / "branch-coverage.json")])
    assert code == 0


def test_main_reference_git_absente_non_bloquante(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _ecrire_categories(tmp_path, _categories_deux())
    _ecrire_baseline(tmp_path, _baseline_deux({"orchestrateurs": 50.0, "securite": 50.0}))
    _ecrire_rapport_fichier(tmp_path, _rapport({
        "src/forgeai/deploy/a.py": _fichier_summary(10, 1),
        "src/forgeai/secrets/b.py": _fichier_summary(10, 1),
    }))
    monkeypatch.setattr(gate_git_ref, "charger_base_reference_git", _reference_absente)
    code = branch_coverage_ratchet.main(["--racine", str(tmp_path), "--sortie-json", str(tmp_path / "branch-coverage.json")])
    assert code == 0
    err = capsys.readouterr().err
    assert "Avertissement" in err


def test_main_reference_git_panne_fait_echouer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _ecrire_categories(tmp_path, _categories_deux())
    _ecrire_baseline(tmp_path, _baseline_deux())
    _ecrire_rapport_fichier(tmp_path, _rapport({
        "src/forgeai/deploy/a.py": _fichier_summary(10, 1),
    }))

    def _panne(*args: object, **kwargs: object):
        raise RuntimeError("git indisponible")

    monkeypatch.setattr(gate_git_ref, "charger_base_reference_git", _panne)
    code = branch_coverage_ratchet.main(["--racine", str(tmp_path), "--sortie-json", str(tmp_path / "branch-coverage.json")])
    assert code == 1


def test_main_regenerer_baseline_ecrit_seuils_et_preserve_cles(
    tmp_path: Path
) -> None:
    _ecrire_categories(tmp_path, _categories_deux())
    baseline_initiale = {
        "_schema": "branch-coverage-baseline-v1",
        "seuil_global_initial_branches_pct": 90.21043,
        "_comment": "preserve",
        "seuils_par_categorie": {"orchestrateurs": 10.0, "securite": 10.0},
    }
    _ecrire_baseline(tmp_path, baseline_initiale)
    _ecrire_rapport_fichier(tmp_path, _rapport({
        "src/forgeai/deploy/a.py": _fichier_summary(10, 2),
        "src/forgeai/secrets/b.py": _fichier_summary(20, 5),
        "src/forgeai/models/vault.py": _fichier_summary(10, 0),
    }))
    code = branch_coverage_ratchet.main([
        "--racine", str(tmp_path),
        "--sortie-json", str(tmp_path / "branch-coverage.json"),
        "--regenerer-baseline",
    ])
    assert code == 0
    nouvelle = json.loads((tmp_path / "governance" / "branch-coverage-baseline.json").read_text(encoding="utf-8"))
    assert nouvelle["_schema"] == "branch-coverage-baseline-v1"
    assert nouvelle["seuil_global_initial_branches_pct"] == pytest.approx(90.21043)
    assert nouvelle["_comment"] == "preserve"
    # orchestrateurs: 10 branches, 2 manquantes => 80%
    # securite: 30 branches (20+10), 5 manquantes => 83.333...
    assert nouvelle["seuils_par_categorie"]["orchestrateurs"] == pytest.approx(80.0)
    assert nouvelle["seuils_par_categorie"]["securite"] == pytest.approx(83.33333333333334)


def test_main_regenerer_baseline_rapport_sans_files_echoue(
    tmp_path: Path
) -> None:
    _ecrire_categories(tmp_path, _categories_deux())
    _ecrire_baseline(tmp_path, _baseline_deux())
    _ecrire_rapport_fichier(tmp_path, {"pas_files": {}})
    code = branch_coverage_ratchet.main([
        "--racine", str(tmp_path),
        "--sortie-json", str(tmp_path / "branch-coverage.json"),
        "--regenerer-baseline",
    ])
    assert code == 1


def test_main_regenerer_baseline_categorie_sans_fichier_refuse(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Round 8 de revue scellée (#451, objection mineure fondée) : --regenerer-baseline ne doit
    jamais écrire un seuil de 100% factice pour une catégorie sans aucun fichier matché — le
    mode normal la rejetterait aussitôt après, la régénération doit échouer AVANT d'écrire."""
    _ecrire_categories(tmp_path, _categories_deux())
    _ecrire_baseline(tmp_path, _baseline_deux())
    _ecrire_rapport_fichier(tmp_path, _rapport({
        "src/forgeai/deploy/a.py": _fichier_summary(10, 1),
    }))
    ancien_contenu = (tmp_path / "governance" / "branch-coverage-baseline.json").read_text(encoding="utf-8")
    code = branch_coverage_ratchet.main([
        "--racine", str(tmp_path),
        "--sortie-json", str(tmp_path / "branch-coverage.json"),
        "--regenerer-baseline",
    ])
    assert code == 1
    err = capsys.readouterr().err
    assert "securite" in err
    nouveau_contenu = (tmp_path / "governance" / "branch-coverage-baseline.json").read_text(encoding="utf-8")
    assert nouveau_contenu == ancien_contenu


def test_main_regenerer_baseline_amorcage_sans_seuils_existants(tmp_path: Path) -> None:
    _ecrire_categories(tmp_path, _categories_deux())
    baseline_initiale = {
        "_schema": "branch-coverage-baseline-v1",
        "seuil_global_initial_branches_pct": 90.21043,
    }
    _ecrire_baseline(tmp_path, baseline_initiale)
    _ecrire_rapport_fichier(tmp_path, _rapport({
        "src/forgeai/deploy/a.py": _fichier_summary(10, 2),
        "src/forgeai/secrets/b.py": _fichier_summary(20, 5),
        "src/forgeai/models/vault.py": _fichier_summary(10, 0),
    }))
    code = branch_coverage_ratchet.main([
        "--racine", str(tmp_path),
        "--sortie-json", str(tmp_path / "branch-coverage.json"),
        "--regenerer-baseline",
    ])
    assert code == 0
    nouvelle = json.loads((tmp_path / "governance" / "branch-coverage-baseline.json").read_text(encoding="utf-8"))
    assert nouvelle["_schema"] == "branch-coverage-baseline-v1"
    assert nouvelle["seuil_global_initial_branches_pct"] == pytest.approx(90.21043)
    assert nouvelle["seuils_par_categorie"]["orchestrateurs"] == pytest.approx(80.0)
    assert nouvelle["seuils_par_categorie"]["securite"] == pytest.approx(83.33333333333334)


def test_main_regenerer_baseline_fichier_baseline_absent(tmp_path: Path) -> None:
    _ecrire_categories(tmp_path, _categories_deux())
    _ecrire_rapport_fichier(tmp_path, _rapport({
        "src/forgeai/deploy/a.py": _fichier_summary(10, 2),
        "src/forgeai/secrets/b.py": _fichier_summary(20, 5),
        "src/forgeai/models/vault.py": _fichier_summary(10, 0),
    }))
    code = branch_coverage_ratchet.main([
        "--racine", str(tmp_path),
        "--sortie-json", str(tmp_path / "branch-coverage.json"),
        "--regenerer-baseline",
    ])
    assert code == 0
    nouvelle = json.loads((tmp_path / "governance" / "branch-coverage-baseline.json").read_text(encoding="utf-8"))
    assert nouvelle["_schema"] == "branch-coverage-baseline-v1"
    assert "seuils_par_categorie" in nouvelle
    assert nouvelle["seuils_par_categorie"]["orchestrateurs"] == pytest.approx(80.0)
    assert nouvelle["seuils_par_categorie"]["securite"] == pytest.approx(83.33333333333334)


def test_main_reference_git_ancien_schema_sans_seuils_par_categorie_tolere(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _ecrire_categories(tmp_path, _categories_deux())
    _ecrire_baseline(tmp_path, _baseline_deux({"orchestrateurs": 80.0, "securite": 80.0}))
    _ecrire_rapport_fichier(tmp_path, _rapport({
        "src/forgeai/deploy/a.py": _fichier_summary(10, 1),
        "src/forgeai/secrets/b.py": _fichier_summary(10, 1),
    }))

    def _ref_ancien_schema(racine: Path, chemin_base: Path, ref: str, valider):
        ancien = {"_schema": "branch-coverage-baseline-v1", "seuil_global_initial_branches_pct": 90.0}
        base_validee = valider(ancien, "base de reference git")
        assert isinstance(base_validee, dict)
        assert base_validee.get("seuils_par_categorie") == {}
        return base_validee, ""

    monkeypatch.setattr(gate_git_ref, "charger_base_reference_git", _ref_ancien_schema)
    code = branch_coverage_ratchet.main(["--racine", str(tmp_path), "--sortie-json", str(tmp_path / "branch-coverage.json")])
    assert code == 0


def test_main_reference_git_nouvelle_categorie_locale_pas_bloquante(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Round 7 de revue scellée (#451, objection majeure fondée) : une catégorie ajoutée
    localement (jamais vue dans la référence git) ne doit PAS bloquer le cliquet — sans ce
    comportement, aucune nouvelle catégorie n'aurait jamais pu être ajoutée après le premier
    merge de ce mécanisme (la référence ne peut évidemment pas la connaître par avance)."""
    categories = dict(_categories_deux())
    categories["nouvelle_cat"] = {"description": "x", "chemins": ["src/forgeai/models/*.py"]}
    _ecrire_categories(tmp_path, categories)
    _ecrire_baseline(tmp_path, _baseline_deux({
        "orchestrateurs": 80.0, "securite": 80.0, "nouvelle_cat": 90.0,
    }))
    _ecrire_rapport_fichier(tmp_path, _rapport({
        "src/forgeai/deploy/a.py": _fichier_summary(10, 1),
        "src/forgeai/secrets/b.py": _fichier_summary(10, 1),
        "src/forgeai/models/vault.py": _fichier_summary(10, 1),
    }))

    def _ref_deux_categories(racine: Path, chemin_base: Path, ref: str, valider):
        ref_baseline = _baseline_deux({"orchestrateurs": 70.0, "securite": 70.0})
        return valider(ref_baseline, "base de reference git"), ""

    monkeypatch.setattr(gate_git_ref, "charger_base_reference_git", _ref_deux_categories)
    code = branch_coverage_ratchet.main(["--racine", str(tmp_path), "--sortie-json", str(tmp_path / "branch-coverage.json")])
    assert code == 0


def test_main_reference_git_categorie_disparue_localement_bloquante(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Symétrique du test précédent : une catégorie présente dans la référence git mais absente
    localement (categories.json ET baseline.json modifiés ensemble pour la retirer) reste
    suspecte et DOIT bloquer — seul l'AJOUT d'une catégorie est toléré, jamais sa disparition."""
    categories = {
        "securite": {"description": "x", "chemins": ["src/forgeai/secrets/**"]},
    }
    _ecrire_categories(tmp_path, categories)
    _ecrire_baseline(tmp_path, _baseline_deux({"securite": 80.0}))
    _ecrire_rapport_fichier(tmp_path, _rapport({
        "src/forgeai/secrets/b.py": _fichier_summary(10, 1),
    }))

    def _ref_deux_categories(racine: Path, chemin_base: Path, ref: str, valider):
        ref_baseline = _baseline_deux({"orchestrateurs": 70.0, "securite": 70.0})
        return valider(ref_baseline, "base de reference git"), ""

    monkeypatch.setattr(gate_git_ref, "charger_base_reference_git", _ref_deux_categories)
    code = branch_coverage_ratchet.main(["--racine", str(tmp_path), "--sortie-json", str(tmp_path / "branch-coverage.json")])
    assert code == 1
    err = capsys.readouterr().err
    assert "orchestrateurs" in err
    assert "incohérence" in err


def test_main_categorie_sans_fichier_matche_echoue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _ecrire_categories(tmp_path, _categories_deux())
    _ecrire_baseline(tmp_path, _baseline_deux({"orchestrateurs": 50.0, "securite": 50.0}))
    _ecrire_rapport_fichier(tmp_path, _rapport({
        "src/forgeai/deploy/a.py": _fichier_summary(10, 1),
    }))
    monkeypatch.setattr(gate_git_ref, "charger_base_reference_git", _reference_absente)
    code = branch_coverage_ratchet.main(["--racine", str(tmp_path), "--sortie-json", str(tmp_path / "branch-coverage.json")])
    assert code == 1
    err = capsys.readouterr().err
    assert "securite" in err
    assert "aucun fichier" in err


def test_main_fichier_matche_sans_branche_ne_declenche_pas_categorie_vide(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Round 4 de revue scellée (#451, objection mineure fondée) : un fichier qui matche un
    glob mais n'a aucune branche (ex. module de pures constantes) ne doit JAMAIS être rapporté
    comme « aucun fichier ne matche » — seule l'absence RÉELLE de fichier matché est suspecte.
    """
    _ecrire_categories(tmp_path, _categories_deux())
    _ecrire_baseline(tmp_path, _baseline_deux({"orchestrateurs": 50.0, "securite": 50.0}))
    _ecrire_rapport_fichier(tmp_path, _rapport({
        "src/forgeai/deploy/a.py": _fichier_summary(10, 1),
        "src/forgeai/secrets/const.py": _fichier_summary(0, 0),
    }))
    monkeypatch.setattr(gate_git_ref, "charger_base_reference_git", _reference_absente)
    code = branch_coverage_ratchet.main(["--racine", str(tmp_path), "--sortie-json", str(tmp_path / "branch-coverage.json")])
    assert code == 0


# ---------------------------------------------------------------------------
# Fichiers JSON absents / invalides
# ---------------------------------------------------------------------------

def test_main_categories_absent_retourne_1(tmp_path: Path) -> None:
    _ecrire_baseline(tmp_path, _baseline_deux())
    _ecrire_rapport_fichier(tmp_path, _rapport({}))
    code = branch_coverage_ratchet.main(["--racine", str(tmp_path), "--sortie-json", str(tmp_path / "branch-coverage.json")])
    assert code == 1


def test_main_baseline_absent_retourne_1(tmp_path: Path) -> None:
    _ecrire_categories(tmp_path, _categories_deux())
    _ecrire_rapport_fichier(tmp_path, _rapport({}))
    code = branch_coverage_ratchet.main(["--racine", str(tmp_path), "--sortie-json", str(tmp_path / "branch-coverage.json")])
    assert code == 1


def test_main_rapport_absent_retourne_1(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _ecrire_categories(tmp_path, _categories_deux())
    _ecrire_baseline(tmp_path, _baseline_deux())
    monkeypatch.setattr(gate_git_ref, "charger_base_reference_git", _reference_absente)
    code = branch_coverage_ratchet.main(["--racine", str(tmp_path), "--sortie-json", str(tmp_path / "branch-coverage.json")])
    assert code == 1


def test_main_rapport_json_invalide_retourne_1(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _ecrire_categories(tmp_path, _categories_deux())
    _ecrire_baseline(tmp_path, _baseline_deux())
    (tmp_path / "branch-coverage.json").write_text("pas du json", encoding="utf-8")
    monkeypatch.setattr(gate_git_ref, "charger_base_reference_git", _reference_absente)
    code = branch_coverage_ratchet.main(["--racine", str(tmp_path), "--sortie-json", str(tmp_path / "branch-coverage.json")])
    assert code == 1


def test_main_categories_json_invalide_retourne_1(tmp_path: Path) -> None:
    (tmp_path / "governance").mkdir(parents=True, exist_ok=True)
    (tmp_path / "governance" / "branch-coverage-categories.json").write_text("{{", encoding="utf-8")
    _ecrire_baseline(tmp_path, _baseline_deux())
    _ecrire_rapport_fichier(tmp_path, _rapport({}))
    code = branch_coverage_ratchet.main(["--racine", str(tmp_path), "--sortie-json", str(tmp_path / "branch-coverage.json")])
    assert code == 1


def test_main_baseline_json_invalide_retourne_1(tmp_path: Path) -> None:
    _ecrire_categories(tmp_path, _categories_deux())
    (tmp_path / "governance").mkdir(parents=True, exist_ok=True)
    (tmp_path / "governance" / "branch-coverage-baseline.json").write_text("{{", encoding="utf-8")
    _ecrire_rapport_fichier(tmp_path, _rapport({}))
    code = branch_coverage_ratchet.main(["--racine", str(tmp_path), "--sortie-json", str(tmp_path / "branch-coverage.json")])
    assert code == 1


def test_main_rapport_sans_cle_files_retourne_1(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _ecrire_categories(tmp_path, _categories_deux())
    _ecrire_baseline(tmp_path, _baseline_deux())
    _ecrire_rapport_fichier(tmp_path, {"autre": 123})
    monkeypatch.setattr(gate_git_ref, "charger_base_reference_git", _reference_absente)
    code = branch_coverage_ratchet.main(["--racine", str(tmp_path), "--sortie-json", str(tmp_path / "branch-coverage.json")])
    assert code == 1


def test_main_categories_json_non_objet_retourne_1(tmp_path: Path) -> None:
    (tmp_path / "governance").mkdir(parents=True, exist_ok=True)
    (tmp_path / "governance" / "branch-coverage-categories.json").write_text("[]", encoding="utf-8")
    _ecrire_baseline(tmp_path, _baseline_deux())
    _ecrire_rapport_fichier(tmp_path, _rapport({}))
    code = branch_coverage_ratchet.main(["--racine", str(tmp_path), "--sortie-json", str(tmp_path / "branch-coverage.json")])
    assert code == 1


def test_main_baseline_json_non_objet_retourne_1(tmp_path: Path) -> None:
    _ecrire_categories(tmp_path, _categories_deux())
    (tmp_path / "governance").mkdir(parents=True, exist_ok=True)
    (tmp_path / "governance" / "branch-coverage-baseline.json").write_text("[]", encoding="utf-8")
    _ecrire_rapport_fichier(tmp_path, _rapport({}))
    code = branch_coverage_ratchet.main(["--racine", str(tmp_path), "--sortie-json", str(tmp_path / "branch-coverage.json")])
    assert code == 1


# ---------------------------------------------------------------------------
# Test structurel anti-dérive gates.yml
# ---------------------------------------------------------------------------

def test_gates_yml_branch_coverage_ratchet_configure() -> None:
    yaml = pytest.importorskip("yaml", reason="pyyaml est installé par le job `tests` de la CI")
    racine = Path(__file__).resolve().parents[1]
    chemin = racine / ".github" / "workflows" / "gates.yml"
    assert chemin.exists(), f"{chemin} introuvable"
    data = yaml.safe_load(chemin.read_text(encoding="utf-8"))
    jobs = data.get("jobs") or {}
    assert "branch-coverage-ratchet" in jobs, "job branch-coverage-ratchet manquant dans gates.yml"
    job = jobs["branch-coverage-ratchet"]
    steps = job.get("steps") or []
    assert any(
        step.get("with", {}).get("fetch-depth") == 0
        for step in steps
    ), "fetch-depth: 0 manquant (requis pour gate_git_ref) dans le job branch-coverage-ratchet"
    assert any(
        "branch_coverage_ratchet.py" in str(step.get("run", ""))
        for step in steps
    ), "invocation branch_coverage_ratchet.py manquante dans gates.yml"
    # Round 10 de revue scellée (#451, objection récurrente depuis le round 2 — enfin fermée) :
    # verrouille les deux propriétés qui protègent contre le double calcul de couverture
    # (correctif round 2) — needs: branch-coverage-report ET l'étape download-artifact avec le
    # bon nom, jamais juste la présence du job.
    needs_ratchet = job.get("needs") or []
    if isinstance(needs_ratchet, str):
        needs_ratchet = [needs_ratchet]
    assert "branch-coverage-report" in needs_ratchet, (
        "branch-coverage-ratchet doit dépendre de branch-coverage-report (needs:) — "
        "sans quoi rien ne garantit que l'artefact existe avant le téléchargement"
    )
    assert any(
        "download-artifact" in str(step.get("uses", ""))
        and step.get("with", {}).get("name") == "branch-coverage-report"
        for step in steps
    ), "étape download-artifact avec name: branch-coverage-report manquante — sans elle, rien ne garantit la réutilisation de l'artefact plutôt qu'un recalcul"
    aggregateur = next((j for j in jobs.values() if j.get("name") == "tests"), None)
    assert aggregateur is not None, "job avec name: tests introuvable dans gates.yml"
    needs = aggregateur.get("needs") or []
    assert "branch-coverage-ratchet" in needs, "branch-coverage-ratchet absent du needs: du job tests"
