"""Tests de la garde metering B-20b §7.4 (scripts/check_metering_sites.py)."""
import importlib.util
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "check_metering_sites",
    Path(__file__).resolve().parent.parent / "scripts" / "check_metering_sites.py",
)
garde = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(garde)


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
