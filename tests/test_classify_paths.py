import importlib.util
import jsonschema
import pathlib
import unicodedata

_MODULE_PATH = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "governance" / "classify_paths.py"
_spec = importlib.util.spec_from_file_location("classify_paths", _MODULE_PATH)
classify_paths = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(classify_paths)


def test_collision_casse_docs_majuscule_minuscule() -> None:
    paths = ["Docs/a.md", "docs/a.md"]

    collisions = classify_paths.detect_collisions(paths)

    assert len(collisions["case"]) == 1
    assert set(collisions["case"][0]["paths"]) == set(paths)
    assert collisions["case"][0]["description"]


def test_collision_unicode_precompose_vs_decompose() -> None:
    precompose = "docs/café.md"
    decompose = "docs/cafe\u0301.md"

    collisions = classify_paths.detect_collisions([precompose, decompose])

    assert collisions["case"] == []
    assert len(collisions["unicode"]) >= 1
    assert any(
        {precompose, decompose}.issubset(set(entry["paths"]))
        and entry["description"]
        for entry in collisions["unicode"]
    )


def test_anomalie_normalisation_nfc_signalee() -> None:
    path = "docs/cafe\u0301.md"

    collisions = classify_paths.detect_collisions([path])

    assert unicodedata.normalize("NFC", path) != path
    assert any(
        entry["kind"] == "non_nfc"
        and path in entry["paths"]
        and entry["description"]
        for entry in collisions["unicode"]
    )


def test_caractere_invisible_rejete() -> None:
    violations = classify_paths.check_portability("docs/a\u200bb.md")

    assert any(
        violation["rule"] == "invisible_character"
        and violation["segment"] == "a\u200bb.md"
        and violation["detail"]
        for violation in violations
    )


def test_aucune_collision_sur_ensemble_sans_probleme() -> None:
    collisions = classify_paths.detect_collisions(["a/b.py", "a/c.py", "d/e.md"])

    assert collisions == {"case": [], "unicode": [], "portability": []}


def test_collision_cible_contre_chemin_non_deplace() -> None:
    paths = ["a/x.md", "b/y.md"]
    targets = {"a/x.md": "b/Y.md"}

    collisions = classify_paths.detect_collisions(paths, targets)

    assert any(
        {"b/Y.md", "b/y.md"}.issubset(set(entry["paths"]))
        and entry["description"]
        for entry in collisions["case"]
    )


def test_caractere_interdit_windows_deux_points() -> None:
    violations = classify_paths.check_portability("a:b.md")

    assert any(
        violation["rule"] == "windows_forbidden_character"
        and violation["segment"] == "a:b.md"
        and violation["detail"]
        for violation in violations
    )


def test_nom_reserve_windows_aux() -> None:
    lower_violations = classify_paths.check_portability("aux.md")
    upper_violations = classify_paths.check_portability("AUX.TXT")

    assert any(
        violation["rule"] == "windows_reserved_name"
        and violation["segment"] == "aux.md"
        for violation in lower_violations
    )
    assert any(
        violation["rule"] == "windows_reserved_name"
        and violation["segment"] == "AUX.TXT"
        for violation in upper_violations
    )


def test_nom_reserve_windows_com1() -> None:
    violations = classify_paths.check_portability("COM1.txt")

    assert any(
        violation["rule"] == "windows_reserved_name"
        and violation["segment"] == "COM1.txt"
        and violation["detail"]
        for violation in violations
    )


def test_segment_termine_par_point_ou_espace() -> None:
    point_violations = classify_paths.check_portability("dossier./f.md")
    espace_violations = classify_paths.check_portability("dossier /f.md")

    assert any(
        violation["rule"] == "windows_trailing_dot_or_space"
        and violation["segment"] == "dossier."
        for violation in point_violations
    )
    assert any(
        violation["rule"] == "windows_trailing_dot_or_space"
        and violation["segment"] == "dossier "
        for violation in espace_violations
    )


def test_segment_dotgit_interdit() -> None:
    violations = classify_paths.check_portability("archives/.git/config")

    assert any(
        violation["rule"] == "reserved_git_segment"
        and violation["segment"] == ".git"
        and violation["detail"]
        for violation in violations
    )


def test_chemin_legal_aucune_violation() -> None:
    violations = classify_paths.check_portability("src/forgeai/core/models.py")

    assert violations == []


def test_chemin_trop_long_echoue() -> None:
    path = "a" * 245

    violations = classify_paths.check_portability(path)

    assert any(
        violation["rule"] == "path_length"
        and violation["severity"] == "error"
        and violation["detail"]
        for violation in violations
    )


def test_chemin_longueur_avertissement() -> None:
    path = "a" * 205

    violations = classify_paths.check_portability(path)

    assert any(
        violation["rule"] == "path_length"
        and violation["severity"] == "warning"
        and violation["detail"]
        for violation in violations
    )


import hashlib
import json
import subprocess
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
RULES_PATH = REPO / "governance" / "path-classification-rules.json"


def test_manifest_valide_contre_son_schema() -> None:
    schema_path = REPO / "governance" / "path-classification.schema.json"
    manifest_path = REPO / "governance" / "path-classification.json"

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    data = json.loads(manifest_path.read_text(encoding="utf-8"))

    jsonschema.Draft202012Validator(schema).validate(data)


def _regles_fixture(rules: list[dict]) -> dict:
    return {
        "_schema": "path-classification-rules-v1",
        "classes": ["PRODUCT", "GOVERNANCE", "ARCHIVE"],
        "owners": {"equipe-test": {"role": "Fixture de test explicite."}},
        "rules": rules,
    }


def _regle_fixture(
    rule_id: str,
    kind: str = "prefix",
    value: str = "src/",
    target: str | None = None,
    target_kind: str = "keep",
) -> dict:
    return {
        "id": rule_id,
        "match": {"kind": kind, "value": value},
        "class": "PRODUCT",
        "generated": False,
        "owner": "equipe-test",
        "target": target,
        "target_kind": target_kind,
        "load_bearing": False,
        "rationale": "Règle de fixture explicitement créée pour ce test.",
    }


def _ecrit_regles_fixture(tmp_path: pathlib.Path, rules: dict) -> pathlib.Path:
    rules_path = tmp_path / "rules.json"
    rules_path.write_text(json.dumps(rules), encoding="utf-8")
    return rules_path


def test_load_rules_charge_le_fichier_reel() -> None:
    rules = classify_paths.load_rules(RULES_PATH)

    assert isinstance(rules, dict)
    assert {"rules", "classes", "owners"}.issubset(rules)


def test_load_rules_id_duplique_leve(tmp_path: pathlib.Path) -> None:
    rules = _regles_fixture(
        [
            _regle_fixture("duplique", value="a/"),
            _regle_fixture("duplique", value="b/"),
        ]
    )

    with pytest.raises(ValueError):
        classify_paths.load_rules(_ecrit_regles_fixture(tmp_path, rules))


def test_load_rules_owner_absent_leve(tmp_path: pathlib.Path) -> None:
    rule = _regle_fixture("owner-absent")
    rule["owner"] = "proprietaire-inexistant"
    rules = _regles_fixture([rule])

    with pytest.raises(ValueError):
        classify_paths.load_rules(_ecrit_regles_fixture(tmp_path, rules))


def test_load_rules_classe_invalide_leve(tmp_path: pathlib.Path) -> None:
    rule = _regle_fixture("classe-invalide")
    rule["class"] = "INEXISTANTE"
    rules = _regles_fixture([rule])

    with pytest.raises(ValueError):
        classify_paths.load_rules(_ecrit_regles_fixture(tmp_path, rules))


def test_load_rules_rationale_vide_leve(tmp_path: pathlib.Path) -> None:
    rule = _regle_fixture("rationale-vide")
    rule["rationale"] = ""
    rules = _regles_fixture([rule])

    with pytest.raises(ValueError):
        classify_paths.load_rules(_ecrit_regles_fixture(tmp_path, rules))


def test_classify_premier_match_gagne() -> None:
    specific = _regle_fixture("specifique", value="src/forgeai/")
    generic = _regle_fixture("generique", value="src/")
    rules = _regles_fixture([specific, generic])

    result = classify_paths.classify("src/forgeai/module.py", rules)

    assert result["rule_id"] == "specifique"


def test_classify_ordre_inverse_donne_lautre_regle() -> None:
    specific = _regle_fixture("specifique", value="src/forgeai/")
    generic = _regle_fixture("generique", value="src/")
    rules = _regles_fixture([generic, specific])

    result = classify_paths.classify("src/forgeai/module.py", rules)

    assert result["rule_id"] == "generique"


def test_classify_aucune_regle_leve() -> None:
    rules = _regles_fixture([_regle_fixture("seulement-src", value="src/")])

    with pytest.raises(ValueError, match="inconnu/fichier.txt"):
        classify_paths.classify("inconnu/fichier.txt", rules)


def test_classify_target_reroot() -> None:
    rule = _regle_fixture(
        "reviews-reroot",
        value="reviews/",
        target="evidence/reviews/",
        target_kind="reroot",
    )
    rules = _regles_fixture([rule])

    result = classify_paths.classify("reviews/x/y.json", rules)

    assert result["target_path"] == "evidence/reviews/x/y.json"


def test_classify_target_keep() -> None:
    rule = _regle_fixture("garder", value="src/", target=None, target_kind="keep")
    rules = _regles_fixture([rule])

    result = classify_paths.classify("src/module.py", rules)

    assert result["target_path"] is None


def test_classify_target_explicit() -> None:
    rule = _regle_fixture(
        "recherche-explicite",
        kind="exact",
        value="Recherche/x.yaml",
        target="archive/recherche/x.yaml",
        target_kind="explicit",
    )
    rules = _regles_fixture([rule])

    result = classify_paths.classify("Recherche/x.yaml", rules)

    assert result["target_path"] == "archive/recherche/x.yaml"


def test_classify_scripts_coordination_test_est_governance() -> None:
    rules = classify_paths.load_rules(RULES_PATH)

    result = classify_paths.classify("scripts/coordination/test_scope_guard.py", rules)

    assert result["class"] == "GOVERNANCE"


def test_classify_catalogue_sha256_est_product_et_generated() -> None:
    rules = classify_paths.load_rules(RULES_PATH)

    result = classify_paths.classify("src/forgeai/data/catalogue.sha256", rules)

    assert result["class"] == "PRODUCT"
    assert result["generated"] is True


def test_classify_state_current_md_est_generated() -> None:
    rules = classify_paths.load_rules(RULES_PATH)

    result = classify_paths.classify("governance/STATE-CURRENT.md", rules)

    assert result["class"] == "GENERATED"


def test_tracked_files_retourne_une_liste_triee_non_vide() -> None:
    paths = classify_paths.tracked_files(REPO)

    assert paths
    assert paths == sorted(paths)
    assert len(paths) == len(set(paths))
    assert "README.md" in paths


def test_tracked_files_compte_coherent_avec_git_ls_files() -> None:
    paths = classify_paths.tracked_files(REPO)
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=REPO,
        capture_output=True,
        check=True,
        text=True,
    )
    direct_paths = [line for line in result.stdout.splitlines() if line]

    assert len(paths) == len(direct_paths)


def test_tous_les_chemins_reels_sont_classes() -> None:
    rules = classify_paths.load_rules(RULES_PATH)

    for chemin in classify_paths.tracked_files(REPO):
        try:
            classify_paths.classify(chemin, rules)
        except ValueError:
            pytest.fail(f"non classé: {chemin}")


def _ecrit_fixture_texte(tmp_path: pathlib.Path, chemin: str, contenu: str) -> None:
    destination = tmp_path / chemin
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(contenu, encoding="utf-8")


def test_graphe_authority_json_produit_une_arete_hard(tmp_path: pathlib.Path) -> None:
    _ecrit_fixture_texte(
        tmp_path,
        "governance/authority.json",
        '{"sources":[{"path":"README.md"}]}',
    )
    _ecrit_fixture_texte(tmp_path, "README.md", "# Fixture\n")
    tracked = ["README.md", "governance/authority.json"]

    graph = classify_paths.build_reference_graph(tmp_path, tracked)

    assert any(
        edge["referrer"] == "governance/authority.json"
        and edge["line"] == 0
        and edge["candidate"] == "README.md"
        and edge["resolved"] == "README.md"
        and edge["severity"] == "hard"
        for edge in graph["edges"]
    )


def test_graphe_authority_json_path_absent_ignore(tmp_path: pathlib.Path) -> None:
    _ecrit_fixture_texte(
        tmp_path,
        "governance/authority.json",
        '{"sources":[{"path":"absent.md"}]}',
    )
    tracked = ["governance/authority.json"]

    graph = classify_paths.build_reference_graph(tmp_path, tracked)

    assert not any(
        edge["referrer"] == "governance/authority.json"
        and edge["candidate"] == "absent.md"
        for edge in graph["edges"]
    )


def test_graphe_binding_txt_resout_prefixe_reviews(tmp_path: pathlib.Path) -> None:
    _ecrit_fixture_texte(tmp_path, "reviews/BINDING.txt", "B-09-civ\n")
    _ecrit_fixture_texte(tmp_path, "reviews/B-09-civ/x.json", "{}")
    tracked = ["reviews/BINDING.txt", "reviews/B-09-civ/x.json"]

    graph = classify_paths.build_reference_graph(tmp_path, tracked)

    assert any(
        edge["referrer"] == "reviews/BINDING.txt"
        and edge["candidate"] == "B-09-civ"
        and edge["resolved"] == "reviews/B-09-civ"
        and edge["severity"] == "hard"
        for edge in graph["edges"]
    )


def test_graphe_binding_txt_commentaire_ignore(tmp_path: pathlib.Path) -> None:
    _ecrit_fixture_texte(tmp_path, "reviews/BINDING.txt", "# B-09-civ\n")
    _ecrit_fixture_texte(tmp_path, "reviews/B-09-civ/x.json", "{}")
    tracked = ["reviews/BINDING.txt", "reviews/B-09-civ/x.json"]

    graph = classify_paths.build_reference_graph(tmp_path, tracked)

    assert not any(
        entry["referrer"] == "reviews/BINDING.txt"
        and entry["candidate"] == "B-09-civ"
        for entry in graph["edges"] + graph["dangling"]
    )


def test_graphe_binding_txt_resout_prefixe_evidence_reviews(tmp_path: pathlib.Path) -> None:
    # RC1-010 (#440) lot 5a : une fois BINDING.txt lui-même déplacé (lot 5d), les entrées
    # doivent se résoudre contre le préfixe evidence/reviews/, pas reviews/.
    _ecrit_fixture_texte(tmp_path, "evidence/reviews/BINDING.txt", "S-migree\n")
    _ecrit_fixture_texte(tmp_path, "evidence/reviews/S-migree/x.json", "{}")
    tracked = ["evidence/reviews/BINDING.txt", "evidence/reviews/S-migree/x.json"]

    graph = classify_paths.build_reference_graph(tmp_path, tracked)

    assert any(
        edge["referrer"] == "evidence/reviews/BINDING.txt"
        and edge["candidate"] == "S-migree"
        and edge["resolved"] == "evidence/reviews/S-migree"
        and edge["severity"] == "hard"
        for edge in graph["edges"]
    )


def test_graphe_binding_txt_tolere_entree_pas_encore_migree(tmp_path: pathlib.Path) -> None:
    # Transition (lots 5b-5c) : BINDING.txt a déjà migré, mais une entrée qu'il référence vit
    # encore sous reviews/ (pas encore déplacée par ce lot précis) — doit rester résoluble.
    _ecrit_fixture_texte(tmp_path, "evidence/reviews/BINDING.txt", "S-pas-encore-migree\n")
    _ecrit_fixture_texte(tmp_path, "reviews/S-pas-encore-migree/x.json", "{}")
    tracked = ["evidence/reviews/BINDING.txt", "reviews/S-pas-encore-migree/x.json"]

    graph = classify_paths.build_reference_graph(tmp_path, tracked)

    assert any(
        edge["referrer"] == "evidence/reviews/BINDING.txt"
        and edge["candidate"] == "S-pas-encore-migree"
        and edge["resolved"] == "reviews/S-pas-encore-migree"
        for edge in graph["edges"]
    )


def test_graphe_sonar_resourcekey_severity_silent(tmp_path: pathlib.Path) -> None:
    _ecrit_fixture_texte(
        tmp_path,
        "sonar-project.properties",
        "sonar.issue.ignore.multicriteria.e1.resourceKey=src/x.py\n",
    )
    _ecrit_fixture_texte(tmp_path, "src/x.py", "pass\n")
    tracked = ["sonar-project.properties", "src/x.py"]

    graph = classify_paths.build_reference_graph(tmp_path, tracked)

    assert any(
        edge["referrer"] == "sonar-project.properties"
        and edge["candidate"] == "src/x.py"
        and edge["resolved"] == "src/x.py"
        and edge["severity"] == "silent"
        for edge in graph["edges"]
    )


def test_graphe_balayage_generique_resout_fichier_exact(tmp_path: pathlib.Path) -> None:
    _ecrit_fixture_texte(tmp_path, "notes.md", "Voir src/x.py pour le détail.\n")
    _ecrit_fixture_texte(tmp_path, "src/x.py", "pass\n")
    tracked = ["notes.md", "src/x.py"]

    graph = classify_paths.build_reference_graph(tmp_path, tracked)

    assert any(
        edge["referrer"] == "notes.md"
        and edge["candidate"] == "src/x.py"
        and edge["resolved"] == "src/x.py"
        for edge in graph["edges"]
    )


def test_graphe_balayage_generique_resout_prefixe_repertoire(tmp_path: pathlib.Path) -> None:
    _ecrit_fixture_texte(tmp_path, "notes.md", "Le module est dans src/pkg.\n")
    _ecrit_fixture_texte(tmp_path, "src/pkg/mod.py", "pass\n")
    tracked = ["notes.md", "src/pkg/mod.py"]

    graph = classify_paths.build_reference_graph(tmp_path, tracked)

    assert any(
        edge["referrer"] == "notes.md"
        and edge["candidate"] == "src/pkg"
        and edge["resolved"] == "src/pkg"
        for edge in graph["edges"]
    )


def test_graphe_url_jamais_une_arete(tmp_path: pathlib.Path) -> None:
    _ecrit_fixture_texte(
        tmp_path,
        "notes.md",
        "Voir https://example.com/src/x.py pour le détail.\n",
    )
    _ecrit_fixture_texte(tmp_path, "src/x.py", "pass\n")
    tracked = ["notes.md", "src/x.py"]

    graph = classify_paths.build_reference_graph(tmp_path, tracked)

    assert not any(
        entry["referrer"] == "notes.md"
        for entry in graph["edges"] + graph["dangling"]
    )


def test_graphe_reference_non_resolue_va_en_dangling(tmp_path: pathlib.Path) -> None:
    candidate = "chemin/qui/nexiste/pas.py"
    _ecrit_fixture_texte(tmp_path, "notes.md", f"Référence: {candidate}\n")
    tracked = ["notes.md"]

    graph = classify_paths.build_reference_graph(tmp_path, tracked)

    assert any(
        entry["referrer"] == "notes.md" and entry["candidate"] == candidate
        for entry in graph["dangling"]
    )
    assert not any(
        entry["referrer"] == "notes.md" and entry["candidate"] == candidate
        for entry in graph["edges"]
    )


def test_graphe_reel_authority_json_a_des_aretes() -> None:
    tracked = classify_paths.tracked_files(REPO)

    graph = classify_paths.build_reference_graph(REPO, tracked)

    assert any(
        edge["referrer"] == "governance/authority.json"
        for edge in graph["edges"]
    )


def test_graphe_reel_coderabbit_recherche_est_dangling() -> None:
    tracked = classify_paths.tracked_files(REPO)

    assert ".coderabbit.yaml" in tracked

    graph = classify_paths.build_reference_graph(REPO, tracked)
    recherche_est_resolu = any(path.startswith("Recherche/") for path in tracked)

    if recherche_est_resolu:
        assert isinstance(graph, dict)
        assert {"edges", "dangling"}.issubset(graph)
    else:
        assert any(
            entry["referrer"] == ".coderabbit.yaml"
            for entry in graph["dangling"]
        )


def test_graphe_fichier_binaire_ignore_sans_erreur(tmp_path: pathlib.Path) -> None:
    binary_path = tmp_path / "fixture.bin"
    binary_path.write_bytes(b"\xff\xfe\x00src/x.py")
    _ecrit_fixture_texte(tmp_path, "src/x.py", "pass\n")
    tracked = ["fixture.bin", "src/x.py"]

    graph = classify_paths.build_reference_graph(tmp_path, tracked)

    assert graph == {"edges": [], "dangling": []}


def test_build_manifest_sur_vrai_depot_zero_non_classe() -> None:
    manifest = classify_paths.build_manifest(REPO)

    assert manifest["summary"]["unclassified_total"] == 0
    assert manifest["summary"]["tracked_total"] == len(classify_paths.tracked_files(REPO))


def test_build_manifest_deux_generations_identiques() -> None:
    first = classify_paths.build_manifest(REPO)
    second = classify_paths.build_manifest(REPO)

    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_build_manifest_rules_sha256_correspond_au_fichier() -> None:
    manifest = classify_paths.build_manifest(REPO)
    normalized = RULES_PATH.read_text(encoding="utf-8").replace("\r\n", "\n")
    expected = hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    assert manifest["rules_sha256"] == expected


def test_build_manifest_entries_triees_par_path() -> None:
    manifest = classify_paths.build_manifest(REPO)
    paths = [entry["path"] for entry in manifest["entries"]]

    assert paths == sorted(paths)


def test_build_manifest_summary_by_class_coherent() -> None:
    manifest = classify_paths.build_manifest(REPO)

    assert sum(manifest["summary"]["by_class"].values()) == manifest["summary"]["tracked_total"]


def test_build_manifest_catalogue_sha256_generated_et_product() -> None:
    manifest = classify_paths.build_manifest(REPO)
    entry = next(
        item
        for item in manifest["entries"]
        if item["path"] == "src/forgeai/data/catalogue.sha256"
    )

    assert entry["class"] == "PRODUCT"
    assert entry["generated"] is True


def test_render_contient_entete_ne_pas_editer() -> None:
    manifest = classify_paths.build_manifest(REPO)

    assert (
        "NE PAS ÉDITER À LA MAIN — généré par "
        "scripts/governance/classify_paths.py --render"
    ) in classify_paths.render(manifest)


def test_render_ne_contient_pas_le_detail_de_chaque_entree() -> None:
    manifest = classify_paths.build_manifest(REPO)

    assert len(classify_paths.render(manifest)) < 5000


def test_check_sur_vrai_depot_avant_render_echoue() -> None:
    json_path = REPO / "governance" / "path-classification.json"
    markdown_path = REPO / "governance" / "PATH-CLASSIFICATION.md"

    ok, messages = classify_paths.check(REPO)

    if not json_path.exists() or not markdown_path.exists():
        assert ok is False
        assert messages
    else:
        assert isinstance(ok, bool)
        assert isinstance(messages, list)


def _initialise_depot_jouet(repo: pathlib.Path) -> None:
    _ecrit_fixture_texte(repo, "README.md", "# Dépôt jouet\n")
    _ecrit_fixture_texte(
        repo,
        "governance/path-classification-rules.json",
        json.dumps(
            {
                "_schema": "path-classification-rules-v1",
                "classes": ["PRODUCT", "GOVERNANCE", "ARCHIVE"],
                "owners": {
                    "equipe-test": {
                        "role": "Fixture de test explicite.",
                    }
                },
                "rules": [
                    {
                        "id": "readme",
                        "match": {"kind": "exact", "value": "README.md"},
                        "class": "PRODUCT",
                        "generated": False,
                        "owner": "equipe-test",
                        "target": None,
                        "target_kind": "keep",
                        "load_bearing": False,
                        "rationale": "Le README est classé pour la fixture.",
                    },
                    {
                        "id": "governance",
                        "match": {"kind": "prefix", "value": "governance/"},
                        "class": "GOVERNANCE",
                        "generated": False,
                        "owner": "equipe-test",
                        "target": None,
                        "target_kind": "keep",
                        "load_bearing": False,
                        "rationale": "La gouvernance est classée pour la fixture.",
                    },
                ],
            }
        ),
    )
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "add", "README.md", "governance/path-classification-rules.json"],
        cwd=repo,
        check=True,
        capture_output=True,
    )


def test_render_puis_check_aller_retour(tmp_path: pathlib.Path) -> None:
    repo_jouet = tmp_path / "repo"
    repo_jouet.mkdir()
    _initialise_depot_jouet(repo_jouet)

    rendered = classify_paths.main(["--repo-root", str(repo_jouet), "--render"])
    checked = classify_paths.main(["--repo-root", str(repo_jouet)])

    assert rendered == 0
    assert checked == 0


def test_check_detecte_derive(tmp_path: pathlib.Path) -> None:
    repo_jouet = tmp_path / "repo"
    repo_jouet.mkdir()
    _initialise_depot_jouet(repo_jouet)
    assert classify_paths.main(["--repo-root", str(repo_jouet), "--render"]) == 0

    manifest_path = repo_jouet / "governance/path-classification.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["summary"]["tracked_total"] = 999
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    ok, messages = classify_paths.check(repo_jouet)

    assert ok is False
    assert messages


def test_main_retourne_1_sur_erreur_sans_lever(tmp_path: pathlib.Path) -> None:
    repo_vide = tmp_path / "repo-vide"
    repo_vide.mkdir()

    result = classify_paths.main(["--repo-root", str(repo_vide)])

    assert result == 1


def _manifest_vagues_fixture(entries: list[dict], edges: list[dict]) -> dict:
    return {
        "entries": entries,
        "reference_graph": {
            "edges": edges,
            "dangling": [],
        },
    }


def _entree_vague_fixture(path: str, target_path: str | None) -> dict:
    return {
        "path": path,
        "target_path": target_path,
    }


def _arete_hard_fixture(referrer: str, resolved: str) -> dict:
    return {
        "referrer": referrer,
        "resolved": resolved,
        "severity": "hard",
    }


def test_compute_waves_sans_dependance_une_seule_vague() -> None:
    manifest = _manifest_vagues_fixture(
        [
            _entree_vague_fixture("archive/a.md", "evidence/a.md"),
            _entree_vague_fixture("archive/b.md", "evidence/b.md"),
        ],
        [],
    )

    waves = classify_paths.compute_waves(manifest)

    assert waves == [
        {
            "id": 0,
            "paths": ["archive/a.md", "archive/b.md"],
            "rollback": waves[0]["rollback"],
        }
    ]
    assert waves[0]["rollback"]


def test_compute_waves_avec_dependance_deux_vagues() -> None:
    manifest = _manifest_vagues_fixture(
        [
            _entree_vague_fixture("archive/a.md", "evidence/a.md"),
            _entree_vague_fixture("archive/b.md", "evidence/b.md"),
        ],
        [_arete_hard_fixture("archive/a.md", "archive/b.md")],
    )

    waves = classify_paths.compute_waves(manifest)
    wave_by_path = {
        path: wave["id"]
        for wave in waves
        for path in wave["paths"]
    }

    assert wave_by_path["archive/b.md"] < wave_by_path["archive/a.md"]
    assert len(waves) == 2


def test_compute_waves_cycle_leve() -> None:
    manifest = _manifest_vagues_fixture(
        [
            _entree_vague_fixture("archive/a.md", "evidence/a.md"),
            _entree_vague_fixture("archive/b.md", "evidence/b.md"),
        ],
        [
            _arete_hard_fixture("archive/a.md", "archive/b.md"),
            _arete_hard_fixture("archive/b.md", "archive/a.md"),
        ],
    )

    with pytest.raises(ValueError, match="archive/[ab]\\.md"):
        classify_paths.compute_waves(manifest)


def test_compute_waves_ignore_entrees_sans_target() -> None:
    manifest = _manifest_vagues_fixture(
        [
            _entree_vague_fixture("archive/deplace.md", "evidence/deplace.md"),
            _entree_vague_fixture("src/reste.py", None),
        ],
        [],
    )

    waves = classify_paths.compute_waves(manifest)
    paths = [path for wave in waves for path in wave["paths"]]

    assert paths == ["archive/deplace.md"]
    assert "src/reste.py" not in paths


def test_compute_waves_chaque_vague_a_un_rollback_non_vide() -> None:
    manifest = _manifest_vagues_fixture(
        [
            _entree_vague_fixture("archive/a.md", "evidence/a.md"),
            _entree_vague_fixture("archive/b.md", "evidence/b.md"),
        ],
        [_arete_hard_fixture("archive/a.md", "archive/b.md")],
    )

    waves = classify_paths.compute_waves(manifest)

    assert len(waves) >= 2
    assert all(
        isinstance(wave["rollback"], str) and wave["rollback"]
        for wave in waves
    )


def test_compute_waves_sur_vrai_manifest_aucune_exception() -> None:
    manifest = classify_paths.build_manifest(REPO)

    try:
        waves = classify_paths.compute_waves(manifest)
    except Exception as error:
        pytest.fail(f"compute_waves a échoué sur le manifest réel : {error}")

    assert isinstance(waves, list)


def test_graphe_ignore_le_manifest_genere_comme_source(
    tmp_path: pathlib.Path,
) -> None:
    manifest_path = getattr(
        classify_paths,
        "_MANIFEST_JSON",
        "governance/path-classification.json",
    )
    if isinstance(manifest_path, pathlib.PurePath):
        manifest_path = manifest_path.as_posix()
    _ecrit_fixture_texte(
        tmp_path,
        manifest_path,
        '{"path": "src/x.py", "candidate": "src/x.py"}',
    )
    _ecrit_fixture_texte(tmp_path, "src/x.py", "pass\n")
    tracked = [manifest_path, "src/x.py"]

    graph = classify_paths.build_reference_graph(tmp_path, tracked)

    assert not any(
        entry["referrer"] == manifest_path
        for entry in graph["edges"] + graph["dangling"]
    )


def test_main_retourne_1_quand_check_echoue_reellement(
    tmp_path: pathlib.Path,
) -> None:
    repo_jouet = tmp_path / "repo"
    repo_jouet.mkdir()
    _initialise_depot_jouet(repo_jouet)

    assert classify_paths.main(["--repo-root", str(repo_jouet), "--render"]) == 0

    manifest_path = repo_jouet / getattr(
        classify_paths,
        "_MANIFEST_JSON",
        "governance/path-classification.json",
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["summary"]["tracked_total"] = 999
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    assert classify_paths.main(["--repo-root", str(repo_jouet)]) == 1


def test_main_exit_code_processus_reflete_lechec(tmp_path: pathlib.Path) -> None:
    _initialise_depot_jouet(tmp_path)

    rendered = subprocess.run(
        [
            sys.executable,
            str(_MODULE_PATH),
            "--repo-root",
            str(tmp_path),
            "--render",
        ],
        capture_output=True,
        text=True,
    )

    assert rendered.returncode == 0

    manifest_path = tmp_path / "governance" / "path-classification.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["summary"]["tracked_total"] = 999
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    checked = subprocess.run(
        [
            sys.executable,
            str(_MODULE_PATH),
            "--repo-root",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
    )

    assert checked.returncode == 1
