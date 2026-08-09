"""Story K8s-OPERATORS — détection + adoption/installation des opérateurs Kubernetes du châssis.

Spec exécutable (TDAD). Discovery/Adoption : un opérateur DÉJÀ présent est ADOPTÉ (jamais
réinstallé) ; un opérateur ABSENT reçoit un plan d'installation Helm. La détection réelle contre
un cluster est prouvée par l'e2e journalisé au registre.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from forgeai.deploy.operators import OPERATORS, detect, install_argv, plan


class _Runner:
    """Runner de test : mappe (par sous-chaîne d'argv) vers (code, sortie)."""
    def __init__(self, rules):
        self.rules = rules
        self.calls = []

    def run(self, argv):
        self.calls.append(argv)
        joined = " ".join(argv)
        for needle, (code, out) in self.rules.items():
            if needle in joined:
                return code, out
        return 127, ""


_HELM_ES = json.dumps([{"name": "external-secrets", "namespace": "external-secrets",
                        "chart": "external-secrets-2.7.0", "status": "deployed"}])


# --- adoption : opérateur présent via release Helm -> ADOPTÉ, aucune commande ---
def test_detect_present_via_helm():
    r = _Runner({"helm list": (0, _HELM_ES)})
    st = detect("external-secrets-operator", r)
    assert st.present and st.source == "helm" and st.version == "external-secrets-2.7.0"


def test_plan_present_adopte_sans_commande():
    r = _Runner({"helm list": (0, _HELM_ES)})
    p = plan("external-secrets-operator", r)
    assert p["action"] == "adopt" and p["commands"] == []


# --- détection alternative par CRD (installé hors Helm) ---
def test_detect_present_via_crd():
    crd = "externalsecrets.external-secrets.io"
    r = _Runner({"helm list": (0, "[]"),
                 f"get crd {crd}": (0, f"customresourcedefinition.apiextensions.k8s.io/{crd}")})
    st = detect("external-secrets-operator", r)
    assert st.present and st.source == "crd"


# --- absent -> plan d'installation Helm (repo add/update + upgrade --install) ---
def test_plan_absent_installe():
    r = _Runner({"helm list": (0, "[]")})  # kubectl get crd -> 127 (absent)
    p = plan("argo-cd", r)
    assert p["action"] == "install"
    cmds = p["commands"]
    assert cmds[0][:3] == ["helm", "repo", "add"]
    assert any("upgrade" in c and "--install" in c for c in cmds)
    # jamais de --force / --replace qui écraserait quoi que ce soit
    assert not any("--force" in c or "--replace" in c for c in cmds)


def test_install_argv_coordonnees_correctes():
    cmds = install_argv("external-secrets-operator")
    flat = " ".join(" ".join(c) for c in cmds)
    assert "https://charts.external-secrets.io" in flat
    assert "external-secrets/external-secrets" in flat
    assert "--create-namespace" in flat


def test_operateur_inconnu_leve():
    with pytest.raises(KeyError):
        plan("inexistant", _Runner({}))


# --- PINNING (audit v7.1, CAND-009) ---------------------------------------------------------
# Constat de l'audit : la garde explicite `if name not in OPERATORS: raise KeyError(...)` en
# tête de plan() n'était prouvée par AUCUN test. La raison : `test_operateur_inconnu_leve`
# ci-dessus vérifie seulement qu'un KeyError SORT de plan() — or detect() lève lui-même un
# KeyError natif (`spec = OPERATORS[name]`) dès qu'on l'appelle avec un nom inconnu. La garde
# de plan() est donc redondante avec la garde implicite de detect() : la neutraliser (if False:
# au lieu du if name not in OPERATORS:) laisse toujours passer un KeyError — juste levé une
# étape plus tard, depuis detect() — et ne fait rougir aucun test existant.
# Ce test PINNE le comportement précis : KeyError levée AVANT tout appel à detect(). On le
# prouve en remplaçant detect() par une sentinelle qui échoue (AssertionError) si on l'atteint ;
# seul un pytest.raises(KeyError) qui n'attrape PAS cette AssertionError démontre que la garde
# amont a bien coupé le chemin avant detect().
#
# Cycle RED-GREEN exécuté (preuve, voir rapport de la story) :
#   1. RED  : garde de plan() neutralisée en `if False:` -> plan() appelle detect() -> la
#             sentinelle lève AssertionError -> pytest.raises(KeyError) ne l'attrape pas ->
#             CE TEST ÉCHOUE (confirmé : 1 failed).
#   2. Garde restaurée (`if name not in OPERATORS:`) -> CE TEST PASSE (confirmé : 1 passed).
def test_plan_operateur_inconnu_leve_avant_tout_appel_a_detect(monkeypatch):
    import forgeai.deploy.operators as operators_mod

    def _detect_ne_doit_jamais_etre_appele(name, runner):
        raise AssertionError(
            "detect() a été appelé alors que le nom est inconnu de OPERATORS : "
            "la garde de plan() ne coupe pas le chemin AVANT detect()."
        )

    monkeypatch.setattr(operators_mod, "detect", _detect_ne_doit_jamais_etre_appele)
    with pytest.raises(KeyError):
        operators_mod.plan("inexistant-pinning-cand009", _Runner({}))


# --- contrôle négatif : un nom CONNU ne lève jamais KeyError depuis plan() ------------------
def test_plan_nom_connu_ne_leve_pas_keyerror():
    for name in OPERATORS:
        try:
            plan(name, _Runner({}))  # runner vide -> detect() renverra "absent", pas d'exception
        except KeyError:
            pytest.fail(f"plan({name!r}) a levé KeyError alors que {name!r} est un opérateur connu")


def test_registre_operateurs_couvre_le_chassis():
    for name in ("external-secrets-operator", "argo-cd", "kserve"):
        assert name in OPERATORS and OPERATORS[name].crd and OPERATORS[name].chart


# --- commande CLI `forgeai operators` (handler couvert : adopt / install / inconnu) ---
def _cli_operators(monkeypatch, plan_result, name=None):
    import forgeai.cli as cli
    monkeypatch.setattr(cli, "SubprocessRunner", lambda: object())
    if isinstance(plan_result, dict):
        monkeypatch.setattr("forgeai.deploy.operators.plan", lambda n, r: plan_result)
    argv = ["operators"] + ([name] if name else [])
    return cli.main(argv)


def test_cli_operators_adopte(monkeypatch, capsys):
    from forgeai.deploy.operators import OperatorStatus
    st = OperatorStatus("external-secrets-operator", True, "helm", "external-secrets-2.7.0")
    rc = _cli_operators(monkeypatch, {"action": "adopt", "status": st, "commands": []},
                        name="external-secrets-operator")
    assert rc == 0 and "ADOPTÉ" in capsys.readouterr().out


def test_cli_operators_absent_montre_plan(monkeypatch, capsys):
    from forgeai.deploy.operators import OperatorStatus
    st = OperatorStatus("argo-cd", False, None, None)
    plan_res = {"action": "install", "status": st,
                "commands": [["helm", "repo", "add", "argo", "url"]]}
    rc = _cli_operators(monkeypatch, plan_res, name="argo-cd")
    assert rc == 0 and "ABSENT" in capsys.readouterr().out


def test_cli_operators_inconnu_retourne_erreur(monkeypatch, capsys):
    rc = _cli_operators(monkeypatch, None, name="inexistant-xyz")
    assert rc == 8
