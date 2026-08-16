from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import mypy_gate  # noqa: E402


def _base(dette=None, fichiers_proteges=None, total_erreurs=0, version=1):
    """Fabrique une base valide pour les tests."""
    return {
        "version": version,
        "borne": {"total_erreurs": total_erreurs},
        "fichiers_proteges": list(fichiers_proteges or []),
        "dette": dict(dette or {}),
    }


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

    base_reference, message = mypy_gate._charger_base_reference_git(
        tmp_path, chemin_base, "origin/main"
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
