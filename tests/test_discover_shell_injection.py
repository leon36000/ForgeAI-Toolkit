"""FAI-0015 (#121) — discover._sonder interpole un nom de binaire dans `sh -c "command -v {binaire}"`.
Le nom vient de signatures-infra.json (embarqué, de confiance aujourd'hui), donc le défaut est LATENT ;
mais toute future source dynamique (config utilisateur, découverte) rouvrirait une injection de commande.

Spécification (défense en profondeur) : le nom du binaire ne doit JAMAIS être interprété comme de la
syntaxe shell — même s'il contient `;`, `$()`, backticks, etc. RED avant correctif : l'interpolation
directe exécute la charge.
"""
import forgeai.network.discover as discover
from forgeai.core.runner import SubprocessRunner


def test_sonder_ne_permet_pas_l_injection_shell(tmp_path, monkeypatch):
    marker = tmp_path / "PWNED"
    payload = f"nonexistent_xyz_$(:) ; touch {marker}"
    monkeypatch.setattr(discover, "charger_signatures",
                        lambda: [{"id": "evil", "binaire": payload}])

    discover._sonder(SubprocessRunner())

    assert not marker.exists(), (
        "injection shell : le nom de binaire a été interprété par le shell "
        "(la commande `touch` interpolée s'est exécutée)")


def test_sonder_detecte_toujours_un_vrai_binaire(tmp_path, monkeypatch):
    """Régression : un binaire réellement présent (sh) est toujours détecté."""
    monkeypatch.setattr(discover, "charger_signatures",
                        lambda: [{"id": "shell", "binaire": "sh"}])
    data = discover._sonder(SubprocessRunner())
    assert data["binaires"]["shell"] is True
