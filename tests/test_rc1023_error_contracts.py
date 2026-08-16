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

# Round 17 (#452) : sentinelle pour total_except_sites — la valeur par défaut doit refléter le
# VRAI décompte AST du fixture tree du test (root/src/forgeai/), sinon le nouveau garde-fou
# coverage.total_except_sites_src_forgeai vs décompte réel (round 17) ferait échouer les tests
# existants qui n'ont pas vocation à tester CE champ précis.
_AUTO_TOTAL = object()


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
    total_except_sites: object = _AUTO_TOTAL,
    measured_on: object = "test",
    measured_command: object = "grep test",
    coverage_note: object = "Note de couverture de test.",
    horizon_justification: object = "Horizon de test pour la validation des contrats.",
    omit_coverage_fields: list[str] | None = None,
    omit_review_horizon_fields: list[str] | None = None,
    schema_value: object = "error-handling-contracts/1",
) -> None:
    nb_contrats = len(contrats)
    contracted_val = nb_contrats if contracted is None else contracted
    floor_val = nb_contrats if floor is None else floor

    if total_except_sites is _AUTO_TOTAL:
        total_except_sites = VALIDATEUR._compter_except_handlers_reels(root)

    coverage = {
        "total_except_sites_src_forgeai": total_except_sites,
        "measured_on": measured_on,
        "measured_command": measured_command,
        "contracted": contracted_val,
        "floor": floor_val,
        "note": coverage_note,
    }
    for champ in omit_coverage_fields or []:
        coverage.pop(champ, None)

    review_horizon = {"days": horizon_days, "justification": horizon_justification}
    for champ in omit_review_horizon_fields or []:
        review_horizon.pop(champ, None)

    (root / "governance").mkdir(parents=True, exist_ok=True)
    (root / "governance" / "error-handling-contracts.json").write_text(
        json.dumps(
            {
                "schema": schema_value,
                "review_horizon": review_horizon,
                "coverage": coverage,
                "contracts": contrats,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _entree_valide(
    *,
    id_contrat: str = "site:src/forgeai/example.py:3",
    path: str = "src/forgeai/example.py",
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
        "src/forgeai/example.py",
        "try:\n    pass\nexcept ValueError:\n    pass\n",
    )
    contrat = _entree_valide(
        id_contrat="site:src/forgeai/example.py:3",
        path="src/forgeai/example.py",
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
        "src/forgeai/example.py",
        "try:\n    pass\nexcept ValueError:\n    pass\n",
    )
    contrat = _entree_valide()
    _ecrire_inventaire(tmp_path, [contrat], contracted=2, floor=1)

    erreurs = VALIDATEUR.valider(tmp_path, aujourd_hui=dt.date(2026, 1, 1))
    assert any("coverage.contracted (2) ne correspond pas" in e for e in erreurs)


def test_coverage_sous_le_plancher_detecte(tmp_path: Path) -> None:
    _creer_fichier_source(
        tmp_path,
        "src/forgeai/example.py",
        "try:\n    pass\nexcept ValueError:\n    pass\n",
    )
    contrat = _entree_valide()
    _ecrire_inventaire(tmp_path, [contrat], contracted=1, floor=5)

    erreurs = VALIDATEUR.valider(tmp_path, aujourd_hui=dt.date(2026, 1, 1))
    assert any("couverture sous le plancher : 1 contrats pour un plancher de 5" in e for e in erreurs)


def test_coverage_total_except_sites_manquant_detecte(tmp_path: Path) -> None:
    # Objection GPT-5.6-Terra-Pro (revue scellée round 8, #452) : coverage.total_except_sites_src_forgeai
    # n'était ni exigé ni typé — un inventaire "amputé" de ce champ passait quand même le gate.
    _creer_fichier_source(
        tmp_path, "src/forgeai/example.py", "try:\n    pass\nexcept ValueError:\n    pass\n"
    )
    contrat = _entree_valide()
    _ecrire_inventaire(tmp_path, [contrat], omit_coverage_fields=["total_except_sites_src_forgeai"])

    erreurs = VALIDATEUR.valider(tmp_path, aujourd_hui=dt.date(2026, 1, 1))
    assert any("total_except_sites_src_forgeai" in e for e in erreurs)


def test_coverage_total_except_sites_type_invalide_detecte(tmp_path: Path) -> None:
    _creer_fichier_source(
        tmp_path, "src/forgeai/example.py", "try:\n    pass\nexcept ValueError:\n    pass\n"
    )
    contrat = _entree_valide()
    _ecrire_inventaire(tmp_path, [contrat], total_except_sites=-5)

    erreurs = VALIDATEUR.valider(tmp_path, aujourd_hui=dt.date(2026, 1, 1))
    assert any("total_except_sites_src_forgeai" in e for e in erreurs)


def test_coverage_total_except_sites_ne_correspond_pas_au_reel_detecte(tmp_path: Path) -> None:
    """Round 17 (#452) — objection GPT-5.6-Terra-Pro (revue scellée) : la valeur de
    total_except_sites_src_forgeai n'était jamais comparée à un décompte AST réel de
    src/forgeai/ — n'importe quel entier positif passait le gate."""
    _creer_fichier_source(
        tmp_path, "src/forgeai/example.py", "try:\n    pass\nexcept ValueError:\n    pass\n"
    )
    contrat = _entree_valide()
    # le fixture tree ci-dessus contient exactement 1 except réel — 999 est délibérément faux
    _ecrire_inventaire(tmp_path, [contrat], total_except_sites=999)

    erreurs = VALIDATEUR.valider(tmp_path, aujourd_hui=dt.date(2026, 1, 1))
    assert any(
        "total_except_sites_src_forgeai (999) ne correspond pas au décompte AST réel" in e
        for e in erreurs
    )


def test_coverage_total_except_sites_auto_correspond_est_valide(tmp_path: Path) -> None:
    """Contre-preuve : la sentinelle _AUTO_TOTAL (utilisée par défaut dans tout le reste de ce
    fichier) doit produire un inventaire valide — confirme que le nouveau garde-fou round 17
    n'introduit aucun faux positif sur un total correctement mesuré."""
    _creer_fichier_source(
        tmp_path, "src/forgeai/example.py", "try:\n    pass\nexcept ValueError:\n    pass\n"
    )
    contrat = _entree_valide()
    _ecrire_inventaire(tmp_path, [contrat])  # total_except_sites=_AUTO_TOTAL par défaut

    erreurs = VALIDATEUR.valider(tmp_path, aujourd_hui=dt.date(2026, 1, 1))
    assert erreurs == []


def test_coverage_measured_on_manquant_detecte(tmp_path: Path) -> None:
    _creer_fichier_source(
        tmp_path, "src/forgeai/example.py", "try:\n    pass\nexcept ValueError:\n    pass\n"
    )
    contrat = _entree_valide()
    _ecrire_inventaire(tmp_path, [contrat], omit_coverage_fields=["measured_on"])

    erreurs = VALIDATEUR.valider(tmp_path, aujourd_hui=dt.date(2026, 1, 1))
    assert any("measured_on" in e for e in erreurs)


def test_coverage_measured_command_manquant_detecte(tmp_path: Path) -> None:
    _creer_fichier_source(
        tmp_path, "src/forgeai/example.py", "try:\n    pass\nexcept ValueError:\n    pass\n"
    )
    contrat = _entree_valide()
    _ecrire_inventaire(tmp_path, [contrat], omit_coverage_fields=["measured_command"])

    erreurs = VALIDATEUR.valider(tmp_path, aujourd_hui=dt.date(2026, 1, 1))
    assert any("measured_command" in e for e in erreurs)


def test_coverage_note_manquante_detectee(tmp_path: Path) -> None:
    _creer_fichier_source(
        tmp_path, "src/forgeai/example.py", "try:\n    pass\nexcept ValueError:\n    pass\n"
    )
    contrat = _entree_valide()
    _ecrire_inventaire(tmp_path, [contrat], omit_coverage_fields=["note"])

    erreurs = VALIDATEUR.valider(tmp_path, aujourd_hui=dt.date(2026, 1, 1))
    assert any("coverage.note" in e for e in erreurs)


def test_review_horizon_justification_manquante_detectee(tmp_path: Path) -> None:
    _creer_fichier_source(
        tmp_path, "src/forgeai/example.py", "try:\n    pass\nexcept ValueError:\n    pass\n"
    )
    contrat = _entree_valide()
    _ecrire_inventaire(tmp_path, [contrat], omit_review_horizon_fields=["justification"])

    erreurs = VALIDATEUR.valider(tmp_path, aujourd_hui=dt.date(2026, 1, 1))
    assert any("review_horizon.justification" in e for e in erreurs)


def test_site_function_manquante_detectee(tmp_path: Path) -> None:
    _creer_fichier_source(
        tmp_path, "src/forgeai/example.py", "try:\n    pass\nexcept ValueError:\n    pass\n"
    )
    contrat = _entree_valide(function_name="")
    _ecrire_inventaire(tmp_path, [contrat])

    erreurs = VALIDATEUR.valider(tmp_path, aujourd_hui=dt.date(2026, 1, 1))
    assert any("site.function" in e for e in erreurs)


def test_id_vide_detecte(tmp_path: Path) -> None:
    # Objection GPT-5.6-Terra-Pro (revue scellée round 10, #452) : la clé `id` était exigée
    # (présence), mais ni son type chaîne ni son caractère non vide ne l'étaient — un contrat
    # avec "id": "" passait la validation, invalidant le caractère machine-identifiable promis.
    _creer_fichier_source(
        tmp_path, "src/forgeai/example.py", "try:\n    pass\nexcept ValueError:\n    pass\n"
    )
    contrat = _entree_valide(id_contrat="")
    _ecrire_inventaire(tmp_path, [contrat])

    erreurs = VALIDATEUR.valider(tmp_path, aujourd_hui=dt.date(2026, 1, 1))
    assert any("champ 'id' doit être une chaîne non vide" in e for e in erreurs)


def test_id_null_detecte(tmp_path: Path) -> None:
    _creer_fichier_source(
        tmp_path, "src/forgeai/example.py", "try:\n    pass\nexcept ValueError:\n    pass\n"
    )
    contrat = _entree_valide(id_contrat=None)
    _ecrire_inventaire(tmp_path, [contrat])

    erreurs = VALIDATEUR.valider(tmp_path, aujourd_hui=dt.date(2026, 1, 1))
    assert any("champ 'id' doit être une chaîne non vide" in e for e in erreurs)


def test_site_line_booleen_detecte(tmp_path: Path) -> None:
    # Durcissement proactif (même famille que les objections GPT-5.6-Terra-Pro sur le typage) :
    # isinstance(line, int) accepte un bool en Python (True/False sont des int). Ce fichier
    # exclut déjà explicitement bool pour coverage.contracted/floor/total_except_sites_src_forgeai
    # — le même piège n'était pas gardé pour site.line.
    _creer_fichier_source(
        tmp_path, "src/forgeai/example.py", "try:\n    pass\nexcept ValueError:\n    pass\n"
    )
    contrat = _entree_valide()
    contrat["site"]["line"] = True
    _ecrire_inventaire(tmp_path, [contrat])

    erreurs = VALIDATEUR.valider(tmp_path, aujourd_hui=dt.date(2026, 1, 1))
    assert any("site.line" in e or "site.path" in e for e in erreurs)


def test_site_path_absolu_detecte(tmp_path: Path) -> None:
    # Objection GPT-5.6-Terra-Pro (revue scellée round 13, #452) : site.path n'était confiné ni
    # à la racine du dépôt ni à src/forgeai/. Piège pathlib : (root / "/etc/passwd") ==
    # Path("/etc/passwd") — un chemin absolu échappait entièrement à root.
    _creer_fichier_source(
        tmp_path, "src/forgeai/example.py", "try:\n    pass\nexcept ValueError:\n    pass\n"
    )
    contrat = _entree_valide(path="/etc/passwd")
    _ecrire_inventaire(tmp_path, [contrat])

    erreurs = VALIDATEUR.valider(tmp_path, aujourd_hui=dt.date(2026, 1, 1))
    assert any("site.path" in e and "absolu" in e for e in erreurs)


def test_site_path_hors_racine_detecte(tmp_path: Path) -> None:
    _creer_fichier_source(
        tmp_path, "src/forgeai/example.py", "try:\n    pass\nexcept ValueError:\n    pass\n"
    )
    # Fichier réel HORS de tmp_path (la « racine du dépôt » de ce test), atteignable par ../../..
    hors_racine = tmp_path.parent / "hors_racine_test.py"
    hors_racine.write_text("try:\n    pass\nexcept ValueError:\n    pass\n", encoding="utf-8")
    profondeur = len(tmp_path.parts) - len(tmp_path.anchor.split("/"))
    chemin_traversee = "/".join([".."] * (profondeur + 1)) + "/hors_racine_test.py"
    contrat = _entree_valide(path=chemin_traversee)
    _ecrire_inventaire(tmp_path, [contrat])

    erreurs = VALIDATEUR.valider(tmp_path, aujourd_hui=dt.date(2026, 1, 1))
    assert any("site.path" in e and ("racine" in e or "src/forgeai" in e) for e in erreurs)


def test_site_path_hors_src_forgeai_detecte(tmp_path: Path) -> None:
    _creer_fichier_source(
        tmp_path, "autre_dossier/example.py", "try:\n    pass\nexcept ValueError:\n    pass\n"
    )
    contrat = _entree_valide(path="autre_dossier/example.py")
    _ecrire_inventaire(tmp_path, [contrat])

    erreurs = VALIDATEUR.valider(tmp_path, aujourd_hui=dt.date(2026, 1, 1))
    assert any("site.path" in e and "src/forgeai" in e for e in erreurs)


def test_site_path_traversee_qui_reste_sous_racine_detecte(tmp_path: Path) -> None:
    """Round 16 (#452) — objection GPT-5.6-Terra-Pro (revue scellée) : le round 13 testait le
    préfixe src/forgeai/ sur la CHAÎNE BRUTE, contournable par une remontée ../.. qui reste sous
    la racine du dépôt tout en s'échappant de src/forgeai/ — ex. 'src/forgeai/../../tests/x.py'
    commence bien par 'src/forgeai/' en texte, mais résout hors de ce dossier."""
    _creer_fichier_source(
        tmp_path, "src/forgeai/example.py", "try:\n    pass\nexcept ValueError:\n    pass\n"
    )
    _creer_fichier_source(
        tmp_path, "tests/hors_scope.py", "try:\n    pass\nexcept ValueError:\n    pass\n"
    )
    contrat = _entree_valide(path="src/forgeai/../../tests/hors_scope.py", line=3)
    _ecrire_inventaire(tmp_path, [contrat])

    erreurs = VALIDATEUR.valider(tmp_path, aujourd_hui=dt.date(2026, 1, 1))
    assert any("site.path" in e and "src/forgeai" in e for e in erreurs)


def test_risk_paths_element_non_chaine_detecte(tmp_path: Path) -> None:
    # Durcissement proactif (round 12-13, même famille que l'objection GPT-5.6-Terra-Pro sur
    # exception_types) : risk_paths était vérifié « est une liste » mais pas le type de ses
    # éléments — [123, None] passait la validation.
    _creer_fichier_source(
        tmp_path, "src/forgeai/example.py", "try:\n    pass\nexcept ValueError:\n    pass\n"
    )
    contrat = _entree_valide()
    contrat["risk_paths"] = [123, None]
    _ecrire_inventaire(tmp_path, [contrat])

    erreurs = VALIDATEUR.valider(tmp_path, aujourd_hui=dt.date(2026, 1, 1))
    assert any("risk_paths" in e for e in erreurs)


def test_schema_version_inconnue_detectee(tmp_path: Path) -> None:
    # Objection GPT-5.6-Terra-Pro (revue scellée round 12, #452) : le validateur exigeait
    # 'schema' non vide, mais ne comparait jamais sa VALEUR à "error-handling-contracts/1" —
    # {"schema": "incompatible/999", ...} franchissait le gate sans être détecté.
    _creer_fichier_source(
        tmp_path, "src/forgeai/example.py", "try:\n    pass\nexcept ValueError:\n    pass\n"
    )
    contrat = _entree_valide()
    _ecrire_inventaire(tmp_path, [contrat], schema_value="incompatible/999")

    erreurs = VALIDATEUR.valider(tmp_path, aujourd_hui=dt.date(2026, 1, 1))
    assert any("schema" in e for e in erreurs)


def test_identifiant_duplique_detecte(tmp_path: Path) -> None:
    _creer_fichier_source(
        tmp_path,
        "src/forgeai/example.py",
        "try:\n    pass\nexcept ValueError:\n    pass\n",
    )
    contrat1 = _entree_valide(id_contrat="site:src/forgeai/example.py:3")
    contrat2 = _entree_valide(id_contrat="site:src/forgeai/example.py:3")
    _ecrire_inventaire(tmp_path, [contrat1, contrat2])

    erreurs = VALIDATEUR.valider(tmp_path, aujourd_hui=dt.date(2026, 1, 1))
    assert any("identifiant de contrat dupliqué : site:src/forgeai/example.py:3" in e for e in erreurs)


def test_sites_dupliques_sous_id_distincts_detecte(tmp_path: Path) -> None:
    """Round 17 (#452) — objection GPT-5.6-Terra-Pro (revue scellée) : deux entrées avec des id
    DISTINCTS mais ciblant le même (site.path, site.line) n'étaient jamais détectées — le plancher
    de couverture pouvait être atteint sans autant de sites AST réellement distincts."""
    _creer_fichier_source(
        tmp_path,
        "src/forgeai/example.py",
        "try:\n    pass\nexcept ValueError:\n    pass\n",
    )
    contrat1 = _entree_valide(id_contrat="site:src/forgeai/example.py:3")
    contrat2 = _entree_valide(id_contrat="un-autre-identifiant-totalement-different")
    _ecrire_inventaire(tmp_path, [contrat1, contrat2])

    erreurs = VALIDATEUR.valider(tmp_path, aujourd_hui=dt.date(2026, 1, 1))
    assert any("site dupliqué" in e and "src/forgeai/example.py:3" in e for e in erreurs)


def test_sites_dupliques_ecritures_de_chemin_equivalentes_detecte(tmp_path: Path) -> None:
    """Round 18 (#452) — objection GPT-5.6-Terra-Pro (revue scellée) : la dédup round 17
    comparait la CHAÎNE BRUTE de site.path, alors que la vérification AST résout et normalise ce
    chemin — 'src/forgeai/example.py' et 'src/forgeai/./example.py' visent le MÊME ExceptHandler
    mais n'étaient pas détectés comme doublons sous cette dédup textuelle."""
    _creer_fichier_source(
        tmp_path,
        "src/forgeai/example.py",
        "try:\n    pass\nexcept ValueError:\n    pass\n",
    )
    contrat1 = _entree_valide(
        id_contrat="site:src/forgeai/example.py:3", path="src/forgeai/example.py"
    )
    contrat2 = _entree_valide(
        id_contrat="un-autre-identifiant-totalement-different",
        path="src/forgeai/./example.py",
    )
    _ecrire_inventaire(tmp_path, [contrat1, contrat2])

    erreurs = VALIDATEUR.valider(tmp_path, aujourd_hui=dt.date(2026, 1, 1))
    assert any("site dupliqué" in e and "src/forgeai/example.py:3" in e for e in erreurs)


def test_champs_obligatoires_manquants_detectes(tmp_path: Path) -> None:
    _creer_fichier_source(
        tmp_path,
        "src/forgeai/example.py",
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
        "src/forgeai/example.py",
        "try:\n    pass\nexcept ValueError:\n    pass\n",
    )
    contrat = _entree_valide(disposition="MAYBE")
    _ecrire_inventaire(tmp_path, [contrat])

    erreurs = VALIDATEUR.valider(tmp_path, aujourd_hui=dt.date(2026, 1, 1))
    assert any("disposition invalide : MAYBE" in e for e in erreurs)


def test_review_due_dans_le_passe_detectee(tmp_path: Path) -> None:
    _creer_fichier_source(
        tmp_path,
        "src/forgeai/example.py",
        "try:\n    pass\nexcept ValueError:\n    pass\n",
    )
    contrat = _entree_valide(review_due="2025-12-31")
    _ecrire_inventaire(tmp_path, [contrat])

    erreurs = VALIDATEUR.valider(tmp_path, aujourd_hui=dt.date(2026, 1, 1))
    assert any("review_due dépassée (2025-12-31)" in e for e in erreurs)


def test_review_due_au_dela_horizon_detectee(tmp_path: Path) -> None:
    _creer_fichier_source(
        tmp_path,
        "src/forgeai/example.py",
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
        "src/forgeai/example.py",
        "try:\n    pass\nexcept ValueError:\n    pass\n",
    )
    contrat = _entree_valide(review_due="01-06-2026")
    _ecrire_inventaire(tmp_path, [contrat])

    erreurs = VALIDATEUR.valider(tmp_path, aujourd_hui=dt.date(2026, 1, 1))
    assert any("review_due doit être une date ISO valide" in e for e in erreurs)


def test_compensating_test_et_reason_tous_deux_null_detectes(tmp_path: Path) -> None:
    _creer_fichier_source(
        tmp_path,
        "src/forgeai/example.py",
        "try:\n    pass\nexcept ValueError:\n    pass\n",
    )
    contrat = _entree_valide(compensating_test=None, compensating_test_reason=None)
    _ecrire_inventaire(tmp_path, [contrat])

    erreurs = VALIDATEUR.valider(tmp_path, aujourd_hui=dt.date(2026, 1, 1))
    assert any("ni compensating_test ni compensating_test_reason" in e for e in erreurs)


def test_compensating_test_et_reason_tous_deux_renseignes_detectes(tmp_path: Path) -> None:
    _creer_fichier_source(
        tmp_path,
        "src/forgeai/example.py",
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
        "src/forgeai/example.py",
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
        "src/forgeai/example.py",
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
        "src/forgeai/example.py",
        "a = 1\nb = 2\nc = 3\n",
    )
    contrat = _entree_valide(path="src/forgeai/example.py", line=2)
    _ecrire_inventaire(tmp_path, [contrat])

    erreurs = VALIDATEUR.valider(tmp_path, aujourd_hui=dt.date(2026, 1, 1))
    assert any("site introuvable" in e for e in erreurs)


def test_derive_type_exception_detectee(tmp_path: Path) -> None:
    _creer_fichier_source(
        tmp_path,
        "src/forgeai/example.py",
        "try:\n    pass\nexcept KeyError:\n    pass\n",
    )
    contrat = _entree_valide(
        path="src/forgeai/example.py",
        line=3,
        exception_types=["ValueError"],
    )
    _ecrire_inventaire(tmp_path, [contrat])

    erreurs = VALIDATEUR.valider(tmp_path, aujourd_hui=dt.date(2026, 1, 1))
    assert any("types d'exception ont dérivé" in e for e in erreurs)


def test_fichier_source_absent_ne_plante_pas_et_signale_site_introuvable(tmp_path: Path) -> None:
    contrat = _entree_valide(
        path="src/forgeai/fichier_totalement_absent.py",
        line=10,
    )
    _ecrire_inventaire(tmp_path, [contrat])

    erreurs = VALIDATEUR.valider(tmp_path, aujourd_hui=dt.date(2026, 1, 1))
    assert any("site introuvable" in e for e in erreurs)


def test_except_avec_tuple_de_types_est_valide(tmp_path: Path) -> None:
    _creer_fichier_source(
        tmp_path,
        "src/forgeai/example.py",
        "try:\n    pass\nexcept (TypeError, ValueError):\n    pass\n",
    )
    contrat = _entree_valide(
        path="src/forgeai/example.py",
        line=3,
        exception_types=["TypeError", "ValueError"],
    )
    _ecrire_inventaire(tmp_path, [contrat])

    erreurs = VALIDATEUR.valider(tmp_path, aujourd_hui=dt.date(2026, 1, 1))
    assert erreurs == []


def test_rendre_rapport_markdown(tmp_path: Path) -> None:
    _creer_fichier_source(
        tmp_path,
        "src/forgeai/example.py",
        "try:\n    pass\nexcept ValueError:\n    pass\n",
    )
    _creer_fichier_source(
        tmp_path,
        "tests/test_example.py",
        "def test_example(): pass\n",
    )
    contrat = _entree_valide(
        id_contrat="site:src/forgeai/example.py:3",
        path="src/forgeai/example.py",
        line=3,
        disposition="FIXED",
        compensating_test="tests/test_example.py::test_example",
        compensating_test_reason=None,
    )
    _ecrire_inventaire(tmp_path, [contrat])

    markdown = VALIDATEUR.rendre(tmp_path)
    assert "# Contrats de gestion d'erreurs et risques acceptés" in markdown
    assert "src/forgeai/example.py:3" in markdown
    assert "FIXED" in markdown
    assert "tests/test_example.py::test_example" in markdown


def test_integration_inventaire_officiel_du_depot() -> None:
    erreurs = VALIDATEUR.valider(RACINE_DEPOT, aujourd_hui=dt.date(2026, 8, 16))
    assert erreurs == []


def test_compensating_test_fonction_inexistante_detectee(tmp_path: Path) -> None:
    _creer_fichier_source(
        tmp_path,
        "src/forgeai/example.py",
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
        "src/forgeai/example.py",
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
        "src/forgeai/example.py",
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
        "src/forgeai/example.py",
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


def test_compensating_test_fonction_non_test_rejetee(tmp_path: Path) -> None:
    """Round 14 (#452) — objection GPT-5.6-Terra-Pro (revue scellée) : compensating_test pouvait
    désigner N'IMPORTE QUELLE fonction existante (y compris du code de production), tant qu'elle
    portait le nom demandé — sans jamais vérifier que pytest la collecterait réellement
    (convention par défaut : le nom doit commencer par 'test_')."""
    _creer_fichier_source(
        tmp_path,
        "src/forgeai/example.py",
        "try:\n    pass\nexcept ValueError:\n    pass\n",
    )
    _creer_fichier_source(
        tmp_path,
        "tests/test_exemple.py",
        "def fonction_helper_pas_un_test(): pass\n",
    )
    contrat = _entree_valide(
        compensating_test="tests/test_exemple.py::fonction_helper_pas_un_test",
        compensating_test_reason=None,
    )
    _ecrire_inventaire(tmp_path, [contrat])

    erreurs = VALIDATEUR.valider(tmp_path, aujourd_hui=dt.date(2026, 1, 1))
    assert any("test compensatoire absent du dépôt" in e for e in erreurs)


def test_compensating_test_hors_dossier_tests_rejete(tmp_path: Path) -> None:
    """Round 14 (#452) — même objection : un fichier hors tests/ n'est jamais collecté par
    pytest (pyproject.toml : testpaths=["tests"]), même si la fonction s'appelle test_*."""
    _creer_fichier_source(
        tmp_path,
        "src/forgeai/example.py",
        "def test_quelque_chose(): pass\n",
    )
    contrat = _entree_valide(
        compensating_test="src/forgeai/example.py::test_quelque_chose",
        compensating_test_reason=None,
    )
    _ecrire_inventaire(tmp_path, [contrat])

    erreurs = VALIDATEUR.valider(tmp_path, aujourd_hui=dt.date(2026, 1, 1))
    assert any("test compensatoire absent du dépôt" in e for e in erreurs)


def test_compensating_test_fichier_hors_convention_pytest_rejete(tmp_path: Path) -> None:
    """Round 14 (#452) — même objection : un fichier sous tests/ mais pas nommé test_*.py (ou
    *_test.py) n'est pas collecté par pytest (python_files par défaut)."""
    _creer_fichier_source(
        tmp_path,
        "src/forgeai/example.py",
        "try:\n    pass\nexcept ValueError:\n    pass\n",
    )
    _creer_fichier_source(
        tmp_path,
        "tests/helpers_pas_un_module_de_tests.py",
        "def test_quelque_chose(): pass\n",
    )
    contrat = _entree_valide(
        compensating_test="tests/helpers_pas_un_module_de_tests.py::test_quelque_chose",
        compensating_test_reason=None,
    )
    _ecrire_inventaire(tmp_path, [contrat])

    erreurs = VALIDATEUR.valider(tmp_path, aujourd_hui=dt.date(2026, 1, 1))
    assert any("test compensatoire absent du dépôt" in e for e in erreurs)


def test_compensating_test_skip_inconditionnel_bare_rejete(tmp_path: Path) -> None:
    """Round 19 (#452) — objection GPT-5.6-Terra-Pro (revue scellée) : un test marqué
    @pytest.mark.skip n'est JAMAIS exécuté par pytest — la présence AST seule ne prouve rien."""
    _creer_fichier_source(
        tmp_path,
        "src/forgeai/example.py",
        "try:\n    pass\nexcept ValueError:\n    pass\n",
    )
    _creer_fichier_source(
        tmp_path,
        "tests/test_skip.py",
        "import pytest\n\n@pytest.mark.skip\ndef test_desactive(): pass\n",
    )
    contrat = _entree_valide(
        compensating_test="tests/test_skip.py::test_desactive",
        compensating_test_reason=None,
    )
    _ecrire_inventaire(tmp_path, [contrat])

    erreurs = VALIDATEUR.valider(tmp_path, aujourd_hui=dt.date(2026, 1, 1))
    assert any("test compensatoire absent du dépôt" in e for e in erreurs)


def test_compensating_test_skip_inconditionnel_avec_reason_rejete(tmp_path: Path) -> None:
    _creer_fichier_source(
        tmp_path,
        "src/forgeai/example.py",
        "try:\n    pass\nexcept ValueError:\n    pass\n",
    )
    _creer_fichier_source(
        tmp_path,
        "tests/test_skip2.py",
        "import pytest\n\n@pytest.mark.skip(reason='temporairement désactivé')\ndef test_desactive(): pass\n",
    )
    contrat = _entree_valide(
        compensating_test="tests/test_skip2.py::test_desactive",
        compensating_test_reason=None,
    )
    _ecrire_inventaire(tmp_path, [contrat])

    erreurs = VALIDATEUR.valider(tmp_path, aujourd_hui=dt.date(2026, 1, 1))
    assert any("test compensatoire absent du dépôt" in e for e in erreurs)


def test_compensating_test_skipif_conditionnel_reste_valide(tmp_path: Path) -> None:
    """Contre-preuve : @pytest.mark.skipif est délibérément TOLÉRÉ (portée bornée, documentée
    dans _decorateur_skip_inconditionnel) — un test skipif s'exécute réellement sous les
    conditions normales de CI (ex. @posix_only dans tests/test_proc.py, vrai sur ubuntu-latest).
    Rejeter systématiquement skipif casserait ce motif légitime déjà utilisé dans le dépôt réel."""
    _creer_fichier_source(
        tmp_path,
        "src/forgeai/example.py",
        "try:\n    pass\nexcept ValueError:\n    pass\n",
    )
    _creer_fichier_source(
        tmp_path,
        "tests/test_skipif.py",
        "import pytest\n\n@pytest.mark.skipif(False, reason='jamais sur cette plateforme')\ndef test_conditionnel(): pass\n",
    )
    contrat = _entree_valide(
        compensating_test="tests/test_skipif.py::test_conditionnel",
        compensating_test_reason=None,
    )
    _ecrire_inventaire(tmp_path, [contrat])

    erreurs = VALIDATEUR.valider(tmp_path, aujourd_hui=dt.date(2026, 1, 1))
    assert erreurs == []


def test_compensating_test_pytestmark_module_skip_rejete(tmp_path: Path) -> None:
    """Round 20 (#452) — objection GPT-5.6-Terra-Pro (revue scellée) : `pytestmark =
    pytest.mark.skip` au niveau module désactive INCONDITIONNELLEMENT tous les tests du fichier
    (vérifié empiriquement : 'skipped', jamais exécuté) — round 19 ne vérifiait que les
    décorateurs de la fonction ciblée, pas ce marqueur de module."""
    _creer_fichier_source(
        tmp_path,
        "src/forgeai/example.py",
        "try:\n    pass\nexcept ValueError:\n    pass\n",
    )
    _creer_fichier_source(
        tmp_path,
        "tests/test_pytestmark.py",
        "import pytest\n\npytestmark = pytest.mark.skip\n\ndef test_desactive_par_module(): pass\n",
    )
    contrat = _entree_valide(
        compensating_test="tests/test_pytestmark.py::test_desactive_par_module",
        compensating_test_reason=None,
    )
    _ecrire_inventaire(tmp_path, [contrat])

    erreurs = VALIDATEUR.valider(tmp_path, aujourd_hui=dt.date(2026, 1, 1))
    assert any("test compensatoire absent du dépôt" in e for e in erreurs)


def test_compensating_test_pytestmark_module_liste_skip_rejete(tmp_path: Path) -> None:
    """pytestmark peut aussi être une liste de marqueurs — même effet."""
    _creer_fichier_source(
        tmp_path,
        "src/forgeai/example.py",
        "try:\n    pass\nexcept ValueError:\n    pass\n",
    )
    _creer_fichier_source(
        tmp_path,
        "tests/test_pytestmark_liste.py",
        "import pytest\n\npytestmark = [pytest.mark.skip]\n\ndef test_desactive(): pass\n",
    )
    contrat = _entree_valide(
        compensating_test="tests/test_pytestmark_liste.py::test_desactive",
        compensating_test_reason=None,
    )
    _ecrire_inventaire(tmp_path, [contrat])

    erreurs = VALIDATEUR.valider(tmp_path, aujourd_hui=dt.date(2026, 1, 1))
    assert any("test compensatoire absent du dépôt" in e for e in erreurs)


def test_compensating_test_pytestmark_skipif_module_reste_valide(tmp_path: Path) -> None:
    """Contre-preuve : pytestmark = pytest.mark.skipif (conditionnel) reste toléré, même
    principe que la contre-preuve décorateur round 19 — cohérence des deux niveaux."""
    _creer_fichier_source(
        tmp_path,
        "src/forgeai/example.py",
        "try:\n    pass\nexcept ValueError:\n    pass\n",
    )
    _creer_fichier_source(
        tmp_path,
        "tests/test_pytestmark_skipif.py",
        "import pytest\n\npytestmark = pytest.mark.skipif(False, reason='x')\n\ndef test_conditionnel(): pass\n",
    )
    contrat = _entree_valide(
        compensating_test="tests/test_pytestmark_skipif.py::test_conditionnel",
        compensating_test_reason=None,
    )
    _ecrire_inventaire(tmp_path, [contrat])

    erreurs = VALIDATEUR.valider(tmp_path, aujourd_hui=dt.date(2026, 1, 1))
    assert erreurs == []


def test_compensating_test_classe_avec_skip_rejetee(tmp_path: Path) -> None:
    """Round 21 (#452) — objection GPT-5.6-Terra-Pro (revue scellée) : @pytest.mark.skip sur une
    classe Test* désactive TOUTES ses méthodes (vérifié empiriquement : 'skipped', jamais
    exécutée) — round 19 ne vérifiait le décorateur que sur la FONCTION/MÉTHODE ciblée, jamais
    sur la classe englobante."""
    _creer_fichier_source(
        tmp_path,
        "src/forgeai/example.py",
        "try:\n    pass\nexcept ValueError:\n    pass\n",
    )
    _creer_fichier_source(
        tmp_path,
        "tests/test_classe_skip.py",
        "import pytest\n\n@pytest.mark.skip\nclass TestDesactivee:\n    def test_methode(self):\n        pass\n",
    )
    contrat = _entree_valide(
        compensating_test="tests/test_classe_skip.py::TestDesactivee::test_methode",
        compensating_test_reason=None,
    )
    _ecrire_inventaire(tmp_path, [contrat])

    erreurs = VALIDATEUR.valider(tmp_path, aujourd_hui=dt.date(2026, 1, 1))
    assert any("test compensatoire absent du dépôt" in e for e in erreurs)


def test_compensating_test_classe_avec_skipif_reste_valide(tmp_path: Path) -> None:
    """Contre-preuve : @pytest.mark.skipif sur une classe reste toléré — cohérence avec les
    contre-preuves fonction (round 19) et module (round 20)."""
    _creer_fichier_source(
        tmp_path,
        "src/forgeai/example.py",
        "try:\n    pass\nexcept ValueError:\n    pass\n",
    )
    _creer_fichier_source(
        tmp_path,
        "tests/test_classe_skipif.py",
        "import pytest\n\n@pytest.mark.skipif(False, reason='x')\nclass TestConditionnelle:\n    def test_methode(self):\n        pass\n",
    )
    contrat = _entree_valide(
        compensating_test="tests/test_classe_skipif.py::TestConditionnelle::test_methode",
        compensating_test_reason=None,
    )
    _ecrire_inventaire(tmp_path, [contrat])

    erreurs = VALIDATEUR.valider(tmp_path, aujourd_hui=dt.date(2026, 1, 1))
    assert erreurs == []


def test_compensating_test_classe_avec_init_rejetee(tmp_path: Path) -> None:
    """Round 15 (#452) — objection GPT-5.6-Terra-Pro (revue scellée) : une classe Test* qui
    définit __init__ n'est PAS collectée par pytest (PytestCollectionWarning: cannot collect
    test class ... because it has a __init__ constructor — vérifié empiriquement), même si la
    méthode existe bien dans l'AST du fichier."""
    _creer_fichier_source(
        tmp_path,
        "src/forgeai/example.py",
        "try:\n    pass\nexcept ValueError:\n    pass\n",
    )
    _creer_fichier_source(
        tmp_path,
        "tests/test_classe_init.py",
        "class TestAvecInit:\n"
        "    def __init__(self):\n"
        "        self.x = 1\n"
        "    def test_methode(self):\n"
        "        assert self.x == 1\n",
    )
    contrat = _entree_valide(
        compensating_test="tests/test_classe_init.py::TestAvecInit::test_methode",
        compensating_test_reason=None,
    )
    _ecrire_inventaire(tmp_path, [contrat])

    erreurs = VALIDATEUR.valider(tmp_path, aujourd_hui=dt.date(2026, 1, 1))
    assert any("test compensatoire absent du dépôt" in e for e in erreurs)


def test_compensating_test_chemin_nu_sans_fonction_rejete(tmp_path: Path) -> None:
    """Round 5 (#452) — objection DeepSeek-V4-Pro (reviews/RC1-023-PR-v4) : un compensating_test
    qui n'est qu'un chemin de fichier existant, SANS ::fonction, ne doit plus suffire — même sans
    aucun rapport avec le correctif réel, un chemin nu passait auparavant la validation."""
    _creer_fichier_source(
        tmp_path,
        "src/forgeai/example.py",
        "try:\n    pass\nexcept ValueError:\n    pass\n",
    )
    _creer_fichier_source(
        tmp_path,
        "tests/test_sans_rapport.py",
        "def test_quelque_chose(): pass\n",
    )
    contrat = _entree_valide(
        disposition="FIXED",
        compensating_test="tests/test_sans_rapport.py",
        compensating_test_reason=None,
    )
    _ecrire_inventaire(tmp_path, [contrat])

    erreurs = VALIDATEUR.valider(tmp_path, aujourd_hui=dt.date(2026, 1, 1))
    assert any("test compensatoire absent du dépôt : tests/test_sans_rapport.py" in e for e in erreurs)


def test_contracts_entree_non_dict_signalee(tmp_path: Path) -> None:
    """Round 5 (#452) — objection DeepSeek-V4-Pro (reviews/RC1-023-PR-v4) : une entrée non-dict
    dans contracts était silencieusement ignorée au lieu de signaler une violation de schéma."""
    _ecrire_inventaire(tmp_path, [42], contracted=1, floor=1)

    erreurs = VALIDATEUR.valider(tmp_path, aujourd_hui=dt.date(2026, 1, 1))
    assert any("contracts[0]" in e and "entrée invalide" in e for e in erreurs)
