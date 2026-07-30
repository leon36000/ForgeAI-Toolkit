"""Tests de la garde metering B-20b §7.4 (scripts/check_metering_sites.py)."""
from forgeai.models import metering_guard as garde


def test_arbre_reel_propre(tmp_path):
    """Sur l'arbre réel du produit, les seuls sites chat/completions sont les
    deux sites mesurés (allowlist) : la garde ne signale RIEN."""
    assert garde.sites_non_autorises() == []


def test_detecte_un_site_non_autorise(tmp_path):
    """Un .py hors allowlist référençant l'endpoint est signalé (le filet mord)."""
    faux_src = tmp_path / "forgeai"
    faux_src.mkdir()
    coupable = faux_src / "fuite.py"
    coupable.write_text(
        'URL = base + "/v1/chat/completions"  # émission directe non mesurée\n',
        encoding="utf-8",
    )
    resultat = garde.sites_non_autorises(src=faux_src, allowlist=frozenset())
    assert resultat == [coupable]


def test_allowlist_exonere_un_site_mesure(tmp_path):
    """Un site présent dans l'allowlist n'est jamais signalé, même s'il émet."""
    faux_src = tmp_path / "forgeai"
    faux_src.mkdir()
    mesure = faux_src / "hardened.py"
    mesure.write_text('URL = "/v1/chat/completions"\n', encoding="utf-8")
    assert garde.sites_non_autorises(src=faux_src, allowlist=frozenset({mesure})) == []


def test_main_arbre_propre_retourne_0(capsys):
    """main() sur l'arbre réel (propre) sort en 0 sans rien écrire sur stderr."""
    assert garde.main() == 0
    assert capsys.readouterr().err == ""


def test_main_signale_retourne_1(monkeypatch, capsys):
    """main() sort en 1 et nomme le coupable sur stderr quand un site fuit.

    Le coupable est sous SRC (⊂ RACINE) comme en réalité : `sites_non_autorises`
    ne retourne que des résultats de `SRC.rglob`, donc `relative_to(RACINE)` du
    message d'erreur tient toujours."""
    coupable = garde.SRC / "fuite.py"
    monkeypatch.setattr(garde, "sites_non_autorises", lambda: [coupable])
    assert garde.main() == 1
    err = capsys.readouterr().err
    assert "GARDE METERING" in err
    assert "fuite.py" in err
