"""Durcissement du renderer k3s/k8s — findings Sentinelle (majeures) sur render_k3s.

Traite 3 trous de robustesse latents (le renderer les portait avant K-CHOICE) :
  1. node_port_for : plage NodePort saturée -> erreur claire, JAMAIS de boucle infinie (DoS) ;
  2. volume mal formé (sans ':') -> ValueError explicite, pas d'IndexError ;
  3. valeurs interpolées au manifeste (name/image/node/volume) : refus des caractères qui
     casseraient/injecteraient le YAML (newline, contrôle) — défense en profondeur.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from forgeai.core.models import DeploymentPlan, RenderTarget, ServiceSpec
from forgeai.renderers.k3s import node_port_for, render_k3s


def _svc(**kw):
    d = dict(name="ollama", image="ollama/ollama:latest", host_port=21434, container_port=11434)
    d.update(kw)
    return ServiceSpec(**d)


def _plan(services):
    return DeploymentPlan(plan_id="t", profile="minimal-cpu", target=RenderTarget.K3S,
                          services=tuple(services), model="m", embed_model="e")


# 1) saturation de la plage NodePort -> erreur bornée, pas de boucle infinie
def test_node_port_for_plage_saturee_leve_erreur():
    used = set(range(30000, 32768))  # les 2768 ports occupés
    with pytest.raises(RuntimeError):
        node_port_for(_svc(), used)


def test_node_port_for_normal_ok():
    used: set = set()
    p1 = node_port_for(_svc(host_port=21434), used)
    p2 = node_port_for(_svc(host_port=24202), used)  # collision de modulo -> réassigné
    assert p1 != p2 and 30000 <= p1 <= 32767 and 30000 <= p2 <= 32767


# 2) volume mal formé -> ValueError claire (pas d'IndexError)
def test_volume_sans_deux_points_leve_valueerror():
    with pytest.raises(ValueError):
        render_k3s(_plan([_svc(volumes=("volume-sans-chemin",))]))


def test_volume_bien_forme_ok():
    out = render_k3s(_plan([_svc(volumes=("data:/root/.ollama",))]))
    assert "name: data" in out and "mountPath: /root/.ollama" in out


# 3) injection YAML : une valeur avec newline/contrôle est refusée
@pytest.mark.parametrize("champ", ["name", "image"])
def test_valeur_avec_newline_refusee(champ):
    with pytest.raises(ValueError):
        render_k3s(_plan([_svc(**{champ: "ok\n      hostPID: true"})]))


def test_node_avec_newline_refuse():
    with pytest.raises(ValueError):
        render_k3s(_plan([_svc()]), node="node\nmalicious: true")
