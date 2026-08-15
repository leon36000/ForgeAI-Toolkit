"""Tests du pipeline de revue (scripts/revue.py) — dépouillement déterministe + neutralité.

Ce code est CRITIQUE : c'est l'outil qui juge toutes les revues futures. Sa logique de
dépouillement est une fonction pure de règles binaires (invariant #10) et sa génération de
prompt est neutre par construction (invariant #5).
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("revue", REPO / "scripts" / "revue.py")
revue = importlib.util.module_from_spec(spec)
spec.loader.exec_module(revue)

SHA = "a" * 64


def _v(vendor, verdict="APPROVE", objs=None, sha=SHA):
    return {"vendor": vendor, "prompt_sha256": sha, "verdict": verdict,
            "objections": objs or []}


# ---------- vendor mapping ----------

def test_composer_et_grok_meme_vendor():
    assert revue.vendor_of("composer") == revue.vendor_of("grok")
    assert revue.vendor_of("composer") != revue.vendor_of("deepseek")


def test_vendors_distincts_reconnus():
    assert len({revue.vendor_of(m) for m in ("deepseek", "gemini", "glm52")}) == 3


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
    # "qwen37max" (sans séparateur, régression pré-existante test_reviews_gate.py) et
    # "qwen3.7-max" (provider_id réel de manifests/roles.yaml) doivent résoudre au même vendor.
    assert revue.vendor_of("qwen37max") == revue.vendor_of("qwen") == "alibaba"


def test_alias_modele_reponse_routes_yaml_reconnu():
    # manifests/roles.yaml déclare provider_id "deepseek" pour ce membre, mais le nom de route
    # LiteLLM réel (manifests/routes.yaml, modele_reponse) — celui qui apparaît effectivement
    # comme reviewer_model dans les verdicts scellés réels — est "DeepSeek-V4-Pro" : les deux
    # doivent résoudre au même vendor sans que revue.py ait besoin de le coder en dur.
    assert revue.vendor_of("DeepSeek-V4-Pro") == revue.vendor_of("deepseek") == "deepseek"


def test_route_modele_reponse_avec_espace_reconnu(tmp_path):
    # Régression revue scellée RC1-003-PR489-v2 (objection mineure Gemini-3.1-Pro) : le
    # nom de route réel (modele_reponse) peut contenir un espace — un futur vendor avec un
    # tel nom ne doit pas échapper à la reconnaissance de son identité anti-Sybil.
    roles = tmp_path / "manifests" / "roles.yaml"
    routes = tmp_path / "manifests" / "routes.yaml"
    roles.parent.mkdir()
    roles.write_text(
        "membres:\n"
        "  - id: espace-modele\n"
        "    vendor: vendor-espace\n"
        "    provider_id: EspaceModele\n"
        "regles_revue:\n"
        "  vendors_par_story: 3\n",
        encoding="utf-8",
    )
    routes.write_text(
        "routes:\n"
        "  - {membre: espace-modele, provider_id: EspaceModele,"
        " modele_reponse: Nom Avec Espace, statut: ok}\n",
        encoding="utf-8",
    )

    table = revue._vendor_table(roles_path=roles, routes_path=routes)

    assert table is not None
    # Les clés sont normalisées (ponctuation/espaces retirés) : "Nom Avec Espace" doit être
    # capturé EN ENTIER par le parseur (pas tronqué au 1er espace) avant normalisation, sinon
    # la clé stockée ne correspondrait pas à une recherche sur le nom complet.
    assert revue.vendor_of("Nom Avec Espace", table) == "vendor-espace"


def test_id_membre_avec_commentaire_inline_reconnu(tmp_path):
    # Régression revue scellée RC1-003-PR489 (objection mineure DeepSeek-V4-Pro) : un
    # commentaire inline sur la ligne "- id:" elle-même (pas seulement sur vendor/provider_id/
    # modele) ne doit pas faire disparaître silencieusement le membre du roster.
    roles = tmp_path / "manifests" / "roles.yaml"
    roles.parent.mkdir()
    roles.write_text(
        "membres:\n"
        "  - id: avec-commentaire  # codeur de cette story\n"
        "    vendor: vendor-teste\n"
        "    provider_id: AvecCommentaire\n"
        "regles_revue:\n"
        "  vendors_par_story: 3\n",
        encoding="utf-8",
    )

    table = revue._vendor_table(roles_path=roles)

    assert table is not None
    assert "vendor-teste" in table.values()


def test_ajouter_un_vendor_ne_touche_pas_revue_py(tmp_path):
    # Preuve exécutable du critère d'acceptation #433 : un nouveau vendor devient reconnu
    # par une donnée seule (manifests/roles.yaml), sans toucher une ligne de revue.py.
    roles = tmp_path / "manifests" / "roles.yaml"
    roles.parent.mkdir()
    roles.write_text(
        "membres:\n"
        "  - id: nouveau-modele\n"
        "    modele: Nouveau Modèle v1\n"
        "    vendor: nouveau-vendor\n"
        "    provider_id: NouveauModele-v1\n"
        "regles_revue:\n"
        "  vendors_par_story: 3\n",
        encoding="utf-8",
    )

    table = revue._vendor_table(roles_path=roles)

    assert table is not None
    assert "nouveau-vendor" in table.values()
    assert table["nouveaumodelev1"] == "nouveau-vendor"


def test_tally_invalide_si_roster_introuvable(monkeypatch):
    monkeypatch.setattr(revue, "_vendor_table", lambda: None)

    result = revue.tally([_v("deepseek"), _v("gemini"), _v("longcat")])

    assert result["result"] == "INVALIDE"
    assert "roster" in result["reason"]


# ---------- dépouillement ----------

def test_tally_approve_unanime_3_vendors():
    res = revue.tally([_v("deepseek"), _v("gemini"), _v("longcat")])
    assert res["result"] == "APPROVE" and sorted(res["vendors"]) == ["deepseek", "google", "meituan"]


def test_tally_reject_si_un_reject():
    res = revue.tally([_v("deepseek"), _v("gemini", "REJECT",
                       [{"severity": "eleve", "file": "x.py", "line": 1, "desc": "bug"}]),
                       _v("longcat")])
    assert res["result"] == "REJECT" and res["bloquantes"]


def test_tally_invalide_moins_de_3():
    assert revue.tally([_v("deepseek"), _v("gemini")])["result"] == "INVALIDE"


def test_tally_invalide_moins_de_3_vendors_distincts():
    # composer + grok = même vendor xai → seulement 2 vendors distincts
    res = revue.tally([_v("composer"), _v("grok"), _v("gemini")])
    assert res["result"] == "INVALIDE" and "vendor" in res["reason"]


def test_tally_invalide_prompts_non_identiques():
    res = revue.tally([_v("deepseek", sha=SHA), _v("gemini", sha="b" * 64), _v("longcat")])
    assert res["result"] == "INVALIDE" and "identiques" in res["reason"]


def test_tally_invalide_verdict_malforme():
    res = revue.tally([_v("deepseek"), _v("gemini", "PEUT-ETRE"), _v("longcat")])
    assert res["result"] == "INVALIDE"


def test_tally_objections_triees_par_severite():
    res = revue.tally([
        _v("deepseek", "REJECT", [{"severity": "faible", "desc": "f"}]),
        _v("gemini", "REJECT", [{"severity": "critique", "desc": "c"}]),
        _v("longcat", "REJECT", [{"severity": "moyen", "desc": "m"}])])
    assert [o["severity"] for o in res["objections"]] == ["critique", "moyen", "faible"]


# ---------- neutralité du générateur ----------

def test_build_prompt_deterministe_et_sans_injection(tmp_path):
    # le prompt = template + substitutions SEULEMENT (l'orchestrateur ne peut rien injecter)
    p1, sha1 = revue.build_prompt("B-09", "critère X", "a.py", "code_A")
    p2, sha2 = revue.build_prompt("B-09", "critère X", "a.py", "code_A")
    assert p1 == p2 and sha1 == sha2                       # déterministe
    assert "code_A" in p1 and "B-09" in p1
    # neutralité D8 : aucune formulation orientant le verdict (« note : … », « vérifie que … »)
    low = p1.lower()
    assert "note :" not in low and "vérifie que" not in low
    # neutralité structurelle : le prompt = template + substitutions SEULEMENT. En re-substituant
    # les 4 champs par des sentinelles, on doit retrouver EXACTEMENT le squelette du template
    # (l'orchestrateur ne peut injecter aucun texte hors des 4 champs).
    body = revue.TEMPLATE.read_text(encoding="utf-8").split("-->", 1)[1].lstrip("\n")
    skel = (body.replace("{story_id}", "B-09").replace("{criteres}", "critère X")
                .replace("{artefact_path}", "a.py").replace("{artefact}", "code_A"))
    assert p1 == skel


def test_build_prompt_change_avec_artefact():
    p1, sha1 = revue.build_prompt("S", "c", "f", "AAA")
    p2, sha2 = revue.build_prompt("S", "c", "f", "BBB")
    assert sha1 != sha2                                    # le hash lie le prompt à l'artefact exact


def test_tally_rejette_vendor_inconnu():
    # anti-Sybil : des chaînes de vendor bidon ne peuvent pas simuler 3 vendors distincts
    res = revue.tally([_v("bidon-a"), _v("bidon-b"), _v("bidon-c")])
    assert res["result"] == "INVALIDE" and "inconnu" in res["reason"]


def test_build_prompt_exige_marqueur(tmp_path):
    # un template sans marqueur '-->' fuiterait son en-tête → doit échouer fort
    bad = tmp_path / "bad-template.md"
    bad.write_text("Pas de marqueur ici {story_id} {criteres} {artefact_path} {artefact}",
                   encoding="utf-8")
    import pytest as _pytest
    with _pytest.raises(ValueError):
        revue.build_prompt("s", "c", "p", "a", template_path=bad)


def test_build_prompt_pas_d_injection_croisee():
    # Défaut trouvé par la revue aveugle (Qwen) : un champ contenant le placeholder d'un
    # autre champ ne doit PAS être re-substitué (substitution en un seul passage).
    prompt, _ = revue.build_prompt(story_id="{artefact}", criteres="{artefact}",
                                   artefact_path="p", artefact="CONTENU_SECRET_ARTEFACT")
    # Le placeholder littéral reste tel quel dans les positions story/critères…
    assert "STORY : {artefact}" in prompt
    # …et n'a PAS été remplacé par la valeur du champ artefact.
    assert prompt.count("CONTENU_SECRET_ARTEFACT") == 1   # uniquement dans le slot artefact
