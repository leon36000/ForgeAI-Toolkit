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
        / "validate_sonar_suppressions.py"
    )
    spec = importlib.util.spec_from_file_location("validate_sonar_suppressions", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


VALIDATEUR = _charger_validateur()
RACINE_DEPOT = Path(__file__).resolve().parents[1]


def _ecrire_inventaire(root: Path, suppressions: list[dict], *, horizon: int = 180) -> None:
    (root / "governance").mkdir(parents=True, exist_ok=True)
    (root / "governance" / "sonar-suppressions.json").write_text(
        json.dumps(
            {
                "review_horizon": {
                    "days": horizon,
                    "justification": "Horizon de test.",
                },
                "suppressions": suppressions,
            }
        ),
        encoding="utf-8",
    )


def _entree_inline(*, review_due: str = "2026-06-01") -> dict:
    return {
        "id": "inline:src/active.py:1:S1234",
        "kind": "inline",
        "rule": "S1234",
        "scope": "line",
        "sites": [{"path": "src/active.py", "line": 1}],
        "owner": "équipe test",
        "justification": "Justification testée.",
        "compensating_test": None,
        "compensating_test_reason": "La suppression est réduite à la ligne concernée.",
        "review_due": review_due,
        "accepted_risk": "Risque test.",
    }


def _preparer_suppression_inline(root: Path, *, review_due: str = "2026-06-01") -> None:
    (root / "src").mkdir()
    (root / "sonar-project.properties").write_text("sonar.sources=src\n", encoding="utf-8")
    (root / "src" / "active.py").write_text(
        "value = 1  # NOSONAR(S1234)\n",
        encoding="utf-8",
    )
    _ecrire_inventaire(root, [_entree_inline(review_due=review_due)])


def test_scan_limite_aux_sources_et_ignore_les_chaines_et_regex(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "scripts" / "governance").mkdir(parents=True)
    (tmp_path / "tests").mkdir()
    (tmp_path / "sonar-project.properties").write_text(
        "sonar.sources=src,scripts\n",
        encoding="utf-8",
    )
    (tmp_path / "src" / "active.py").write_text(
        'MESSAGE = "# NOSONAR(S1234)"\n'
        'MOTIF = r"#\\s*NOSONAR"\n'
        "value = 1  # NOSONAR(S9999)\n",
        encoding="utf-8",
    )
    (tmp_path / "tests" / "hors_perimetre.py").write_text(
        "value = 1  # NOSONAR(S0001)\n",
        encoding="utf-8",
    )
    (tmp_path / "scripts" / "governance" / "validate_sonar_suppressions.py").write_text(
        "value = 1  # NOSONAR(S0002)\n",
        encoding="utf-8",
    )

    resultats = VALIDATEUR.suppressions_reelles(tmp_path)

    assert [item["id"] for item in resultats] == ["inline:src/active.py:3:S9999"]


def test_scan_ignore_un_nosonar_dans_un_chemin_exclu(tmp_path: Path) -> None:
    (tmp_path / "src" / "exclu").mkdir(parents=True)
    (tmp_path / "sonar-project.properties").write_text(
        "sonar.sources=src\nsonar.exclusions=src/exclu/**\n",
        encoding="utf-8",
    )
    (tmp_path / "src" / "exclu" / "active.py").write_text(
        "value = 1  # NOSONAR(S1234)\n",
        encoding="utf-8",
    )
    _ecrire_inventaire(tmp_path, [])

    resultats = VALIDATEUR.suppressions_reelles(tmp_path)

    assert not any(item["id"].startswith("inline:") for item in resultats)
    assert {
        item["id"]
        for item in resultats
        if item["kind"] == "analysis-exclusion"
    } == {"analysis-exclusion:sonar.exclusions:src/exclu/**"}


def test_scan_detecte_nosonar_apres_un_autre_pragma(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "sonar-project.properties").write_text("sonar.sources=src\n", encoding="utf-8")
    (tmp_path / "src" / "active.py").write_text(
        'PASSWORD = "immudb"  # noqa: S105  proof:allow  # NOSONAR(S2068)\n',
        encoding="utf-8",
    )

    resultats = VALIDATEUR.suppressions_reelles(tmp_path)

    assert [item["id"] for item in resultats] == ["inline:src/active.py:1:S2068"]


def test_commentaire_nu_est_signale_et_non_inventorie(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "sonar-project.properties").write_text("sonar.sources=src\n", encoding="utf-8")
    (tmp_path / "src" / "active.py").write_text("value = 1  # NOSONAR\n", encoding="utf-8")
    _ecrire_inventaire(tmp_path, [])

    erreurs = VALIDATEUR.valider(tmp_path)

    assert "NOSONAR nu interdit : src/active.py:1 ; indiquez la règle exacte" in erreurs
    assert "suppression réelle non inventoriée : inline:src/active.py:1:NU" in erreurs


def test_forme_legacy_sans_parentheses_est_rejetee(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "sonar-project.properties").write_text("sonar.sources=src\n", encoding="utf-8")
    (tmp_path / "src" / "active.py").write_text(
        "value = 1  # NOSONAR S1234\n",
        encoding="utf-8",
    )
    _ecrire_inventaire(tmp_path, [])

    erreurs = VALIDATEUR.valider(tmp_path)

    assert (
        "NOSONAR ciblé mal formé : src/active.py:1 ; utilisez # NOSONAR(S1234)"
    ) in erreurs
    assert "suppression réelle non inventoriée : inline:src/active.py:1:NU" in erreurs


def test_commentaire_inventorie_ne_produit_aucune_erreur(tmp_path: Path) -> None:
    _preparer_suppression_inline(tmp_path)

    assert VALIDATEUR.valider(tmp_path, aujourd_hui=dt.date(2026, 1, 1)) == []


def test_entree_inventaire_fossile_est_rejetee(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "sonar-project.properties").write_text("sonar.sources=src\n", encoding="utf-8")
    _ecrire_inventaire(tmp_path, [_entree_inline()])

    erreurs = VALIDATEUR.valider(tmp_path, aujourd_hui=dt.date(2026, 1, 1))

    assert "entrée d'inventaire fossile : inline:src/active.py:1:S1234" in erreurs


def test_review_due_depassee_est_rejetee_avec_date_injectee(tmp_path: Path) -> None:
    _preparer_suppression_inline(tmp_path, review_due="2025-12-31")

    erreurs = VALIDATEUR.valider(tmp_path, aujourd_hui=dt.date(2026, 1, 1))

    assert "inline:src/active.py:1:S1234 : review_due dépassée (2025-12-31)" in erreurs


def test_review_due_non_depassee_est_acceptee_avec_date_injectee(tmp_path: Path) -> None:
    _preparer_suppression_inline(tmp_path, review_due="2026-01-02")

    erreurs = VALIDATEUR.valider(tmp_path, aujourd_hui=dt.date(2026, 1, 1))

    assert erreurs == []


def test_review_due_au_dela_du_plafond_est_rejetee(tmp_path: Path) -> None:
    _preparer_suppression_inline(tmp_path, review_due="2026-07-01")

    erreurs = VALIDATEUR.valider(tmp_path, aujourd_hui=dt.date(2026, 1, 1))

    assert (
        "inline:src/active.py:1:S1234 : review_due dépasse l'horizon de révision "
        "(2026-07-01 > 2026-06-30)"
    ) in erreurs


def test_review_due_dans_le_plafond_est_acceptee(tmp_path: Path) -> None:
    _preparer_suppression_inline(tmp_path, review_due="2026-06-30")

    erreurs = VALIDATEUR.valider(tmp_path, aujourd_hui=dt.date(2026, 1, 1))

    assert erreurs == []


def test_portee_file_sans_test_ni_justification_non_reductible_est_rejetee(tmp_path: Path) -> None:
    (tmp_path / "sonar-project.properties").write_text(
        "\n".join(
            [
                "sonar.issue.ignore.multicriteria=x1",
                "sonar.issue.ignore.multicriteria.x1.ruleKey=python:S1234",
                "sonar.issue.ignore.multicriteria.x1.resourceKey=src/example.py",
                "",
            ]
        ),
        encoding="utf-8",
    )
    _ecrire_inventaire(
        tmp_path,
        [
            {
                "id": "properties-multicriteria:x1",
                "kind": "properties-multicriteria",
                "rule": "python:S1234",
                "scope": "file",
                "sites": [{"path": "src/example.py"}],
                "owner": "équipe test",
                "justification": "Justification testée.",
                "compensating_test": None,
                "review_due": "2026-06-01",
                "accepted_risk": "Risque test.",
            }
        ],
    )

    erreurs = VALIDATEUR.valider(tmp_path, aujourd_hui=dt.date(2026, 1, 1))

    assert (
        "properties-multicriteria:x1 : portée file sans test compensatoire "
        "ni justification explicite de non-réductibilité"
    ) in erreurs


def test_portee_file_avec_justification_non_reductible_est_acceptee(tmp_path: Path) -> None:
    (tmp_path / "sonar-project.properties").write_text(
        "\n".join(
            [
                "sonar.issue.ignore.multicriteria=x1",
                "sonar.issue.ignore.multicriteria.x1.ruleKey=python:S1234",
                "sonar.issue.ignore.multicriteria.x1.resourceKey=src/example.py",
                "",
            ]
        ),
        encoding="utf-8",
    )
    _ecrire_inventaire(
        tmp_path,
        [
            {
                "id": "properties-multicriteria:x1",
                "kind": "properties-multicriteria",
                "rule": "python:S1234",
                "scope": "file",
                "sites": [{"path": "src/example.py"}],
                "owner": "équipe test",
                "justification": "Justification testée.",
                "compensating_test": None,
                "compensating_test_reason": (
                    "Non-réductible : la règle ne permet pas une portée plus fine."
                ),
                "review_due": "2026-06-01",
                "accepted_risk": "Risque test.",
            }
        ],
    )

    erreurs = VALIDATEUR.valider(tmp_path, aujourd_hui=dt.date(2026, 1, 1))

    assert erreurs == []


def test_suppression_inline_sans_test_ni_justification_est_rejetee(
    tmp_path: Path,
) -> None:
    _preparer_suppression_inline(tmp_path)
    inventaire = _entree_inline()
    del inventaire["compensating_test_reason"]
    _ecrire_inventaire(tmp_path, [inventaire])

    erreurs = VALIDATEUR.valider(tmp_path, aujourd_hui=dt.date(2026, 1, 1))

    assert (
        "inline:src/active.py:1:S1234 : portée line sans test compensatoire "
        "ni justification explicite de non-réductibilité"
    ) in erreurs


def test_suppression_inline_avec_justification_absence_test_est_acceptee(
    tmp_path: Path,
) -> None:
    _preparer_suppression_inline(tmp_path)
    inventaire = _entree_inline()
    inventaire["compensating_test_reason"] = (
        "La suppression porte sur une constante documentaire et non sur "
        "un comportement exécutable."
    )
    _ecrire_inventaire(tmp_path, [inventaire])

    erreurs = VALIDATEUR.valider(tmp_path, aujourd_hui=dt.date(2026, 1, 1))

    assert erreurs == []


def test_test_compensatoire_inexistant_est_rejete(tmp_path: Path) -> None:
    _preparer_suppression_inline(tmp_path)
    inventaire = _entree_inline()
    inventaire["compensating_test"] = "tests/test_inexistant_xyz.py"
    _ecrire_inventaire(tmp_path, [inventaire])

    erreurs = VALIDATEUR.valider(tmp_path, aujourd_hui=dt.date(2026, 1, 1))

    assert (
        "inline:src/active.py:1:S1234 : test compensatoire absent du dépôt : "
        "tests/test_inexistant_xyz.py"
    ) in erreurs


def test_test_compensatoire_existant_est_accepte(tmp_path: Path) -> None:
    _preparer_suppression_inline(tmp_path)
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_compensatoire.py").write_text(
        "def test_compensatoire() -> None:\n    assert True\n",
        encoding="utf-8",
    )
    inventaire = _entree_inline()
    inventaire["compensating_test"] = "tests/test_compensatoire.py"
    del inventaire["compensating_test_reason"]
    _ecrire_inventaire(tmp_path, [inventaire])

    erreurs = VALIDATEUR.valider(tmp_path, aujourd_hui=dt.date(2026, 1, 1))

    assert erreurs == []


def test_s2612_openbao_reste_limitee_aux_trois_lignes_inventoriees() -> None:
    proprietes = VALIDATEUR._proprietes(RACINE_DEPOT / "sonar-project.properties")
    ressources_multicriteres = [
        valeur
        for cle, valeur in proprietes.items()
        if cle.startswith("sonar.issue.ignore.multicriteria.")
        and cle.endswith(".resourceKey")
    ]
    inventaire = json.loads(
        (RACINE_DEPOT / "governance" / "sonar-suppressions.json").read_text(
            encoding="utf-8"
        )
    )
    suppressions_s2612 = [
        entree
        for entree in inventaire["suppressions"]
        if entree["rule"] == "S2612"
    ]

    assert all("openbao_flow.py" not in ressource for ressource in ressources_multicriteres)
    assert len(suppressions_s2612) == 3
    assert {entree["scope"] for entree in suppressions_s2612} == {"line"}
    assert {
        (entree["sites"][0]["path"], entree["sites"][0]["line"])
        for entree in suppressions_s2612
    } == {
        ("src/forgeai/deploy/openbao_flow.py", 102),
        ("src/forgeai/deploy/openbao_flow.py", 104),
        ("src/forgeai/deploy/openbao_flow.py", 109),
    }


def test_rapport_sonar_suppressions_est_synchronise_avec_inventaire() -> None:
    rapport = (RACINE_DEPOT / "governance" / "SONAR-SUPPRESSIONS.md").read_text(
        encoding="utf-8"
    )

    assert rapport == VALIDATEUR.rendre(RACINE_DEPOT)
