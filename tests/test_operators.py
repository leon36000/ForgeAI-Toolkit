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

from forgeai.deploy.operators import OPERATORS, detect, fetch_releases_helm, install_argv, plan


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
        # plan() ET fetch_releases_helm() sont désormais tous deux appelés par _operators() ;
        # le runner mocké (object() nu, sans .run) ne doit jamais être sollicité directement.
        monkeypatch.setattr("forgeai.deploy.operators.plan",
                            lambda n, r, releases_helm=None: plan_result)
        monkeypatch.setattr("forgeai.deploy.operators.fetch_releases_helm", lambda r: [])
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


# --- BUG PERF (trouvé en session, jamais couvert par l'audit v7.1) -------------------------
# `forgeai operators` sans --name boucle sur les 3 opérateurs (OPERATORS) et appelle
# plan(name, runner) -> detect(name, runner) une fois PAR opérateur. Or detect() relance
# ELLE-MÊME `helm list -A -o json` (liste TOUTES les releases de TOUS les namespaces,
# indépendamment de `name`) à chaque appel : 3 opérateurs -> 3 appels Helm IDENTIQUES pour
# la même information. Ce test exécute le VRAI chemin CLI (cli.main(["operators"]), plan()/
# detect() réels, non mockés) avec un runner-espion qui compte les appels `helm list -A`.
class _RunnerCompteHelmList:
    """Runner-espion : répond à helm list / kubectl get crd, compte chaque appel reçu."""
    def __init__(self):
        self.calls: list[list[str]] = []

    def run(self, argv):
        self.calls.append(list(argv))
        joined = " ".join(argv)
        if "helm list" in joined:
            return 0, "[]"  # aucune release -> chaque opérateur retombe sur le fallback CRD
        if "kubectl" in joined and "get crd" in joined:
            return 127, ""  # CRD absent -> action "install" (peu importe pour cette preuve)
        return 127, ""

    def appels_helm_list(self):
        return [c for c in self.calls if c[:3] == ["helm", "list", "-A"]]


def test_operators_sans_nom_appelle_helm_list_une_seule_fois(monkeypatch, capsys):
    """PREUVE DU BUG (RED avant correctif, GREEN après) : `forgeai operators` sans --name
    boucle sur les 3 opérateurs du châssis (external-secrets-operator, argo-cd, kserve).
    `helm list -A -o json` liste TOUTES les releases indépendamment de l'opérateur visé :
    un seul appel doit suffire pour statuer sur les 3, jamais 3 appels identiques."""
    import forgeai.cli as cli
    runner = _RunnerCompteHelmList()
    monkeypatch.setattr(cli, "SubprocessRunner", lambda: runner)
    rc = cli.main(["operators"])
    capsys.readouterr()
    assert rc == 0
    appels = runner.appels_helm_list()
    assert len(appels) == 1, (
        f"attendu 1 seul appel `helm list -A -o json` pour statuer sur les 3 opérateurs, "
        f"obtenu {len(appels)} appels identiques {appels} "
        f"(régression : detect() rappelle helm list une fois par opérateur)"
    )


def test_operators_avec_nom_appelle_helm_list_une_seule_fois(monkeypatch, capsys):
    """Non-régression : l'usage isolé --name (un seul opérateur) continue de ne déclencher
    qu'UN SEUL appel `helm list -A -o json`, comme avant le correctif."""
    import forgeai.cli as cli
    runner = _RunnerCompteHelmList()
    monkeypatch.setattr(cli, "SubprocessRunner", lambda: runner)
    rc = cli.main(["operators", "argo-cd"])
    capsys.readouterr()
    assert rc == 0
    assert len(runner.appels_helm_list()) == 1


# --- non-régression : appel ISOLÉ de detect()/plan() sur (name, runner), sans le nouveau
# paramètre optionnel releases_helm — doit continuer à fonctionner EXACTEMENT comme avant.
def test_detect_isole_sans_releases_helm_fonctionne_comme_avant():
    r = _Runner({"helm list": (0, _HELM_ES)})
    st = detect("external-secrets-operator", r)
    assert st.present and st.source == "helm" and st.version == "external-secrets-2.7.0"
    appels_helm_list = [c for c in r.calls if c[:3] == ["helm", "list", "-A"]]
    assert len(appels_helm_list) == 1


def test_plan_isole_sans_releases_helm_fonctionne_comme_avant():
    r = _Runner({"helm list": (0, _HELM_ES)})
    p = plan("external-secrets-operator", r)
    assert p["action"] == "adopt" and p["commands"] == []
    appels_helm_list = [c for c in r.calls if c[:3] == ["helm", "list", "-A"]]
    assert len(appels_helm_list) == 1


# --- le paramètre optionnel releases_helm, quand fourni, court-circuite l'appel helm list :
# c'est le mécanisme qui permet à _operators() de factoriser l'appel entre les 3 opérateurs.
def test_detect_avec_releases_helm_fourni_ne_rappelle_pas_helm_list():
    r = _Runner({"helm list": (0, "JSON invalide si jamais appelé")})
    releases = json.loads(_HELM_ES)
    st = detect("external-secrets-operator", r, releases_helm=releases)
    assert st.present and st.source == "helm" and st.version == "external-secrets-2.7.0"
    assert not any(c[:3] == ["helm", "list", "-A"] for c in r.calls)


def test_plan_avec_releases_helm_fourni_ne_rappelle_pas_helm_list():
    r = _Runner({"helm list": (0, "JSON invalide si jamais appelé")})
    releases = json.loads(_HELM_ES)
    p = plan("external-secrets-operator", r, releases_helm=releases)
    assert p["action"] == "adopt"
    assert not any(c[:3] == ["helm", "list", "-A"] for c in r.calls)


def test_detect_avec_releases_helm_vide_retombe_sur_crd():
    """releases_helm=[] (aucune release) doit quand même retomber sur le fallback CRD,
    exactement comme un helm list qui ne trouve rien — sans jamais appeler runner.run
    pour helm list puisque la liste est déjà fournie."""
    crd = "applications.argoproj.io"
    r = _Runner({f"get crd {crd}": (0, f"customresourcedefinition.apiextensions.k8s.io/{crd}")})
    st = detect("argo-cd", r, releases_helm=[])
    assert st.present and st.source == "crd"
    assert not any(c[:3] == ["helm", "list", "-A"] for c in r.calls)


# --- robustesse : une réponse Helm JSON valide mais non-liste retombe sur une liste vide ---
@pytest.mark.parametrize("sortie", ["null", "42", '"texte"', '{"releases": []}'])
def test_fetch_releases_helm_retourne_liste_vide_pour_json_non_liste(sortie):
    r = _Runner({"helm list": (0, sortie)})
    resultat = fetch_releases_helm(r)
    assert resultat == []
    assert isinstance(resultat, list)


def test_detect_null_helm_retombe_sur_fallback_crd():
    crd = "externalsecrets.external-secrets.io"
    r = _Runner({
        "helm list": (0, "null"),
        f"get crd {crd}": (0, f"customresourcedefinition.apiextensions.k8s.io/{crd}"),
    })
    st = detect("external-secrets-operator", r)
    assert st.present is True
    assert st.source == "crd"


def test_detect_null_helm_et_crd_absent_retourne_absent():
    r = _Runner({"helm list": (0, "null")})
    st = detect("external-secrets-operator", r)
    assert st.present is False
    assert st.source is None


def test_plan_null_helm_et_crd_absent_produit_installation():
    r = _Runner({"helm list": (0, "null")})
    p = plan("external-secrets-operator", r)
    assert p["action"] == "install"


def test_detect_liste_helm_non_vide_continue_de_detecter_la_release():
    r = _Runner({"helm list": (0, _HELM_ES)})
    st = detect("external-secrets-operator", r)
    assert st.present is True
    assert st.source == "helm"
    assert st.version == "external-secrets-2.7.0"
