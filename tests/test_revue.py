"""Tests du pipeline de revue."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("revue", REPO / "scripts" / "revue.py")
revue = importlib.util.module_from_spec(spec)
spec.loader.exec_module(revue)

SHA = "a" * 64
DATE = "2025-01-01T12:00:00+00:00"


def _v(vendor, verdict="APPROVE", objs=None, sha=SHA, date=DATE):
    return {
        "vendor": vendor,
        "prompt_sha256": sha,
        "verdict": verdict,
        "objections": objs or [],
        "date_heure": date,
    }


def _etat():
    return {
        "base_commit": "b" * 40,
        "head_commit": "c" * 40,
        "head_tree": "d" * 40,
        "diff_digest": "e" * 64,
    }


def _recu(**changes):
    recu = {
        "schema": "recu-revue/1",
        "dossier": "S-1",
        "issue": 434,
        "round": 1,
        **_etat(),
        "prompt_sha256": SHA,
        "reviewers_attendus": ["deepseek", "gemini_flash", "longcat_20"],
        "codeur": ["fable"],  # jamais un vendor reviewer par défaut (anthropic n'y figure pas)
        "resultat": "APPROVE",
        "date_heure": DATE,
        "fenetre_heures": 24,
    }
    recu.update(changes)
    return recu


def test_composer_et_grok_meme_vendor():
    assert revue.vendor_of("composer_25") == revue.vendor_of("grok_45")
    assert revue.vendor_of("composer_25") != revue.vendor_of("deepseek")


def test_vendors_distincts_reconnus():
    assert len({revue.vendor_of(model) for model in ("deepseek", "gemini_flash", "glm_52")}) == 3


def test_trio_actif_de_revue_resout_trois_vendors_distincts():
    trio = ("DeepSeek-V4-Flash-0731", "Qwen3.8-27B", "gpt-daybreak-blue-latest")
    assert {revue.vendor_of(model) for model in trio} == {"deepseek", "alibaba", "openai"}


def test_vendor_table_derivee_de_roles_yaml_reelle():
    table = revue._vendor_table()
    assert table is not None
    assert "deepseek" in table
    assert table["deepseek"] == "deepseek"


def test_fable_exclu_car_provider_id_null():
    table = revue._vendor_table()
    assert table is not None
    assert "fable" not in table


def test_alias_ponctuation_variable_normalise_pareil():
    assert revue.vendor_of("qwen_37") == revue.vendor_of("qwen") == "alibaba"


def test_alias_modele_reponse_routes_yaml_reconnu():
    assert revue.vendor_of("DeepSeek-V4-Pro") == revue.vendor_of("deepseek") == "deepseek"


def test_alias_qwen_pc3_expose_par_litellm_resout_alibaba():
    assert {
        revue.vendor_of("Qwen3.8-27B"),
        revue.vendor_of("Qwen3.8-Flagship-PC3"),
    } == {"alibaba"}


def test_route_modele_reponse_avec_espace_reconnu(tmp_path):
    roles = tmp_path / "manifests" / "roles.yaml"
    routes = tmp_path / "manifests" / "routes.yaml"
    roles.parent.mkdir()
    roles.write_text(
        "membres:\n  - id: espace-modele\n    vendor: vendor-espace\n"
        "    provider_id: EspaceModele\nregles_revue:\n  vendors_par_story: 3\n",
        encoding="utf-8",
    )
    routes.write_text(
        "routes:\n  - {membre: espace-modele, provider_id: EspaceModele, modele_reponse: Nom Avec Espace, statut: ok}\n",
        encoding="utf-8",
    )
    table = revue._vendor_table(roles_path=roles, routes_path=routes)
    assert table is not None
    assert revue.vendor_of("Nom Avec Espace", table) == "vendor-espace"


def test_id_membre_avec_commentaire_inline_reconnu(tmp_path):
    roles = tmp_path / "manifests" / "roles.yaml"
    roles.parent.mkdir()
    roles.write_text(
        "membres:\n  - id: avec-commentaire  # commentaire\n    vendor: vendor-teste\n"
        "    provider_id: AvecCommentaire\nregles_revue:\n  vendors_par_story: 3\n",
        encoding="utf-8",
    )
    table = revue._vendor_table(roles_path=roles)
    assert table is not None
    assert "vendor-teste" in table.values()


def test_ajouter_un_vendor_ne_touche_pas_revue_py(tmp_path):
    roles = tmp_path / "manifests" / "roles.yaml"
    roles.parent.mkdir()
    roles.write_text(
        "membres:\n  - id: nouveau-modele\n    modele: Nouveau Modèle v1\n"
        "    vendor: nouveau-vendor\n    provider_id: NouveauModele-v1\n",
        encoding="utf-8",
    )
    table = revue._vendor_table(roles_path=roles)
    assert table is not None
    assert table["nouveaumodelev1"] == "nouveau-vendor"


def test_tally_invalide_si_roster_introuvable(monkeypatch):
    monkeypatch.setattr(revue, "_vendor_table", lambda: None)
    assert revue.tally([_v("deepseek"), _v("gemini_flash"), _v("longcat_20")])["result"] == "INVALIDE"


def test_tally_approve_unanime_3_vendors():
    result = revue.tally([_v("deepseek"), _v("gemini_flash"), _v("longcat_20")])
    assert result["result"] == "APPROVE"
    assert sorted(result["vendors"]) == ["deepseek", "google", "meituan"]


def test_tally_reject_si_un_reject():
    result = revue.tally([
        _v("deepseek"),
        _v("gemini_flash", "REJECT", [{"severity": "eleve", "file": "x.py", "line": 1, "desc": "bug"}]),
        _v("longcat_20"),
    ])
    assert result["result"] == "REJECT" and result["bloquantes"]


def test_tally_invalide_moins_de_3():
    assert revue.tally([_v("deepseek"), _v("gemini_flash")])["result"] == "INVALIDE"


def test_tally_invalide_moins_de_3_vendors_distincts():
    result = revue.tally([_v("composer_25"), _v("grok_45"), _v("gemini_flash")])
    assert result["result"] == "INVALIDE" and "vendor" in result["reason"]


def test_tally_invalide_prompts_non_identiques():
    result = revue.tally([_v("deepseek"), _v("gemini_flash", sha="b" * 64), _v("longcat_20")])
    assert result["result"] == "INVALIDE" and "identiques" in result["reason"]


def test_tally_invalide_verdict_malforme():
    assert revue.tally([_v("deepseek"), _v("gemini_flash", "PEUT-ETRE"), _v("longcat_20")])["result"] == "INVALIDE"


def test_tally_objections_triees_par_severite():
    result = revue.tally([
        _v("deepseek", "REJECT", [{"severity": "faible", "desc": "f"}]),
        _v("gemini_flash", "REJECT", [{"severity": "critique", "desc": "c"}]),
        _v("longcat_20", "REJECT", [{"severity": "moyen", "desc": "m"}]),
    ])
    assert [objection["severity"] for objection in result["objections"]] == ["critique", "moyen", "faible"]


def test_tally_reconnait_severite_francaise():
    result = revue.tally([
        _v("deepseek", "REJECT", [{"severite": "majeure"}]),
        _v("gemini_flash"),
        _v("longcat_20"),
    ])
    assert result["bloquantes"]


def test_tally_reconnait_severite_anglaise():
    result = revue.tally([
        _v("deepseek", "REJECT", [{"severity": "eleve"}]),
        _v("gemini_flash"),
        _v("longcat_20"),
    ])
    assert result["bloquantes"]


def test_build_prompt_deterministe_et_sans_injection():
    p1, sha1 = revue.build_prompt("B-09", "critère X", "a.py", "code_A")
    p2, sha2 = revue.build_prompt("B-09", "critère X", "a.py", "code_A")
    assert p1 == p2 and sha1 == sha2
    assert "code_A" in p1 and "B-09" in p1
    assert "note :" not in p1.lower() and "vérifie que" not in p1.lower()


def test_build_prompt_change_avec_artefact():
    assert revue.build_prompt("S", "c", "f", "AAA")[1] != revue.build_prompt("S", "c", "f", "BBB")[1]


def test_tally_rejette_vendor_inconnu():
    result = revue.tally([_v("bidon-a"), _v("bidon-b"), _v("bidon-c")])
    assert result["result"] == "INVALIDE" and "inconnu" in result["reason"]


def test_build_prompt_exige_marqueur(tmp_path):
    template = tmp_path / "bad.md"
    template.write_text("sans marqueur", encoding="utf-8")
    with pytest.raises(ValueError):
        revue.build_prompt("s", "c", "p", "a", template_path=template)


def test_build_prompt_pas_d_injection_croisee():
    prompt, _ = revue.build_prompt("{artefact}", "{artefact}", "p", "SECRET")
    assert "STORY : {artefact}" in prompt
    assert prompt.count("SECRET") == 1


def test_codeur_vendor_table_inclut_fable_sans_provider_id():
    table = revue._codeur_vendor_table()
    assert table is not None
    assert table["fable"] == "anthropic"


def test_diff_canonique_exclut_evidence_reviews():
    # RC1-010 (#440) lot 5d : evidence/reviews/ est la racine unique (reviews/ n'existe plus,
    # le repli legacy posé au lot 5a est retiré) — garde anti-paradoxe-bootstrap (le reçu et
    # les verdicts d'une revue en cours ne doivent jamais entrer dans le hash du diff qu'ils
    # examinent).
    code = ":100644 100644 a b M\0src/a.py\0"
    reviewed = code + ":000000 100644 0 c A\0evidence/reviews/S/RECU.json\0"
    assert revue._diff_canonique("base", "HEAD", runner=lambda _: code) == revue._diff_canonique(
        "base", "HEAD", runner=lambda _: reviewed
    )


def test_diff_canonique_exclut_path_classification_json():
    # #504 : governance/path-classification.json (généré par classify_paths.py) trace
    # individuellement chaque fichier reviews/**/evidence/reviews/**, y compris les nouveaux
    # RECU.json/*.verdict.json committés par CE reçu — donc régénérer ce manifeste APRÈS avoir
    # scellé le reçu change le diff que le reçu prétend attester (interblocage documenté #504).
    # Ce fichier est de toute façon déjà retiré à la main des packs de revue depuis le lot 5b
    # (reviewers ne le voient jamais) — l'exclure du diff_digest aligne l'outillage sur ce qui
    # est réellement revu.
    code = ":100644 100644 a b M\0src/a.py\0"
    reviewed = code + ":100644 100644 d e M\0governance/path-classification.json\0"
    assert revue._diff_canonique("base", "HEAD", runner=lambda _: code) == revue._diff_canonique(
        "base", "HEAD", runner=lambda _: reviewed
    )


def test_diff_canonique_exclut_sdd_review_history():
    code = ":100644 100644 a b M\0src/a.py\0"
    reviewed = code + ":100644 100644 d e M\0.superpowers/sdd/old-review.md\0"
    assert revue._diff_canonique("base", "HEAD", runner=lambda _: code) == revue._diff_canonique(
        "base", "HEAD", runner=lambda _: reviewed
    )


def test_diff_sdd_canonique_lie_le_journal_exclu_separement():
    code = ":100644 100644 a b M\0src/a.py\0"
    reviewed = code + ":100644 100644 d e M\0.superpowers/sdd/old-review.md\0"
    empty_sdd = revue._diff_sdd_canonique("base", "HEAD", runner=lambda _: code)
    changed_sdd = revue._diff_sdd_canonique("base", "HEAD", runner=lambda _: reviewed)

    assert empty_sdd != changed_sdd
    assert revue._diff_canonique("base", "HEAD", runner=lambda _: code) == revue._diff_canonique(
        "base", "HEAD", runner=lambda _: reviewed
    )


def test_diff_mission_canonique_lie_le_registre_exclu_separement():
    code = ":100644 100644 a b M\0src/a.py\0"
    reviewed = code + ":100644 100644 d e M\0evidence/registres/mission.jsonl\0"
    empty_mission = revue._diff_mission_canonique("base", "HEAD", runner=lambda _: code)
    changed_mission = revue._diff_mission_canonique("base", "HEAD", runner=lambda _: reviewed)

    assert empty_mission != changed_mission
    assert revue._diff_canonique("base", "HEAD", runner=lambda _: code) == revue._diff_canonique(
        "base", "HEAD", runner=lambda _: reviewed
    )


def test_diff_canonique_exclut_path_classification_markdown():
    # Même motif que ci-dessus pour le rendu Markdown (les compteurs affichés varient pour la
    # même raison — sans cette exclusion, le cycle se rouvrirait via ce second fichier généré).
    code = ":100644 100644 a b M\0src/a.py\0"
    reviewed = code + ":100644 100644 d e M\0governance/PATH-CLASSIFICATION.md\0"
    assert revue._diff_canonique("base", "HEAD", runner=lambda _: code) == revue._diff_canonique(
        "base", "HEAD", runner=lambda _: reviewed
    )


def test_diff_canonique_rejette_ref_commencant_par_tiret():
    with pytest.raises(ValueError):
        revue._diff_canonique("-x", "HEAD", runner=lambda _: "")


def test_diff_canonique_deterministe_ordre_independant():
    first = ":100644 100644 a b M\0z.py\0:100644 100644 c d M\0a.py\0"
    second = ":100644 100644 c d M\0a.py\0:100644 100644 a b M\0z.py\0"
    assert revue._diff_canonique("base", "HEAD", runner=lambda _: first) == revue._diff_canonique(
        "base", "HEAD", runner=lambda _: second
    )


def test_diff_canonique_invoque_git_avec_no_abbrev():
    """#569 : sans --no-abbrev, git --raw abrège les hash à une longueur qui dépend du nombre
    total d'objets du dépôt LOCAL (pas seulement du contenu diffé) — un worktree partageant le
    .git du dépôt principal et un clone frais produisent alors des digests différents pour le
    même diff logique. Ce test verrouille la présence du flag dans la commande invoquée."""
    commandes_recues = []

    def runner_espion(commande):
        commandes_recues.append(commande)
        return ""

    revue._diff_canonique("base", "HEAD", runner=runner_espion)
    assert len(commandes_recues) == 1
    assert "--no-abbrev" in commandes_recues[0]


def test_diff_artifact_sol_fige_la_configuration_git():
    commandes_recues = []

    revue._diff_artifact_canonique(
        "base",
        "HEAD",
        runner=lambda commande: commandes_recues.append(commande) or "",
    )
    commande = commandes_recues[0]
    for option in (
        "--no-textconv",
        "--full-index",
        "--diff-algorithm=myers",
        "--no-indent-heuristic",
        "--unified=3",
        "--inter-hunk-context=0",
        "--no-color",
        "--no-prefix",
        "--no-relative",
    ):
        assert option in commande


def test_sol_criteria_lit_la_section_de_la_story_figee():
    story = "# Story\n\n## Critères d’acceptation\n\n- [x] contrat\n\n## Limites\n"

    def runner(command):
        assert command[:2] == ["git", "show"]
        return story

    criteria = revue._sol_criteria_from_git(
        runner,
        "b" * 40,
        revue._SOL_CANONICAL_STORY_ID,
    )
    assert criteria == "- [x] contrat"


def test_sol_issue_est_le_numero_de_pr_et_non_le_numero_de_story():
    assert (
        revue._validate_sol_story_id(revue._SOL_CANONICAL_STORY_ID, 607)
        == revue._SOL_CANONICAL_STORY_ID
    )
    with pytest.raises(ValueError):
        revue._validate_sol_story_id(revue._SOL_CANONICAL_STORY_ID, 0)


def test_politique_sol_verifie_decision_et_frontieres_t3(tmp_path):
    policy = revue.load_autonomy_policy()
    policy["decision"] = "arbitrary"
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(policy), encoding="utf-8")
    with pytest.raises(ValueError, match="decision"):
        revue.load_autonomy_policy(path)

    policy = revue.load_autonomy_policy()
    policy["t3_limits"] = []
    path.write_text(json.dumps(policy), encoding="utf-8")
    with pytest.raises(ValueError, match="t3_limits"):
        revue.load_autonomy_policy(path)


def test_verifier_recu_approve_nominal():
    result = revue.verifier_recu(_recu(), [_v("deepseek"), _v("gemini_flash"), _v("longcat_20")], _etat())
    assert result["result"] == "APPROVE" and "reçu valide" in result["reason"]


def test_verifier_recu_donnees_absentes():
    receipt = _recu()
    del receipt["head_commit"]
    result = revue.verifier_recu(receipt, [_v("deepseek"), _v("gemini_flash"), _v("longcat_20")], _etat())
    assert result["result"] == "INVALIDE" and "head_commit" in result["reason"]


def test_verifier_recu_base_differente_rejete():
    result = revue.verifier_recu(
        _recu(base_commit="x" * 40), [_v("deepseek"), _v("gemini_flash"), _v("longcat_20")], _etat()
    )
    assert result["result"] == "INVALIDE" and "un autre commit" in result["reason"]


def test_verifier_recu_approve_meme_si_head_commit_differe_de_letat_git_actuel():
    # Régression revue scellée RC1-004-PR497 (objection critique DeepSeek-V4-Pro) : un reçu
    # correctement généré PUIS COMMIS ne peut structurellement jamais contenir le hash exact
    # du commit qui l'inclut lui-même (le commit du reçu change le head_commit). La liaison
    # réelle repose sur base_commit (jamais auto-référentiel) + diff_digest (déjà insensible,
    # exclut reviews/** des deux côtés) — PAS sur l'égalité stricte head_commit/head_tree.
    result = revue.verifier_recu(
        _recu(head_commit="x" * 40, head_tree="y" * 40),
        [_v("deepseek"), _v("gemini_flash"), _v("longcat_20")],
        _etat(),
    )
    assert result["result"] == "APPROVE"


def test_verifier_recu_diff_modifie_apres_revue():
    result = revue.verifier_recu(
        _recu(diff_digest="x" * 64), [_v("deepseek"), _v("gemini_flash"), _v("longcat_20")], _etat()
    )
    assert result["result"] == "INVALIDE" and "diff modifié" in result["reason"]


def test_verifier_recu_nombre_incorrect_de_reviewers():
    result = revue.verifier_recu(
        _recu(reviewers_attendus=["deepseek", "gemini_flash"]),
        [_v("deepseek"), _v("gemini_flash"), _v("longcat_20")],
        _etat(),
    )
    assert result["result"] == "INVALIDE" and "nombre incorrect" in result["reason"]


def test_verifier_recu_reponse_contradictoire():
    result = revue.verifier_recu(
        _recu(),
        [_v("deepseek"), _v("gemini_flash", "REJECT"), _v("longcat_20")],
        _etat(),
    )
    assert result["result"] == "REJECT" and "APPROVE" in result["reason"]


def test_verifier_recu_verdict_perime():
    expired = revue.verifier_recu(
        _recu(),
        [_v("deepseek", date="2025-01-03T12:00:00+00:00"), _v("gemini_flash"), _v("longcat_20")],
        _etat(),
    )
    valid = revue.verifier_recu(
        _recu(),
        [_v("deepseek", date="2025-01-01T14:00:00+00:00"), _v("gemini_flash"), _v("longcat_20")],
        _etat(),
    )
    assert expired["result"] == "INVALIDE" and "périmé" in expired["reason"]
    assert valid["result"] == "APPROVE"


def test_verifier_recu_auteur_ne_peut_pas_etre_reviewer():
    result = revue.verifier_recu(
        _recu(codeur=["deepseek"]), [_v("deepseek"), _v("gemini_flash"), _v("longcat_20")], _etat()
    )
    assert result["result"] == "INVALIDE" and "auteur" in result["reason"] and "reviewer" in result["reason"]


def test_verifier_recu_codeur_inconnu_echoue_dur():
    result = revue.verifier_recu(
        _recu(codeur=["id-bidon-inexistant"]),
        [_v("deepseek"), _v("gemini_flash"), _v("longcat_20")],
        _etat(),
    )
    assert result["result"] == "INVALIDE" and "codeur inconnu" in result["reason"]


def test_verifier_recu_codeur_vide_rejete():
    # Régression revue scellée RC1-004-PR497-v2 (objection critique DeepSeek-V4-Pro) :
    # verifier_recu() EST la frontière d'application réelle du gate — un RECU.json écrit ou
    # modifié à la main avec codeur:[] ne doit JAMAIS passer, même si la CLI `recu` exige
    # --codeur (un attaquant/une erreur peut toujours écrire le fichier directement).
    result = revue.verifier_recu(
        _recu(codeur=[]), [_v("deepseek"), _v("gemini_flash"), _v("longcat_20")], _etat()
    )
    assert result["result"] == "INVALIDE" and "codeur" in result["reason"]


def test_verifier_recu_objection_bloquante_avec_cle_francaise():
    verdicts = [
        _v("deepseek", objs=[{"severite": "critique", "desc": "bloquant"}]),
        _v("gemini_flash"),
        _v("longcat_20"),
    ]
    tally_result = revue.tally(verdicts)
    result = revue.verifier_recu(_recu(), verdicts, _etat())
    assert tally_result["bloquantes"]
    assert result["result"] == "REJECT" and "bloquante" in result["reason"]


def test_cli_recu_exige_codeur(monkeypatch, tmp_path):
    # Régression revue scellée RC1-004-PR497 (objection majeure DeepSeek-V4-Pro) : --codeur
    # silencieusement optionnel (défaut []) contournait l'anti-auto-review par omission —
    # désormais requis par argparse (SystemExit(2), jamais un défaut vide silencieux).
    monkeypatch.setattr(
        sys, "argv",
        [
            "revue.py", "recu",
            "--dossier", "S",
            "--base-ref", "origin/main",
            "--issue", "434",
            "--round", "1",
        ],
    )
    with pytest.raises(SystemExit) as excinfo:
        revue.main()
    assert excinfo.value.code == 2


def test_cmd_diff_canonique_imprime_empreinte(monkeypatch, capsys):
    monkeypatch.setattr(revue, "_diff_canonique", lambda base_ref, head_ref: "empreinte-test")
    args = SimpleNamespace(base_ref="origin/main", head_ref="HEAD")

    rc = revue._cmd_diff_canonique(args)

    assert rc == 0
    assert capsys.readouterr().out.strip() == "empreinte-test"


def test_cli_diff_canonique_route_correctement(monkeypatch, capsys):
    # Preuve que main() route bien "diff-canonique" vers _cmd_diff_canonique via argparse
    # (pas seulement testé en appel direct de la fonction ci-dessus).
    monkeypatch.setattr(revue, "_diff_canonique", lambda base_ref, head_ref: "e" * 8)
    monkeypatch.setattr(sys, "argv", ["revue.py", "diff-canonique", "--base-ref", "origin/main"])

    with pytest.raises(SystemExit) as excinfo:
        revue.main()

    assert excinfo.value.code == 0
    assert capsys.readouterr().out.strip() == "e" * 8


def test_cmd_recu_ecrit_fichier_avec_etat_mocke(monkeypatch, tmp_path, capsys):
    dossier = tmp_path / "evidence" / "reviews" / "S-1"
    dossier.mkdir(parents=True)
    verdict = _v("deepseek")
    (dossier / "DeepSeek-V4-Pro.verdict.json").write_text(json.dumps(verdict), encoding="utf-8")
    (dossier / "Gemini-3.7-Flash.verdict.json").write_text(
        json.dumps(_v("gemini_flash")), encoding="utf-8"
    )
    (dossier / "LongCat-2.0.verdict.json").write_text(
        json.dumps(_v("longcat_20")), encoding="utf-8"
    )
    monkeypatch.setattr(revue, "REPO", tmp_path)
    monkeypatch.setattr(revue, "_etat_git_reel", lambda base_ref, head_ref: _etat())
    out_file = tmp_path / "RECU.json"
    args = SimpleNamespace(
        dossier="S-1",
        base_ref="origin/main",
        head_ref="HEAD",
        issue=434,
        round=1,
        codeur=["fable"],
        fenetre_heures=24,
        out=str(out_file),
    )

    rc = revue._cmd_recu(args)

    assert rc == 0
    written = json.loads(out_file.read_text(encoding="utf-8"))
    assert written["resultat"] == "APPROVE"
    assert written["codeur"] == ["fable"]
    assert written["base_commit"] == _etat()["base_commit"]


def test_cmd_recu_imprime_sur_stdout_sans_out(monkeypatch, tmp_path, capsys):
    dossier = tmp_path / "evidence" / "reviews" / "S-2"
    dossier.mkdir(parents=True)
    (dossier / "DeepSeek-V4-Pro.verdict.json").write_text(
        json.dumps(_v("deepseek", "REJECT")), encoding="utf-8"
    )
    monkeypatch.setattr(revue, "REPO", tmp_path)
    monkeypatch.setattr(revue, "_etat_git_reel", lambda base_ref, head_ref: _etat())
    args = SimpleNamespace(
        dossier="S-2",
        base_ref="origin/main",
        head_ref="HEAD",
        issue=434,
        round=1,
        codeur=["fable"],
        fenetre_heures=24,
        out=None,
    )

    rc = revue._cmd_recu(args)

    assert rc == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["resultat"] == "INVALIDE"
