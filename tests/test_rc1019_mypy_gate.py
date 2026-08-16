from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import mypy_gate  # noqa: E402


def _base(dette=None, fichiers_proteges=None, total_erreurs=0, version=1, classification=None):
    """Fabrique une base valide pour les tests."""
    base = {
        "version": version,
        "borne": {"total_erreurs": total_erreurs},
        "fichiers_proteges": list(fichiers_proteges or []),
        "dette": dict(dette or {}),
    }
    if classification is not None:
        base["classification"] = classification
    return base


# ---------------------------------------------------------------------------
# CA « mesurer la baseline » — erreurs_par_fichier
# ---------------------------------------------------------------------------

def test_g1_erreurs_par_fichier_compte_plusieurs_erreurs_par_fichier():
    sortie = (
        "src/forgeai/a.py:10: error: ...\n"
        "src/forgeai/a.py:12: error: ...\n"
    )
    assert mypy_gate.erreurs_par_fichier(sortie) == {"src/forgeai/a.py": 2}


@pytest.mark.parametrize(
    "ligne",
    [
        "note: ceci est la suite de la meme erreur",
        "Found 4 errors in 2 files (checked 86 source files)",
    ],
)
def test_g1b_ignorer_lignes_note_et_resume(ligne):
    sortie = "src/a.py:1: error: vraie erreur\n" + ligne + "\n"
    assert mypy_gate.erreurs_par_fichier(sortie) == {"src/a.py": 1}


def test_g1c_success_no_issues_retourne_dict_vide():
    assert mypy_gate.erreurs_par_fichier(
        "Success: no issues found in 86 source files\n"
    ) == {}


# ---------------------------------------------------------------------------
# CA « aucune nouvelle erreur dans un module couvert » — protection
# ---------------------------------------------------------------------------

def test_g2_fichier_protege_en_erreur_produit_regression():
    base = _base(fichiers_proteges=["src/a.py"], total_erreurs=2)
    anomalies = mypy_gate.anomalies(
        reels={"src/a.py"},
        erreurs={"src/a.py": 2},
        base=base,
        base_reference=None,
    )
    assert any("src/a.py" in m and "regression" in m for m in anomalies)


def test_g2b_fichier_protege_zero_erreur_aucune_anomalie():
    base = _base(fichiers_proteges=["src/a.py"], total_erreurs=0)
    assert mypy_gate.anomalies(
        reels={"src/a.py"},
        erreurs={},
        base=base,
        base_reference=None,
    ) == []


# ---------------------------------------------------------------------------
# CA « baseline décroissante et non extensible sans justification »
# ---------------------------------------------------------------------------

def test_g3_augmenter_plafond_dette_depuis_reference_est_refuse():
    reference = _base(dette={"src/a.py": 2}, total_erreurs=2)
    base = _base(dette={"src/a.py": 3}, total_erreurs=2)

    anomalies = mypy_gate.anomalies(
        reels={"src/a.py"},
        erreurs={"src/a.py": 2},
        base=base,
        base_reference=reference,
    )

    assert any("doit decroitre" in m for m in anomalies)


def test_g3b_ajouter_dette_absente_reference_produit_extension_non_justifiee():
    reference = _base(total_erreurs=1)
    base = _base(dette={"src/b.py": 5}, total_erreurs=1)

    anomalies = mypy_gate.anomalies(
        reels={"src/b.py"},
        erreurs={"src/b.py": 1},
        base=base,
        base_reference=reference,
    )

    assert any("extension non justifiee" in m for m in anomalies)


def test_g3c_sans_base_reference_le_controle_reference_est_absent():
    base = _base(dette={"src/a.py": 5}, total_erreurs=1)
    assert mypy_gate.anomalies(
        reels={"src/a.py"},
        erreurs={"src/a.py": 1},
        base=base,
        base_reference=None,
    ) == []


# ---------------------------------------------------------------------------
# CA « dette dépassée »
# ---------------------------------------------------------------------------

def test_g4_plafond_dette_depasse_montre_les_deux_nombres_exacts():
    base = _base(dette={"src/a.py": 5}, total_erreurs=8)
    anomalies = mypy_gate.anomalies(
        reels={"src/a.py"},
        erreurs={"src/a.py": 8},
        base=base,
        base_reference=None,
    )
    assert any("src/a.py" in m and "8 > 5" in m for m in anomalies)


# ---------------------------------------------------------------------------
# CA « hygiène de la base »
# ---------------------------------------------------------------------------

def test_g5_dette_zero_erreur_demande_retrait():
    base = _base(dette={"src/a.py": 5}, total_erreurs=0)
    anomalies = mypy_gate.anomalies(
        reels={"src/a.py"},
        erreurs={},
        base=base,
        base_reference=None,
    )
    assert any(
        "src/a.py" in m and "retirer de la dette" in m for m in anomalies
    )


def test_g5b_amelioration_partielle_aucune_anomalie():
    base = _base(dette={"src/a.py": 5}, total_erreurs=3)
    assert mypy_gate.anomalies(
        reels={"src/a.py"},
        erreurs={"src/a.py": 3},
        base=base,
        base_reference=None,
    ) == []


# ---------------------------------------------------------------------------
# CA « borne totale inconditionnelle »
# ---------------------------------------------------------------------------

def test_g6_depassement_borne_totale_sans_depasser_plafonds_individuels():
    base = _base(dette={"src/a.py": 3, "src/b.py": 3}, total_erreurs=4)
    anomalies = mypy_gate.anomalies(
        reels={"src/a.py", "src/b.py"},
        erreurs={"src/a.py": 3, "src/b.py": 3},
        base=base,
        base_reference=None,
    )
    assert any(
        "le total mypy est de 6 erreurs alors que la borne est fixee a 4" in m
        for m in anomalies
    )


# ---------------------------------------------------------------------------
# CA « validation de base »
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "base_invalide, message_attendu",
    [
        ([], "doit etre un objet JSON"),
        (
            {
                "version": 1,
                "borne": {"total_erreurs": 0},
                "fichiers_proteges": [],
                "dette": {"a": -1},
            },
            "strictement positif",
        ),
        (
            {
                "version": 1,
                "borne": {"total_erreurs": 0},
                "fichiers_proteges": [],
                "dette": {"a": 0},
            },
            "strictement positif",
        ),
        (
            {
                "version": 1,
                "borne": {"total_erreurs": 0},
                "fichiers_proteges": [],
                "dette": {"a": True},
            },
            "strictement positif",
        ),
        (
            {
                "version": 1,
                "borne": {"total_erreurs": 0},
                "fichiers_proteges": ["a", "a"],
                "dette": {},
            },
            "doublons",
        ),
        (
            {
                "version": 1,
                "borne": {"total_erreurs": 0},
                "fichiers_proteges": ["a"],
                "dette": {"a": 1},
            },
            "a la fois",
        ),
        (
            {
                "version": 1,
                "borne": {"total_erreurs": -1},
                "fichiers_proteges": [],
                "dette": {},
            },
            "positif ou nul",
        ),
        (
            {
                "version": 1,
                "borne": {"total_erreurs": True},
                "fichiers_proteges": [],
                "dette": {},
            },
            "positif ou nul",
        ),
    ],
)
def test_g7_valider_base_refuse_formes_invalides(base_invalide, message_attendu):
    with pytest.raises(ValueError, match=message_attendu):
        mypy_gate._valider_base(base_invalide, "base")


def test_g7b_valider_base_accepte_base_valide():
    base = _base(dette={"a": 1}, fichiers_proteges=["b"], total_erreurs=2)
    assert mypy_gate._valider_base(base, "base") == base


# ---------------------------------------------------------------------------
# CA « fichier disparu »
# ---------------------------------------------------------------------------

def test_g8_fichier_protege_disparu_produit_anomalie():
    base = _base(fichiers_proteges=["src/disparu.py"], total_erreurs=0)
    anomalies = mypy_gate.anomalies(
        reels={"src/a.py"},
        erreurs={},
        base=base,
        base_reference=None,
    )
    assert any("src/disparu.py" in m and "absent du depot" in m for m in anomalies)


def test_g8b_fichier_dette_disparu_produit_anomalie():
    base = _base(dette={"src/disparu.py": 5}, total_erreurs=0)
    anomalies = mypy_gate.anomalies(
        reels={"src/a.py"},
        erreurs={},
        base=base,
        base_reference=None,
    )
    assert any("src/disparu.py" in m and "absent du depot" in m for m in anomalies)


# ---------------------------------------------------------------------------
# CA « nouveau fichier en erreur non baseliné »
# ---------------------------------------------------------------------------

def test_g9_nouveau_fichier_en_erreur_non_baseline_produit_anomalie():
    base = _base(total_erreurs=2)
    anomalies = mypy_gate.anomalies(
        reels={"src/nouveau.py"},
        erreurs={"src/nouveau.py": 2},
        base=base,
        base_reference=None,
    )
    assert any("src/nouveau.py" in m and "absent de la base" in m for m in anomalies)


# ---------------------------------------------------------------------------
# CA « fichiers_reels »
# ---------------------------------------------------------------------------

def test_g10_fichiers_reels_retourne_chemins_posix(tmp_path):
    (tmp_path / "src" / "forgeai" / "sub").mkdir(parents=True)
    (tmp_path / "src" / "forgeai" / "a.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "src" / "forgeai" / "sub" / "b.py").write_text("y = 2\n", encoding="utf-8")
    (tmp_path / "src" / "forgeai" / "sub" / "note.txt").write_text(
        "pas un fichier python", encoding="utf-8"
    )

    reels = mypy_gate.fichiers_reels(tmp_path, "src/forgeai")
    assert reels == {"src/forgeai/a.py", "src/forgeai/sub/b.py"}
    assert all("/" in f and "\\" not in f for f in reels)


# ---------------------------------------------------------------------------
# CA « première introduction » — référence git absente
# ---------------------------------------------------------------------------

def test_g11_base_reference_absente_a_la_ref_retourne_none_et_message(
    tmp_path, monkeypatch
):
    chemin_base = tmp_path / "base.json"
    chemin_base.write_text(json.dumps(_base()), encoding="utf-8")

    def fake_run(args, **kwargs):
        class Result:
            returncode = 0

        if args[:2] == ["git", "rev-parse"]:
            return Result()
        if args[:2] == ["git", "show"]:
            raise mypy_gate.subprocess.CalledProcessError(1, args)
        raise AssertionError(f"appel subprocess inattendu: {args}")

    monkeypatch.setattr(mypy_gate.subprocess, "run", fake_run)

    base_reference, message = mypy_gate.gate_git_ref.charger_base_reference_git(
        tmp_path, chemin_base, "origin/main", mypy_gate._valider_base
    )

    assert base_reference is None
    assert message != ""


# ---------------------------------------------------------------------------
# CA « end-to-end » — main() sans mypy réel
# ---------------------------------------------------------------------------

def test_g12_main_retourne_0_sans_anomalie_et_1_avec_anomalie(tmp_path, monkeypatch):
    (tmp_path / "src" / "forgeai").mkdir(parents=True)
    (tmp_path / "src" / "forgeai" / "a.py").write_text("x = 1\n", encoding="utf-8")
    chemin_base = tmp_path / "base.json"
    chemin_base.write_text(json.dumps(_base()), encoding="utf-8")

    def _exec_fake_success(racine, cible):
        return "Success: no issues found in 1 source file\n"

    monkeypatch.setattr(mypy_gate, "executer_mypy", _exec_fake_success)
    code = mypy_gate.main(["--racine", str(tmp_path), "--base", str(chemin_base)])
    assert code == 0

    def _exec_fake_erreur(racine, cible):
        return (
            "src/forgeai/a.py:1: error: ...\n"
            "Found 1 error in 1 file (checked 1 source file)\n"
        )

    monkeypatch.setattr(mypy_gate, "executer_mypy", _exec_fake_erreur)
    code = mypy_gate.main(["--racine", str(tmp_path), "--base", str(chemin_base)])
    assert code == 1


# ---------------------------------------------------------------------------
# CA « --rapport-json »
# ---------------------------------------------------------------------------

def test_g13_rapport_json_contient_cles_attendues(tmp_path, monkeypatch):
    (tmp_path / "src" / "forgeai").mkdir(parents=True)
    (tmp_path / "src" / "forgeai" / "a.py").write_text("x = 1\n", encoding="utf-8")
    chemin_base = tmp_path / "base.json"
    chemin_base.write_text(json.dumps(_base()), encoding="utf-8")
    rapport = tmp_path / "rapport.json"

    def _exec_fake_erreur(racine, cible):
        return (
            "src/forgeai/a.py:1: error: ...\n"
            "Found 1 error in 1 file (checked 1 source file)\n"
        )

    monkeypatch.setattr(mypy_gate, "executer_mypy", _exec_fake_erreur)

    code = mypy_gate.main([
        "--racine",
        str(tmp_path),
        "--base",
        str(chemin_base),
        "--rapport-json",
        str(rapport),
    ])

    assert code == 1
    contenu = json.loads(rapport.read_text(encoding="utf-8"))
    assert "total_erreurs" in contenu
    assert "anomalies" in contenu
    assert contenu["total_erreurs"] == 1
    assert any("src/forgeai/a.py" in anomalie for anomalie in contenu["anomalies"])


# ---------------------------------------------------------------------------
# Correctif SonarCloud #449 — étape 4/4
# ---------------------------------------------------------------------------

def test_g14_rapport_json_chemin_invalide_ne_plante_pas_main(tmp_path, monkeypatch):
    (tmp_path / "src" / "forgeai").mkdir(parents=True)
    (tmp_path / "src" / "forgeai" / "a.py").write_text("x = 1\n", encoding="utf-8")
    chemin_base = tmp_path / "base.json"
    chemin_base.write_text(json.dumps(_base()), encoding="utf-8")
    monkeypatch.setattr(
        mypy_gate, "executer_mypy",
        lambda racine, cible: "Success: no issues found in 1 source file\n",
    )
    chemin_invalide = str(tmp_path / "inexistant" / "rapport.json")
    code = mypy_gate.main([
        "--racine", str(tmp_path), "--base", str(chemin_base),
        "--rapport-json", chemin_invalide,
    ])
    assert code == 1


# ---------------------------------------------------------------------------
# Tests RÉELS de executer_mypy (ferme l'écart de couverture)
# ---------------------------------------------------------------------------

def test_g15_executer_mypy_construit_la_commande_attendue(tmp_path, monkeypatch):
    """subprocess.run doit être appelé avec la commande exacte et les options de capture."""
    captured = {}

    def fake_run(args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs

        class Result:
            stdout = ""
            stderr = ""
            returncode = 0

        return Result()

    monkeypatch.setattr(mypy_gate.subprocess, "run", fake_run)

    resultat = mypy_gate.executer_mypy(tmp_path, "src/forgeai")

    assert resultat == ""
    assert captured["args"] == [
        sys.executable,
        "-m",
        "mypy",
        "src/forgeai",
        "--config-file=",
    ]
    assert captured["kwargs"]["cwd"] == str(tmp_path)
    assert captured["kwargs"]["capture_output"] is True
    assert captured["kwargs"]["text"] is True


def test_g15b_executer_mypy_retourne_stdout_stderr(tmp_path, monkeypatch):
    """executer_mypy doit concaténer stdout et stderr."""
    class Result:
        stdout = "STDOUT\n"
        stderr = "STDERR\n"
        returncode = 1

    monkeypatch.setattr(mypy_gate.subprocess, "run", lambda *a, **k: Result())
    assert mypy_gate.executer_mypy(tmp_path, "src/forgeai") == "STDOUT\nSTDERR\n"


@pytest.mark.parametrize(
    "message",
    [
        "No module named mypy",
        "No module named 'mypy'",
    ],
)
def test_g15c_executer_mypy_erreur_si_module_mypy_absent(tmp_path, monkeypatch, message):
    """executer_mypy lève RuntimeError avec mention mypy>=1.10 quand mypy n'est pas installé."""
    class Result:
        stdout = message + "\n"
        stderr = ""
        returncode = 1

    monkeypatch.setattr(mypy_gate.subprocess, "run", lambda *a, **k: Result())
    with pytest.raises(RuntimeError, match="mypy>=1.10"):
        mypy_gate.executer_mypy(tmp_path, "src/forgeai")


def test_g15d_executer_mypy_erreur_si_python3_introuvable(tmp_path, monkeypatch):
    """executer_mypy convertit FileNotFoundError en RuntimeError explicite."""
    def fake_run(*args, **kwargs):
        raise FileNotFoundError

    monkeypatch.setattr(mypy_gate.subprocess, "run", fake_run)
    with pytest.raises(RuntimeError, match="interpreteur Python introuvable"):
        mypy_gate.executer_mypy(tmp_path, "src/forgeai")


def test_g15e_executer_mypy_refuse_cible_invalide_avant_subprocess(tmp_path, monkeypatch):
    """Une cible invalide doit être refusée AVANT tout appel à subprocess.run."""
    def boom(*args, **kwargs):
        raise AssertionError(
            "subprocess.run ne doit pas etre appele pour une cible invalide"
        )

    monkeypatch.setattr(mypy_gate.subprocess, "run", boom)
    with pytest.raises(ValueError, match="cible mypy invalide"):
        mypy_gate.executer_mypy(tmp_path, "--evil")


# ---------------------------------------------------------------------------
# Tests de _valider_cible
# ---------------------------------------------------------------------------

def test_g16_valider_cible_refuse_vide():
    with pytest.raises(ValueError, match="cible mypy invalide"):
        mypy_gate._valider_cible("")


def test_g16b_valider_cible_refuse_prefixe_tiret():
    with pytest.raises(ValueError, match="cible mypy invalide"):
        mypy_gate._valider_cible("-cible")


def test_g16c_valider_cible_accepte_cible_normale():
    mypy_gate._valider_cible("src/forgeai")  # ne doit pas lever


# ---------------------------------------------------------------------------
# Tests de _valider_chemin_rapport
# ---------------------------------------------------------------------------

def test_g17_valider_chemin_rapport_accepte_repertoire_parent_existant(tmp_path):
    chemin = mypy_gate._valider_chemin_rapport(str(tmp_path / "rapport.json"))
    assert isinstance(chemin, Path)
    assert chemin == (tmp_path / "rapport.json").resolve()


def test_g17b_valider_chemin_rapport_refuse_parent_inexistant(tmp_path):
    chemin = tmp_path / "inexistant" / "rapport.json"
    with pytest.raises(ValueError, match="--rapport-json"):
        mypy_gate._valider_chemin_rapport(str(chemin))


# ---------------------------------------------------------------------------
# Correctif post-revue scellée #449 (round 1) — protection permanente
# ---------------------------------------------------------------------------

def test_g18_fichier_proteges_retrograde_vers_dette_est_detecte():
    """Un fichier protégé dans la référence, rétrogradé en dette courante, est détecté."""
    reference = _base(fichiers_proteges=["src/a.py"], total_erreurs=0)
    base = _base(dette={"src/a.py": 1}, total_erreurs=1)

    anomalies = mypy_gate.anomalies(
        reels={"src/a.py"},
        erreurs={"src/a.py": 1},
        base=base,
        base_reference=reference,
    )

    assert any(
        "src/a.py" in m and "retire de la protection" in m for m in anomalies
    )


def test_g18b_fichier_proteges_retire_completement_est_detecte():
    """Un fichier protégé dans la référence, absent de la base courante, est détecté."""
    reference = _base(fichiers_proteges=["src/a.py"], total_erreurs=0)
    base = _base(total_erreurs=0)

    anomalies = mypy_gate.anomalies(
        reels={"src/a.py"},
        erreurs={},
        base=base,
        base_reference=reference,
    )

    assert any(
        "src/a.py" in m and "retire de la protection" in m for m in anomalies
    )


def test_g18c_fichier_proteges_dans_la_reference_ET_courant_ne_produit_aucune_anomalie_de_ce_type():
    """Un fichier protégé dans les deux bases ne déclenche pas cette anomalie."""
    reference = _base(fichiers_proteges=["src/a.py"], total_erreurs=0)
    base = _base(fichiers_proteges=["src/a.py"], total_erreurs=0)

    anomalies = mypy_gate.anomalies(
        reels={"src/a.py"},
        erreurs={},
        base=base,
        base_reference=reference,
    )

    assert not any("retire de la protection" in m for m in anomalies)
    assert anomalies == []


# ---------------------------------------------------------------------------
# Tests pour _valider_classification
# ---------------------------------------------------------------------------

def test_g19_classification_absente_est_acceptee():
    """Une classification absente (None) est acceptée et retourne {}."""
    assert mypy_gate._valider_classification(None, {"a.py": 3}, "base") == {}


def test_g19b_classification_coherente_est_acceptee():
    """Une classification cohérente avec la dette est acceptée telle quelle."""
    classification = {"a.py": {"union-attr": 2, "misc": 1}}
    assert (
        mypy_gate._valider_classification(
            classification, {"a.py": 3}, "base"
        )
        == classification
    )


def test_g19c_classification_somme_incoherente_leve():
    """La somme des comptes doit égale la dette, sinon ValueError."""
    with pytest.raises(ValueError, match="incoherente"):
        mypy_gate._valider_classification(
            {"a.py": {"union-attr": 5}}, {"a.py": 3}, "base"
        )


def test_g19d_classification_cles_incoherentes_avec_dette_leve():
    """Les clés de classification doivent correspondre exactement aux clés de dette."""
    # Clé en trop dans la classification.
    with pytest.raises(ValueError):
        mypy_gate._valider_classification(
            {"a.py": {"x": 3}, "b.py": {"y": 2}},
            {"a.py": 3},
            "base",
        )

    # Clé manquante dans la classification.
    with pytest.raises(ValueError):
        mypy_gate._valider_classification(
            {"a.py": {"x": 2}},
            {"a.py": 2, "b.py": 4},
            "base",
        )


def test_g19e_classification_valeur_non_positive_leve():
    """Chaque compte de code doit être un entier strictement positif non booléen."""
    # Zéro.
    with pytest.raises(ValueError):
        mypy_gate._valider_classification(
            {"a.py": {"x": 0}}, {"a.py": 1}, "base"
        )

    # Négatif.
    with pytest.raises(ValueError):
        mypy_gate._valider_classification(
            {"a.py": {"x": -1}}, {"a.py": 1}, "base"
        )

    # Booléen.
    with pytest.raises(ValueError):
        mypy_gate._valider_classification(
            {"a.py": {"x": True}}, {"a.py": 1}, "base"
        )


def test_g19f_valider_base_accepte_classification_valide():
    """_valider_base accepte une base complète avec classification cohérente."""
    base = _base(
        dette={"a.py": 3},
        fichiers_proteges=["b.py"],
        total_erreurs=3,
        classification={"a.py": {"union-attr": 2, "misc": 1}},
    )
    assert mypy_gate._valider_base(base, "base") == base


def test_g19g_valider_base_refuse_classification_incoherente():
    """_valider_base lève ValueError si la classification est incohérente avec la dette."""
    base = _base(
        dette={"a.py": 3},
        fichiers_proteges=["b.py"],
        total_erreurs=3,
        classification={"a.py": {"union-attr": 5}},
    )
    with pytest.raises(ValueError, match="incoherente"):
        mypy_gate._valider_base(base, "base")


# ---------------------------------------------------------------------------
# Correctif post-revue scellée #449 (round 3) — .pyi
# ---------------------------------------------------------------------------

def test_g20_erreurs_par_fichier_reconnait_les_stubs_pyi():
    sortie = (
        "src/forgeai/a.py:1: error: x\n"
        "src/forgeai/b.pyi:2: error: y\n"
    )
    assert mypy_gate.erreurs_par_fichier(sortie) == {
        "src/forgeai/a.py": 1,
        "src/forgeai/b.pyi": 1,
    }


def test_g21_fichiers_reels_inclut_les_stubs_pyi(tmp_path):
    dossier = tmp_path / "src" / "forgeai"
    dossier.mkdir(parents=True)
    (dossier / "a.py").write_text("x = 1\n", encoding="utf-8")
    (dossier / "b.pyi").write_text("y: int\n", encoding="utf-8")

    reels = mypy_gate.fichiers_reels(tmp_path, "src/forgeai")
    assert reels == {"src/forgeai/a.py", "src/forgeai/b.pyi"}


# ---------------------------------------------------------------------------
# Correctif post-revue scellée #449 (round 4) — --config-file=
# ---------------------------------------------------------------------------

def test_g22_executer_mypy_ignore_config_mypy_du_depot(tmp_path, monkeypatch):
    """Garantit que --config-file= est toujours passé à mypy, neutralisant toute config du dépôt."""
    captured = {}

    def fake_run(args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs

        class Result:
            stdout = ""
            stderr = ""
            returncode = 0

        return Result()

    monkeypatch.setattr(mypy_gate.subprocess, "run", fake_run)

    mypy_gate.executer_mypy(tmp_path, "src/forgeai")

    assert "--config-file=" in captured["args"]


# ---------------------------------------------------------------------------
# Correctif post-revue scellée #449 (round 5) — retire de la dette sans promotion
# ---------------------------------------------------------------------------

def test_g23_fichier_dette_retire_sans_promotion_est_detecte():
    """Un fichier présent dans la dette de référence, retiré de la dette courante
    sans être promu aux fichiers_proteges, doit produire une anomalie.
    """
    reference = _base(
        dette={"src/a.py": 106, "src/b.py": 28},
        total_erreurs=134,
    )
    base = _base(
        dette={"src/b.py": 28},
        total_erreurs=28,
    )

    anomalies = mypy_gate.anomalies(
        reels={"src/a.py", "src/b.py"},
        erreurs={"src/b.py": 28},  # src/a.py absent = 0, simule une directive d'ignore
        base=base,
        base_reference=reference,
    )

    assert any(
        "retire de la dette" in m and "src/a.py" in m for m in anomalies
    )


def test_g23b_fichier_dette_retire_ET_promu_proteges_aucune_anomalie():
    """Même scénario, mais src/a.py est promu aux fichiers_proteges : aucune anomalie
    de ce type ne doit apparaître.
    """
    reference = _base(
        dette={"src/a.py": 106, "src/b.py": 28},
        total_erreurs=134,
    )
    base = _base(
        fichiers_proteges=["src/a.py"],
        dette={"src/b.py": 28},
        total_erreurs=28,
    )

    anomalies = mypy_gate.anomalies(
        reels={"src/a.py", "src/b.py"},
        erreurs={"src/b.py": 28},  # src/a.py est protégé et propre
        base=base,
        base_reference=reference,
    )

    assert not any(
        "retire de la dette" in m and "src/a.py" in m for m in anomalies
    )


# ---------------------------------------------------------------------------
# Correctif post-revue scellée #449 (round 6) — neutralisation mypy
# ---------------------------------------------------------------------------

def test_g24_fichiers_neutralises_detecte_la_directive(tmp_path):
    chemin = tmp_path / "a.py"
    chemin.write_text("# mypy: ignore-errors\nx = 1\n", encoding="utf-8")
    assert mypy_gate.fichiers_neutralises(tmp_path, {"a.py"}) == {"a.py"}


def test_g24b_fichiers_neutralises_ignore_fichier_sain(tmp_path):
    chemin = tmp_path / "a.py"
    chemin.write_text("x = 1\n", encoding="utf-8")
    assert mypy_gate.fichiers_neutralises(tmp_path, {"a.py"}) == set()


def test_g24c_fichiers_neutralises_ignore_fichier_absent(tmp_path):
    # Ne doit pas lever d'exception et ne pas inclure le fichier absent.
    assert mypy_gate.fichiers_neutralises(tmp_path, {"absent.py"}) == set()


def test_g25_anomalies_signale_fichier_protege_neutralise():
    base = _base(fichiers_proteges=["a.py"], total_erreurs=0)
    anomalies = mypy_gate.anomalies(
        reels={"a.py"},
        erreurs={},
        base=base,
        base_reference=None,
        neutralises={"a.py"},
    )
    assert any(
        "directive mypy inline" in m and "a.py" in m for m in anomalies
    )


def test_g25b_anomalies_sans_neutralises_aucune_regression():
    base = _base(fichiers_proteges=["a.py"], total_erreurs=0)
    anomalies = mypy_gate.anomalies(
        reels={"a.py"},
        erreurs={},
        base=base,
        base_reference=None,
    )
    assert anomalies == []


# ---------------------------------------------------------------------------
# Correctif post-revue scellée #449 (round 7) — encodage non UTF-8
# ---------------------------------------------------------------------------

def test_g26_fichiers_neutralises_detecte_meme_encodage_non_utf8(tmp_path):
    chemin = tmp_path / "a.py"
    chemin.write_bytes(
        b'# -*- coding: latin-1 -*-\n# mypy: ignore-errors\nx = "caf\xe9"\n'
    )
    assert mypy_gate.fichiers_neutralises(tmp_path, {"a.py"}) == {"a.py"}


# ---------------------------------------------------------------------------
# Correctif post-revue scellée #449 (round 8) — généralisation directive mypy
# ---------------------------------------------------------------------------

def test_g27_fichiers_neutralises_detecte_disable_error_code(tmp_path):
    chemin = tmp_path / "a.py"
    chemin.write_bytes(b"# mypy: disable-error-code=assignment\nx = 1\n")
    assert mypy_gate.fichiers_neutralises(tmp_path, {"a.py"}) == {"a.py"}


def test_g27b_fichiers_neutralises_ignore_commentaire_mypy_sans_deux_points(tmp_path):
    chemin = tmp_path / "a.py"
    chemin.write_bytes(b"# mypy is a great tool\nx = 1\n")
    assert mypy_gate.fichiers_neutralises(tmp_path, {"a.py"}) == set()


# ---------------------------------------------------------------------------
# Correctif post-revue scellée #449 (round 8) — `tests/test_rc1019_mypy_gate.py`
# ---------------------------------------------------------------------------

def test_g28_fichier_dette_avec_directive_est_detecte():
    base = _base(dette={"server.py": 106}, total_erreurs=106)
    anomalies = mypy_gate.anomalies(
        reels={"server.py"},
        erreurs={"server.py": 50},
        base=base,
        base_reference=None,
        neutralises={"server.py"},
    )
    assert any(
        "directive mypy inline" in m and "server.py" in m for m in anomalies
    )


# ---------------------------------------------------------------------------
# Correctif post-revue scellée #449 (round 11) — perimetre etendu a `reels`
# ---------------------------------------------------------------------------

def test_g29_fichier_non_baseline_avec_directive_est_detecte():
    base = _base(total_erreurs=0)
    anomalies = mypy_gate.anomalies(
        reels={"nouveau.py"},
        erreurs={},
        base=base,
        base_reference=None,
        neutralises={"nouveau.py"},
    )
    assert any(
        "directive mypy inline" in m and "nouveau.py" in m for m in anomalies
    )


def test_g29b_fichier_non_baseline_sans_directive_ni_erreur_aucune_anomalie():
    base = _base(total_erreurs=0)
    anomalies = mypy_gate.anomalies(
        reels={"nouveau.py"},
        erreurs={},
        base=base,
        base_reference=None,
    )
    assert anomalies == []


def test_g30_fichiers_neutralises_couvre_fichier_hors_base(tmp_path):
    chemin = tmp_path / "hors_base.py"
    chemin.write_bytes(b"# mypy: ignore-errors\nx = 1\n")
    assert mypy_gate.fichiers_neutralises(tmp_path, {"hors_base.py"}) == {"hors_base.py"}


# ---------------------------------------------------------------------------
# Correctif post-revue scellée #449 (round 12) — cliquet # type: ignore
# ---------------------------------------------------------------------------

def test_g31_occurrences_type_ignore_compte_les_occurrences(tmp_path):
    chemin = tmp_path / "a.py"
    chemin.write_bytes(b"x = 1  # type: ignore\ny = 2  # type: ignore\nz = 3\n")
    assert mypy_gate.occurrences_type_ignore(tmp_path, {"a.py"}) == {"a.py": 2}


def test_g31b_occurrences_type_ignore_fichier_sans_occurrence_absent_du_resultat(tmp_path):
    chemin = tmp_path / "a.py"
    chemin.write_bytes(b"x = 1\n")
    assert mypy_gate.occurrences_type_ignore(tmp_path, {"a.py"}) == {}


def test_g31c_occurrences_type_ignore_variantes_espacement_toutes_comptees(tmp_path):
    chemin = tmp_path / "a.py"
    chemin.write_bytes(
        b"a = 1  # type: ignore\nb = 2  #type:ignore\nc = 3  # type:ignore[return-value]\nd = 4  #  type:   ignore\n"
    )
    assert mypy_gate.occurrences_type_ignore(tmp_path, {"a.py"}) == {"a.py": 4}


def test_g31d_occurrences_type_ignore_ignore_faux_positifs(tmp_path):
    chemin = tmp_path / "a.py"
    chemin.write_bytes(
        b"x = 1  # ceci mentionne type: ignore dans une phrase normale\ny = 2  # type: ignoreme\n"
    )
    assert mypy_gate.occurrences_type_ignore(tmp_path, {"a.py"}) == {}


def test_g32_anomalies_signale_hausse_type_ignore_nouveau_fichier():
    base = _base(total_erreurs=0)
    anomalies = mypy_gate.anomalies(
        reels={"nouveau.py"},
        erreurs={},
        base=base,
        base_reference=None,
        occurrences={"nouveau.py": 1},
    )
    assert any("# type: ignore en hausse" in m and "nouveau.py" in m for m in anomalies)


def test_g32b_anomalies_type_ignore_sous_le_plafond_aucune_anomalie():
    base = _base(total_erreurs=0, dette={}, fichiers_proteges=[])
    base["type_ignore"] = {"core/proc.py": 10}
    anomalies = mypy_gate.anomalies(
        reels={"core/proc.py"},
        erreurs={},
        base=base,
        base_reference=None,
        occurrences={"core/proc.py": 10},
    )
    assert anomalies == []


def test_g32c_anomalies_type_ignore_depasse_le_plafond_est_detecte():
    base = _base(total_erreurs=0, dette={}, fichiers_proteges=[])
    base["type_ignore"] = {"core/proc.py": 10}
    anomalies = mypy_gate.anomalies(
        reels={"core/proc.py"},
        erreurs={},
        base=base,
        base_reference=None,
        occurrences={"core/proc.py": 11},
    )
    assert any(
        "# type: ignore en hausse" in m
        and "core/proc.py" in m
        and "11" in m
        and "10" in m
        for m in anomalies
    )


def test_g32d_anomalies_sans_occurrences_aucune_regression():
    anomalies = mypy_gate.anomalies(
        reels={"nouveau.py"},
        erreurs={},
        base=_base(total_erreurs=0),
        base_reference=None,
    )
    assert anomalies == []


def test_g33_valider_type_ignore_rejette_plafond_non_positif():
    with pytest.raises(ValueError):
        mypy_gate._valider_type_ignore({"a.py": 0}, "base")


def test_g33b_valider_type_ignore_absent_retourne_dict_vide():
    assert mypy_gate._valider_type_ignore(None, "base") == {}


# ---------------------------------------------------------------------------
# Correctif post-revue scellée #449 (round 13) — reference git pour type_ignore
# ---------------------------------------------------------------------------

def test_g34_anomalies_signale_plafond_type_ignore_augmente_depuis_reference():
    base = {
        "version": 1,
        "borne": {"total_erreurs": 0},
        "fichiers_proteges": [],
        "dette": {},
        "type_ignore": {"a.py": 50},
    }
    reference = {
        "version": 1,
        "borne": {"total_erreurs": 0},
        "fichiers_proteges": [],
        "dette": {},
        "type_ignore": {"a.py": 1},
    }
    anomalies = mypy_gate.anomalies(
        reels={"a.py"},
        erreurs={},
        base=base,
        base_reference=reference,
        occurrences={"a.py": 50},
    )
    assert any(
        "type_ignore" in m and "a.py" in m and "50" in m and "1" in m
        for m in anomalies
    )


def test_g34b_anomalies_signale_nouveau_fichier_type_ignore_absent_de_reference():
    base = {
        "version": 1,
        "borne": {"total_erreurs": 0},
        "fichiers_proteges": [],
        "dette": {},
        "type_ignore": {"nouveau.py": 3},
    }
    reference = {
        "version": 1,
        "borne": {"total_erreurs": 0},
        "fichiers_proteges": [],
        "dette": {},
        "type_ignore": {},
    }
    anomalies = mypy_gate.anomalies(
        reels={"nouveau.py"},
        erreurs={},
        base=base,
        base_reference=reference,
        occurrences={"nouveau.py": 3},
    )
    assert any(
        "type_ignore" in m and "nouveau.py" in m and "absent de la reference" in m
        for m in anomalies
    )


def test_g34c_anomalies_type_ignore_meme_plafond_que_reference_aucune_anomalie():
    base = {
        "version": 1,
        "borne": {"total_erreurs": 0},
        "fichiers_proteges": [],
        "dette": {},
        "type_ignore": {"a.py": 5},
    }
    reference = {
        "version": 1,
        "borne": {"total_erreurs": 0},
        "fichiers_proteges": [],
        "dette": {},
        "type_ignore": {"a.py": 5},
    }
    anomalies = mypy_gate.anomalies(
        reels={"a.py"},
        erreurs={},
        base=base,
        base_reference=reference,
        occurrences={"a.py": 5},
    )
    assert anomalies == []


def test_g34d_anomalies_type_ignore_plafond_diminue_depuis_reference_aucune_anomalie():
    base = {
        "version": 1,
        "borne": {"total_erreurs": 0},
        "fichiers_proteges": [],
        "dette": {},
        "type_ignore": {"a.py": 2},
    }
    reference = {
        "version": 1,
        "borne": {"total_erreurs": 0},
        "fichiers_proteges": [],
        "dette": {},
        "type_ignore": {"a.py": 5},
    }
    anomalies = mypy_gate.anomalies(
        reels={"a.py"},
        erreurs={},
        base=base,
        base_reference=reference,
        occurrences={"a.py": 2},
    )
    assert anomalies == []


def test_g34e_anomalies_reference_sans_type_ignore_retrocompatible():
    base = {
        "version": 1,
        "borne": {"total_erreurs": 0},
        "fichiers_proteges": [],
        "dette": {},
        "type_ignore": {"a.py": 1},
    }
    reference = {
        "version": 1,
        "borne": {"total_erreurs": 0},
        "fichiers_proteges": [],
        "dette": {},
    }
    anomalies = mypy_gate.anomalies(
        reels={"a.py"},
        erreurs={},
        base=base,
        base_reference=reference,
        occurrences={"a.py": 1},
    )
    assert any(
        "type_ignore" in m and "a.py" in m and "absent de la reference" in m
        for m in anomalies
    )


# ---------------------------------------------------------------------------
# Correctif post-revue scellée #449 (round 14) — empreintes de contenu type_ignore
# ---------------------------------------------------------------------------

def test_g35_contenus_type_ignore_capture_une_empreinte(tmp_path):
    chemin = tmp_path / "a.py"
    chemin.write_bytes(b"x = 1  # type: ignore\n")
    attendu = hashlib.sha256(b"x = 1  # type: ignore").hexdigest()
    assert mypy_gate.contenus_type_ignore(tmp_path, {"a.py"}) == {"a.py": {attendu: 1}}


def test_g35b_contenus_type_ignore_deux_lignes_identiques_apres_strip_une_seule_empreinte(tmp_path):
    chemin = tmp_path / "a.py"
    chemin.write_bytes(b"    x = 1  # type: ignore\nx = 1  # type: ignore\n")
    assert len(mypy_gate.contenus_type_ignore(tmp_path, {"a.py"})["a.py"]) == 1
    assert list(mypy_gate.contenus_type_ignore(tmp_path, {"a.py"})["a.py"].values()) == [2]


def test_g35c_contenus_type_ignore_fichier_sans_occurrence_absent_du_resultat(tmp_path):
    chemin = tmp_path / "a.py"
    chemin.write_bytes(b"x = 1\n")
    assert mypy_gate.contenus_type_ignore(tmp_path, {"a.py"}) == {}


def test_g36_anomalies_signale_ligne_type_ignore_non_baselinee():
    base = {
        "version": 1,
        "borne": {"total_erreurs": 0},
        "fichiers_proteges": [],
        "dette": {},
        "type_ignore": {"a.py": 1},
        "type_ignore_lignes": {"a.py": {"deadbeef" * 8: 1}},
    }
    anomalies = mypy_gate.anomalies(
        reels={"a.py"},
        erreurs={},
        base=base,
        base_reference=None,
        occurrences={"a.py": 1},
        contenus={"a.py": {"cafebabe" * 8: 1}},
    )
    assert any("suppression non verifiee" in m and "a.py" in m for m in anomalies)


def test_g36b_anomalies_meme_empreinte_que_baseline_aucune_anomalie():
    base = {
        "version": 1,
        "borne": {"total_erreurs": 0},
        "fichiers_proteges": [],
        "dette": {},
        "type_ignore": {"a.py": 1},
        "type_ignore_lignes": {"a.py": {"cafebabe" * 8: 1}},
    }
    anomalies = mypy_gate.anomalies(
        reels={"a.py"},
        erreurs={},
        base=base,
        base_reference=None,
        occurrences={"a.py": 1},
        contenus={"a.py": {"cafebabe" * 8: 1}},
    )
    assert anomalies == []


def test_g36c_anomalies_sans_contenus_aucune_regression():
    anomalies = mypy_gate.anomalies(
        reels={"a.py"},
        erreurs={},
        base=_base(total_erreurs=0),
        base_reference=None,
    )
    assert anomalies == []


def test_g37_anomalies_reference_signale_empreinte_type_ignore_lignes_ajoutee():
    base = {
        "version": 1,
        "borne": {"total_erreurs": 0},
        "fichiers_proteges": [],
        "dette": {},
        "type_ignore": {"a.py": 1},
        "type_ignore_lignes": {"a.py": {"cafebabe" * 8: 1}},
    }
    reference = {
        "version": 1,
        "borne": {"total_erreurs": 0},
        "fichiers_proteges": [],
        "dette": {},
        "type_ignore": {"a.py": 1},
        "type_ignore_lignes": {"a.py": {"deadbeef" * 8: 1}},
    }
    anomalies = mypy_gate.anomalies(
        reels={"a.py"},
        erreurs={},
        base=base,
        base_reference=reference,
        occurrences={"a.py": 1},
        contenus={"a.py": {"cafebabe" * 8: 1}},
    )
    assert any(
        "type_ignore_lignes" in m and "a.py" in m and "augmentee" in m
        for m in anomalies
    )


def test_g37b_anomalies_reference_sans_type_ignore_lignes_retrocompatible():
    base = {
        "version": 1,
        "borne": {"total_erreurs": 0},
        "fichiers_proteges": [],
        "dette": {},
        "type_ignore": {"a.py": 1},
        "type_ignore_lignes": {"a.py": {"cafebabe" * 8: 1}},
    }
    reference = {
        "version": 1,
        "borne": {"total_erreurs": 0},
        "fichiers_proteges": [],
        "dette": {},
        "type_ignore": {"a.py": 1},
    }
    anomalies = mypy_gate.anomalies(
        reels={"a.py"},
        erreurs={},
        base=base,
        base_reference=reference,
        occurrences={"a.py": 1},
        contenus={"a.py": {"cafebabe" * 8: 1}},
    )
    assert any(
        "type_ignore_lignes" in m and "a.py" in m and "augmentee" in m
        for m in anomalies
    )


def test_g38_valider_type_ignore_lignes_rejette_valeur_qui_nest_pas_un_objet():
    with pytest.raises(ValueError):
        mypy_gate._valider_type_ignore_lignes({"a.py": ["pas-un-dict"]}, "base")


def test_g38b_valider_type_ignore_lignes_absent_retourne_dict_vide():
    assert mypy_gate._valider_type_ignore_lignes(None, "base") == {}


def test_g38c_valider_type_ignore_lignes_rejette_compte_non_positif():
    with pytest.raises(ValueError):
        mypy_gate._valider_type_ignore_lignes({"a.py": {"hashA": 0}}, "base")


# ---------------------------------------------------------------------------
# Correctif post-revue scellée #449 (round 15) — multiplicite des empreintes
# ---------------------------------------------------------------------------

def test_g39_anomalies_duplication_empreinte_deja_connue_est_detectee():
    base = {
        "version": 1,
        "borne": {"total_erreurs": 0},
        "fichiers_proteges": [],
        "dette": {},
        "type_ignore": {"a.py": 2},
        "type_ignore_lignes": {"a.py": {"hashA": 1}},
    }
    anomalies = mypy_gate.anomalies(
        reels={"a.py"},
        erreurs={},
        base=base,
        base_reference=None,
        occurrences={"a.py": 2},
        contenus={"a.py": {"hashA": 2}},
    )
    assert any("hashA" in m and "a.py" in m for m in anomalies)


# ---------------------------------------------------------------------------
# Correctif post-revue scellée #449 (round 17) — tokenize, littéraux vs commentaires
# ---------------------------------------------------------------------------

def test_g40_occurrences_type_ignore_ignore_litteral_de_chaine(tmp_path):
    chemin = tmp_path / "a.py"
    chemin.write_bytes(b'message = "# type: ignore"\n')
    assert mypy_gate.occurrences_type_ignore(tmp_path, {"a.py"}) == {}


def test_g40b_occurrences_type_ignore_detecte_toujours_vrai_commentaire(tmp_path):
    chemin = tmp_path / "a.py"
    chemin.write_bytes(b"x = 1  # type: ignore\n")
    assert mypy_gate.occurrences_type_ignore(tmp_path, {"a.py"}) == {"a.py": 1}


def test_g41_fichiers_neutralises_ignore_litteral_de_chaine(tmp_path):
    chemin = tmp_path / "a.py"
    chemin.write_bytes(b'message = "# mypy: ignore-errors"\n')
    assert mypy_gate.fichiers_neutralises(tmp_path, {"a.py"}) == set()


def test_g41b_fichiers_neutralises_detecte_toujours_vrai_commentaire(tmp_path):
    chemin = tmp_path / "a.py"
    chemin.write_bytes(b"# mypy: ignore-errors\nx = 1\n")
    assert mypy_gate.fichiers_neutralises(tmp_path, {"a.py"}) == {"a.py"}


def test_g42_contenus_type_ignore_ignore_litteral_de_chaine(tmp_path):
    chemin = tmp_path / "a.py"
    chemin.write_bytes(b'message = "# type: ignore"\n')
    assert mypy_gate.contenus_type_ignore(tmp_path, {"a.py"}) == {}


def test_g42b_contenus_type_ignore_detecte_toujours_vrai_commentaire(tmp_path):
    chemin = tmp_path / "a.py"
    chemin.write_bytes(b"x = 1  # type: ignore\n")
    attendu = hashlib.sha256(b"x = 1  # type: ignore").hexdigest()
    assert mypy_gate.contenus_type_ignore(tmp_path, {"a.py"}) == {"a.py": {attendu: 1}}


def test_g43_lignes_avec_commentaire_reel_gere_fichier_illisible(tmp_path):
    assert (
        mypy_gate._lignes_avec_commentaire_reel(
            tmp_path, "absent.py", mypy_gate._DIRECTIVE_TYPE_IGNORE
        )
        is None
    )


def test_g43b_lignes_avec_commentaire_reel_gere_syntaxe_invalide(tmp_path):
    chemin = tmp_path / "invalide.py"
    chemin.write_bytes(b"def f(:\n    pass\n")
    assert (
        mypy_gate._lignes_avec_commentaire_reel(
            tmp_path, "invalide.py", mypy_gate._DIRECTIVE_TYPE_IGNORE
        )
        is None
    )


def test_g43c_lignes_avec_commentaire_reel_encodage_non_utf8(tmp_path):
    chemin = tmp_path / "a.py"
    chemin.write_bytes(
        b"# -*- coding: latin-1 -*-\n# mypy: ignore-errors\nx = \"caf\xe9\"\n"
    )
    assert (
        mypy_gate._lignes_avec_commentaire_reel(
            tmp_path, "a.py", mypy_gate._DIRECTIVE_NEUTRALISATION
        )
        == {2}
    )
