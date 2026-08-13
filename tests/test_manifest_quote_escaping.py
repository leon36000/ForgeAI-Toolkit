"""PERF/BUG (trouvé en session, jamais couvert par l'audit v7.1) — corruption de manifeste sur
guillemet non échappé dans command/env (k3s.py) et command (compose.py).

_safe() (k3s.py) ne rejette que les caractères de contrôle Unicode, JAMAIS un guillemet double.
command_block et env_block interpolaient la valeur dans un `f'"{...}"'` fait main sans échapper
les guillemets internes — le même fichier connaît pourtant ce risque et le corrige ailleurs
(_probes_block utilise json.dumps précisément parce qu'un argument contenant `: `, `#`, `*` ou
`[` serait sinon RÉINTERPRÉTÉ par le parseur YAML, cf. commentaire k3s.py). Cette protection
n'était pas appliquée à command/env. Même défaut indépendant dans compose.py::render_compose
pour `command:` (le bloc `environment:` du même fichier échappe déjà correctement).

Preuve : une valeur contenant un guillemet double casse le YAML généré (yaml.safe_load_all lève
ScannerError) — reproduit AVANT correctif, absent APRÈS.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

try:  # PyYAML = dépendance de TEST seulement (le paquet runtime reste sans dépendance), skip si absent.
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from forgeai.core.models import DeploymentPlan, RenderTarget, ServiceSpec
from forgeai.renderers.compose import render_compose
from forgeai.renderers.k3s import render_k3s

pytestmark = pytest.mark.skipif(
    yaml is None,
    reason=("PyYAML est une dépendance de TEST (le paquet runtime reste sans dépendance) : ces tests "
            "TOURNENT en CI et en dev avec l'extra `dev` (même justification scellée que "
            "tests/test_openbao_unsealer_compose.py, preuve S4 au Registres/mission.jsonl) ; "
            "ils ne SKIPPENT que dans un environnement nu sans la dépendance de test."),
)

# Valeur volontairement hostile au YAML : un guillemet suivi de ": " est réinterprété par le
# parseur comme une frontière de mapping si l'échappement est absent (mesuré avant correctif).
_VALEUR_HOSTILE = 'a"b: c'


def _plan_k3s(service: ServiceSpec) -> DeploymentPlan:
    return DeploymentPlan(
        plan_id="t", profile="minimal-cpu", target=RenderTarget.K3S,
        services=(service,), model="m", embed_model="e",
    )


def _plan_compose(service: ServiceSpec) -> DeploymentPlan:
    return DeploymentPlan(
        plan_id="t", profile="minimal-cpu", target=RenderTarget.COMPOSE,
        services=(service,), model="m", embed_model="e",
    )


def test_k3s_command_avec_guillemet_produit_un_yaml_valide():
    svc = ServiceSpec(
        name="litellm", image="litellm/litellm:latest", host_port=24000, container_port=4000,
        command=("--config", _VALEUR_HOSTILE),
    )
    out = render_k3s(_plan_k3s(svc))
    docs = list(yaml.safe_load_all(out))  # ne doit PAS lever ScannerError
    deployment = next(d for d in docs if d and d.get("kind") == "Deployment")
    args = deployment["spec"]["template"]["spec"]["containers"][0]["args"]
    assert _VALEUR_HOSTILE in args, "la valeur doit survivre INTACTE au round-trip YAML"


def test_k3s_env_avec_guillemet_produit_un_yaml_valide():
    svc = ServiceSpec(
        name="litellm", image="litellm/litellm:latest", host_port=24000, container_port=4000,
        env={"FOO": _VALEUR_HOSTILE},
    )
    out = render_k3s(_plan_k3s(svc))
    docs = list(yaml.safe_load_all(out))  # ne doit PAS lever ScannerError
    deployment = next(d for d in docs if d and d.get("kind") == "Deployment")
    env = deployment["spec"]["template"]["spec"]["containers"][0]["env"]
    valeurs = {e["name"]: e.get("value") for e in env}
    assert valeurs["FOO"] == _VALEUR_HOSTILE, "la valeur doit survivre INTACTE au round-trip YAML"


def test_compose_command_avec_guillemet_produit_un_yaml_valide():
    svc = ServiceSpec(
        name="litellm", image="litellm/litellm:latest", host_port=24000, container_port=4000,
        command=("--config", _VALEUR_HOSTILE),
    )
    out = render_compose(_plan_compose(svc))
    doc = yaml.safe_load(out)  # ne doit PAS lever ScannerError
    command = doc["services"]["litellm"]["command"]
    assert _VALEUR_HOSTILE in command, "la valeur doit survivre INTACTE au round-trip YAML"


def test_non_regression_command_sans_guillemet():
    """Contrôle négatif : une valeur normale reste inchangée sur les deux renderers."""
    svc_k3s = ServiceSpec(
        name="litellm", image="litellm/litellm:latest", host_port=24000, container_port=4000,
        command=("--config", "/etc/litellm.yaml"),
    )
    out_k3s = render_k3s(_plan_k3s(svc_k3s))
    docs = list(yaml.safe_load_all(out_k3s))
    deployment = next(d for d in docs if d and d.get("kind") == "Deployment")
    assert "/etc/litellm.yaml" in deployment["spec"]["template"]["spec"]["containers"][0]["args"]

    svc_compose = ServiceSpec(
        name="litellm", image="litellm/litellm:latest", host_port=24000, container_port=4000,
        command=("--config", "/etc/litellm.yaml"),
    )
    out_compose = render_compose(_plan_compose(svc_compose))
    doc = yaml.safe_load(out_compose)
    assert "/etc/litellm.yaml" in doc["services"]["litellm"]["command"]
