"""Inventaire + résolveur de doublons de preuves (RC1-011, #441).

Décision d'architecture (voir stories/RC1-011.md) : manifest JSON généré + résolveur
exécutable. AUCUN ARTEFACT DE REVUE SCELLÉ existant sous `evidence/reviews/**` n'est supprimé ni
modifié — seul un nouveau manifest sous `evidence/dedup/` est produit (`evidence/reviews/
BINDING.txt`, l'index d'ancrage append-only du gate `reviews-sealed`, reçoit lui une nouvelle
ligne par story scellée — motif standard de ce dépôt, sans rapport avec les artefacts eux-mêmes).
Le "canonique" d'un groupe est le chemin minimal en
ordre POSIX (convention purement déterministe, sans prétention d'antériorité). Les groupes
composés à 100% de fichiers `*.verdict.json` reçoivent la classe `attestation-verdict` et ne
sont JAMAIS dédupliqués (canonique=None, résolution = identité) — l'exception "quasi-doublons
sémantiques non fusionnés" de l'issue #441 est ainsi appliquée par du code, pas par une
convention non testée.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location(
    "evidence_dedup", REPO / "scripts" / "governance" / "evidence_dedup.py"
)
evidence_dedup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evidence_dedup)


def _ecrire(racine: Path, chemin_relatif: str, contenu: str) -> Path:
    cible = racine / chemin_relatif
    cible.parent.mkdir(parents=True, exist_ok=True)
    cible.write_text(contenu, encoding="utf-8")
    return cible


# ---------------------------------------------------------------------------
# empreinte() / inventaire()
# ---------------------------------------------------------------------------

def test_empreinte_deterministe_et_correcte(tmp_path):
    f = _ecrire(tmp_path, "a.txt", "contenu-test")
    attendu = hashlib.sha256(b"contenu-test").hexdigest()
    premier_appel = evidence_dedup.empreinte(f)
    second_appel = evidence_dedup.empreinte(f)  # 2e appel indépendant, même fichier
    assert premier_appel == attendu
    assert second_appel == attendu
    assert premier_appel == second_appel  # déterministe : 2 appels, même résultat


def test_inventaire_utilise_rglob_pas_git(tmp_path, monkeypatch):
    # Doit fonctionner SANS .git (extraction dans un clone propre) — aucun appel subprocess/git.
    import subprocess
    def _echoue_si_appele(*a, **k):
        raise AssertionError("inventaire() ne doit JAMAIS invoquer git/subprocess")
    monkeypatch.setattr(subprocess, "run", _echoue_si_appele)
    monkeypatch.setattr(subprocess, "Popen", _echoue_si_appele)

    _ecrire(tmp_path, "a.txt", "x")
    _ecrire(tmp_path, "sous/b.txt", "y")
    inv = evidence_dedup.inventaire(tmp_path)
    assert set(inv.keys()) == {"a.txt", "sous/b.txt"}


def test_inventaire_exclut_evidence_dedup_lui_meme(tmp_path):
    _ecrire(tmp_path, "a.txt", "x")
    _ecrire(tmp_path, "dedup/manifest-avant.json", "{}")
    inv = evidence_dedup.inventaire(tmp_path, exclure=("dedup/",))
    assert "a.txt" in inv
    assert "dedup/manifest-avant.json" not in inv


# ---------------------------------------------------------------------------
# grouper() / classifier() — logique de dédup
# ---------------------------------------------------------------------------

def test_grouper_ignore_les_fichiers_sans_doublon(tmp_path):
    _ecrire(tmp_path, "a.txt", "unique-a")
    _ecrire(tmp_path, "b.txt", "unique-b")
    inv = evidence_dedup.inventaire(tmp_path)
    groupes = evidence_dedup.grouper(inv)
    assert groupes == []


def test_grouper_detecte_un_groupe_de_2():
    inv = {"z/GREEN-focused.txt": "aaa", "z/evidence/GREEN.txt": "aaa", "autre.txt": "bbb"}
    groupes = evidence_dedup.grouper(inv)
    assert len(groupes) == 1
    assert groupes[0]["sha256"] == "aaa"
    assert set(groupes[0]["membres"]) == {"z/GREEN-focused.txt", "z/evidence/GREEN.txt"}


def test_canonique_est_le_min_posix_deterministe():
    membres = ["z/evidence/GREEN.txt", "z/GREEN-focused.txt", "a/x.txt"]
    assert evidence_dedup.canonique(membres) == "a/x.txt"


def test_classifier_groupe_ordinaire_duplique_avec_canonique():
    groupe = {"sha256": "aaa", "membres": ["b/x.txt", "a/x.txt"]}
    classe, can = evidence_dedup.classifier(groupe)
    assert classe == "duplique"
    assert can == "a/x.txt"


def test_classifier_groupe_100pct_verdicts_est_attestation_sans_canonique():
    groupe = {
        "sha256": "aaa",
        "membres": [
            "evidence/reviews/plan-v1.0/round-2/glm.verdict.json",
            "evidence/reviews/plan-v1.0/round-2/kimi.verdict.json",
        ],
    }
    classe, can = evidence_dedup.classifier(groupe)
    assert classe == "attestation-verdict"
    assert can is None


def test_classifier_groupe_mixte_verdict_et_autre_reste_duplique():
    # Un groupe où SEULS certains membres sont des verdicts (mélange) n'est PAS une attestation
    # — la règle protège les verdicts, elle ne doit pas sur-protéger un doublon ordinaire qui se
    # trouve juste avoir un nom contenant "verdict" par coïncidence dans un mélange.
    groupe = {"sha256": "aaa", "membres": ["a/x.verdict.json", "b/x.txt"]}
    classe, can = evidence_dedup.classifier(groupe)
    assert classe == "duplique"
    assert can == "a/x.verdict.json"


# ---------------------------------------------------------------------------
# resoudre() — 5 cas (critère "test de résolution d'une référence vers l'objet canonique")
# ---------------------------------------------------------------------------

def _manifest_test():
    return {
        "schema": "evidence-dedup/1",
        "groupes": [
            {
                "sha256": "aaa",
                "classe": "duplique",
                "canonique": "a/x.txt",
                "repliques": ["b/x.txt"],
            },
            {
                "sha256": "bbb",
                "classe": "attestation-verdict",
                "canonique": None,
                "repliques": [
                    "evidence/reviews/r/glm.verdict.json",
                    "evidence/reviews/r/kimi.verdict.json",
                ],
            },
        ],
    }


def test_resoudre_replique_vers_canonique():
    assert evidence_dedup.resoudre(_manifest_test(), "b/x.txt") == "a/x.txt"


def test_resoudre_canonique_vers_lui_meme_idempotent():
    assert evidence_dedup.resoudre(_manifest_test(), "a/x.txt") == "a/x.txt"


def test_resoudre_chemin_hors_groupe_vers_lui_meme():
    assert evidence_dedup.resoudre(_manifest_test(), "hors/groupe.txt") == "hors/groupe.txt"


def test_resoudre_attestation_verdict_vers_lui_meme_jamais_dereference():
    m = _manifest_test()
    assert evidence_dedup.resoudre(m, "evidence/reviews/r/glm.verdict.json") == (
        "evidence/reviews/r/glm.verdict.json"
    )
    assert evidence_dedup.resoudre(m, "evidence/reviews/r/kimi.verdict.json") == (
        "evidence/reviews/r/kimi.verdict.json"
    )


def test_resoudre_manifest_committe_canonique_existe_et_sha_concorde():
    # Les chemins déclarés dans le manifest sont relatifs à SA racine de scan (evidence/, pas la
    # racine du dépôt — voir construire_manifest(racine="evidence", ...)). Assertion dure (pas de
    # skip) : evidence/dedup/manifest-apres.json est un livrable COMMITTÉ de cette story, son
    # absence est un vrai échec (régression), pas un état intermédiaire à tolérer.
    manifest_path = REPO / "evidence" / "dedup" / "manifest-apres.json"
    assert manifest_path.is_file(), "evidence/dedup/manifest-apres.json absent — livrable manquant"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    racine_scan = REPO / "evidence"
    for groupe in manifest["groupes"]:
        if groupe["classe"] == "attestation-verdict":
            # canonique=None par construction (jamais dédupliqué) : pas de vérification
            # canonique/repliques, mais CHAQUE membre doit quand même exister sur disque avec
            # le sha256 déclaré du groupe — sinon un verdict corrompu/déplacé ne serait détecté
            # par aucune assertion de ce test.
            assert groupe["canonique"] is None
            for membre in groupe["repliques"]:
                chemin_membre = racine_scan / membre
                assert chemin_membre.is_file(), f"membre attestation-verdict absent du disque : {membre}"
                assert evidence_dedup.empreinte(chemin_membre) == groupe["sha256"]
            continue
        chemin_can = racine_scan / groupe["canonique"]
        assert chemin_can.is_file(), f"canonique absent du disque : {groupe['canonique']}"
        sha_can = evidence_dedup.empreinte(chemin_can)
        assert sha_can == groupe["sha256"]
        for replique in groupe["repliques"]:
            chemin_rep = racine_scan / replique
            assert chemin_rep.is_file(), f"réplique absente du disque : {replique}"
            assert evidence_dedup.empreinte(chemin_rep) == groupe["sha256"]


# ---------------------------------------------------------------------------
# construire_manifest() / cliquet avant==après
# ---------------------------------------------------------------------------

def test_construire_manifest_schema_et_champs(tmp_path):
    _ecrire(tmp_path, "a.txt", "same")
    _ecrire(tmp_path, "b.txt", "same")
    manifest = evidence_dedup.construire_manifest(tmp_path, phase="avant")
    assert manifest["schema"] == "evidence-dedup/1"
    assert manifest["phase"] == "avant"
    assert manifest["fichiers_total"] == 2
    assert len(manifest["groupes"]) == 1
    assert "inventaire_sha256" in manifest


def test_inventaire_sha256_stable_pour_le_meme_contenu(tmp_path):
    _ecrire(tmp_path, "a.txt", "same")
    _ecrire(tmp_path, "b.txt", "same")
    m1 = evidence_dedup.construire_manifest(tmp_path, phase="avant")
    m2 = evidence_dedup.construire_manifest(tmp_path, phase="apres")
    assert m1["inventaire_sha256"] == m2["inventaire_sha256"]


def test_avant_apres_committes_ont_le_meme_inventaire_sha256():
    # Preuve mécanique du critère "aucun changement de contenu non documenté" : si les deux
    # manifests committés divergent sur inventaire_sha256, un fichier a changé entre les deux
    # générations -- ce test l'attraperait. Assertion dure (pas de skip) : les deux manifests
    # sont des livrables COMMITTÉS de cette story.
    avant_path = REPO / "evidence" / "dedup" / "manifest-avant.json"
    apres_path = REPO / "evidence" / "dedup" / "manifest-apres.json"
    assert avant_path.is_file(), "manifest-avant.json absent — livrable manquant"
    assert apres_path.is_file(), "manifest-apres.json absent — livrable manquant"
    avant = json.loads(avant_path.read_text(encoding="utf-8"))
    apres = json.loads(apres_path.read_text(encoding="utf-8"))
    assert avant["inventaire_sha256"] == apres["inventaire_sha256"]


def test_manifest_committe_sans_derive_de_GROUPES_vs_inventaire_live():
    # Portée DÉLIBÉRÉMENT restreinte aux GROUPES de doublons (pas fichiers_total/inventaire_sha256
    # complets) : la story documente explicitement que le compte de fichiers sous evidence/ varie
    # à chaque rebase (autres PR mergées en parallèle) SANS que ce soit une dérive de dédup — un
    # nouveau fichier UNIQUE ajouté ne doit PAS faire échouer ce test. Ce qui DOIT rester stable
    # entre deux runs, et que ce test protège : la composition exacte des groupes de fichiers
    # BYTE-IDENTIQUES (nouveau doublon apparu, doublon existant disparu/modifié, changement de
    # canonique/repliques) — c'est la seule dérive qui invaliderait la déclaration
    # canonique/repliques du manifest committé, donc la seule pertinente pour resoudre(). Un
    # nouveau fichier unique fait légitimement diverger fichiers_total/inventaire_sha256 SANS
    # dérive de dédup ; ce n'est pas le périmètre de ce test (voir
    # test_avant_apres_committes_ont_le_meme_inventaire_sha256 pour la stabilité entre les 2
    # PASSES avant/après, un contrat différent : même instant, deux exécutions).
    # Comme pour le cliquet KNOWN_INVALID de tests/test_rc1011_packs_md.py, ce test attend une
    # régénération du manifest (mécanique, `evidence_dedup.py --racine evidence --phase apres
    # --sortie ...`) quand un doublon apparaît/disparaît réellement — maintenance normale.
    apres_path = REPO / "evidence" / "dedup" / "manifest-apres.json"
    assert apres_path.is_file(), "evidence/dedup/manifest-apres.json absent — livrable manquant"
    committe = json.loads(apres_path.read_text(encoding="utf-8"))
    frais = evidence_dedup.construire_manifest(REPO / "evidence", phase="apres")
    assert frais["groupes"] == committe["groupes"], (
        "le manifest committé a dérivé de l'inventaire live sous evidence/ — régénérer "
        "evidence/dedup/manifest-avant.json et manifest-apres.json"
    )


# ---------------------------------------------------------------------------
# main() — CLI (couvre aussi la validation des chemins construits en CLI avant
# accès disque : --sortie/--verifier sont résolus + vérifiés avant lecture/écriture)
# ---------------------------------------------------------------------------

def test_main_phase_ecrit_un_manifest_valide(tmp_path, monkeypatch):
    _ecrire(tmp_path, "a.txt", "x")
    sortie = tmp_path / "sortie" / "manifest.json"
    sortie.parent.mkdir()
    monkeypatch.setattr(
        sys, "argv",
        ["evidence_dedup.py", "--racine", str(tmp_path), "--phase", "avant", "--sortie", str(sortie)],
    )
    rc = evidence_dedup.main()
    assert rc == 0
    manifest = json.loads(sortie.read_text(encoding="utf-8"))
    assert manifest["schema"] == "evidence-dedup/1"
    assert manifest["phase"] == "avant"


def test_main_phase_sortie_parent_introuvable_retourne_2(tmp_path, monkeypatch, capsys):
    _ecrire(tmp_path, "a.txt", "x")
    sortie = tmp_path / "dossier-absent" / "manifest.json"
    monkeypatch.setattr(
        sys, "argv",
        ["evidence_dedup.py", "--racine", str(tmp_path), "--phase", "avant", "--sortie", str(sortie)],
    )
    rc = evidence_dedup.main()
    assert rc == 2
    assert "répertoire parent introuvable" in capsys.readouterr().err


def test_main_resoudre_avec_verifier_imprime_le_canonique(tmp_path, monkeypatch, capsys):
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(_manifest_test()), encoding="utf-8")
    monkeypatch.setattr(
        sys, "argv",
        ["evidence_dedup.py", "--resoudre", "b/x.txt", "--verifier", str(manifest_path)],
    )
    rc = evidence_dedup.main()
    assert rc == 0
    assert capsys.readouterr().out.strip() == "a/x.txt"


def test_main_resoudre_sans_verifier_retourne_2(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["evidence_dedup.py", "--resoudre", "b/x.txt"])
    rc = evidence_dedup.main()
    assert rc == 2
    assert "--verifier" in capsys.readouterr().err


def test_main_resoudre_verifier_fichier_introuvable_retourne_2(tmp_path, monkeypatch, capsys):
    absent = tmp_path / "absent.json"
    monkeypatch.setattr(
        sys, "argv",
        ["evidence_dedup.py", "--resoudre", "b/x.txt", "--verifier", str(absent)],
    )
    rc = evidence_dedup.main()
    assert rc == 2
    assert "fichier introuvable" in capsys.readouterr().err


def test_main_sans_option_affiche_l_aide_et_retourne_2(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["evidence_dedup.py"])
    rc = evidence_dedup.main()
    assert rc == 2
