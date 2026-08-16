from __future__ import annotations

import datetime as dt
import importlib.util
import json
from pathlib import Path


def _charger_validateur():
    path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "governance"
        / "validate_error_contracts.py"
    )
    spec = importlib.util.spec_from_file_location("validate_error_contracts", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


VALIDATEUR = _charger_validateur()
RACINE_DEPOT = Path(__file__).resolve().parents[1]


def _creer_fichier_source(root: Path, rel_path: str, contenu: str) -> Path:
    cible = root / rel_path
    cible.parent.mkdir(parents=True, exist_ok=True)
    cible.write_text(contenu, encoding="utf-8")
    return cible


def _ecrire_inventaire(
    root: Path,
    contrats: list[dict],
    *,
    horizon_days: int = 180,
    contracted: int | None = None,
    floor: int | None = None,
) -> None:
    nb_contrats = len(contrats)
    contracted_val = nb_contrats if contracted is None else contracted
    floor_val = nb_contrats if floor is None else floor

    (root / "governance").mkdir(parents=True, exist_ok=True)
    (root / "governance" / "error-handling-contracts.json").write_text(
        json.dumps(
            {
                "schema": "error-handling-contracts/1",
                "review_horizon": {
                    "days": horizon_days,
                    "justification": "Horizon de test pour la validation des contrats.",
                },
                "coverage": {
                    "total_except_sites_src_forgeai": 100,
                    "measured_on": "test",
                    "measured_command": "grep test",
                    "contracted": contracted_val,
                    "floor": floor_val,
                    "note": "Note de couverture de test.",
                },
                "contracts": contrats,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _entree_valide(
    *,
    id_contrat: str = "site:src/example.py:3",
    path: str = "src/example.py",
    line: int = 3,
    function_name: str = "src.example.foo",
    exception_types: list[str] | None = None,
    disposition: str = "JUSTIFIED",
    compensating_test: str | None = None,
    compensating_test_reason: str | None = "Comportement documenté et non critique.",
    review_due: str = "2026-06-01",
) -> dict:
    return {
        "id": id_contrat,
        "site": {
            "path": path,
            "line": line,
            "function": function_name,
        },
        "exception_types": ["ValueError"] if exception_types is None else exception_types,
        "risk_paths": ["persistance"],
        "disposition": disposition,
        "behavior_contract": "Retourne une valeur par défaut en cas d'erreur.",
        "logging": "aucune — journalisation non requise pour ce cas",
        "owner": "équipe plateforme",
        "justification": "Justification de test détaillée et explicite.",
        "compensating_test": compensating_test,
        "compensating_test_reason": compensating_test_reason,
        "review_due": review_due,
        "accepted_risk": "Risque accepté pour les tests.",
    }


def test_inventaire_minimal_valide(tmp_path: Path) -> None:
    _creer_fichier_source(
        tmp_path,
        "src/example.py",
        "try:\n    pass\nexcept ValueError:\n    pass\n",
    )
    contrat = _entree_valide(
        id_contrat="site:src/example.py:3",
        path="src/example.py",
        line=3,
        exception_types=["ValueError"],
        disposition="JUSTIFIED",
        compensating_test=None,
        compensating_test_reason="Comportement documenté et testé au niveau supérieur.",
        review_due="2026-06-01",
    )
    _ecrire_inventaire(tmp_path, [contrat])

    erreurs = VALIDATEUR.valider(tmp_path, aujourd_hui=dt.date(2026, 1, 1))
    assert erreurs == []


def test_coverage_contracted_incoherent_detecte(tmp_path: Path) -> None:
    _creer_fichier_source(
        tmp_path,
        "src/example.py",
        "try:\n    pass\nexcept ValueError:\n    pass\n",
    )
    contrat = _entree_valide()
    _ecrire_inventaire(tmp_path, [contrat], contracted=2, floor=1)

    erreurs = VALIDATEUR.valider(tmp_path, aujourd_hui=dt.date(2026, 1, 1))
    assert any("coverage.contracted (2) ne correspond pas" in e for e in erreurs)


def test_coverage_sous_le_plancher_detecte(tmp_path: Path) -> None:
    _creer_fichier_source(
        tmp_path,
        "src/example.py",
        "try:\n    pass\nexcept ValueError:\n    pass\n",
    )
    contrat = _entree_valide()
    _ecrire_inventaire(tmp_path, [contrat], contracted=1, floor=5)

    erreurs = VALIDATEUR.valider(tmp_path, aujourd_hui=dt.date(2026, 1, 1))
    assert any("couverture sous le plancher : 1 contrats pour un plancher de 5" in e for e in erreurs)


def test_identifiant_duplique_detecte(tmp_path: Path) -> None:
    _creer_fichier_source(
        tmp_path,
        "src/example.py",
        "try:\n    pass\nexcept ValueError:\n    pass\n",
    )
    contrat1 = _entree_valide(id_contrat="site:src/example.py:3")
    contrat2 = _entree_valide(id_contrat="site:src/example.py:3")
    _ecrire_inventaire(tmp_path, [contrat1, contrat2])

    erreurs = VALIDATEUR.valider(tmp_path, aujourd_hui=dt.date(2026, 1, 1))
    assert any("identifiant de contrat dupliqué : site:src/example.py:3" in e for e in erreurs)


def test_champs_obligatoires_manquants_detectes(tmp_path: Path) -> None:
    _creer_fichier_source(
        tmp_path,
        "src/example.py",
        "try:\n    pass\nexcept ValueError:\n    pass\n",
    )
    contrat1 = _entree_valide()
    del contrat1["disposition"]
    _ecrire_inventaire(tmp_path, [contrat1])

    erreurs1 = VALIDATEUR.valider(tmp_path, aujourd_hui=dt.date(2026, 1, 1))
    assert any("champs obligatoires absents : disposition" in e for e in erreurs1)

    contrat2 = _entree_valide()
    del contrat2["owner"]
    _ecrire_inventaire(tmp_path, [contrat2])

    erreurs2 = VALIDATEUR.valider(tmp_path, aujourd_hui=dt.date(2026, 1, 1))
    assert any("champs obligatoires absents : owner" in e for e in erreurs2)


def test_disposition_invalide_detectee(tmp_path: Path) -> None:
    _creer_fichier_source(
        tmp_path,
        "src/example.py",
        "try:\n    pass\nexcept ValueError:\n    pass\n",
    )
    contrat = _entree_valide(disposition="MAYBE")
    _ecrire_inventaire(tmp_path, [contrat])

    erreurs = VALIDATEUR.valider(tmp_path, aujourd_hui=dt.date(2026, 1, 1))
    assert any("disposition invalide : MAYBE" in e for e in erreurs)


def test_review_due_dans_le_passe_detectee(tmp_path: Path) -> None:
    _creer_fichier_source(
        tmp_path,
        "src/example.py",
        "try:\n    pass\nexcept ValueError:\n    pass\n",
    )
    contrat = _entree_valide(review_due="2025-12-31")
    _ecrire_inventaire(tmp_path, [contrat])

    erreurs = VALIDATEUR.valider(tmp_path, aujourd_hui=dt.date(2026, 1, 1))
    assert any("review_due dépassée (2025-12-31)" in e for e in erreurs)


def test_review_due_au_dela_horizon_detectee(tmp_path: Path) -> None:
    _creer_fichier_source(
        tmp_path,
        "src/example.py",
        "try:\n    pass\nexcept ValueError:\n    pass\n",
    )
    # Horizon = 180 jours. Pour 2026-01-01, max = 2026-06-30. 2026-07-01 dépasse.
    contrat = _entree_valide(review_due="2026-07-01")
    _ecrire_inventaire(tmp_path, [contrat], horizon_days=180)

    erreurs = VALIDATEUR.valider(tmp_path, aujourd_hui=dt.date(2026, 1, 1))
    assert any("review_due dépasse l'horizon de révision" in e for e in erreurs)


def test_review_due_malformee_detectee(tmp_path: Path) -> None:
    _creer_fichier_source(
        tmp_path,
        "src/example.py",
        "try:\n    pass\nexcept ValueError:\n    pass\n",
    )
    contrat = _entree_valide(review_due="01-06-2026")
    _ecrire_inventaire(tmp_path, [contrat])

    erreurs = VALIDATEUR.valider(tmp_path, aujourd_hui=dt.date(2026, 1, 1))
    assert any("review_due doit être une date ISO valide" in e for e in erreurs)


def test_compensating_test_et_reason_tous_deux_null_detectes(tmp_path: Path) -> None:
    _creer_fichier_source(
        tmp_path,
        "src/example.py",
        "try:\n    pass\nexcept ValueError:\n    pass\n",
    )
    contrat = _entree_valide(compensating_test=None, compensating_test_reason=None)
    _ecrire_inventaire(tmp_path, [contrat])

    erreurs = VALIDATEUR.valider(tmp_path, aujourd_hui=dt.date(2026, 1, 1))
    assert any("ni compensating_test ni compensating_test_reason" in e for e in erreurs)


def test_compensating_test_et_reason_tous_deux_renseignes_detectes(tmp_path: Path) -> None:
    _creer_fichier_source(
        tmp_path,
        "src/example.py",
        "try:\n    pass\nexcept ValueError:\n    pass\n",
    )
    _creer_fichier_source(
        tmp_path,
        "tests/test_example.py",
        "def test_foo(): assert True\n",
    )
    contrat = _entree_valide(
        compensating_test="tests/test_example.py::test_foo",
        compensating_test_reason="Une raison en trop.",
    )
    _ecrire_inventaire(tmp_path, [contrat])

    erreurs = VALIDATEUR.valider(tmp_path, aujourd_hui=dt.date(2026, 1, 1))
    assert any("compensating_test ET compensating_test_reason tous les deux renseignés" in e for e in erreurs)


def test_compensating_test_inexistant_detecte(tmp_path: Path) -> None:
    _creer_fichier_source(
        tmp_path,
        "src/example.py",
        "try:\n    pass\nexcept ValueError:\n    pass\n",
    )
    contrat = _entree_valide(
        compensating_test="tests/test_inexistant.py::test_absent",
        compensating_test_reason=None,
    )
    _ecrire_inventaire(tmp_path, [contrat])

    erreurs = VALIDATEUR.valider(tmp_path, aujourd_hui=dt.date(2026, 1, 1))
    assert any("test compensatoire absent du dépôt : tests/test_inexistant.py::test_absent" in e for e in erreurs)


def test_disposition_fixed_sans_test_detectee(tmp_path: Path) -> None:
    _creer_fichier_source(
        tmp_path,
        "src/example.py",
        "try:\n    pass\nexcept ValueError:\n    pass\n",
    )
    contrat = _entree_valide(
        disposition="FIXED",
        compensating_test=None,
        compensating_test_reason="Correction simple sans test dédié.",
    )
    _ecrire_inventaire(tmp_path, [contrat])

    erreurs = VALIDATEUR.valider(tmp_path, aujourd_hui=dt.date(2026, 1, 1))
    assert any("disposition FIXED sans compensating_test" in e for e in erreurs)


def test_derive_site_ligne_non_except_detectee(tmp_path: Path) -> None:
    _creer_fichier_source(
        tmp_path,
        "src/example.py",
        "a = 1\nb = 2\nc = 3\n",
    )
    contrat = _entree_valide(path="src/example.py", line=2)
    _ecrire_inventaire(tmp_path, [contrat])

    erreurs = VALIDATEUR.valider(tmp_path, aujourd_hui=dt.date(2026, 1, 1))
    assert any("site introuvable" in e for e in erreurs)


def test_derive_type_exception_detectee(tmp_path: Path) -> None:
    _creer_fichier_source(
        tmp_path,
        "src/example.py",
        "try:\n    pass\nexcept KeyError:\n    pass\n",
    )
    contrat = _entree_valide(
        path="src/example.py",
        line=3,
        exception_types=["ValueError"],
    )
    _ecrire_inventaire(tmp_path, [contrat])

    erreurs = VALIDATEUR.valider(tmp_path, aujourd_hui=dt.date(2026, 1, 1))
    assert any("types d'exception ont dérivé" in e for e in erreurs)


def test_fichier_source_absent_ne_plante_pas_et_signale_site_introuvable(tmp_path: Path) -> None:
    contrat = _entree_valide(
        path="src/fichier_totalement_absent.py",
        line=10,
    )
    _ecrire_inventaire(tmp_path, [contrat])

    erreurs = VALIDATEUR.valider(tmp_path, aujourd_hui=dt.date(2026, 1, 1))
    assert any("site introuvable" in e for e in erreurs)


def test_except_avec_tuple_de_types_est_valide(tmp_path: Path) -> None:
    _creer_fichier_source(
        tmp_path,
        "src/example.py",
        "try:\n    pass\nexcept (TypeError, ValueError):\n    pass\n",
    )
    contrat = _entree_valide(
        path="src/example.py",
        line=3,
        exception_types=["TypeError", "ValueError"],
    )
    _ecrire_inventaire(tmp_path, [contrat])

    erreurs = VALIDATEUR.valider(tmp_path, aujourd_hui=dt.date(2026, 1, 1))
    assert erreurs == []


def test_rendre_rapport_markdown(tmp_path: Path) -> None:
    _creer_fichier_source(
        tmp_path,
        "src/example.py",
        "try:\n    pass\nexcept ValueError:\n    pass\n",
    )
    _creer_fichier_source(
        tmp_path,
        "tests/test_example.py",
        "def test_example(): pass\n",
    )
    contrat = _entree_valide(
        id_contrat="site:src/example.py:3",
        path="src/example.py",
        line=3,
        disposition="FIXED",
        compensating_test="tests/test_example.py::test_example",
        compensating_test_reason=None,
    )
    _ecrire_inventaire(tmp_path, [contrat])

    markdown = VALIDATEUR.rendre(tmp_path)
    assert "# Contrats de gestion d'erreurs et risques acceptés" in markdown
    assert "src/example.py:3" in markdown
    assert "FIXED" in markdown
    assert "tests/test_example.py::test_example" in markdown


def test_integration_inventaire_officiel_du_depot() -> None:
    erreurs = VALIDATEUR.valider(RACINE_DEPOT, aujourd_hui=dt.date(2026, 8, 16))
    assert erreurs == []


def test_compensating_test_fonction_inexistante_detectee(tmp_path: Path) -> None:
    _creer_fichier_source(
        tmp_path,
        "src/example.py",
        "try:\n    pass\nexcept ValueError:\n    pass\n",
    )
    _creer_fichier_source(
        tmp_path,
        "tests/test_exemple.py",
        "def test_autre_chose(): pass\n",
    )
    contrat = _entree_valide(
        compensating_test="tests/test_exemple.py::test_inexistante",
        compensating_test_reason=None,
    )
    _ecrire_inventaire(tmp_path, [contrat])

    erreurs = VALIDATEUR.valider(tmp_path, aujourd_hui=dt.date(2026, 1, 1))
    assert any("test compensatoire absent du dépôt : tests/test_exemple.py::test_inexistante" in e for e in erreurs)


def test_compensating_test_fonction_existante_est_valide(tmp_path: Path) -> None:
    _creer_fichier_source(
        tmp_path,
        "src/example.py",
        "try:\n    pass\nexcept ValueError:\n    pass\n",
    )
    _creer_fichier_source(
        tmp_path,
        "tests/test_exemple.py",
        "def test_autre_chose(): pass\n",
    )
    contrat = _entree_valide(
        compensating_test="tests/test_exemple.py::test_autre_chose",
        compensating_test_reason=None,
    )
    _ecrire_inventaire(tmp_path, [contrat])

    erreurs = VALIDATEUR.valider(tmp_path, aujourd_hui=dt.date(2026, 1, 1))
    assert erreurs == []


def test_compensating_test_methode_de_classe_existante_est_valide(tmp_path: Path) -> None:
    _creer_fichier_source(
        tmp_path,
        "src/example.py",
        "try:\n    pass\nexcept ValueError:\n    pass\n",
    )
    _creer_fichier_source(
        tmp_path,
        "tests/test_classe.py",
        "class TestExemple:\n    def test_methode(self):\n        pass\n",
    )
    contrat = _entree_valide(
        compensating_test="tests/test_classe.py::TestExemple::test_methode",
        compensating_test_reason=None,
    )
    _ecrire_inventaire(tmp_path, [contrat])

    erreurs = VALIDATEUR.valider(tmp_path, aujourd_hui=dt.date(2026, 1, 1))
    assert erreurs == []


def test_compensating_test_methode_de_classe_inexistante_detectee(tmp_path: Path) -> None:
    _creer_fichier_source(
        tmp_path,
        "src/example.py",
        "try:\n    pass\nexcept ValueError:\n    pass\n",
    )
    _creer_fichier_source(
        tmp_path,
        "tests/test_classe.py",
        "class TestExemple:\n    def test_methode(self):\n        pass\n",
    )
    contrat = _entree_valide(
        compensating_test="tests/test_classe.py::TestExemple::test_absente",
        compensating_test_reason=None,
    )
    _ecrire_inventaire(tmp_path, [contrat])

    erreurs = VALIDATEUR.valider(tmp_path, aujourd_hui=dt.date(2026, 1, 1))
    assert any("test compensatoire absent du dépôt : tests/test_classe.py::TestExemple::test_absente" in e for e in erreurs)
