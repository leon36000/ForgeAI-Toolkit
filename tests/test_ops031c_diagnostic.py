"""OPS-031C — bundle de diagnostic reproductible et rédigé.

Un bundle de support QUITTE la machine : l'absence de secret est donc la propriété centrale, et la
reproductibilité doit être vérifiable (horodatage injecté, sérialisation canonique, empreinte).
"""

import argparse
import json
import time

from forgeai import diagnostic as diag_mod
from forgeai.core.redaction import REDACTED
from forgeai.diagnostic import collect_diagnostic, empreinte, rendre

HORODATAGE = "2025-01-01T12:00:00+00:00"
_SECRET_MOTIF = "api_key=" + "z" * 32  # proof:allow (construit, jamais littéral — gitleaks)


def faux_etat() -> dict:
    """État factice : contient un secret DÉTECTABLE PAR MOTIF et une clé sensible PAR NOM."""
    return {
        "backends": {"disponibles": 3},
        "cluster": {"noeuds": 5},
        "deploiement": {"dernier": "2025-01-01T00:00:00Z"},
        "materiel": {"cpu": 8, "memoire": "16Go"},
        "password": "valeurBanale",  # valeur anodine : seul le NOM de la clé doit la neutraliser
    }


def faux_logs() -> list:
    return ["INFO: démarrage", f"DEBUG: {_SECRET_MOTIF}", "INFO: terminé"]


def test_g1_reproductible_memes_octets_et_meme_empreinte():
    """CA1 : même horodatage + même état → octets identiques et même empreinte."""
    b1 = collect_diagnostic(horodatage=HORODATAGE, etat=faux_etat, logs=faux_logs)
    b2 = collect_diagnostic(horodatage=HORODATAGE, etat=faux_etat, logs=faux_logs)
    assert rendre(b1) == rendre(b2), "le rendu doit être déterministe"
    assert b1["empreinte"] == b2["empreinte"]


def test_g1b_horodatage_different_change_empreinte():
    """CA1 : l'horodatage fait partie du contenu couvert par l'empreinte."""
    b1 = collect_diagnostic(horodatage=HORODATAGE, etat=faux_etat, logs=faux_logs)
    b2 = collect_diagnostic(horodatage="2025-01-01T12:00:01+00:00", etat=faux_etat, logs=faux_logs)
    assert b1["empreinte"] != b2["empreinte"]


def test_g2_empreinte_detecte_l_alteration():
    """CA1 : altérer une valeur du contenu change l'empreinte recalculée."""
    bundle = collect_diagnostic(horodatage=HORODATAGE, etat=faux_etat, logs=faux_logs)
    contenu = json.loads(json.dumps(bundle["contenu"]))  # copie profonde
    contenu["etat"]["backends"]["disponibles"] = 99
    assert empreinte(contenu) != bundle["empreinte"], "toute altération doit être détectable"


def test_g3_secret_par_motif_absent_du_bundle():
    """CA2 : un secret présent dans les logs et l'état n'apparaît nulle part dans le rendu."""
    bundle = collect_diagnostic(horodatage=HORODATAGE, etat=faux_etat, logs=faux_logs)
    rendu = rendre(bundle)
    assert "z" * 32 not in rendu, "FUITE : la valeur du secret est présente"
    assert _SECRET_MOTIF not in rendu
    assert REDACTED in rendu, "la rédaction doit être visible"


def test_g4_cle_sensible_neutralisee_par_son_NOM():
    """CA2 : une clé sensible est neutralisée même si sa valeur est parfaitement anodine.

    Détecteur distinct de G3 : ici la valeur ne ressemble PAS à un secret, donc seule la détection
    par NOM de clé (`is_sensitive_key`) peut agir. Sans elle, le test passerait à tort.
    """
    bundle = collect_diagnostic(
        horodatage=HORODATAGE, etat=lambda: {"password": "valeurBanale"}, logs=lambda: []
    )
    rendu = rendre(bundle)
    assert "valeurBanale" not in rendu, "une clé sensible doit être neutralisée par son nom"
    assert REDACTED in rendu
    # La CLÉ doit survivre : un bundle qui SUPPRIME silencieusement les champs sensibles passerait
    # les deux assertions ci-dessus tout en rendant le diagnostic trompeur (« ce champ n'existe
    # pas » au lieu de « ce champ est masqué »). On exige donc la neutralisation, pas l'effacement.
    assert "password" in rendu, "le NOM de la clé doit être conservé (masquée, pas supprimée)"
    assert json.loads(rendu)["contenu"]["etat"]["password"] == REDACTED


def test_g5_aucune_horloge_interne():
    """CA1 : le module ne lit jamais l'horloge — un délai réel ne change pas les octets."""
    b1 = collect_diagnostic(horodatage=HORODATAGE, etat=faux_etat, logs=faux_logs)
    time.sleep(0.02)
    b2 = collect_diagnostic(horodatage=HORODATAGE, etat=faux_etat, logs=faux_logs)
    assert rendre(b1) == rendre(b2), "une horloge interne rendrait le bundle non reproductible"


def test_g6_cli_ecrit_un_bundle_valide(tmp_path, monkeypatch):
    """CA4 : `forgeai diagnostic --out F` écrit un JSON valide (contenu + empreinte)."""
    from forgeai.cli import _diagnostic

    factice = {"contenu": {"essai": True}, "empreinte": "empreinte-factice"}
    monkeypatch.setattr(diag_mod, "collect_diagnostic", lambda **kw: factice)

    sortie = tmp_path / "diag.json"
    assert _diagnostic(argparse.Namespace(out=str(sortie), tail=5)) == 0
    charge = json.loads(sortie.read_text(encoding="utf-8"))
    assert charge == factice


def test_g6b_cli_sans_out_imprime_du_json(capsys, monkeypatch):
    """CA4 : sans --out, la sortie standard porte un JSON valide."""
    from forgeai.cli import _diagnostic

    factice = {"contenu": {"stdout": True}, "empreinte": "abc123"}
    monkeypatch.setattr(diag_mod, "collect_diagnostic", lambda **kw: factice)

    assert _diagnostic(argparse.Namespace(out=None, tail=5)) == 0
    assert json.loads(capsys.readouterr().out) == factice
