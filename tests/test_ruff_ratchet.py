from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import ruff_ratchet  # noqa: E402


def _base(dette=None, classification=None, total_violations=0, version=1, regles_activees=None):
    """Fabrique une base ruff-baseline-v1 valide pour les tests.

    Valeurs par défaut cohérentes : dette/classification vides, borne à 0, version 1,
    regles_activees triées. `regles_activees=None` (et non `[]`) garde la possibilité de
    passer explicitement une liste vide pour les tests de validation. Depuis l'invariant
    borne == somme(dette), tout test qui passe une `dette` non vide DOIT passer le
    `total_violations` égal à sa somme, faute de quoi `_valider_base` lève avant le
    comportement visé.
    """
    return {
        "version": version,
        "regles_activees": (
            list(regles_activees)
            if regles_activees is not None
            else ["ARG001", "B904"]
        ),
        "borne": {"total_violations": total_violations},
        "dette": dict(dette or {}),
        "classification": {
            fichier: dict(comptes) for fichier, comptes in (classification or {}).items()
        },
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
    """Ecrit governance/ruff-baseline.json dans la racine factice."""
    dossier = racine / "governance"
    dossier.mkdir(parents=True, exist_ok=True)
    (dossier / "ruff-baseline.json").write_text(json.dumps(base), encoding="utf-8")


def _reference_git_absente(*args: object, **kwargs: object) -> tuple[None, str]:
    """Simule une reference git non chargeable (premiere introduction du mecanisme)."""
    return None, "reference git absente a cette ref"


# ---------------------------------------------------------------------------
# regles_defaut_candidat
# ---------------------------------------------------------------------------

def test_regles_defaut_candidat_classification_vide_leve_valueerror() -> None:
    """Une classification sans aucune regle defaut_candidat est refusee."""
    with pytest.raises(ValueError, match="aucune regle categorisee"):
        ruff_ratchet.regles_defaut_candidat({"regles": {}})


def test_regles_defaut_candidat_champ_regles_absent_leve_valueerror() -> None:
    """Le champ 'regles' absent est refuse : jamais de cliquet sur un ensemble vide."""
    with pytest.raises(ValueError, match="aucune regle categorisee"):
        ruff_ratchet.regles_defaut_candidat({})


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

    assert ruff_ratchet.regles_defaut_candidat(classification) == ["ARG001", "B904"]


# ---------------------------------------------------------------------------
# mesurer — chemins d'erreur (subprocess.run mocke)
# ---------------------------------------------------------------------------

def test_mesurer_ruff_absent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ruff introuvable sur le PATH -> RuntimeError explicite."""

    def ruff_absent(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError("ruff")

    monkeypatch.setattr(ruff_ratchet.subprocess, "run", ruff_absent)

    with pytest.raises(RuntimeError, match="ruff est indisponible"):
        ruff_ratchet.mesurer(tmp_path, ["ARG001"])


def test_mesurer_code_retour_inattendu(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Un code de sortie hors 0/1 -> RuntimeError mentionnant le code."""
    resultat = subprocess.CompletedProcess(
        args=["ruff"],
        returncode=2,
        stdout="",
        stderr="erreur ruff",
    )
    monkeypatch.setattr(ruff_ratchet.subprocess, "run", lambda *args, **kwargs: resultat)

    with pytest.raises(RuntimeError, match="code 2"):
        ruff_ratchet.mesurer(tmp_path, ["ARG001"])


def test_mesurer_sortie_json_invalide(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Une sortie non JSON -> RuntimeError."""
    resultat = subprocess.CompletedProcess(
        args=["ruff"],
        returncode=1,
        stdout="pas du JSON",
        stderr="",
    )
    monkeypatch.setattr(ruff_ratchet.subprocess, "run", lambda *args, **kwargs: resultat)

    with pytest.raises(RuntimeError, match="sortie JSON de ruff est invalide"):
        ruff_ratchet.mesurer(tmp_path, ["ARG001"])


def test_mesurer_sortie_json_pas_une_liste(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Un JSON valide mais qui n'est pas une liste de violations -> RuntimeError."""
    resultat = subprocess.CompletedProcess(
        args=["ruff"],
        returncode=0,
        stdout="{}",
        stderr="",
    )
    monkeypatch.setattr(ruff_ratchet.subprocess, "run", lambda *args, **kwargs: resultat)

    with pytest.raises(RuntimeError, match="doit être une liste de violations"):
        ruff_ratchet.mesurer(tmp_path, ["ARG001"])


# ---------------------------------------------------------------------------
# mesurer + agreger — unique test avec ruff REEL sur un mini-projet jetable
# ---------------------------------------------------------------------------

def test_mesurer_et_agreger_sur_mini_projet_reel(tmp_path: Path) -> None:
    """ruff reel sur un projet jetable : ARG001 detecte, chemin relatif POSIX, agregats exacts."""
    (tmp_path / "src" / "pkg").mkdir(parents=True)
    (tmp_path / "scripts").mkdir()
    (tmp_path / "src" / "pkg" / "mod.py").write_text(
        "def f(x, y):\n    return x\n", encoding="utf-8"
    )

    violations = ruff_ratchet.mesurer(tmp_path, ["ARG001"])

    assert any(
        violation.get("code") == "ARG001"
        and violation.get("filename") == "src/pkg/mod.py"
        for violation in violations
    )

    dette, classification = ruff_ratchet.agreger(violations)
    assert dette == {"src/pkg/mod.py": 1}
    assert classification == {"src/pkg/mod.py": {"ARG001": 1}}


# ---------------------------------------------------------------------------
# agreger — cas synthetiques (sans ruff reel)
# ---------------------------------------------------------------------------

def test_agreger_plusieurs_codes_sur_meme_fichier() -> None:
    """La dette est la somme toutes regles confondues, la classification ventile par code."""
    violations = [
        {"filename": "src/a.py", "code": "ARG001"},
        {"filename": "src/a.py", "code": "B904"},
        {"filename": "src/a.py", "code": "ARG001"},
    ]

    dette, classification = ruff_ratchet.agreger(violations)

    assert dette == {"src/a.py": 3}
    assert classification == {"src/a.py": {"ARG001": 2, "B904": 1}}


def test_agreger_violations_incompletes_ne_levent_pas() -> None:
    """Cles absentes ou non chaines -> conventions fichier_inconnu / code_inconnu."""
    violations = [
        {"filename": None, "code": 101},
        {"code": "ARG001"},
        {"filename": "src/b.py"},
    ]

    dette, classification = ruff_ratchet.agreger(violations)

    assert dette == {"fichier_inconnu": 2, "src/b.py": 1}
    assert classification == {
        "fichier_inconnu": {"code_inconnu": 1, "ARG001": 1},
        "src/b.py": {"code_inconnu": 1},
    }


def test_agreger_liste_vide() -> None:
    """Aucune violation -> agregats vides."""
    assert ruff_ratchet.agreger([]) == ({}, {})


# ---------------------------------------------------------------------------
# fichiers_reels
# ---------------------------------------------------------------------------

def test_fichiers_reels_src_et_scripts(tmp_path: Path) -> None:
    """Les .py de src/ et scripts/ sont retenus, en chemins relatifs POSIX."""
    (tmp_path / "src" / "sub").mkdir(parents=True)
    (tmp_path / "scripts").mkdir()
    (tmp_path / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "scripts" / "b.py").write_text("y = 2\n", encoding="utf-8")
    (tmp_path / "src" / "sub" / "c.py").write_text("z = 3\n", encoding="utf-8")

    reels = ruff_ratchet.fichiers_reels(tmp_path)

    assert reels == {"src/a.py", "scripts/b.py", "src/sub/c.py"}
    assert all("\\" not in f for f in reels)


def test_fichiers_reels_scripts_absent_ne_leve_pas(tmp_path: Path) -> None:
    """Un dossier scripts/ absent est simplement ignore."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")

    assert ruff_ratchet.fichiers_reels(tmp_path) == {"src/a.py"}


def test_fichiers_reels_ignore_les_non_python(tmp_path: Path) -> None:
    """Seuls les fichiers .py sont retenus."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "src" / "note.txt").write_text("pas du python\n", encoding="utf-8")

    assert ruff_ratchet.fichiers_reels(tmp_path) == {"src/a.py"}


# ---------------------------------------------------------------------------
# construire_baseline — vrai appel ruff sur un mini-projet jetable
# ---------------------------------------------------------------------------

def test_construire_baseline_sur_mini_projet_reel(tmp_path: Path) -> None:
    """Deux violations ARG001 sur le meme fichier -> baseline complete, coherente, valide."""
    (tmp_path / "src" / "pkg").mkdir(parents=True)
    (tmp_path / "scripts").mkdir()
    (tmp_path / "src" / "pkg" / "mod.py").write_text(
        "def f(x, y):\n    return x\n\n\ndef g(a, b):\n    return a\n",
        encoding="utf-8",
    )

    base = ruff_ratchet.construire_baseline(tmp_path, ["ARG001"])

    assert base["version"] == 1
    assert base["regles_activees"] == ["ARG001"]
    assert base["borne"] == {"total_violations": 2}
    assert base["dette"] == {"src/pkg/mod.py": 2}
    assert base["classification"] == {"src/pkg/mod.py": {"ARG001": 2}}
    assert base["_schema"]
    assert base["_description"]
    # Preuve que construire_baseline produit toujours un schema directement valide.
    assert ruff_ratchet._valider_base(base, "test") == base


# ---------------------------------------------------------------------------
# Validation de schema (_valider_base)
# ---------------------------------------------------------------------------

def test_valider_base_version_non_entier() -> None:
    """version non entiere (chaine) -> ValueError."""
    base = _base(version="1")

    with pytest.raises(ValueError, match="version doit etre un entier"):
        ruff_ratchet._valider_base(base, "base locale")


def test_valider_base_regles_activees_vide() -> None:
    """regles_activees vide -> ValueError."""
    base = _base(regles_activees=[])

    with pytest.raises(ValueError, match="regles_activees doit etre une liste non vide"):
        ruff_ratchet._valider_base(base, "base locale")


def test_valider_base_regles_activees_doublon() -> None:
    """regles_activees avec doublon -> ValueError."""
    base = _base(regles_activees=["ARG001", "ARG001"])

    with pytest.raises(ValueError, match="regles_activees contient des doublons"):
        ruff_ratchet._valider_base(base, "base locale")


def test_valider_base_regles_activees_non_triee() -> None:
    """regles_activees non triee alphabetiquement -> ValueError."""
    base = _base(regles_activees=["B904", "ARG001"])

    with pytest.raises(ValueError, match="regles_activees doit etre triee alphabetiquement"):
        ruff_ratchet._valider_base(base, "base locale")


def test_valider_base_borne_negative() -> None:
    """borne.total_violations negatif -> ValueError."""
    base = _base(total_violations=-1)

    with pytest.raises(
        ValueError, match="total_violations doit etre un entier positif ou nul"
    ):
        ruff_ratchet._valider_base(base, "base locale")


def test_valider_base_borne_booleenne() -> None:
    """borne.total_violations booleen -> ValueError (bool est une sous-classe de int)."""
    base = _base(total_violations=True)

    with pytest.raises(
        ValueError, match="total_violations doit etre un entier positif ou nul"
    ):
        ruff_ratchet._valider_base(base, "base locale")


def test_valider_base_borne_superieure_a_la_somme_dette() -> None:
    """borne gonflee au-dessus de la somme des plafonds -> marge cachee refusee."""
    base = _base(
        dette={"src/a.py": 1},
        classification={"src/a.py": {"ARG001": 1}},
        total_violations=2,
    )

    with pytest.raises(
        ValueError,
        match=r"borne\.total_violations .* ne correspond pas a la somme de dette",
    ):
        ruff_ratchet._valider_base(base, "base locale")


def test_valider_base_borne_inferieure_a_la_somme_dette() -> None:
    """borne sous la somme des plafonds -> l'egalite est stricte dans les deux sens."""
    base = _base(
        dette={"src/a.py": 2},
        classification={"src/a.py": {"ARG001": 2}},
        total_violations=1,
    )

    with pytest.raises(
        ValueError,
        match=r"borne\.total_violations .* ne correspond pas a la somme de dette",
    ):
        ruff_ratchet._valider_base(base, "base locale")


def test_valider_base_borne_egale_somme_dette_valide() -> None:
    """Egalite exacte borne == somme(dette) -> base acceptee sans erreur."""
    base = _base(
        dette={"src/a.py": 1, "src/b.py": 2},
        classification={
            "src/a.py": {"ARG001": 1},
            "src/b.py": {"ARG001": 1, "B904": 1},
        },
        total_violations=3,
    )

    assert ruff_ratchet._valider_base(base, "base locale") == base


def test_valider_base_dette_nulle() -> None:
    """dette avec une valeur 0 -> ValueError (representation creuse, stricte positivite)."""
    base = _base(dette={"src/a.py": 0})

    with pytest.raises(ValueError, match="dette.*strictement positif"):
        ruff_ratchet._valider_base(base, "base locale")


def test_valider_base_dette_booleenne() -> None:
    """dette avec une valeur booleenne -> ValueError."""
    base = _base(dette={"src/a.py": True})

    with pytest.raises(ValueError, match="dette.*strictement positif"):
        ruff_ratchet._valider_base(base, "base locale")


def test_valider_base_classification_cle_en_trop() -> None:
    """classification avec une cle absente de dette -> ValueError."""
    base = _base(
        dette={"src/a.py": 1},
        classification={"src/a.py": {"ARG001": 1}, "src/b.py": {"ARG001": 1}},
        total_violations=1,
    )

    with pytest.raises(ValueError, match="en trop pour"):
        ruff_ratchet._valider_base(base, "base locale")


def test_valider_base_classification_cle_manquante() -> None:
    """classification sans une cle presente dans dette -> ValueError."""
    base = _base(
        dette={"src/a.py": 1, "src/b.py": 2},
        classification={"src/a.py": {"ARG001": 1}},
        total_violations=3,
    )

    with pytest.raises(ValueError, match="manquantes pour"):
        ruff_ratchet._valider_base(base, "base locale")


def test_valider_base_classification_somme_incoherente() -> None:
    """Somme des comptes d'un fichier differente de dette[fichier] -> ValueError."""
    base = _base(
        dette={"src/a.py": 2},
        classification={"src/a.py": {"ARG001": 1}},
        total_violations=2,
    )

    with pytest.raises(ValueError, match="somme des codes"):
        ruff_ratchet._valider_base(base, "base locale")


def test_valider_base_classification_regle_fantome() -> None:
    """Un code absent de regles_activees dans classification -> ValueError."""
    base = _base(
        dette={"src/a.py": 1},
        classification={"src/a.py": {"S101": 1}},
        total_violations=1,
    )

    with pytest.raises(ValueError, match="regle fantome"):
        ruff_ratchet._valider_base(base, "base locale")


def test_valider_base_valide_retourne_base_inchangee() -> None:
    """Une base bien formee (pleine ou vide) est retournee sans erreur."""
    base = _base(
        dette={"src/a.py": 2},
        classification={"src/a.py": {"ARG001": 1, "B904": 1}},
        total_violations=2,
    )

    assert ruff_ratchet._valider_base(base, "base locale") == base
    assert ruff_ratchet._valider_base(_base(), "base locale") == _base()


# ---------------------------------------------------------------------------
# anomalies — logique pure, une regle par test
# ---------------------------------------------------------------------------

def test_anomalies_vert_total_quand_mesure_egale_base() -> None:
    """Mesure exactement egale a la base locale, sans reference -> aucune anomalie."""
    base = _base(
        dette={"src/a.py": 1},
        classification={"src/a.py": {"ARG001": 1}},
        total_violations=1,
    )

    assert ruff_ratchet.anomalies(
        mesure_dette={"src/a.py": 1},
        mesure_classification={"src/a.py": {"ARG001": 1}},
        fichiers_reels={"src/a.py"},
        regles_courantes=["ARG001", "B904"],
        base_locale=base,
        base_reference=None,
    ) == []


def test_anomalies_regle0_regle_disparue_de_la_classification_courante() -> None:
    """Une regle baselinee disparue de la classification courante -> base perimee a regenerer."""
    base = _base(
        dette={"src/a.py": 1},
        classification={"src/a.py": {"ARG001": 1}},
        total_violations=1,
    )

    resultat = ruff_ratchet.anomalies(
        mesure_dette={"src/a.py": 1},
        mesure_classification={"src/a.py": {"ARG001": 1}},
        fichiers_reels={"src/a.py"},
        regles_courantes=["ARG001"],
        base_locale=base,
        base_reference=None,
    )

    assert len(resultat) == 1
    message = resultat[0]
    assert "ARG001" in message and "B904" in message
    assert "ne correspondent plus" in message
    assert "regenerer governance/ruff-baseline.json" in message


def test_anomalies_regle0_comparaison_insensible_a_l_ordre() -> None:
    """Memes regles dans un ordre different en entree -> aucune anomalie (tri avant comparaison)."""
    base = _base(
        dette={"src/a.py": 1},
        classification={"src/a.py": {"ARG001": 1}},
        total_violations=1,
    )

    assert ruff_ratchet.anomalies(
        mesure_dette={"src/a.py": 1},
        mesure_classification={"src/a.py": {"ARG001": 1}},
        fichiers_reels={"src/a.py"},
        regles_courantes=["B904", "ARG001"],
        base_locale=base,
        base_reference=None,
    ) == []


def test_anomalies_regle0_listes_identiques_aucune_anomalie() -> None:
    """regles_activees exactement alignees sur la classification courante -> regle 0 verte."""
    base = _base(
        dette={"src/a.py": 1},
        classification={"src/a.py": {"ARG001": 1}},
        total_violations=1,
    )

    assert ruff_ratchet.anomalies(
        mesure_dette={"src/a.py": 1},
        mesure_classification={"src/a.py": {"ARG001": 1}},
        fichiers_reels={"src/a.py"},
        regles_courantes=["ARG001", "B904"],
        base_locale=base,
        base_reference=None,
    ) == []


def test_anomalies_regle1_fichier_reel_en_violation_absent_de_la_base() -> None:
    """Un fichier reel en violation jamais baseline est signale."""
    resultat = ruff_ratchet.anomalies(
        mesure_dette={"src/nouveau.py": 2},
        mesure_classification={"src/nouveau.py": {"ARG001": 2}},
        fichiers_reels={"src/nouveau.py"},
        regles_courantes=["ARG001", "B904"],
        base_locale=_base(),
        base_reference=None,
    )

    assert any(
        "src/nouveau.py" in m and "absent de la base" in m for m in resultat
    )


def test_anomalies_regle2_dette_fichier_depassee() -> None:
    """Un fichier baseline dont le compte mesure depasse le plafond -> regression."""
    base = _base(
        dette={"src/a.py": 1},
        classification={"src/a.py": {"ARG001": 1}},
        total_violations=1,
    )

    resultat = ruff_ratchet.anomalies(
        mesure_dette={"src/a.py": 3},
        mesure_classification={"src/a.py": {"ARG001": 3}},
        fichiers_reels={"src/a.py"},
        regles_courantes=["ARG001", "B904"],
        base_locale=base,
        base_reference=None,
    )

    assert any(
        "src/a.py" in m and "depasse sa dette baselinee" in m and "(3 > 1)" in m
        for m in resultat
    )


def test_anomalies_regle3_fichier_devenu_propre_doit_sortir_de_la_base() -> None:
    """Un fichier baseline dont le compte mesure tombe a 0 doit etre retire de la base."""
    base = _base(
        dette={"src/a.py": 2},
        classification={"src/a.py": {"ARG001": 2}},
        total_violations=2,
    )

    resultat = ruff_ratchet.anomalies(
        mesure_dette={},
        mesure_classification={},
        fichiers_reels={"src/a.py"},
        regles_courantes=["ARG001", "B904"],
        base_locale=base,
        base_reference=None,
    )

    assert any(
        "src/a.py" in m and "desormais propre" in m and "retirer" in m
        for m in resultat
    )


def test_anomalies_regle3_amelioration_partielle_sans_faux_positif() -> None:
    """Compte mesure > 0 mais inferieur au plafond : amelioration legitime, aucune anomalie."""
    base = _base(
        dette={"src/a.py": 3},
        classification={"src/a.py": {"ARG001": 3}},
        total_violations=3,
    )

    assert ruff_ratchet.anomalies(
        mesure_dette={"src/a.py": 1},
        mesure_classification={"src/a.py": {"ARG001": 1}},
        fichiers_reels={"src/a.py"},
        regles_courantes=["ARG001", "B904"],
        base_locale=base,
        base_reference=None,
    ) == []


def test_anomalies_regle4_code_en_hausse_compense_par_baisse_d_un_autre_code() -> None:
    """Total du fichier stable mais un code depasse son plafond propre -> regle 4 seule."""
    base = _base(
        dette={"src/a.py": 2},
        classification={"src/a.py": {"ARG001": 1, "B904": 1}},
        total_violations=2,
    )

    resultat = ruff_ratchet.anomalies(
        mesure_dette={"src/a.py": 2},
        mesure_classification={"src/a.py": {"ARG001": 2}},
        fichiers_reels={"src/a.py"},
        regles_courantes=["ARG001", "B904"],
        base_locale=base,
        base_reference=None,
    )

    assert any(
        "src/a.py" in m and "regle ARG001 en hausse" in m and "(2 > 1" in m
        for m in resultat
    )


def test_anomalies_regle4_nouveau_code_jamais_baseline_compense_par_baisse_d_un_autre() -> None:
    """Round 2 de revue : ARG001 corrige (1->0), B904 apparait — jamais dans classification_base.

    Dette totale du fichier inchangee (1 -> 1). Sans l'union baseline/mesure sur les codes,
    B904 (absent de classification_base) n'aurait jamais ete examine par la regle 4.
    """
    base = _base(
        dette={"src/a.py": 1},
        classification={"src/a.py": {"ARG001": 1}},
        total_violations=1,
    )

    resultat = ruff_ratchet.anomalies(
        mesure_dette={"src/a.py": 1},
        mesure_classification={"src/a.py": {"B904": 1}},
        fichiers_reels={"src/a.py"},
        regles_courantes=["ARG001", "B904"],
        base_locale=base,
        base_reference=None,
    )

    assert any(
        "src/a.py" in m and "regle B904 en hausse" in m and "(1 > 0" in m
        for m in resultat
    )
    # Preuve que ni la regle 2 (total fichier stable) ni la regle 5 (total global stable)
    # ne l'auraient detecte seules.
    assert not any("depasse sa dette baselinee" in m for m in resultat)
    assert not any("total des violations" in m for m in resultat)
    assert not any("depasse sa dette baselinee" in m for m in resultat)


def test_anomalies_regle5_borne_totale_depassee_sans_depassement_individuel() -> None:
    """Total mesure au-dela de la borne sans qu'aucun plafond individuel ne soit depasse.

    Depuis l'egalite stricte borne == somme(dette), ce cas n'est atteignable que via un
    fichier en violation absent de la base (conjointement a la regle 1) : la borne suit
    desormais exactement la dette declaree, sans marge cachee.
    """
    base = _base(
        dette={"src/a.py": 1},
        classification={"src/a.py": {"ARG001": 1}},
        total_violations=1,
    )

    resultat = ruff_ratchet.anomalies(
        mesure_dette={"src/a.py": 1, "src/b.py": 1},
        mesure_classification={
            "src/a.py": {"ARG001": 1},
            "src/b.py": {"ARG001": 1},
        },
        fichiers_reels={"src/a.py", "src/b.py"},
        regles_courantes=["ARG001", "B904"],
        base_locale=base,
        base_reference=None,
    )

    assert any(
        "total des violations" in m and "est de 2" in m and "borne est fixee a 1" in m
        for m in resultat
    )
    assert not any("depasse sa dette baselinee" in m for m in resultat)


def test_anomalies_regle6_absence_de_reference_ne_produit_aucune_anomalie() -> None:
    """Sans base de reference, aucun controle de non-croissance n'est applicable."""
    base = _base(
        dette={"src/a.py": 5},
        classification={"src/a.py": {"ARG001": 5}},
        total_violations=5,
    )

    assert ruff_ratchet.anomalies(
        mesure_dette={"src/a.py": 5},
        mesure_classification={"src/a.py": {"ARG001": 5}},
        fichiers_reels={"src/a.py"},
        regles_courantes=["ARG001", "B904"],
        base_locale=base,
        base_reference=None,
    ) == []


def test_anomalies_regle6_dette_augmentee_depuis_reference_detectee_seule() -> None:
    """Plafond de dette gonfle vs la reference : detecte UNIQUEMENT par la regle 6."""
    reference = _base(
        dette={"src/a.py": 1},
        classification={"src/a.py": {"ARG001": 1}},
        total_violations=1,
    )
    locale = _base(
        dette={"src/a.py": 2},
        classification={"src/a.py": {"ARG001": 2}},
        total_violations=2,
    )

    resultat = ruff_ratchet.anomalies(
        mesure_dette={"src/a.py": 2},
        mesure_classification={"src/a.py": {"ARG001": 2}},
        fichiers_reels={"src/a.py"},
        regles_courantes=["ARG001", "B904"],
        base_locale=locale,
        base_reference=reference,
    )

    assert resultat
    assert any(
        "dette baselinee pour src/a.py augmentee depuis la reference" in m
        for m in resultat
    )
    assert all("reference" in m for m in resultat)


def test_anomalies_regle6_classification_augmentee_depuis_reference() -> None:
    """Un couple (fichier, code) gonfle vs la reference, total du fichier inchange."""
    reference = _base(
        dette={"src/a.py": 2},
        classification={"src/a.py": {"ARG001": 1, "B904": 1}},
        total_violations=2,
    )
    locale = _base(
        dette={"src/a.py": 2},
        classification={"src/a.py": {"ARG001": 2}},
        total_violations=2,
    )

    resultat = ruff_ratchet.anomalies(
        mesure_dette={"src/a.py": 2},
        mesure_classification={"src/a.py": {"ARG001": 2}},
        fichiers_reels={"src/a.py"},
        regles_courantes=["ARG001", "B904"],
        base_locale=locale,
        base_reference=reference,
    )

    assert resultat
    assert any(
        "classification baselinee pour src/a.py" in m
        and "ARG001" in m
        and "reference" in m
        for m in resultat
    )
    assert all("reference" in m for m in resultat)


def test_anomalies_regle6_borne_totale_augmentee_depuis_reference() -> None:
    """borne.total_violations gonflee vs la reference -> extension non justifiee.

    Depuis l'egalite stricte borne == somme(dette), une hausse de la borne est toujours
    adossee a une hausse de dette : le controle de la borne reste le filet qui la confirme.
    """
    reference = _base(
        dette={"src/a.py": 1},
        classification={"src/a.py": {"ARG001": 1}},
        total_violations=1,
    )
    locale = _base(
        dette={"src/a.py": 2},
        classification={"src/a.py": {"ARG001": 2}},
        total_violations=2,
    )

    resultat = ruff_ratchet.anomalies(
        mesure_dette={"src/a.py": 2},
        mesure_classification={"src/a.py": {"ARG001": 2}},
        fichiers_reels={"src/a.py"},
        regles_courantes=["ARG001", "B904"],
        base_locale=locale,
        base_reference=reference,
    )

    assert resultat
    assert any(
        "borne totale augmentee" in m and "extension non justifiee" in m
        for m in resultat
    )
    assert all("reference" in m for m in resultat)


def test_anomalies_regle6_retrait_non_justifie_si_fichier_encore_en_violation() -> None:
    """Fichier retire de la dette de reference alors qu'il a encore des violations."""
    reference = _base(
        dette={"src/a.py": 2},
        classification={"src/a.py": {"ARG001": 2}},
        total_violations=2,
    )
    locale = _base()

    resultat = ruff_ratchet.anomalies(
        mesure_dette={"src/a.py": 1},
        mesure_classification={"src/a.py": {"ARG001": 1}},
        fichiers_reels={"src/a.py"},
        regles_courantes=["ARG001", "B904"],
        base_locale=locale,
        base_reference=reference,
    )

    assert any(
        "retire de la dette de reference" in m and "retrait non justifie" in m
        for m in resultat
    )


def test_anomalies_regle6_retrait_legitime_si_fichier_reellement_propre() -> None:
    """Fichier retire de la dette de reference et reellement a 0 violation : legitime."""
    reference = _base(
        dette={"src/a.py": 2},
        classification={"src/a.py": {"ARG001": 2}},
        total_violations=2,
    )
    locale = _base()

    assert ruff_ratchet.anomalies(
        mesure_dette={},
        mesure_classification={},
        fichiers_reels={"src/a.py"},
        regles_courantes=["ARG001", "B904"],
        base_locale=locale,
        base_reference=reference,
    ) == []


def test_anomalies_regle6_decroissance_legitime_de_la_base() -> None:
    """Un plafond de dette plus bas que la reference (dette reduite) -> aucune anomalie."""
    reference = _base(
        dette={"src/a.py": 3},
        classification={"src/a.py": {"ARG001": 3}},
        total_violations=3,
    )
    locale = _base(
        dette={"src/a.py": 1},
        classification={"src/a.py": {"ARG001": 1}},
        total_violations=1,
    )

    assert ruff_ratchet.anomalies(
        mesure_dette={"src/a.py": 1},
        mesure_classification={"src/a.py": {"ARG001": 1}},
        fichiers_reels={"src/a.py"},
        regles_courantes=["ARG001", "B904"],
        base_locale=locale,
        base_reference=reference,
    ) == []


def test_anomalies_regle6_fichier_ajoute_a_la_dette_absent_de_la_reference() -> None:
    """Attaque de la revue : nouveau fichier baseline, compense par la baisse d'un autre.

    Le total mesure reste sous la borne et aucun plafond individuel n'est depasse :
    sans la comparaison de non-croissance contre la reference, ce cas passait inapercu.
    """
    reference = _base(
        dette={"src/a.py": 3},
        classification={"src/a.py": {"ARG001": 3}},
        total_violations=3,
    )
    locale = _base(
        dette={"src/a.py": 1, "src/nouveau.py": 2},
        classification={
            "src/a.py": {"ARG001": 1},
            "src/nouveau.py": {"ARG001": 2},
        },
        total_violations=3,
    )

    resultat = ruff_ratchet.anomalies(
        mesure_dette={"src/a.py": 1, "src/nouveau.py": 2},
        mesure_classification={
            "src/a.py": {"ARG001": 1},
            "src/nouveau.py": {"ARG001": 2},
        },
        fichiers_reels={"src/a.py", "src/nouveau.py"},
        regles_courantes=["ARG001", "B904"],
        base_locale=locale,
        base_reference=reference,
    )

    assert any(
        "src/nouveau.py" in m
        and "ajoute a la dette baselinee" in m
        and "extension non justifiee" in m
        for m in resultat
    )
    # Preuve explicite que les regles 2, 4 et 5 seules n'auraient RIEN detecte ici.
    assert not any("depasse" in m for m in resultat)
    assert not any("borne" in m for m in resultat)
    assert all("reference" in m for m in resultat)


def test_anomalies_regle6_couple_fichier_regle_ajoute_absent_de_la_reference() -> None:
    """Fichier connu des deux bases, mais un NOUVEAU code ajoute a sa classification locale."""
    reference = _base(
        dette={"src/a.py": 2},
        classification={"src/a.py": {"ARG001": 2}},
        total_violations=2,
    )
    locale = _base(
        dette={"src/a.py": 2},
        classification={"src/a.py": {"ARG001": 1, "B904": 1}},
        total_violations=2,
    )

    resultat = ruff_ratchet.anomalies(
        mesure_dette={"src/a.py": 2},
        mesure_classification={"src/a.py": {"ARG001": 1, "B904": 1}},
        fichiers_reels={"src/a.py"},
        regles_courantes=["ARG001", "B904"],
        base_locale=locale,
        base_reference=reference,
    )

    # La regle 6 "fichier" ne se declenche PAS (fichier present dans les deux bases) :
    # seule l'anomalie au niveau du couple (fichier, regle) est levee.
    assert len(resultat) == 1
    message = resultat[0]
    assert "src/a.py" in message and "B904" in message
    assert "ajoutee a la classification baselinee" in message
    assert "extension non justifiee" in message


# ---------------------------------------------------------------------------
# main() — bout en bout via mock de ruff_ratchet.mesurer (jamais subprocess ici)
# ---------------------------------------------------------------------------

def test_main_retourne_0_quand_la_mesure_respecte_la_base(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cliquet vert : mesure exactement egale a la base -> code de retour 0."""
    _ecrire_classification(tmp_path)
    _ecrire_base(
        tmp_path,
        _base(
            dette={"src/pkg/mod.py": 1},
            classification={"src/pkg/mod.py": {"ARG001": 1}},
            total_violations=1,
        ),
    )
    (tmp_path / "src" / "pkg").mkdir(parents=True)
    (tmp_path / "src" / "pkg" / "mod.py").write_text(
        "def f(x, y):\n    return x\n", encoding="utf-8"
    )

    def fausse_mesure(racine: Path, regles: list[str]) -> list[dict[str, object]]:
        return [{"filename": "src/pkg/mod.py", "code": "ARG001"}]

    monkeypatch.setattr(ruff_ratchet, "mesurer", fausse_mesure)
    monkeypatch.setattr(
        ruff_ratchet.gate_git_ref,
        "charger_base_reference_git",
        _reference_git_absente,
    )

    assert ruff_ratchet.main(["--racine", str(tmp_path)]) == 0


def test_main_retourne_1_quand_la_mesure_depasse_la_base(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cliquet rouge : mesure au-dela du plafond baseline -> code de retour 1."""
    _ecrire_classification(tmp_path)
    _ecrire_base(
        tmp_path,
        _base(
            dette={"src/pkg/mod.py": 1},
            classification={"src/pkg/mod.py": {"ARG001": 1}},
            total_violations=1,
        ),
    )
    (tmp_path / "src" / "pkg").mkdir(parents=True)
    (tmp_path / "src" / "pkg" / "mod.py").write_text(
        "def f(x, y):\n    return x\n", encoding="utf-8"
    )

    def fausse_mesure(racine: Path, regles: list[str]) -> list[dict[str, object]]:
        return [
            {"filename": "src/pkg/mod.py", "code": "ARG001"},
            {"filename": "src/pkg/mod.py", "code": "ARG001"},
        ]

    monkeypatch.setattr(ruff_ratchet, "mesurer", fausse_mesure)
    monkeypatch.setattr(
        ruff_ratchet.gate_git_ref,
        "charger_base_reference_git",
        _reference_git_absente,
    )

    assert ruff_ratchet.main(["--racine", str(tmp_path)]) == 1


def test_main_retourne_1_si_classification_absente(tmp_path: Path) -> None:
    """governance/ruff-classification.json absent -> code 1, sans traceback."""
    _ecrire_base(tmp_path, _base())

    assert ruff_ratchet.main(["--racine", str(tmp_path)]) == 1


def test_main_retourne_1_si_baseline_absente(tmp_path: Path) -> None:
    """governance/ruff-baseline.json absent -> code 1, sans traceback."""
    _ecrire_classification(tmp_path)

    assert ruff_ratchet.main(["--racine", str(tmp_path)]) == 1


def test_main_reference_git_absente_est_non_bloquante(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Premiere introduction : reference non chargeable -> avertissement, cliquet local vert."""
    _ecrire_classification(tmp_path)
    _ecrire_base(
        tmp_path,
        _base(
            dette={"src/pkg/mod.py": 1},
            classification={"src/pkg/mod.py": {"ARG001": 1}},
            total_violations=1,
        ),
    )
    (tmp_path / "src" / "pkg").mkdir(parents=True)
    (tmp_path / "src" / "pkg" / "mod.py").write_text(
        "def f(x, y):\n    return x\n", encoding="utf-8"
    )

    def fausse_mesure(racine: Path, regles: list[str]) -> list[dict[str, object]]:
        return [{"filename": "src/pkg/mod.py", "code": "ARG001"}]

    monkeypatch.setattr(ruff_ratchet, "mesurer", fausse_mesure)
    monkeypatch.setattr(
        ruff_ratchet.gate_git_ref,
        "charger_base_reference_git",
        _reference_git_absente,
    )

    code = ruff_ratchet.main(["--racine", str(tmp_path)])

    assert code == 0
    assert "Avertissement" in capsys.readouterr().err


def test_main_regenerer_baseline_reecrit_une_base_perimee(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--regenerer-baseline reecrit integralement une base perimee depuis une mesure fraiche."""
    _ecrire_classification(tmp_path)
    _ecrire_base(
        tmp_path,
        _base(
            dette={"src/ancien.py": 5},
            classification={"src/ancien.py": {"ARG001": 5}},
            total_violations=5,
        ),
    )
    (tmp_path / "src" / "pkg").mkdir(parents=True)
    (tmp_path / "src" / "pkg" / "mod.py").write_text(
        "def f(x, y):\n    return x\n", encoding="utf-8"
    )

    def fausse_mesure(racine: Path, regles: list[str]) -> list[dict[str, object]]:
        return [{"filename": "src/pkg/mod.py", "code": "ARG001"}]

    monkeypatch.setattr(ruff_ratchet, "mesurer", fausse_mesure)

    assert ruff_ratchet.main(["--racine", str(tmp_path), "--regenerer-baseline"]) == 0

    base_reecrite = json.loads(
        (tmp_path / "governance" / "ruff-baseline.json").read_text(encoding="utf-8")
    )
    # L'ancien contenu perime (src/ancien.py) a integralement disparu : la base suit
    # desormais la mesure fraiche du mini-projet, pas l'etat d'avant l'appel.
    assert base_reecrite["dette"] == {"src/pkg/mod.py": 1}
    assert base_reecrite["classification"] == {"src/pkg/mod.py": {"ARG001": 1}}
    assert base_reecrite["borne"] == {"total_violations": 1}
    assert base_reecrite["regles_activees"] == ["ARG001", "B904"]
    assert base_reecrite["version"] == 1
    assert ruff_ratchet._valider_base(base_reecrite, "base reecrite") == base_reecrite


def test_main_regenerer_baseline_cree_le_fichier_si_absent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Premiere generation : aucune base preexistante requise, le fichier est cree."""
    _ecrire_classification(tmp_path)
    (tmp_path / "src" / "pkg").mkdir(parents=True)
    (tmp_path / "src" / "pkg" / "mod.py").write_text(
        "def f(x, y):\n    return x\n", encoding="utf-8"
    )
    chemin_base = tmp_path / "governance" / "ruff-baseline.json"
    assert not chemin_base.exists()

    def fausse_mesure(racine: Path, regles: list[str]) -> list[dict[str, object]]:
        return [{"filename": "src/pkg/mod.py", "code": "ARG001"}]

    monkeypatch.setattr(ruff_ratchet, "mesurer", fausse_mesure)

    assert ruff_ratchet.main(["--racine", str(tmp_path), "--regenerer-baseline"]) == 0

    assert chemin_base.exists()
    base_creee = json.loads(chemin_base.read_text(encoding="utf-8"))
    assert base_creee["dette"] == {"src/pkg/mod.py": 1}
    assert base_creee["classification"] == {"src/pkg/mod.py": {"ARG001": 1}}
    assert base_creee["borne"] == {"total_violations": 1}
    assert base_creee["regles_activees"] == ["ARG001", "B904"]
    assert ruff_ratchet._valider_base(base_creee, "base creee") == base_creee
