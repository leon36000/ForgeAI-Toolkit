from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import gate_exit_codes  # noqa: E402

RACINE = Path(__file__).resolve().parents[1]
GATES = RACINE / ".github" / "workflows" / "gates.yml"


def _charger_jobs_gates() -> dict:
    yaml = pytest.importorskip("yaml", reason="pyyaml est installé par le job `tests` de la CI")
    return yaml.safe_load(GATES.read_text(encoding="utf-8"))["jobs"]


# ---------------------------------------------------------------------------
# anomalies() — logique pure
# ---------------------------------------------------------------------------

def test_anomalies_registre_coherent_retourne_vide():
    registre = {"codes_par_commande": {"cmd": [{"code": 0, "ligne": 2}]}}
    lignes_cli = ["ligne 1", "    return 0", "ligne 3"]
    assert gate_exit_codes.anomalies(registre, lignes_cli) == []


def test_anomalies_entree_en_derive_signalee():
    registre = {"codes_par_commande": {"ma_commande": [{"code": 5, "ligne": 1}]}}
    lignes_cli = ["    return 0"]
    resultat = gate_exit_codes.anomalies(registre, lignes_cli)
    assert len(resultat) == 1
    assert "ma_commande" in resultat[0]
    assert "return 5" in resultat[0]


def test_anomalies_ligne_hors_bornes():
    registre = {"codes_par_commande": {"cmd": [{"code": 1, "ligne": 10}]}}
    lignes_cli = ["a", "b"]
    resultat = gate_exit_codes.anomalies(registre, lignes_cli)
    assert len(resultat) == 1
    assert "hors bornes" in resultat[0]


def test_anomalies_ligne_ternaire_sans_return_litteral_signalee():
    """Round 1 de revue scellée (#443, 3 objections majeures) : une ligne ternaire
    (`return 0 if x else 9`) ne contient PAS la sous-chaîne littérale `return 9`
    exigée par la story — elle doit être signalée, pas acceptée."""
    registre = {"codes_par_commande": {"cmd": [{"code": 9, "ligne": 1}]}}
    lignes_cli = ["    return 0 if x else 9"]
    resultat = gate_exit_codes.anomalies(registre, lignes_cli)
    assert len(resultat) == 1


def test_anomalies_commentaire_fin_ligne_pas_anomalie():
    """Round 1 de revue scellée : `return 10  # commentaire` contient bien la
    sous-chaîne `return 10` et ne doit pas être signalé (faux négatif corrigé,
    l'ancienne implémentation `endswith()` le rejetait à tort)."""
    registre = {"codes_par_commande": {"cmd": [{"code": 10, "ligne": 1}]}}
    lignes_cli = ["    return 10  # commentaire"]
    assert gate_exit_codes.anomalies(registre, lignes_cli) == []


def test_anomalies_frontiere_mot_return_8_ne_matche_pas_return_80():
    registre = {"codes_par_commande": {"cmd": [{"code": 8, "ligne": 1}]}}
    lignes_cli = ["    return 80"]
    resultat = gate_exit_codes.anomalies(registre, lignes_cli)
    assert len(resultat) == 1


def test_anomalies_codes_par_commande_vide():
    registre = {"codes_par_commande": {}}
    assert gate_exit_codes.anomalies(registre, ["anything"]) == []


def test_anomalies_code_ou_ligne_non_entier_signalee():
    registre = {"codes_par_commande": {"cmd": [{"code": "abc", "ligne": "xyz"}]}}
    resultat = gate_exit_codes.anomalies(registre, ["    return 0"])
    assert len(resultat) == 1
    assert "invalide" in resultat[0].lower()


# ---------------------------------------------------------------------------
# charger_registre() — fichiers réels via tmp_path
# ---------------------------------------------------------------------------

def test_charger_registre_fichier_valide(tmp_path: Path):
    contenu = {"codes_par_commande": {"cmd": [{"code": 0, "ligne": 1}]}}
    chemin = tmp_path / "registre.json"
    chemin.write_text(json.dumps(contenu), encoding="utf-8")
    assert gate_exit_codes.charger_registre(chemin) == contenu


def test_charger_registre_fichier_absent(tmp_path: Path):
    chemin = tmp_path / "absent.json"
    with pytest.raises(FileNotFoundError):
        gate_exit_codes.charger_registre(chemin)


def test_charger_registre_json_invalide(tmp_path: Path):
    chemin = tmp_path / "bad.json"
    chemin.write_text("{invalide", encoding="utf-8")
    with pytest.raises(ValueError):
        gate_exit_codes.charger_registre(chemin)


# ---------------------------------------------------------------------------
# main() — intégration
# ---------------------------------------------------------------------------

def test_main_integration_reel_retourne_zero(capsys: pytest.CaptureFixture[str]):
    assert gate_exit_codes.main([]) == 0
    out = capsys.readouterr().out
    assert "OK" in out or "entrées vérifiées" in out


def test_main_integration_reel_report_retourne_zero_et_affiche_nombre(capsys: pytest.CaptureFixture[str]):
    assert gate_exit_codes.main(["--report"]) == 0
    out = capsys.readouterr().out
    assert "entrées vérifiées" in out


def test_main_report_ne_bloque_pas_meme_en_derive_simulee(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    monkeypatch.setattr(gate_exit_codes, "anomalies", lambda *a, **k: ["dérive simulée"])
    assert gate_exit_codes.main(["--report"]) == 0


def test_main_defaut_avec_derive_simulee_retourne_un(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    monkeypatch.setattr(gate_exit_codes, "anomalies", lambda *a, **k: ["dérive simulée"])
    assert gate_exit_codes.main([]) == 1
    err = capsys.readouterr().err
    assert "dérive simulée" in err


def test_main_registre_racine_liste_retourne_un(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    """Round 1 de revue scellée : un registre JSON valide mais dont la racine
    n'est pas un objet (ex. une liste `[]`) doit être rejeté proprement par
    main(), sans AttributeError non capturée."""
    monkeypatch.setattr(gate_exit_codes, "charger_registre", lambda chemin: [])
    assert gate_exit_codes.main([]) == 1
    assert "invalide" in capsys.readouterr().err.lower()


def test_main_codes_par_commande_liste_retourne_un(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    """Round 1 de revue scellée : codes_par_commande présent mais non-objet
    (liste au lieu de dict) doit être rejeté, pas traité comme 0 entrée."""
    monkeypatch.setattr(gate_exit_codes, "charger_registre", lambda chemin: {"codes_par_commande": []})
    assert gate_exit_codes.main([]) == 1
    assert "invalide" in capsys.readouterr().err.lower()


# ---------------------------------------------------------------------------
# structure .github/workflows/gates.yml
# ---------------------------------------------------------------------------

def test_job_exit_codes_existe():
    jobs = _charger_jobs_gates()
    assert "exit-codes" in jobs, "job exit-codes manquant dans gates.yml"


def test_job_exit_codes_invoque_script_sans_report():
    jobs = _charger_jobs_gates()
    job = jobs["exit-codes"]
    commandes = " ".join(str(etape.get("run", "")) for etape in job.get("steps", []))
    assert "scripts/gate_exit_codes.py" in commandes
    assert "python3 scripts/gate_exit_codes.py" in commandes
    for etape in job.get("steps", []):
        run = str(etape.get("run", ""))
        if "gate_exit_codes.py" in run:
            assert "--report" not in run, "le job exit-codes doit invoquer le gate en mode bloquant, pas --report"
            break
    else:
        pytest.fail("aucune étape n'invoque gate_exit_codes.py")


def test_agregateur_tests_needs_contient_exit_codes():
    jobs = _charger_jobs_gates()
    aggregateur = next((j for j in jobs.values() if j.get("name") == "tests"), None)
    assert aggregateur is not None, "agrégateur name: tests introuvable"
    needs = aggregateur.get("needs") or []
    assert "exit-codes" in needs, "exit-codes absent de needs: de l'agrégateur tests"
