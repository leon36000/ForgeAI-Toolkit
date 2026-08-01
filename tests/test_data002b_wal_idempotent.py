"""DATA-002B — la récupération WAL ne doit jamais annuler une transaction commitée.

Défaut trouvé par la revue multi-vendor REV-043 (issue #306) : `add_cloud` commite via DEUX
`os.replace` puis supprime le journal. Un crash entre le commit et la suppression laissait un
journal périmé, et la récupération restaurait l'état PRÉ-commit — perte de données silencieuse.

Le crash est un **vrai SIGKILL** sur un vrai processus, jamais un simulacre : la propriété testée
est précisément ce qui survit à une mort brutale, et un mock ne le prouverait pas.
"""

from __future__ import annotations

import json
import multiprocessing as mp
import os
import signal

import pytest

from forgeai.models._locking import commit_deja_applique, empreinte_canonique
from forgeai.models.routes import RouteStore

from tests.test_routestore_concurrence import (  # réutilise l'outillage de crash existant
    _add_cloud_pause_before_journal_unlink,
    _GreenTransport,
)

JOURNAL = ".models-transaction.json"


def _crash_apres_commit(tmp_path):
    """Tue un vrai processus ENTRE le commit et l'unlink du journal, et renvoie `home`."""
    home = tmp_path / "models"
    contexte = mp.get_context("fork")
    pret = contexte.Event()
    processus = contexte.Process(
        target=_add_cloud_pause_before_journal_unlink, args=(str(home), pret)
    )
    processus.start()
    assert pret.wait(timeout=10), "le processus n'a pas atteint l'unlink du journal"
    os.kill(processus.pid, signal.SIGKILL)
    processus.join(timeout=5)

    assert processus.exitcode == -signal.SIGKILL
    # Préconditions : le commit A abouti, et le journal périmé survit. Sans elles, le test
    # vérifierait autre chose que le défaut.
    assert json.loads((home / "routes.json").read_text())[0]["name"] == "orpheline"
    assert (home / JOURNAL).exists()
    return home


@pytest.mark.skipif(
    not hasattr(signal, "SIGKILL"),
    reason="SIGKILL est POSIX ; justification Registres/ : la propriété testée est la survie à "
    "une mort brutale, que Windows ne peut pas reproduire à l'identique",
)
def test_g1_une_transaction_commitee_survit_au_crash(tmp_path):
    """CA1 — LE test rouge de la story.

    Sur le code d'avant le correctif, la récupération restaure l'état pré-commit et
    `recuperee.list()` est vide : rouge garanti, et pour la BONNE raison (pas par plantage).
    """
    home = _crash_apres_commit(tmp_path)

    recuperee = RouteStore(home)
    noms = [r.name for r in recuperee.list()]

    assert noms == ["orpheline"], (
        "une transaction COMMITÉE a été annulée par la récupération — c'est la perte de "
        f"données silencieuse de l'issue #306 (routes vues : {noms})"
    )
    assert recuperee.vault.get("orpheline", "pp-coffre"), "le secret commité doit rester lisible"
    assert not (home / JOURNAL).exists(), "le journal périmé doit être supprimé, pas rejoué"


@pytest.mark.skipif(
    not hasattr(signal, "SIGKILL"),
    reason="SIGKILL est POSIX ; justification Registres/ : voir G1",
)
def test_g1b_la_recuperation_est_idempotente(tmp_path):
    """CA1 — rouvrir plusieurs fois ne doit pas finir par défaire la transaction.

    Le rollback d'origine n'était pas ré-entrant proprement : `restore_*` CONSERVE le journal si
    une restauration échoue, donc un état à moitié dé-publié se rejouait à chaque ouverture.
    """
    home = _crash_apres_commit(tmp_path)

    for tour in range(3):
        assert [r.name for r in RouteStore(home).list()] == ["orpheline"], (
            f"la route a disparu au tour {tour + 1}"
        )


def test_g3_journal_legacy_sans_cible_declenche_le_rollback(tmp_path):
    """CA3 — un journal écrit par un binaire ANTÉRIEUR au correctif n'a pas de section `cible`.

    Le comportement sûr est alors le rollback inconditionnel, par une branche EXPLICITE. Sans
    cette règle, un journal legitime pré-commit pourrait être lu comme « commit réussi ».
    """
    home = tmp_path / "models"
    home.mkdir(parents=True)
    vault = home / "vault.json"
    vault.write_text("{}", encoding="utf-8")

    legacy = {"routes_existed": False, "routes": [], "vault_name": "vault.json",
              "vault_existed": True, "vault": {}}

    assert commit_deja_applique(home, vault, legacy) is False, (
        "sans section `cible`, on ne peut RIEN conclure : le rollback doit s'appliquer"
    )


def test_g4_champ_cible_absent_ne_vaut_jamais_commit_applique(tmp_path):
    """CA3 — détecteur du fail-open le plus facile à introduire ici.

    Le dépôt contient déjà le motif `snapshot.get("vault_name", "vault.json")`. Le reproduire sur
    la cible serait fatal : `snapshot.get("cible") == calcule` est VRAI quand la clé manque et que
    le calcul vaut `None` — un journal pré-commit légitime passerait alors pour un commit réussi,
    et le rollback du cas « clé orpheline » serait sauté.
    """
    home = tmp_path / "models"
    home.mkdir(parents=True)
    vault = home / "vault.json"
    vault.write_text("{}", encoding="utf-8")
    (home / "routes.json").write_text("[]", encoding="utf-8")

    for incomplet in (
        {"cible": {}},
        {"cible": {"routes": empreinte_canonique([])}},   # une seule des deux
        {"cible": {"vault": empreinte_canonique({})}},
    ):
        base = {"routes_existed": True, "routes": [], "vault_name": "vault.json",
                "vault_existed": True, "vault": {}}
        base.update(incomplet)
        assert commit_deja_applique(home, vault, base) is False, (
            f"une cible incomplète ne doit jamais valoir « commit appliqué » : {incomplet}"
        )


def test_g5_l_empreinte_est_canonique_pas_octet_a_octet(tmp_path):
    """CA1 — un changement de style d'écriture (indent, ordre des clés) ne doit PAS changer le
    verdict.

    Si l'empreinte portait sur les octets bruts, passer `indent=1` à `indent=2` dans le writer
    casserait toutes les empreintes, et le mode d'échec serait « discordance => rollback » :
    la perte de données de l'issue #306, réintroduite par une modification cosmétique.
    """
    home = tmp_path / "models"
    home.mkdir(parents=True)
    vault = home / "vault.json"
    routes = home / "routes.json"

    contenu_routes = [{"name": "a", "provenance": "openrouter"}]
    contenu_vault = {"a": "blob"}

    snapshot = {"routes_existed": True, "routes": [], "vault_name": "vault.json",
                "vault_existed": True, "vault": {},
                "cible": {"routes": empreinte_canonique(contenu_routes),
                          "vault": empreinte_canonique(contenu_vault)}}

    # Écriture « compacte », clés dans un ordre, puis « indentée », clés dans l'autre ordre.
    routes.write_text(json.dumps(contenu_routes, separators=(",", ":")), encoding="utf-8")
    vault.write_text(json.dumps(contenu_vault, indent=4, sort_keys=False), encoding="utf-8")
    assert commit_deja_applique(home, vault, snapshot) is True

    routes.write_text(json.dumps(contenu_routes, indent=8), encoding="utf-8")
    vault.write_text(json.dumps(contenu_vault, separators=(",", ":")), encoding="utf-8")
    assert commit_deja_applique(home, vault, snapshot) is True, (
        "le verdict doit dépendre de la DONNÉE, jamais de sa mise en forme"
    )


def test_g6_correspondance_partielle_declenche_le_rollback(tmp_path):
    """CA2 — c'est le cas « clé orpheline » : crash ENTRE les deux `os.replace`.

    Le coffre est à jour, les routes non. Le rollback doit rester appliqué — sans quoi le
    correctif introduirait une clé scellée sans route correspondante.
    """
    home = tmp_path / "models"
    home.mkdir(parents=True)
    vault = home / "vault.json"
    routes = home / "routes.json"

    cible_routes = [{"name": "a"}]
    cible_vault = {"a": "blob"}
    snapshot = {"routes_existed": True, "routes": [], "vault_name": "vault.json",
                "vault_existed": True, "vault": {},
                "cible": {"routes": empreinte_canonique(cible_routes),
                          "vault": empreinte_canonique(cible_vault)}}

    vault.write_text(json.dumps(cible_vault), encoding="utf-8")     # commité
    routes.write_text(json.dumps([]), encoding="utf-8")             # PAS commité

    assert commit_deja_applique(home, vault, snapshot) is False, (
        "une seule des deux cibles atteinte = commit INCOMPLET : le rollback reste légitime"
    )


def test_g6b_fichier_cible_absent_ou_illisible_declenche_le_rollback(tmp_path):
    """CA3 — fail-closed : on ne suppose jamais que le commit a abouti."""
    home = tmp_path / "models"
    home.mkdir(parents=True)
    vault = home / "vault.json"
    routes = home / "routes.json"
    snapshot = {"routes_existed": True, "routes": [], "vault_name": "vault.json",
                "vault_existed": True, "vault": {},
                "cible": {"routes": empreinte_canonique([]), "vault": empreinte_canonique({})}}

    vault.write_text("{}", encoding="utf-8")
    assert commit_deja_applique(home, vault, snapshot) is False, "routes.json absent"

    routes.write_text("{ pas du json", encoding="utf-8")
    assert commit_deja_applique(home, vault, snapshot) is False, "routes.json illisible"


def test_g4b_aucune_matiere_secrete_ajoutee_au_journal(tmp_path):
    """CA4 — le journal n'est supprimé que conditionnellement : y placer le blob scellé de la clé
    nouvellement créée laisserait ce chiffré dans un journal résiduel après qu'un utilisateur a
    détruit le coffre pour révoquer la clé. Seules des empreintes y sont écrites.
    """
    home = _crash_apres_commit(tmp_path)
    journal = json.loads((home / JOURNAL).read_text(encoding="utf-8"))

    cible = journal["cible"]
    assert set(cible) == {"routes", "vault"}, f"la cible ne doit porter que 2 empreintes : {cible}"
    for valeur in cible.values():
        assert isinstance(valeur, str) and len(valeur) == 64, "une empreinte SHA-256 hexadécimale"
        int(valeur, 16)  # lève si ce n'est pas de l'hexadécimal : donc pas du contenu
