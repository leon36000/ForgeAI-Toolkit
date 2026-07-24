"""Story SEC-YAML-INJECT — le plan rejette les caractères de contrôle dans ses champs scalaires
qui atteignent en brut le YAML/Compose rendu (plan_id, profile, model, embed_model).

Preuve d'attaque (RED sur l'ancien code) : un plan_id porteur de \n injecte un document YAML
arbitraire dans le flux k3s multi-documents (escalade forgeai-sa -> cluster-admin)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from forgeai.core.models import DeploymentPlan, RenderTarget, ServiceSpec

_SVC = ServiceSpec(name="redis", image="redis:7", host_port=6379, container_port=6379)

# payload bien formé : termine par ---\n#  pour absorber la queue « (profil X) » en commentaire
_PAYLOAD_CRB = (
    "p1-x\n---\napiVersion: rbac.authorization.k8s.io/v1\nkind: ClusterRoleBinding\n"
    "metadata:\n  name: pwn\nroleRef:\n  kind: ClusterRole\n  name: cluster-admin\n"
    "  apiGroup: rbac.authorization.k8s.io\nsubjects:\n- kind: ServiceAccount\n"
    "  name: forgeai-sa\n  namespace: forgeai-minimal\n---\n# "
)


def _plan(**over):
    base = dict(plan_id="p1-abcd1234", profile="minimal-cpu", target=RenderTarget.K3S,
                services=(_SVC,), model="qwen2.5:0.5b", embed_model="nomic-embed-text")
    base.update(over)
    return DeploymentPlan(**base)


def test_injection_yaml_via_plan_id_est_bloquee_a_la_construction():
    """Le vecteur d'attaque prouvé : construire un plan avec un plan_id porteur de \n DOIT lever
    ValueError AVANT tout rendu (défense à la source, dataclass frozen)."""
    with pytest.raises(ValueError, match="plan_id"):
        _plan(plan_id=_PAYLOAD_CRB)


@pytest.mark.parametrize("champ", ["plan_id", "profile", "model", "embed_model"])
@pytest.mark.parametrize("mauvais", ["a\nb", "a\rb", "x\ty", "z\x00", "w\x1f"])
def test_caracteres_de_controle_rejetes(champ, mauvais):
    with pytest.raises(ValueError, match=champ):
        _plan(**{champ: mauvais})


def test_message_ne_divulgue_pas_le_payload_complet():
    """Le message nomme le champ sans recracher tout le payload injecté (anti-fuite logs)."""
    with pytest.raises(ValueError) as exc:
        _plan(plan_id=_PAYLOAD_CRB)
    msg = str(exc.value)
    assert "plan_id" in msg
    assert "ClusterRoleBinding" not in msg and "cluster-admin" not in msg


def test_plan_legitime_se_construit_sans_erreur():
    """Aucune régression : un plan légitime (identifiants normaux) reste valide."""
    p = _plan()
    assert p.plan_id == "p1-abcd1234" and p.profile == "minimal-cpu"
    # profils réels + repli dry-run tous acceptés
    for prof in ("minimal-gpu-cuda", "minimal-gpu-rocm", "minimal-gpu-intel",
                 "minimal-cpu", "Minimal"):
        assert _plan(profile=prof).profile == prof
