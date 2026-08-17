from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import ruff_noqa_gate  # noqa: E402

# Regles surveillees dans les tests : les deux codes "defaut_candidat" de la
# classification factice ci-dessous.
REGLES_SURVEILLEES = ["ARG001", "B904"]


def _base(occurrences=None, total_occurrences=0, version=1):
    """Fabrique une base ruff-noqa-baseline-v1 valide pour les tests.

    Valeurs par defaut coherentes : occurrences vides, borne a 0, version 1. Depuis
    l'invariant borne == somme(occurrences), tout test qui passe des `occurrences` non
    vides DOIT passer le `total_occurrences` egal a leur somme, faute de quoi
    `_valider_base` leve avant le comportement vise.
    """
    return {
        "_schema": "ruff-noqa-baseline-v1",
        "version": version,
        "borne": {"total_occurrences": total_occurrences},
        "occurrences": dict(occurrences or {}),
    }


def _classification_ruff_factice() -> dict:
    """Classification Ruff factice : deux regles defaut_candidat et une regle style."""
    return {
        "_familles_candidates": ["ARG", "B"],
        "regles": {
            "ARG001": {"categorie": "defaut_candidat"},
            "B904": {"categorie": "defaut_candidat"},
            "S101": {"categorie": "style"},
        },
    }


def _ecrire_classification(racine: Path) -> None:
    """Ecrit governance/ruff-classification.json dans la racine factice."""
    dossier = racine / "governance"
    dossier.mkdir(parents=True, exist_ok=True)
    (dossier / "ruff-classification.json").write_text(
        json.dumps(_classification_ruff_factice()), encoding="utf-8"
    )


def _ecrire_base(racine: Path, base: dict) -> None:
    """Ecrit governance/ruff-noqa-baseline.json dans la racine factice."""
    dossier = racine / "governance"
    dossier.mkdir(parents=True, exist_ok=True)
    (dossier / "ruff-noqa-baseline.json").write_text(
        json.dumps(base), encoding="utf-8"
    )


def _ecrire_source(racine: Path, chemin_relatif: str, *lignes: str) -> None:
    """Ecrit un fichier source factice sous `racine` (dossiers parents crees au besoin)."""
    chemin = racine / chemin_relatif
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text("\n".join(lignes) + "\n", encoding="utf-8")


def _reference_git_absente(*args: object, **kwargs: object) -> tuple[None, str]:
    """Simule une reference git non chargeable (premiere introduction du mecanisme)."""
    return None, "reference git absente a cette ref"


# ---------------------------------------------------------------------------
# regles_defaut_candidat
# ---------------------------------------------------------------------------

def test_regles_defaut_candidat_classification_vide_leve_valueerror() -> None:
    """Une classification sans aucune regle defaut_candidat est refusee."""
    with pytest.raises(ValueError, match="aucune regle categorisee"):
        ruff_noqa_gate.regles_defaut_candidat({"regles": {}})


def test_regles_defaut_candidat_filtre_et_trie() -> None:
    """Seuls les codes defaut_candidat sont retenus, tries alphabetiquement."""
    classification = {
        "regles": {
            "B904": {"categorie": "defaut_candidat"},
            "S101": {"categorie": "style"},
            "ARG001": {"categorie": "defaut_candidat"},
            "F401": {"categorie": "dette"},
        }
    }

    assert ruff_noqa_gate.regles_defaut_candidat(classification) == ["ARG001", "B904"]


# ---------------------------------------------------------------------------
# fichiers_reels
# ---------------------------------------------------------------------------

def test_fichiers_reels_ne_retient_que_les_py(tmp_path: Path) -> None:
    """Seuls les `.py` de src/ et scripts/ sont retenus, en chemins relatifs POSIX."""
    _ecrire_source(tmp_path, "src/paquet/module.py", "x = 1")
    _ecrire_source(tmp_path, "scripts/outil.py", "y = 2")
    _ecrire_source(tmp_path, "src/notes.txt", "ceci n'est pas du python")

    assert ruff_noqa_gate.fichiers_reels(tmp_path) == {
        "src/paquet/module.py",
        "scripts/outil.py",
    }


# ---------------------------------------------------------------------------
# noqa_non_conformes — vrais fichiers sur disque, aucun mock
# ---------------------------------------------------------------------------

def test_noqa_non_conformes_avec_date_est_conforme(tmp_path: Path) -> None:
    """Regle surveillee AVEC date de revision : conforme, absente du resultat."""
    _ecrire_source(
        tmp_path,
        "src/conforme.py",
        "x = 1  # noqa: ARG001 — justifie (révision: 2027-01-01)",
    )

    assert ruff_noqa_gate.noqa_non_conformes(tmp_path, REGLES_SURVEILLEES) == {}


def test_noqa_non_conformes_sans_date_est_comptee(tmp_path: Path) -> None:
    """Regle surveillee SANS date de revision : une occurrence non conforme."""
    _ecrire_source(
        tmp_path,
        "src/sans_date.py",
        "x = 1  # noqa: ARG001 — justifie mais sans date",
    )

    assert ruff_noqa_gate.noqa_non_conformes(tmp_path, REGLES_SURVEILLEES) == {
        "src/sans_date.py": 1
    }


def test_noqa_non_conformes_deux_occurrences_meme_regle(tmp_path: Path) -> None:
    """Deux suppressions non conformes de la MEME regle sur deux lignes : compte 2."""
    _ecrire_source(
        tmp_path,
        "src/deux.py",
        "x = 1  # noqa: ARG001 — premiere suppression sans date",
        "y = 2  # noqa: ARG001 — seconde suppression sans date",
    )

    assert ruff_noqa_gate.noqa_non_conformes(tmp_path, REGLES_SURVEILLEES) == {
        "src/deux.py": 2
    }


def test_noqa_non_conformes_regle_hors_perimetre_ignoree(tmp_path: Path) -> None:
    """Un code non surveille (B999) est ignore, MEME sans date : hors perimetre."""
    _ecrire_source(
        tmp_path,
        "src/hors_perimetre.py",
        "x = 1  # noqa: B999 — texte sans aucune date",
    )

    assert ruff_noqa_gate.noqa_non_conformes(tmp_path, REGLES_SURVEILLEES) == {}


def test_noqa_non_conformes_code_insensible_a_la_casse(tmp_path: Path) -> None:
    """Le code est reconnu quelle que soit sa casse : `arg001` vaut `ARG001`.

    Le fichier avec date est conforme ; le fichier sans date EST compte, ce qui prouve
    que la reconnaissance du code a bien eu lieu malgre la casse (une comparaison
    sensible a la casse l'aurait silencieusement ignore).
    """
    _ecrire_source(
        tmp_path,
        "src/casse_ok.py",
        "x = 1  # noqa: arg001 — justifie (révision: 2027-01-01)",
    )
    _ecrire_source(
        tmp_path,
        "src/casse_ko.py",
        "y = 2  # noqa: arg001 — sans date",
    )

    assert ruff_noqa_gate.noqa_non_conformes(tmp_path, REGLES_SURVEILLEES) == {
        "src/casse_ko.py": 1
    }


def test_noqa_non_conformes_date_sans_accent_reconnue(tmp_path: Path) -> None:
    """L'orthographe sans accent `(revision: ...)` est acceptee au meme titre."""
    _ecrire_source(
        tmp_path,
        "src/sans_accent.py",
        "x = 1  # noqa: B904 — justifie (revision: 2027-01-01)",
    )

    assert ruff_noqa_gate.noqa_non_conformes(tmp_path, REGLES_SURVEILLEES) == {}


def test_noqa_non_conformes_date_sans_justification_est_comptee(tmp_path: Path) -> None:
    """Round 2 de revue (defaut critique) : date presente mais AUCUNE justification -> non conforme."""
    _ecrire_source(
        tmp_path,
        "src/sans_justification.py",
        "x = 1  # noqa: ARG001 (revision: 2027-01-01)",
    )

    assert ruff_noqa_gate.noqa_non_conformes(tmp_path, REGLES_SURVEILLEES) == {
        "src/sans_justification.py": 1
    }


def test_noqa_non_conformes_justification_reduite_a_la_ponctuation_est_comptee(
    tmp_path: Path,
) -> None:
    """Justification reduite a des separateurs seuls (ex. '—') -> equivalente a une absence."""
    _ecrire_source(
        tmp_path,
        "src/ponctuation_seule.py",
        "x = 1  # noqa: ARG001 — (revision: 2027-01-01)",
    )

    assert ruff_noqa_gate.noqa_non_conformes(tmp_path, REGLES_SURVEILLEES) == {
        "src/ponctuation_seule.py": 1
    }


def test_noqa_non_conformes_multi_codes_liste_native_ruff(tmp_path: Path) -> None:
    """Round 2 de revue (majeur) : `# noqa: CODE1, CODE2` (syntaxe native ruff) sans
    justification ni date -> non conforme, meme si un seul code etait auparavant capture."""
    _ecrire_source(
        tmp_path,
        "src/multi_codes.py",
        "x = 1  # noqa: ARG001, S310",
    )

    assert ruff_noqa_gate.noqa_non_conformes(tmp_path, REGLES_SURVEILLEES) == {
        "src/multi_codes.py": 1
    }


def test_noqa_non_conformes_multi_codes_conforme_compte_une_seule_fois(
    tmp_path: Path,
) -> None:
    """Une seule justification/date pour TOUS les codes de la liste -> 1 seule ligne, pas
    une occurrence par code."""
    _ecrire_source(
        tmp_path,
        "src/multi_codes_conforme.py",
        "x = 1  # noqa: ARG001, S310 — justifie une bonne fois (revision: 2027-01-01)",
    )

    assert ruff_noqa_gate.noqa_non_conformes(tmp_path, REGLES_SURVEILLEES) == {}


def test_noqa_non_conformes_multi_codes_un_seul_surveille_suffit(
    tmp_path: Path,
) -> None:
    """Parmi une liste de codes, un seul code surveille suffit a rendre la ligne pertinente
    (meme si l'autre code de la liste est hors perimetre du cliquet)."""
    _ecrire_source(
        tmp_path,
        "src/multi_codes_partiel.py",
        "x = 1  # noqa: B999, ARG001",
    )

    assert ruff_noqa_gate.noqa_non_conformes(tmp_path, REGLES_SURVEILLEES) == {
        "src/multi_codes_partiel.py": 1
    }


def test_noqa_non_conformes_ligne_de_commentaire_pur_ignoree(tmp_path: Path) -> None:
    """Round 3 de revue (2 REJECT convergents) : un texte '# noqa: CODE' a l'interieur d'un
    bloc de COMMENTAIRE PUR (rien avant le # sauf des espaces) n'est jamais une vraie
    directive -> ignore integralement, meme sans justification ni date."""
    _ecrire_source(
        tmp_path,
        "src/doc_pure.py",
        "# Exemple de syntaxe attendue : # noqa: ARG001 sans aucune justification ni date",
        "  # Meme chose avec indentation avant le premier #",
        "x = 1",
    )

    assert ruff_noqa_gate.noqa_non_conformes(tmp_path, REGLES_SURVEILLEES) == {}


def test_noqa_non_conformes_ligne_de_code_avec_noqa_toujours_detectee(
    tmp_path: Path,
) -> None:
    """Le filtre ne touche PAS aux vraies directives : du code reel avant le # reste detecte."""
    _ecrire_source(
        tmp_path,
        "src/vrai_code.py",
        "resultat = appel_dangereux()  # noqa: ARG001 sans justification ni date",
    )

    assert ruff_noqa_gate.noqa_non_conformes(tmp_path, REGLES_SURVEILLEES) == {
        "src/vrai_code.py": 1
    }


def test_noqa_non_conformes_date_calendaire_invalide_est_comptee(tmp_path: Path) -> None:
    """Round 3 de revue (mineur, DeepSeek) : une date de forme valide mais calendairement
    impossible (mois 99) est traitee comme une date ABSENTE -> non conforme."""
    _ecrire_source(
        tmp_path,
        "src/date_impossible.py",
        "x = 1  # noqa: ARG001 — justifie (révision: 2027-99-99)",
    )

    assert ruff_noqa_gate.noqa_non_conformes(tmp_path, REGLES_SURVEILLEES) == {
        "src/date_impossible.py": 1
    }


def test_noqa_non_conformes_date_calendaire_valide_reste_conforme(tmp_path: Path) -> None:
    """Non-regression : une date calendairement valide (29 fevrier d'une annee bissextile)
    reste acceptee."""
    _ecrire_source(
        tmp_path,
        "src/date_bissextile.py",
        "x = 1  # noqa: ARG001 — justifie (révision: 2028-02-29)",
    )

    assert ruff_noqa_gate.noqa_non_conformes(tmp_path, REGLES_SURVEILLEES) == {}


def test_noqa_non_conformes_fichier_sans_noqa_absent(tmp_path: Path) -> None:
    """Un fichier sans aucun `# noqa` n'apparait pas dans le resultat."""
    _ecrire_source(tmp_path, "src/propre.py", "x = 1", "y = 2")

    assert ruff_noqa_gate.noqa_non_conformes(tmp_path, REGLES_SURVEILLEES) == {}


def test_noqa_non_conformes_representation_creuse_dict_vide(tmp_path: Path) -> None:
    """Aucune suppression non conforme : retourne EXACTEMENT {} (pas de cles a 0)."""
    _ecrire_source(
        tmp_path,
        "src/conforme.py",
        "x = 1  # noqa: ARG001 — justifie (révision: 2027-01-01)",
    )
    _ecrire_source(tmp_path, "scripts/propre.py", "print('rien a signaler')")

    resultat = ruff_noqa_gate.noqa_non_conformes(tmp_path, REGLES_SURVEILLEES)

    assert resultat == {}


# ---------------------------------------------------------------------------
# construire_baseline — bout en bout sur un mini-projet jetable reel
# ---------------------------------------------------------------------------

def test_construire_baseline_mini_projet(tmp_path: Path) -> None:
    """Baseline complete depuis une mesure fraiche : schema, borne, occurrences triees."""
    _ecrire_source(tmp_path, "src/un.py", "x = 1  # noqa: ARG001 — sans date")
    _ecrire_source(
        tmp_path,
        "scripts/deux.py",
        "y = 2  # noqa: B904 — sans date non plus",
    )

    base = ruff_noqa_gate.construire_baseline(tmp_path, REGLES_SURVEILLEES)

    assert base["_schema"] == "ruff-noqa-baseline-v1"
    assert base["version"] == 1
    assert base["borne"] == {"total_occurrences": 2}
    assert base["occurrences"] == {"scripts/deux.py": 1, "src/un.py": 1}
    assert list(base["occurrences"]) == ["scripts/deux.py", "src/un.py"]
    assert ruff_noqa_gate._valider_base(base, "test") == base


# ---------------------------------------------------------------------------
# _valider_base — validation du schema ruff-noqa-baseline-v1
# ---------------------------------------------------------------------------

def test_valider_base_schema_absent_leve_valueerror() -> None:
    """Le champ `_schema` absent est refuse."""
    base = _base()
    del base["_schema"]

    with pytest.raises(ValueError, match="_schema doit etre"):
        ruff_noqa_gate._valider_base(base, "test")


def test_valider_base_schema_incorrect_leve_valueerror() -> None:
    """Un `_schema` different de 'ruff-noqa-baseline-v1' est refuse."""
    base = _base()
    base["_schema"] = "ruff-baseline-v1"

    with pytest.raises(ValueError, match="_schema doit etre"):
        ruff_noqa_gate._valider_base(base, "test")


def test_valider_base_version_non_entier_leve_valueerror() -> None:
    """Une `version` non entiere est refusee."""
    with pytest.raises(ValueError, match="version doit etre un entier"):
        ruff_noqa_gate._valider_base(_base(version="1"), "test")


def test_valider_base_version_differente_de_1_leve_valueerror() -> None:
    """Une `version` entiere mais differente de 1 est refusee."""
    with pytest.raises(ValueError, match="version doit etre 1"):
        ruff_noqa_gate._valider_base(_base(version=2), "test")


def test_valider_base_borne_negative_leve_valueerror() -> None:
    """Une borne totale negative est refusee."""
    with pytest.raises(
        ValueError, match="total_occurrences doit etre un entier positif ou nul"
    ):
        ruff_noqa_gate._valider_base(_base(total_occurrences=-1), "test")


def test_valider_base_borne_booleenne_leve_valueerror() -> None:
    """Une borne booleenne est refusee (bool est une sous-classe de int)."""
    with pytest.raises(
        ValueError, match="total_occurrences doit etre un entier positif ou nul"
    ):
        ruff_noqa_gate._valider_base(_base(total_occurrences=True), "test")


def test_valider_base_occurrence_nulle_leve_valueerror() -> None:
    """Un plafond d'occurrences a 0 est refuse : representation creuse obligatoire."""
    base = _base(occurrences={"src/a.py": 0}, total_occurrences=0)

    with pytest.raises(ValueError, match="doit etre un entier strictement positif"):
        ruff_noqa_gate._valider_base(base, "test")


def test_valider_base_occurrence_booleenne_leve_valueerror() -> None:
    """Un plafond d'occurrences booleen est refuse."""
    base = _base(occurrences={"src/a.py": True}, total_occurrences=1)

    with pytest.raises(ValueError, match="doit etre un entier strictement positif"):
        ruff_noqa_gate._valider_base(base, "test")


def test_valider_base_borne_superieure_a_la_somme_leve_valueerror() -> None:
    """Borne > somme des occurrences : aucune marge cachee n'est admise."""
    base = _base(occurrences={"src/a.py": 1}, total_occurrences=2)

    with pytest.raises(ValueError, match="ne correspond pas a la somme"):
        ruff_noqa_gate._valider_base(base, "test")


def test_valider_base_borne_inferieure_a_la_somme_leve_valueerror() -> None:
    """Borne < somme des occurrences : l'egalite est stricte dans les deux sens."""
    base = _base(occurrences={"src/a.py": 2}, total_occurrences=1)

    with pytest.raises(ValueError, match="ne correspond pas a la somme"):
        ruff_noqa_gate._valider_base(base, "test")


def test_valider_base_valide_retourne_base_inchangee() -> None:
    """Une base conforme (egalite exacte borne/somme) passe et est retournee telle quelle."""
    base = _base(occurrences={"src/a.py": 2, "src/b.py": 1}, total_occurrences=3)

    assert ruff_noqa_gate._valider_base(base, "test") == base


# ---------------------------------------------------------------------------
# anomalies — logique pure, dicts fabriques a la main, aucun disque
# ---------------------------------------------------------------------------

def test_anomalies_vert_total_mesure_egale_base() -> None:
    """Mesure exactement egale a la base locale, reference absente : aucune anomalie."""
    base = _base(occurrences={"src/a.py": 2}, total_occurrences=2)

    assert ruff_noqa_gate.anomalies({"src/a.py": 2}, {"src/a.py"}, base, None) == []


def test_anomalies_regle1_fichier_reel_absent_de_la_base() -> None:
    """Fichier reel en violation jamais baseline : anomalie mentionnant le fichier."""
    rapport = ruff_noqa_gate.anomalies(
        {"src/nouveau.py": 1}, {"src/nouveau.py"}, _base(), None
    )

    assert any(
        "src/nouveau.py" in anomalie and "absent de la base locale" in anomalie
        for anomalie in rapport
    )


def test_anomalies_regle2_plafond_fichier_depasse() -> None:
    """Compte mesure au-dessus du plafond baseline : anomalie avec les deux valeurs."""
    base = _base(occurrences={"src/a.py": 1}, total_occurrences=1)

    rapport = ruff_noqa_gate.anomalies({"src/a.py": 3}, {"src/a.py"}, base, None)

    assert any(
        "src/a.py" in anomalie and "depasse" in anomalie and "(3 > 1)" in anomalie
        for anomalie in rapport
    )


def test_anomalies_regle3_fichier_devenu_conforme() -> None:
    """Fichier baseline desormais a 0 occurrence : il doit etre retire de la base."""
    base = _base(occurrences={"src/a.py": 2}, total_occurrences=2)

    rapport = ruff_noqa_gate.anomalies({}, {"src/a.py"}, base, None)

    assert any(
        "src/a.py" in anomalie
        and "desormais conforme" in anomalie
        and "retirer" in anomalie
        for anomalie in rapport
    )


def test_anomalies_regle3_amelioration_partielle_sans_anomalie() -> None:
    """Compte mesure > 0 mais inferieur au plafond : amelioration partielle acceptee."""
    base = _base(occurrences={"src/a.py": 3}, total_occurrences=3)

    rapport = ruff_noqa_gate.anomalies({"src/a.py": 1}, {"src/a.py"}, base, None)

    assert rapport == []


def test_anomalies_regle4_borne_totale_depassee() -> None:
    """Le total depasse la borne alors qu'AUCUN fichier ne depasse son propre plafond.

    Plusieurs petites contributions de fichiers non baselines (src/b.py, src/c.py)
    gonflent le total sans jamais declencher la regle 2 : la borne totale est un filet
    de securite independant des plafonds par fichier.
    """
    base = _base(occurrences={"src/a.py": 1}, total_occurrences=1)
    mesure = {"src/a.py": 1, "src/b.py": 1, "src/c.py": 1}
    reels = {"src/a.py", "src/b.py", "src/c.py"}

    rapport = ruff_noqa_gate.anomalies(mesure, reels, base, None)

    assert any(
        "borne est fixee a 1" in anomalie and "est de 3" in anomalie
        for anomalie in rapport
    )
    assert not any("depasse son plafond" in anomalie for anomalie in rapport)


def test_anomalies_regle5_sans_reference_aucune_anomalie() -> None:
    """base_reference=None : la regle 5 est entierement ignoree, pas une erreur."""
    base = _base(occurrences={"src/a.py": 2}, total_occurrences=2)

    rapport = ruff_noqa_gate.anomalies({"src/a.py": 2}, {"src/a.py"}, base, None)

    assert rapport == []


def test_anomalies_regle5_nouveau_fichier_extension_non_justifiee() -> None:
    """Fichier ajoute a la baseline, absent de la reference : extension non justifiee.

    Cas construit pour n'etre detectable QUE via la regle 5 : le compte mesure reste
    dans les clous de la base locale, donc ni la regle 1, ni la regle 2, ni la regle 4
    ne se declenchent.
    """
    base = _base(occurrences={"src/a.py": 1, "src/nouveau.py": 1}, total_occurrences=2)
    reference = _base(occurrences={"src/a.py": 1}, total_occurrences=1)
    mesure = {"src/a.py": 1, "src/nouveau.py": 1}
    reels = {"src/a.py", "src/nouveau.py"}

    rapport = ruff_noqa_gate.anomalies(mesure, reels, base, reference)

    assert any(
        "src/nouveau.py" in anomalie
        and "reference" in anomalie
        and "extension non justifiee" in anomalie
        for anomalie in rapport
    )
    assert not any("depasse" in anomalie for anomalie in rapport)
    assert not any("absent de la base locale" in anomalie for anomalie in rapport)


def test_anomalies_regle5_plafond_augmente_depuis_reference() -> None:
    """Plafond augmente vs la reference pour un fichier present dans les deux : anomalie."""
    base = _base(occurrences={"src/a.py": 2}, total_occurrences=2)
    reference = _base(occurrences={"src/a.py": 1}, total_occurrences=1)

    rapport = ruff_noqa_gate.anomalies({"src/a.py": 2}, {"src/a.py"}, base, reference)

    assert any(
        "src/a.py" in anomalie
        and "augmente depuis la reference" in anomalie
        and "(2 > 1)" in anomalie
        for anomalie in rapport
    )


def test_anomalies_regle5_retrait_non_justifie() -> None:
    """Fichier retire de la reference mais encore en violation reelle : anomalie."""
    base = _base(occurrences={"src/a.py": 1}, total_occurrences=1)
    reference = _base(
        occurrences={"src/a.py": 1, "src/ancien.py": 2}, total_occurrences=3
    )
    mesure = {"src/a.py": 1, "src/ancien.py": 2}
    reels = {"src/a.py", "src/ancien.py"}

    rapport = ruff_noqa_gate.anomalies(mesure, reels, base, reference)

    assert any(
        "src/ancien.py" in anomalie
        and "retire de la base de reference" in anomalie
        and "retrait non justifie" in anomalie
        for anomalie in rapport
    )


def test_anomalies_regle5_retrait_legitime_fichier_devenu_conforme() -> None:
    """Fichier retire de la reference et reellement devenu conforme (0 mesure) : vert."""
    base = _base(occurrences={"src/a.py": 1}, total_occurrences=1)
    reference = _base(
        occurrences={"src/a.py": 1, "src/ancien.py": 2}, total_occurrences=3
    )
    mesure = {"src/a.py": 1}
    reels = {"src/a.py", "src/ancien.py"}

    rapport = ruff_noqa_gate.anomalies(mesure, reels, base, reference)

    assert rapport == []


def test_anomalies_regle5_decroissance_legitime_sans_anomalie() -> None:
    """Plafond local plus bas que la reference : la base decroit, c'est le but."""
    base = _base(occurrences={"src/a.py": 1}, total_occurrences=1)
    reference = _base(occurrences={"src/a.py": 3}, total_occurrences=3)

    rapport = ruff_noqa_gate.anomalies({"src/a.py": 1}, {"src/a.py"}, base, reference)

    assert rapport == []


def test_anomalies_regle5_borne_totale_augmentee() -> None:
    """Borne totale locale superieure a celle de la reference : anomalie explicite."""
    base = _base(occurrences={"src/a.py": 2, "src/b.py": 2}, total_occurrences=4)
    reference = _base(occurrences={"src/a.py": 2, "src/b.py": 1}, total_occurrences=3)
    mesure = {"src/a.py": 2, "src/b.py": 2}
    reels = {"src/a.py", "src/b.py"}

    rapport = ruff_noqa_gate.anomalies(mesure, reels, base, reference)

    assert any(
        "borne totale augmentee depuis la reference" in anomalie
        and "(4 > 3)" in anomalie
        for anomalie in rapport
    )


# ---------------------------------------------------------------------------
# main — bout en bout ; seul gate_git_ref.charger_base_reference_git est mocke,
# la mesure est pilotee par de vrais fichiers .py ecrits dans tmp_path
# ---------------------------------------------------------------------------

def test_main_cliquet_vert(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Aucune violation non conforme, baseline vide coherente, reference absente : 0."""
    _ecrire_classification(tmp_path)
    _ecrire_base(tmp_path, _base())
    _ecrire_source(tmp_path, "src/propre.py", "x = 1")
    _ecrire_source(
        tmp_path,
        "scripts/conforme.py",
        "y = 2  # noqa: ARG001 — justifie (révision: 2027-01-01)",
    )
    monkeypatch.setattr(
        ruff_noqa_gate.gate_git_ref,
        "charger_base_reference_git",
        _reference_git_absente,
    )

    assert ruff_noqa_gate.main(["--racine", str(tmp_path)]) == 0


def test_main_cliquet_rouge_mesure_depasse_baseline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Une suppression non conforme absente de la baseline vide fait echouer le gate."""
    _ecrire_classification(tmp_path)
    _ecrire_base(tmp_path, _base())
    _ecrire_source(
        tmp_path,
        "src/violation.py",
        "x = 1  # noqa: ARG001 — suppression sans date",
    )
    monkeypatch.setattr(
        ruff_noqa_gate.gate_git_ref,
        "charger_base_reference_git",
        _reference_git_absente,
    )

    assert ruff_noqa_gate.main(["--racine", str(tmp_path)]) == 1


def test_main_classification_absente_retourne_1(tmp_path: Path) -> None:
    """governance/ruff-classification.json introuvable : echec propre, retour 1."""
    _ecrire_base(tmp_path, _base())
    _ecrire_source(tmp_path, "src/propre.py", "x = 1")

    assert ruff_noqa_gate.main(["--racine", str(tmp_path)]) == 1


def test_main_baseline_absente_retourne_1(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Classification presente mais baseline introuvable : echec propre, retour 1."""
    _ecrire_classification(tmp_path)
    _ecrire_source(tmp_path, "src/propre.py", "x = 1")
    monkeypatch.setattr(
        ruff_noqa_gate.gate_git_ref,
        "charger_base_reference_git",
        _reference_git_absente,
    )

    assert ruff_noqa_gate.main(["--racine", str(tmp_path)]) == 1


def test_main_panne_reference_git_retourne_1(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Panne REELLE de la reference git (exception levee) : retour 1, jamais de
    degradation silencieuse du controle de non-croissance."""
    _ecrire_classification(tmp_path)
    _ecrire_base(tmp_path, _base())
    _ecrire_source(tmp_path, "src/propre.py", "x = 1")

    def panne_git(*args: object, **kwargs: object) -> None:
        raise RuntimeError("git indisponible : fetch-depth insuffisant")

    monkeypatch.setattr(
        ruff_noqa_gate.gate_git_ref,
        "charger_base_reference_git",
        panne_git,
    )

    assert ruff_noqa_gate.main(["--racine", str(tmp_path)]) == 1


def test_main_regenerer_baseline_cree_le_fichier(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--regenerer-baseline reecrit la baseline depuis une mesure fraiche, sans baseline
    preexistante et sans jamais consulter la reference git."""
    _ecrire_classification(tmp_path)
    _ecrire_source(
        tmp_path,
        "src/cible.py",
        "x = 1  # noqa: ARG001 — suppression sans date",
    )

    def git_ne_doit_pas_etre_consulte(*args: object, **kwargs: object) -> None:
        raise AssertionError("git ne doit pas etre consulte en mode regeneration")

    monkeypatch.setattr(
        ruff_noqa_gate.gate_git_ref,
        "charger_base_reference_git",
        git_ne_doit_pas_etre_consulte,
    )

    chemin_base = tmp_path / "governance" / "ruff-noqa-baseline.json"
    assert not chemin_base.exists()

    assert (
        ruff_noqa_gate.main(["--racine", str(tmp_path), "--regenerer-baseline"]) == 0
    )

    base = json.loads(chemin_base.read_text(encoding="utf-8"))
    assert base["_schema"] == "ruff-noqa-baseline-v1"
    assert base["version"] == 1
    assert base["borne"] == {"total_occurrences": 1}
    assert base["occurrences"] == {"src/cible.py": 1}
    assert ruff_noqa_gate._valider_base(base, "baseline relue") == base
