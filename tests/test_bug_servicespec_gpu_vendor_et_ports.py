"""BUG-servicespec-validation — `ServiceSpec.__post_init__` ne validait ni `gpu_vendor` ni les
ports (`host_port`/`container_port`), alors que le motif de validation existe déjà dans ce
même fichier pour des champs analogues.

BUG A (gpu_vendor non validé) : `renderers/k3s.py` refuse un `gpu_vendor` inconnu au rendu
(cf. `test_k3s_gpu_vendor_inconnu_refuse`, tests/test_k3s_gpu_vendor.py) mais
`renderers/compose.py` ne valide rien — `vendor = svc.gpu_vendor or "nvidia"`
(src/forgeai/renderers/compose.py) fait silencieusement retomber tout vendor inconnu sur
"nvidia". Le MÊME `ServiceSpec` produit donc un refus explicite sur un renderer et un
comportement divergent et silencieux sur l'autre. Fermé à la source, dans
`ServiceSpec.__post_init__` (core/models.py), pour que les deux renderers héritent
automatiquement de la même garde sans dupliquer la logique de validation.

BUG B (ports non bornés) : `host_port`/`container_port` n'étaient bornés nulle part avant
rendu, alors que `adopted_endpoint` valide déjà son port dans [1, 65535]
(core/models.py, ~lignes 469-473, motif repris ici à l'identique). Un port invalide (0,
négatif, >65535, ou non entier) produisait un manifeste k3s/compose invalide plus tard au
lieu d'être refusé à la construction du `ServiceSpec`.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from forgeai.core.models import ServiceSpec


def _svc(**overrides):
    base = dict(name="engine", image="img:latest", host_port=8000, container_port=8000)
    base.update(overrides)
    return ServiceSpec(**base)


# ---------------------------------------------------------------------------
# BUG A — gpu_vendor non validé à la construction du ServiceSpec
# ---------------------------------------------------------------------------

def test_gpu_vendor_inconnu_refuse_a_la_construction():
    """PREUVE : un gpu_vendor hors {nvidia, amd, intel, None} doit être refusé DÈS la
    construction du ServiceSpec — avant même d'atteindre un renderer, pour que k3s ET
    compose partagent la même garde plutôt que de diverger silencieusement."""
    with pytest.raises(ValueError, match="ERR_SERVICE_VENDOR_INCONNU"):
        _svc(gpu=True, gpu_vendor="exotic-vendor")


def test_gpu_vendor_inconnu_refuse_meme_sans_gpu_actif():
    """gpu_vendor est un champ structurel du ServiceSpec, pas seulement au rendu : un
    vendor inconnu doit être refusé même si `gpu=False` (donnée incohérente dès la
    construction, pas seulement au moment où un renderer la lirait)."""
    with pytest.raises(ValueError, match="ERR_SERVICE_VENDOR_INCONNU"):
        _svc(gpu=False, gpu_vendor="exotic-vendor")


@pytest.mark.parametrize("vendor", ["nvidia", "amd", "intel", None])
def test_gpu_vendor_connu_ou_none_accepte_non_regression(vendor):
    """Non-régression : les vendors historiquement acceptés par k3s.py/compose.py (et
    l'absence de vendor, None) restent acceptés sans exception."""
    svc = _svc(gpu=True, gpu_vendor=vendor)
    assert svc.gpu_vendor == vendor


# ---------------------------------------------------------------------------
# BUG B — host_port / container_port non bornés à la construction du ServiceSpec
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("champ", ["host_port", "container_port"])
@pytest.mark.parametrize("valeur", [0, -1, 65536, 100000])
def test_port_hors_bornes_refuse_a_la_construction(champ, valeur):
    """PREUVE : un port hors [1, 65535] doit être refusé DÈS la construction du
    ServiceSpec, avant qu'un manifeste k3s/compose invalide ne soit émis."""
    with pytest.raises(ValueError, match="ERR_SERVICE_PORT_BORNES"):
        _svc(**{champ: valeur})


@pytest.mark.parametrize("champ", ["host_port", "container_port"])
@pytest.mark.parametrize("valeur", ["8000", 80.0, True])
def test_port_non_entier_refuse_a_la_construction(champ, valeur):
    """Un port non entier (chaîne, flottant, booléen — `bool` est une sous-classe d'`int`
    en Python, donc `True == 1` doit tout de même être refusé) doit être rejeté."""
    with pytest.raises(ValueError, match="ERR_SERVICE_PORT_BORNES"):
        _svc(**{champ: valeur})


@pytest.mark.parametrize("champ,valeur", [
    ("host_port", 1), ("host_port", 65535),
    ("container_port", 1), ("container_port", 65535),
])
def test_port_borne_extreme_acceptee_non_regression(champ, valeur):
    """Non-régression : les bornes elles-mêmes (1 et 65535) restent acceptées."""
    svc = _svc(**{champ: valeur})
    assert getattr(svc, champ) == valeur
