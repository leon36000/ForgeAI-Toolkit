"""REG-029B — ancrage des registres : détection de rollback, troncature et réécriture.

`verify()` prouve l'INTÉGRITÉ de la chaîne. Elle ne peut pas prouver qu'il ne MANQUE rien : une
chaîne tronquée reste parfaitement valide. Chaque test ci-dessous construit donc un vrai registre
via `append()` puis mesure les DEUX contrôles, pour que la démonstration porte sur l'écart entre
eux — et non sur des données fabriquées à la main qui vaudraient pour un chemin inexistant.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from forgeai.core.registre import append, verify
from forgeai.core.registre_ancrage import (
    anomalies_ancrage,
    anomalies_base,
    anomalies_seq,
    checkpoint_de,
    prefixe_conserve,
    verifier_ancres,
)

GATES = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "gates.yml"


def _registre(tmp_path: Path, nombre: int = 5) -> Path:
    """Construit un VRAI registre chaîné via l'API de production."""
    chemin = tmp_path / "mission.jsonl"
    for i in range(nombre):
        append(chemin, "story_complete", "test", {"story": f"S-{i}"})
    return chemin


def _entrees(chemin: Path) -> list[dict]:
    return [json.loads(l) for l in chemin.read_text(encoding="utf-8").splitlines() if l.strip()]


def test_g1_troncature_de_queue_verify_dit_oui_ancrage_dit_non(tmp_path):
    """CA3 — le test rouge exigé par l'ADR (lignes 235-237).

    C'est LA démonstration de la story : après troncature, `verify()` renvoie succès. Si ce test
    n'affirmait que l'échec de l'ancrage, il ne prouverait pas que le contrôle AJOUTE quelque
    chose — d'où la double assertion.
    """
    chemin = _registre(tmp_path, 5)
    reference = _entrees(chemin)

    chemin.write_text("\n".join(json.dumps(e) for e in reference[:3]) + "\n", encoding="utf-8")
    courant = _entrees(chemin)

    assert verify(chemin) is None, (
        "PRÉCONDITION de la story : une chaîne tronquée reste valide pour verify() — "
        "si cette assertion tombe, la story n'a plus de raison d'être"
    )
    message = prefixe_conserve(reference, courant)
    assert message is not None, "la troncature doit être détectée"
    assert "troncature" in message.lower()


def test_g2_reecriture_totale_coherente(tmp_path):
    """CA3 — chaîne entièrement reconstruite : `verify()` succès, ancrage échec.

    C'est le cas dénoncé par l'ADR §2.3 : « verify retourne succès sur une chaîne entièrement
    réécrite de façon cohérente ».
    """
    chemin = _registre(tmp_path, 4)
    reference = _entrees(chemin)

    chemin.unlink()
    for i in range(4):
        append(chemin, "story_complete", "attaquant", {"story": f"FAUX-{i}"})
    courant = _entrees(chemin)

    assert verify(chemin) is None, "la chaîne réécrite est cohérente, donc valide"
    assert len(courant) == len(reference), "même longueur : seul le contenu diffère"
    message = prefixe_conserve(reference, courant)
    assert message is not None, "une réécriture totale doit être détectée"
    assert "divergence" in message.lower()


def test_g3_avance_legitime_acceptee(tmp_path):
    """CA3 — appender après la référence reste valide, sinon le contrôle interdirait le
    fonctionnement normal du dépôt."""
    chemin = _registre(tmp_path, 3)
    reference = _entrees(chemin)
    append(chemin, "tdad_green", "test", {"story": "S-nouveau"})

    assert prefixe_conserve(reference, _entrees(chemin)) is None


def test_g4_registre_supprime_est_un_rouge(tmp_path):
    """CA4 — ferme le fail-open MESURÉ : un fichier absent n'est plus énuméré par le glob, donc
    n'est examiné par personne. Mesuré sur l'existant : `registre.py verify <absent>` imprime
    « OK, 0 entrées, chaîne intègre » et sort 0.

    Le contrôle itère donc sur l'UNION référence ∪ courant, jamais sur le seul disque.
    """
    reference = {"mission.jsonl": [{"seq": 1, "hash": "h1"}, {"seq": 2, "hash": "h2"}]}
    courant: dict[str, list[dict]] = {}

    messages = anomalies_ancrage(reference, courant)
    assert messages, "un registre entièrement supprimé DOIT être signalé"
    assert any("supprim" in m for m in messages)


def test_g5_registre_absent_de_la_reference_est_un_nouveau_legitime():
    """CA4 — sans cette règle, la PR REG-029B, qui crée son propre PATCH-REG-029B.jsonl,
    échouerait à son propre gate."""
    reference: dict[str, list[dict]] = {}
    courant = {"PATCH-REG-029B.jsonl": [{"seq": 1, "hash": "neuf"}]}

    assert anomalies_ancrage(reference, courant) == []


def test_g5b_union_ne_masque_pas_une_suppression_derriere_un_ajout():
    """CA4 — détecteur d'une itération naïve : un ajout ne doit pas « compenser » une suppression.

    Une implémentation qui compterait les registres, ou qui itérerait sur `courant` seul, passerait
    ce cas en silence puisque le total reste identique.
    """
    reference = {"parti.jsonl": [{"seq": 1, "hash": "a"}]}
    courant = {"neuf.jsonl": [{"seq": 1, "hash": "b"}]}

    messages = anomalies_ancrage(reference, courant)
    assert any("parti.jsonl" in m and "supprim" in m for m in messages)


def test_g6_seq_trou_doublon_recul_detectes():
    """CA2 — contrôle de cohérence des `seq`.

    PORTÉE HONNÊTE, vérifiée par le dernier bloc : ce contrôle n'apporte PAS l'anti-rollback.
    Tronquer puis ré-appender laisse les `seq` parfaitement contigus. Il attrape l'édition
    manuelle et une divergence d'un second écrivain du format.
    """
    assert anomalies_seq([{"seq": 1}, {"seq": 2}, {"seq": 3}]) == []
    assert anomalies_seq([{"seq": 1}, {"seq": 3}]), "un trou doit être détecté"
    assert anomalies_seq([{"seq": 1}, {"seq": 1}]), "un doublon doit être détecté"
    assert anomalies_seq([{"seq": 2}, {"seq": 1}]), "un recul doit être détecté"
    assert anomalies_seq([{"seq": 2}]), "un départ ailleurs qu'à 1 doit être détecté"

    tronque_puis_reappende = [{"seq": 1}, {"seq": 2}, {"seq": 3}]
    assert anomalies_seq(tronque_puis_reappende) == [], (
        "portée honnête : des `seq` contigus ne prouvent RIEN sur le rollback — "
        "c'est prefixe_conserve qui porte cette garantie, pas ce contrôle"
    )


def test_g7_checkpoint_refuse_un_registre_vide():
    """CA4 — un checkpoint « de rien » vaudrait ancrage de rien : c'est un fail-open."""
    with pytest.raises(ValueError):
        checkpoint_de([], "mission.jsonl")


def test_g8_ancre_malformee_est_une_anomalie_dure():
    """CA4 — une ancre illisible ne doit jamais être ignorée par un `continue` silencieux."""
    registres = {"mission.jsonl": [{"seq": 1, "hash": "h1"}]}

    assert verifier_ancres([{"registre": "mission.jsonl"}], registres), "champs manquants"
    assert verifier_ancres(["pas un dict"], registres), "type invalide"

    ancre = {"registre": "absent.jsonl", "seq": 1, "hash_ancre": "h", "entrees": 1}
    assert verifier_ancres([ancre], registres), "un registre ancré mais absent doit être signalé"


def test_g9_la_base_de_reference_est_bornee(tmp_path):
    """CA5 — la propriété qui rend « il suffit d'élargir la base » impossible pour l'avenir.

    Une anomalie à `seq` supérieur à la borne ne peut PAS être baselinée, même si quelqu'un
    l'ajoute au fichier.
    """
    base = {
        "identites": [{"fichier": "mission.jsonl", "seq": 500, "type": "schema", "champ": "story"}],
        "bornes": {"mission.jsonl": {"seq_max": 384, "hash": "abc"}},
    }
    reelles = [{"fichier": "mission.jsonl", "seq": 500, "type": "schema", "champ": "story"}]

    messages = anomalies_base(base, reference_base=base, anomalies_reelles=reelles)
    assert messages, "une identité au-delà de la borne doit être refusée"
    assert any("borne" in m.lower() for m in messages)


def test_g10_la_base_ne_peut_pas_croitre():
    """CA5 — le cliquet : ajouter une identité par rapport à `origin/main` est un échec ;
    en retirer est autorisé."""
    identite = {"fichier": "mission.jsonl", "seq": 10, "type": "schema", "champ": "story"}
    autre = {"fichier": "mission.jsonl", "seq": 11, "type": "schema", "champ": "story"}
    bornes = {"mission.jsonl": {"seq_max": 384, "hash": "abc"}}

    ancienne = {"identites": [identite], "bornes": bornes}
    elargie = {"identites": [identite, autre], "bornes": bornes}

    assert anomalies_base(elargie, ancienne, [identite, autre]), "élargir la base doit échouer"
    assert anomalies_base(ancienne, elargie, [identite]) == [], "en retirer est autorisé"


def test_g10b_identite_perimee_refusee():
    """CA5 — une identité qui ne correspond plus à une anomalie réelle doit être retirée,
    sinon la base deviendrait une couverture générale."""
    identite = {"fichier": "mission.jsonl", "seq": 10, "type": "schema", "champ": "story"}
    base = {"identites": [identite], "bornes": {"mission.jsonl": {"seq_max": 384, "hash": "a"}}}

    assert anomalies_base(base, base, anomalies_reelles=[]), "identité périmée => échec"


def test_g11_le_gate_ci_appelle_reellement_les_controles():
    """CA2/CA8 — sans ce test on livrerait un mécanisme défini et JAMAIS invoqué.

    Aucun test du dépôt ne lisait `.github/workflows/gates.yml` avant celui-ci : un contrôle
    parfaitement testé mais absent de la CI serait vert partout et n'aurait aucun effet.
    """
    yaml = pytest.importorskip("yaml", reason="pyyaml est installé par le job `tests` de la CI")
    # On interroge la STRUCTURE, pas le texte : un découpage de chaîne se trompe silencieusement
    # (« \n  » matche aussi l'indentation de `runs-on`) et rendrait ce test vert ou rouge pour la
    # mauvaise raison.
    etapes = yaml.safe_load(GATES.read_text(encoding="utf-8"))["jobs"]["registres"]["steps"]

    commandes = " ".join(e.get("run", "") for e in etapes)
    assert "registre.py ancrage" in commandes, (
        "le job `registres` doit RÉELLEMENT invoquer la commande d'ancrage : un contrôle testé "
        "mais absent de la CI serait vert partout et n'aurait aucun effet"
    )

    checkout = [e for e in etapes if str(e.get("uses", "")).startswith("actions/checkout")]
    assert checkout, "le job registres doit faire un checkout"
    assert checkout[0].get("with", {}).get("fetch-depth") == 0, (
        "`fetch-depth: 0` doit être DANS le job registres : la référence est `origin/main`, et "
        "sans historique complet le contrôle serait inopérant. Le trouver dans un AUTRE job "
        "(gitleaks) rendrait l'assertion vraie pour la mauvaise raison."
    )


def test_g12_le_checkpoint_n_ecrit_jamais_dans_le_registre(tmp_path):
    """CA3 — l'émission d'une ancre est en lecture seule : un outil d'audit qui modifie ce qu'il
    audite invalide sa propre preuve."""
    chemin = _registre(tmp_path, 3)
    avant = chemin.read_bytes()

    charge = checkpoint_de(_entrees(chemin), "mission.jsonl")

    assert chemin.read_bytes() == avant, "le registre audité doit être intact"
    assert charge == {
        "registre": "mission.jsonl",
        "seq": 3,
        "hash_ancre": _entrees(chemin)[-1]["hash"],
        "entrees": 3,
    }


# ---------------------------------------------------------------------------
# Tests de la CLI. Les gates CI n'appellent PAS les fonctions pures : ils
# appellent `scripts/registre.py`. Les tests ci-dessus étaient tous verts alors
# que la CLI plantait sur quatre appels (str au lieu de Path, `verify` traité
# comme un itérable) — un contrôle parfait derrière une commande cassée ne
# protège rien. On exerce donc le point d'entrée RÉEL.
# ---------------------------------------------------------------------------

import subprocess  # noqa: E402

CLI = Path(__file__).resolve().parents[1] / "scripts" / "registre.py"


def _cli(*args, cwd=None):
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        capture_output=True, text=True, cwd=cwd,
    )


def _git(depot: Path, *args) -> None:
    """Invoque git en ISOLANT le dépôt de fixture de la configuration globale du poste.

    Sans `core.hooksPath` neutralisé, les hooks globaux du développeur s'exécutent dans le dépôt
    jetable et le test échoue — pour lui seul. Un test ne doit jamais dépendre de la machine qui
    le lance : ce dépôt de fixture doit se comporter identiquement partout dans le monde.
    """
    subprocess.run(
        ["git", "-c", "core.hooksPath=" + str(depot / ".git" / "hooks-vides"),
         "-c", "commit.gpgsign=false", "-c", "user.email=t@t", "-c", "user.name=t",
         "-C", str(depot), *args],
        check=True, capture_output=True,
    )


def _depot_git(tmp_path: Path) -> Path:
    """Un vrai dépôt git avec un registre commité : la référence d'ancrage est `HEAD`."""
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, capture_output=True)
    (tmp_path / ".git" / "hooks-vides").mkdir(exist_ok=True)
    dossier = tmp_path / "Registres"
    dossier.mkdir()
    for i in range(4):
        append(dossier / "mission.jsonl", "story_complete", "t", {"story": f"S{i}"})
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "socle")
    return tmp_path


def test_g13_chaque_sous_commande_repond(tmp_path):
    """CA7 — les cinq sous-commandes vivent dans UN seul argparse et fonctionnent réellement."""
    registre = tmp_path / "mission.jsonl"

    assert _cli("append", str(registre), "--type", "t", "--actor", "a",
                "--payload-json", "{}").returncode == 0
    assert _cli("verify", str(registre)).returncode == 0
    assert _cli("completude", str(registre)).returncode in (0, 1)  # rapporte, ne plante pas
    assert _cli("checkpoint", str(registre), "--registre", "mission.jsonl").returncode == 0

    aide = _cli("--help").stdout
    for commande in ("append", "verify", "completude", "checkpoint", "ancrage"):
        assert commande in aide, f"`{commande}` doit être découvrable par --help"


def test_g13b_completude_accepte_plusieurs_fichiers(tmp_path):
    """CA7 — l'ancienne commande n'acceptait qu'UN fichier ; le gate CI en passe 34,
    ce qui aurait planté avec « unrecognized arguments »."""
    a, b = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    append(a, "story_complete", "t", {"story": "A"})
    append(b, "story_complete", "t", {"story": "B"})

    resultat = _cli("completude", str(a), str(b))
    assert "unrecognized arguments" not in resultat.stderr
    assert "anomalie" in resultat.stdout


def test_g14_ancrage_detecte_la_troncature_de_bout_en_bout(tmp_path):
    """CA3 — la preuve traversant le chemin RÉEL du gate : `verify` reste vert, `ancrage` rougit."""
    depot = _depot_git(tmp_path)
    registre = depot / "Registres" / "mission.jsonl"
    lignes = registre.read_text(encoding="utf-8").splitlines()
    registre.write_text("\n".join(lignes[:2]) + "\n", encoding="utf-8")

    assert _cli("verify", str(registre), cwd=depot).returncode == 0, (
        "l'intégrité reste intacte après troncature — c'est tout le problème"
    )
    resultat = _cli("ancrage", "--ref", "HEAD", cwd=depot)
    assert resultat.returncode == 1, "la troncature doit faire rougir le gate"
    assert "troncature" in resultat.stdout.lower()


def test_g14b_ancrage_detecte_un_registre_supprime(tmp_path):
    """CA4 — de bout en bout : le glob ne voit pas un fichier supprimé, l'union si."""
    depot = _depot_git(tmp_path)
    (depot / "Registres" / "mission.jsonl").unlink()

    resultat = _cli("ancrage", "--ref", "HEAD", cwd=depot)
    assert resultat.returncode == 1
    assert "supprim" in resultat.stdout.lower()


def test_g15_reference_introuvable_echoue_en_nommant_le_remede(tmp_path):
    """CA4 — strict par défaut : jamais de SKIP, et le message doit être actionnable."""
    depot = _depot_git(tmp_path)

    resultat = _cli("ancrage", "--ref", "refs/absente", cwd=depot)
    assert resultat.returncode != 0, "une référence absente ne doit JAMAIS produire un succès"
    assert "fetch-depth" in (resultat.stdout + resultat.stderr), (
        "le message doit nommer le remède, sinon le mainteneur ne peut pas agir"
    )


def test_g16_le_cliquet_laisse_passer_l_herite_et_rougit_sur_le_nouveau(tmp_path):
    """CA5 de bout en bout — la seule forme qui rend la base non contournable.

    Une base qui ferait simplement taire les anomalies serait une couverture générale. Ici la
    dette héritée passe, mais une anomalie NOUVELLE (au-delà de la borne `seq_max`) rougit — et
    elle ne peut pas être baselinée, puisque `anomalies_base` refuse toute identité hors borne.
    """
    registre = tmp_path / "mission.jsonl"
    append(registre, "revue_scellee", "t", {"story": "HERITE"})  # incomplète : anomalie
    entrees = _entrees(registre)

    base = tmp_path / "base.json"
    base.write_text(json.dumps({
        "version": 1,
        "identites": [{"fichier": "mission.jsonl", "seq": 1, "type": "schema",
                       "champ": c} for c in ("champ obligatoire manquant: prompt_sha256",
                                             "champ obligatoire manquant: vendors")],
        "bornes": {"mission.jsonl": {"seq_max": entrees[-1]["seq"], "hash": entrees[-1]["hash"]}},
    }), encoding="utf-8")

    herite = _cli("completude", str(registre), "--base", str(base))
    assert herite.returncode == 0, f"la dette héritée doit passer : {herite.stdout}"

    append(registre, "revue_scellee", "t", {"story": "NOUVEAU"})  # au-delà de la borne
    nouveau = _cli("completude", str(registre), "--base", str(base))
    assert nouveau.returncode == 1, "une anomalie nouvelle doit faire rougir"
    assert "nouvelle" in nouveau.stdout.lower()


def test_g17_le_gate_ci_appelle_aussi_le_cliquet_de_completude():
    """CA5 — même exigence que G11 : un cliquet non invoqué ne protège rien."""
    yaml = pytest.importorskip("yaml")
    etapes = yaml.safe_load(GATES.read_text(encoding="utf-8"))["jobs"]["registres"]["steps"]
    commandes = " ".join(e.get("run", "") for e in etapes)

    assert "completude" in commandes, "le gate doit invoquer le contrôle de complétude"
    assert "--base-ref-git" in commandes, (
        "sans `--base-ref-git`, `reference_base` vaut None et le contrôle de NON-CROISSANCE "
        "est silencieusement ignoré : la base pourrait être élargie dans la PR même"
    )
    assert "BASELINE-COMPLETUDE.json" in commandes, (
        "sans `--base`, le gate rougirait sur les 31 anomalies héritées dès le premier jour — "
        "et serait désactivé au lieu d'être respecté"
    )


# ---------------------------------------------------------------------------
# Branches de refus. Une garde n'est prouvée que par un test qui NOMME son absence :
# sans ces cas, `verifier_ancres` et `anomalies_base` pourraient renvoyer une liste
# vide sur des données corrompues, ce qui est un succès silencieux.
# ---------------------------------------------------------------------------


def test_g18_ancre_incomplete_ou_divergente(tmp_path):
    """CA3 — chaque manière dont une ancre peut ne plus être honorée est signalée."""
    ancre = {"registre": "m.jsonl", "seq": 3, "hash_ancre": "h3", "entrees": 3}
    complet = {"m.jsonl": [{"hash": "h1"}, {"hash": "h2"}, {"hash": "h3"}]}

    assert verifier_ancres([ancre], complet) == [], "l'état conforme ne doit rien signaler"

    tronque = {"m.jsonl": [{"hash": "h1"}, {"hash": "h2"}]}
    assert any("incomplet" in m for m in verifier_ancres([ancre], tronque))

    divergent = {"m.jsonl": [{"hash": "h1"}, {"hash": "h2"}, {"hash": "AUTRE"}]}
    assert verifier_ancres([ancre], divergent), "un hash divergent au rang ancré doit être signalé"

    sans_hash = {"m.jsonl": [{"hash": "h1"}, {"hash": "h2"}, {"pas_de_hash": 1}]}
    assert any("invalide" in m for m in verifier_ancres([ancre], sans_hash))

    pas_une_liste = {"m.jsonl": "ceci n'est pas une liste"}
    assert any("invalide" in m for m in verifier_ancres([ancre], pas_une_liste))


def test_g19_ancres_typees_faussement():
    """CA4 — une ancre dont les champs ont le mauvais TYPE est refusée, pas ignorée.

    `bool` est une sous-classe de `int` en Python : `seq=True` passerait un `isinstance(seq, int)`
    naïf. Le refus doit être explicite.
    """
    registres = {"m.jsonl": [{"hash": "h1"}]}
    for mauvais in (
        {"registre": "", "seq": 1, "hash_ancre": "h", "entrees": 1},
        {"registre": "m.jsonl", "seq": True, "hash_ancre": "h", "entrees": 1},
        {"registre": "m.jsonl", "seq": 0, "hash_ancre": "h", "entrees": 1},
        {"registre": "m.jsonl", "seq": 1, "hash_ancre": 42, "entrees": 1},
        {"registre": "m.jsonl", "seq": 1, "hash_ancre": "h", "entrees": 0},
    ):
        assert verifier_ancres([mauvais], registres), f"doit refuser : {mauvais}"


def test_g20_prefixe_conserve_refuse_une_entree_sans_hash():
    """CA3 — une entrée sans `hash` est une divergence, jamais un succès : sans cette règle, on
    contournerait le contrôle en supprimant simplement le champ comparé."""
    reference = [{"seq": 1, "hash": "h1"}]
    assert prefixe_conserve(reference, [{"seq": 1}]) is not None
    assert prefixe_conserve(reference, [{"seq": 1, "hash": None}]) is not None
    assert prefixe_conserve([], []) is None, "deux états vides sont cohérents"


def test_g21_anomalies_seq_refuse_les_seq_non_entiers():
    """CA2 — un `seq` absent ou non entier est une anomalie : le `seq` sert de clé d'identité à
    la base de référence, donc un `seq` non fiable ruinerait le cliquet."""
    assert anomalies_seq([{"type": "sans_seq"}])
    assert anomalies_seq([{"seq": "1"}])
    assert anomalies_seq([{"seq": True}])
    assert anomalies_seq([]) == [], "un registre vide n'a pas d'anomalie de séquence"


def test_g22_anomalies_base_refuse_une_base_malformee():
    """CA5 — une base illisible ou incomplète ne doit jamais valoir « aucune anomalie »."""
    reelles = [{"fichier": "m.jsonl", "seq": 1, "type": "schema", "champ": "story"}]

    sans_bornes = {"identites": reelles}
    assert anomalies_base(sans_bornes, None, reelles), "une base sans borne ne peut rien garantir"

    identite_incomplete = {"identites": [{"fichier": "m.jsonl"}],
                           "bornes": {"m.jsonl": {"seq_max": 10, "hash": "a"}}}
    assert anomalies_base(identite_incomplete, None, reelles)


def test_g23_la_non_croissance_est_reellement_appliquee_depuis_git(tmp_path):
    """CA5 — ferme le fail-open CRITIQUE relevé en revue scellée.

    Le gate ne passait que `--base` : `reference_base` valait `None`, donc le contrôle de
    non-croissance était **silencieusement ignoré** et la base pouvait être élargie dans la PR
    même. Ce test prouve que la référence est bien résolue depuis git ET qu'elle mord.
    """
    depot = _depot_git(tmp_path)
    registre = depot / "Registres" / "mission.jsonl"
    append(registre, "revue_scellee", "t", {"story": "INCOMPLETE"})
    entrees = _entrees(registre)
    seq_derniere = entrees[-1]["seq"]

    # La base est CALCULÉE depuis les anomalies réellement mesurées, comme la vraie base du
    # dépôt : l'écrire à la main ferait rougir le test pour une anomalie non couverte, donc
    # pour une raison qui n'est pas celle qu'on teste.
    from forgeai.core.registre_completude import anomalies as _anomalies

    base = depot / "base.json"
    identites = [
        {"fichier": "mission.jsonl", "seq": a["seq"], "type": a["type"], "champ": a["raison"]}
        for a in _anomalies(entrees)
    ]
    assert identites, "la fixture doit produire au moins une anomalie à baseliner"
    bornes = {"mission.jsonl": {"seq_max": seq_derniere, "hash": entrees[-1]["hash"]}}
    base.write_text(json.dumps({"version": 1, "identites": identites, "bornes": bornes}),
                    encoding="utf-8")
    _git(depot, "add", "-A")
    _git(depot, "commit", "-qm", "base de reference")

    conforme = _cli("completude", str(registre), "--base", str(base),
                    "--base-ref-git", "HEAD", cwd=depot)
    assert conforme.returncode == 0, f"la base inchangée doit passer : {conforme.stdout}"

    # On ÉLARGIT la base sans toucher au registre : c'est l'attaque que le cliquet doit stopper.
    elargie = json.loads(base.read_text(encoding="utf-8"))
    elargie["identites"].append({"fichier": "mission.jsonl", "seq": 1, "type": "schema",
                                 "champ": "invente"})
    base.write_text(json.dumps(elargie), encoding="utf-8")

    attaque = _cli("completude", str(registre), "--base", str(base),
                   "--base-ref-git", "HEAD", cwd=depot)
    assert attaque.returncode == 1, (
        "élargir la base par rapport à la référence git DOIT échouer — sinon le cliquet "
        "ne protège rien et la base devient une couverture générale"
    )


def test_g24_reference_git_inaccessible_pour_la_base_echoue_durement(tmp_path):
    """CA4 — « je ne peux pas voir » ne doit jamais valoir « tout va bien »."""
    depot = _depot_git(tmp_path)
    base = depot / "base.json"
    base.write_text(json.dumps({"version": 1, "identites": [], "bornes": {}}), encoding="utf-8")

    resultat = _cli("completude", str(depot / "Registres" / "mission.jsonl"),
                    "--base", str(base), "--base-ref-git", "refs/absente", cwd=depot)
    assert resultat.returncode != 0
    assert "fetch-depth" in (resultat.stdout + resultat.stderr)


def test_g25_base_absente_de_la_reference_est_visible_pas_silencieuse(tmp_path):
    """CA5 — la PR qui INTRODUIT la base est légitime, mais l'inapplicabilité du contrôle de
    non-croissance doit apparaître dans la sortie : un contrôle inapplicable et muet est
    indiscernable d'un contrôle réussi."""
    depot = _depot_git(tmp_path)
    base = depot / "base.json"
    base.write_text(json.dumps({"version": 1, "identites": [], "bornes": {}}), encoding="utf-8")

    resultat = _cli("completude", str(depot / "Registres" / "mission.jsonl"),
                    "--base", str(base), "--base-ref-git", "HEAD", cwd=depot)
    assert "non-croissance" in resultat.stdout, (
        "l'inapplicabilité du contrôle doit être annoncée explicitement"
    )
