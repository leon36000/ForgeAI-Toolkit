"""DOC-032 — le gate qui rend la dérive documentaire détectable.

Mesure ayant motivé ce gate : **5 sous-commandes documentées sur 21**. Le défaut n'était pas que
la documentation MENTE (aucune commande fantôme n'y était citée) mais qu'elle OMETTE — ce qui
échappe à toute relecture, puisqu'il n'y a rien à contredire. Seul un contrôle automatique peut
voir une absence.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import gate_docs  # noqa: E402

RACINE = Path(__file__).resolve().parents[1]
CLI = RACINE / "src" / "forgeai" / "cli.py"
GATES = RACINE / ".github" / "workflows" / "gates.yml"
BASE = RACINE / "Docs" / "BASELINE-CLI-DOC.json"
REFERENCE_CLI = RACINE / "Docs" / "reference" / "cli.md"


def _base(commandes, borne):
    return {"version": 1, "commandes": list(commandes), "borne": {"nombre_commandes": borne}}


def test_g7_la_source_de_verite_est_la_cli_pas_une_liste_recopiee(tmp_path):
    """CA1 — ajouter une commande à `cli.py` la fait entrer dans le périmètre du gate sans
    toucher au gate. Une liste recopiée en dur dériverait exactement comme la doc qu'elle
    prétend contrôler."""
    faux = tmp_path / "cli.py"
    faux.write_text(
        "import argparse\n"
        "parser = argparse.ArgumentParser()\n"
        "sub = parser.add_subparsers(dest='cmd')\n"
        "sub.add_parser('alpha')\n"
        "sub.add_parser('beta')\n",
        encoding="utf-8",
    )
    assert gate_docs.sous_commandes(faux) == ["alpha", "beta"]


def test_g7b_seules_les_commandes_de_premier_niveau_comptent(tmp_path):
    """CA1 — les sous-commandes IMBRIQUÉES sont exclues.

    La documentation est repérée par la chaîne « forgeai <cmd> », qui ne peut par construction
    jamais correspondre à `forgeai node prepare`. Les compter produirait des anomalies
    systématiques et indéfendables — 42 commandes au lieu de 21 sur ce dépôt.
    """
    faux = tmp_path / "cli.py"
    faux.write_text(
        "import argparse\n"
        "parser = argparse.ArgumentParser()\n"
        "sub = parser.add_subparsers(dest='cmd')\n"
        "p_node = sub.add_parser('node')\n"
        "node_sub = p_node.add_subparsers(dest='node_cmd')\n"
        "node_sub.add_parser('prepare')\n",
        encoding="utf-8",
    )
    assert gate_docs.sous_commandes(faux) == ["node"], "« prepare » est imbriquée, pas top-level"


def test_g7c_structure_cli_inconnue_refuse_de_conclure(tmp_path):
    """CA1 — si la CLI ne présente aucun `add_subparsers`, le gate ne peut pas conclure : il
    doit lever, jamais renvoyer une liste vide qui vaudrait « rien à vérifier »."""
    faux = tmp_path / "cli.py"
    faux.write_text("x = 1\n", encoding="utf-8")
    with pytest.raises(ValueError):
        gate_docs.sous_commandes(faux)


def test_g1_commande_ni_documentee_ni_baselinee_rougit():
    """CA1 — la règle de base."""
    messages = gate_docs.anomalies(
        reelles=["alpha", "beta"], documentees={"alpha"},
        base=_base([], 2), base_reference=None,
    )
    assert any("beta" in m for m in messages)


def test_g2_une_commande_nouvelle_ne_peut_pas_etre_baselinee():
    """CA2 — LA propriété qui rend le cliquet non contournable.

    Détecteur d'un défaut réel : la borne était initialement imbriquée dans le bloc
    `base_reference`, donc muette sans `--base-ref-git`. Il suffisait alors d'ajouter la commande
    à la base pour faire passer la PR — exactement le contournement que la borne existe pour
    fermer. La borne est autoportante : elle ne doit dépendre d'aucun argument optionnel.
    """
    messages = gate_docs.anomalies(
        reelles=["alpha", "beta", "gamma"], documentees={"alpha"},
        base=_base(["beta", "gamma"], 2),  # borne figée à 2, la CLI en compte 3
        base_reference=None,               # AUCUNE référence git : la borne doit mordre quand même
    )
    assert messages, "élargir la base au-delà de la borne DOIT échouer, même sans référence git"
    assert any("born" in m.lower() for m in messages)


def test_g3_la_base_ne_peut_pas_croitre():
    """CA2 — cliquet : en retirer est autorisé, en ajouter non."""
    croissance = gate_docs.anomalies(
        reelles=["a", "b"], documentees=set(),
        base=_base(["a", "b"], 2), base_reference=_base(["a"], 2),
    )
    assert any("reference" in m for m in croissance)

    reduction = gate_docs.anomalies(
        reelles=["a", "b"], documentees={"b"},
        base=_base(["a"], 2), base_reference=_base(["a", "b"], 2),
    )
    assert reduction == [], f"retirer de la base doit être autorisé : {reduction}"


def test_g4_entree_perimee_refusee():
    """CA2 — sans cette règle, la base deviendrait une couverture générale."""
    supprimee = gate_docs.anomalies(
        reelles=["a"], documentees=set(), base=_base(["a", "disparue"], 2), base_reference=None,
    )
    assert any("disparue" in m for m in supprimee)

    documentee = gate_docs.anomalies(
        reelles=["a"], documentees={"a"}, base=_base(["a"], 2), base_reference=None,
    )
    assert any("documentee" in m for m in documentee), (
        "une commande désormais documentée doit sortir de la base"
    )


def test_g5_le_gate_est_reellement_invoque_par_la_ci():
    """CA1 — un gate parfaitement testé mais absent de la CI est vert partout et sans effet."""
    yaml = pytest.importorskip("yaml")
    jobs = yaml.safe_load(GATES.read_text(encoding="utf-8"))["jobs"]
    assert "docs" in jobs, "le job `docs` doit exister"

    etapes = jobs["docs"]["steps"]
    commandes = " ".join(e.get("run", "") for e in etapes)
    assert "gate_docs.py" in commandes
    assert "--base-ref-git" in commandes, (
        "sans référence git, le contrôle de non-croissance de la base est inapplicable"
    )
    checkout = [e for e in etapes if str(e.get("uses", "")).startswith("actions/checkout")]
    assert checkout and checkout[0].get("with", {}).get("fetch-depth") == 0


def test_g6_la_surface_livree_par_la_lane_est_documentee():
    """CA3 — `status`, `logs` et `diagnostic` ont été livrés puis laissés sans documentation ;
    ce test échoue si la section disparaît."""
    texte = REFERENCE_CLI.read_text(encoding="utf-8")
    for commande in ("status", "logs", "diagnostic"):
        assert f"forgeai {commande}" in texte, f"`forgeai {commande}` doit être documentée"


def test_g8_le_depot_reel_passe_le_gate():
    """CA1/CA4 — le gate doit être vert sur l'état livré, sinon il serait désactivé."""
    resultat = subprocess.run(
        [sys.executable, str(RACINE / "scripts" / "gate_docs.py"), "--base", str(BASE)],
        capture_output=True, text=True, cwd=RACINE,
    )
    assert resultat.returncode == 0, f"le gate doit passer sur le dépôt réel :\n{resultat.stdout}"


def test_g9_la_base_du_depot_est_coherente_avec_la_cli():
    """CA2 — la base versionnée doit correspondre à la mesure, sinon elle ment déjà."""
    base = json.loads(BASE.read_text(encoding="utf-8"))
    reelles = set(gate_docs.sous_commandes(CLI))

    assert base["borne"]["nombre_commandes"] == len(reelles), (
        "la borne doit refléter le nombre réel de sous-commandes au moment du gel"
    )
    assert set(base["commandes"]) <= reelles, "la base ne peut pas citer une commande inexistante"


def test_g10_reference_git_inaccessible_echoue_durement(tmp_path):
    """CA2 — « je ne peux pas voir » ne vaut jamais « tout va bien »."""
    resultat = subprocess.run(
        [sys.executable, str(RACINE / "scripts" / "gate_docs.py"),
         "--base", str(BASE), "--base-ref-git", "refs/absente"],
        capture_output=True, text=True, cwd=RACINE,
    )
    assert resultat.returncode != 0
    assert "fetch-depth" in (resultat.stdout + resultat.stderr)


# ---------------------------------------------------------------------------
# Branches de refus et point d'entrée. Un gate dont la moitié du code n'est jamais
# exécutée par les tests peut échouer en production sur le premier cas inhabituel :
# ce sont précisément les chemins d'ERREUR qui décident s'il est fail-closed.
# ---------------------------------------------------------------------------


def test_g11_base_illisible_ou_malformee_est_un_echec_dur(tmp_path):
    """CA2 — une base absente, illisible ou de forme invalide ne doit JAMAIS valoir
    « aucune anomalie » : c'est le fail-open le plus facile à introduire."""
    for mauvaise in (
        None,
        [],
        {"commandes": ["a"]},                                   # borne manquante
        {"borne": {"nombre_commandes": 1}},                      # commandes manquantes
        {"commandes": "pas une liste", "borne": {"nombre_commandes": 1}},
        {"commandes": ["a"], "borne": {"nombre_commandes": "x"}},
    ):
        with pytest.raises((ValueError, TypeError, KeyError)):
            gate_docs.anomalies(reelles=["a"], documentees=set(),
                                base=mauvaise, base_reference=None)


def test_g12_cli_absente_ou_invalide_leve(tmp_path):
    """CA1 — un fichier CLI introuvable ou syntaxiquement cassé ne peut pas produire
    « 0 sous-commande, tout va bien »."""
    with pytest.raises(ValueError):
        gate_docs.sous_commandes(tmp_path / "inexistant.py")

    casse = tmp_path / "casse.py"
    casse.write_text("def (:\n", encoding="utf-8")
    with pytest.raises(ValueError):
        gate_docs.sous_commandes(casse)


def test_g13_commandes_documentees_lit_bien_l_arborescence(tmp_path):
    """CA1 — la détection doit balayer README/AGENTS/MASTER-PLAN/CLAUDE et Docs/ + CANON/."""
    (tmp_path / "src" / "forgeai").mkdir(parents=True)
    (tmp_path / "src" / "forgeai" / "cli.py").write_text(
        "import argparse\n"
        "parser = argparse.ArgumentParser()\n"
        "sub = parser.add_subparsers(dest='cmd')\n"
        "sub.add_parser('alpha')\nsub.add_parser('beta')\nsub.add_parser('gamma')\n",
        encoding="utf-8",
    )
    (tmp_path / "Docs").mkdir()
    (tmp_path / "README.md").write_text("Utiliser `forgeai alpha` pour démarrer.", encoding="utf-8")
    (tmp_path / "Docs" / "guide.md").write_text("Puis `forgeai beta`.", encoding="utf-8")

    trouvees = gate_docs.commandes_documentees(tmp_path)
    assert "alpha" in trouvees and "beta" in trouvees
    assert "gamma" not in trouvees


def test_g14_main_retourne_1_sur_anomalie_et_0_sinon(tmp_path, monkeypatch, capsys):
    """CA1 — le code de RETOUR est ce que la CI regarde : il doit suivre les anomalies."""
    (tmp_path / "src" / "forgeai").mkdir(parents=True)
    (tmp_path / "src" / "forgeai" / "cli.py").write_text(
        "import argparse\n"
        "parser = argparse.ArgumentParser()\n"
        "sub = parser.add_subparsers(dest='cmd')\n"
        "sub.add_parser('alpha')\n",
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text("rien", encoding="utf-8")
    base = tmp_path / "base.json"

    base.write_text(json.dumps(_base([], 1)), encoding="utf-8")
    assert gate_docs.main(["--racine", str(tmp_path), "--base", str(base)]) == 1

    base.write_text(json.dumps(_base(["alpha"], 1)), encoding="utf-8")
    assert gate_docs.main(["--racine", str(tmp_path), "--base", str(base)]) == 0


def test_g15_main_echoue_si_la_base_est_absente(tmp_path):
    """CA2 — un chemin de base explicitement demandé et introuvable est une erreur, pas un vide."""
    (tmp_path / "src" / "forgeai").mkdir(parents=True)
    (tmp_path / "src" / "forgeai" / "cli.py").write_text(
        "import argparse\nparser = argparse.ArgumentParser()\n"
        "sub = parser.add_subparsers(dest='cmd')\nsub.add_parser('alpha')\n",
        encoding="utf-8",
    )
    assert gate_docs.main(["--racine", str(tmp_path),
                           "--base", str(tmp_path / "absente.json")]) != 0


# --- SonarCloud pythonsecurity:S8705 (New Code, issue #385) ----------------------------------
# `--base-ref-git` est injecte tel quel dans un argv `git`. Un ref commencant par "-" serait
# interprete comme une OPTION git (injection d'argument) plutot qu'un nom de reference.
# _valider_ref_git() doit refuser AVANT tout subprocess.run.

def test_valider_ref_git_refuse_prefixe_tiret():
    with pytest.raises(ValueError, match="reference git invalide"):
        gate_docs._valider_ref_git("--upload-pack=/bin/evil")


def test_valider_ref_git_refuse_vide():
    with pytest.raises(ValueError, match="reference git invalide"):
        gate_docs._valider_ref_git("")


def test_valider_ref_git_accepte_ref_normal():
    gate_docs._valider_ref_git("origin/main")  # ne doit pas lever


def test_charger_base_reference_git_refuse_avant_tout_subprocess(tmp_path, monkeypatch):
    """Isole la garde : un ref malveillant ne doit JAMAIS atteindre subprocess.run."""
    def _boom(*args, **kwargs):
        raise AssertionError(
            "subprocess.run() ne doit jamais etre appele pour un ref refuse par la garde amont"
        )
    # RC1-019 (#449) : le subprocess.run() réel vit désormais dans gate_git_ref (module partagé
    # avec mypy_gate.py) — gate_docs._charger_base_reference_git y délègue entièrement, plus
    # aucun subprocess.run n'est atteignable via gate_docs.subprocess lui-même.
    monkeypatch.setattr(gate_docs.gate_git_ref.subprocess, "run", _boom)
    with pytest.raises(ValueError, match="reference git invalide"):
        gate_docs._charger_base_reference_git(tmp_path, tmp_path / "base.json", "--evil=1")
