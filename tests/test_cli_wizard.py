"""Tests S10 — wizard --ci : chaîne complète avec frontières externes simulées
(docker/ollama/qdrant mockés — tests/ uniquement; le comportement réel est prouvé
par les e2e journalisés au registre, seq preuve_e2e compose et k3s)."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import forgeai.cli as cli

REPO = Path(__file__).resolve().parent.parent
DOC = REPO / "tests" / "fixtures" / "rag" / "faits_forgeai.txt"


class FakeRag:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def pull_models(self):
        return None

    def ingest(self, text, source):
        assert text.strip()
        return 3

    def ask(self, question):
        return {"answer": "Il faut Python 3.10 minimum.", "sources": ["doc"],
                "context_used": True}


class FakeDetector:
    """Le runner CI (disque < 25 Go libres) ferait échouer la dérivation de profil :
    ces tests visent le câblage du CLI — la détection réelle a ses tests dédiés."""

    def __init__(self, runner):
        self.runner = runner

    def full_report(self):
        from forgeai.core.models import Disk, HardwareProfile
        return HardwareProfile(
            cpu_model="ci", cpu_cores=4, cpu_arch="x86_64", ram_gb=32.0,
            os_name="Linux CI",
            disks=(Disk(path="/", total_gb=1000.0, free_gb=500.0),),
        )


@pytest.fixture
def wired(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "HardwareDetector", FakeDetector)
    monkeypatch.setattr(cli, "compose_up", lambda f: None)
    monkeypatch.setattr(cli, "compose_down", lambda f, volumes=False: None)
    monkeypatch.setattr(cli, "wait_healthy",
                        lambda plan, timeout_s: {s.name: "healthy" for s in plan.services})
    monkeypatch.setattr(cli, "RagClient", FakeRag)
    registre_path = tmp_path / "reg.jsonl"
    return tmp_path, registre_path


def _argv(tmp_path, registre_path, **extra):
    argv = ["wizard", "--ci", "--workdir", str(tmp_path / "run"),
            "--registre", str(registre_path), "--document", str(DOC),
            "--question", "Quelle version de Python ?",
            "--expected-fact", extra.pop("fact", "3.10"),
            "--teardown", "--skip-preflight"]
    for key, value in extra.items():
        argv += [key, value]
    return argv


def test_wizard_ci_succes_scelle_la_preuve(wired, capsys):
    tmp_path, registre_path = wired
    code = cli.main(_argv(tmp_path, registre_path))
    out = capsys.readouterr().out
    assert code == 0
    assert "CI_WITNESS=" in out and "RAG_OK=true" in out
    entry = json.loads(registre_path.read_text(encoding="utf-8").splitlines()[-1])
    assert entry["type"] == "preuve_e2e"
    assert entry["payload"]["backend"] == "compose"
    # artefacts écrits
    run_dir = tmp_path / "run"
    assert (run_dir / "hardware.json").exists()
    assert (run_dir / "plan.json").exists()
    assert (run_dir / "docker-compose.yaml").exists()
    assert (run_dir / "k3s.yaml").exists()


def test_wizard_ci_k3s_skip_preflight_ne_nameerror_pas(wired, monkeypatch, capsys):
    """Régression FIX-HTTPOK : --skip-preflight + backend k3s exécute `http_ok` dans la boucle de
    santé k3s (ligne ~413) ALORS que http_ok n'était importé QUE dans le bloc preflight (sauté par
    --skip-preflight) -> NameError. http_ok est désormais importé au NIVEAU MODULE, donc toujours
    défini. `monkeypatch.setattr(cli, "http_ok", ...)` EXIGE d'ailleurs que l'attribut existe au module
    (impossible avant le fix) — double garde. Le chemin k3s complet doit rendre RC=0 et sceller la preuve."""
    tmp_path, registre_path = wired
    # Toutes les fonctions kubectl du chemin k3s sont mockées -> test indépendant de tout cluster.
    monkeypatch.setattr(cli, "k3s_apply", lambda manifest: None)
    monkeypatch.setattr(cli, "k3s_wait_deployments", lambda ns, timeout_s: None)
    monkeypatch.setattr(cli, "k3s_delete_namespace", lambda ns: None)  # teardown --teardown
    # http_ok enregistre ses appels : preuve DIRECTE que la ligne de la boucle de santé k3s s'exécute
    # (avant le fix, http_ok n'était pas au module -> NameError ; monkeypatch.setattr l'exige d'ailleurs).
    appels_http_ok: list[str] = []
    monkeypatch.setattr(cli, "http_ok",
                        lambda url, timeout_s=3.0: (appels_http_ok.append(url), True)[1])
    code = cli.main(_argv(tmp_path, registre_path, **{"--backend": "k3s"}))
    assert appels_http_ok, "http_ok doit être APPELÉ dans la boucle de santé k3s (aucune NameError)"
    assert code == 0, "le chemin k3s --skip-preflight complet doit réussir (RC=0)"
    entry = json.loads(registre_path.read_text(encoding="utf-8").splitlines()[-1])
    assert entry["type"] == "preuve_e2e"
    assert entry["payload"]["backend"] == "k3s"


def test_wizard_ci_fait_absent_retourne_9(wired, capsys):
    tmp_path, registre_path = wired
    code = cli.main(_argv(tmp_path, registre_path, fact="fait-introuvable-xyz"))
    assert code == 9
    assert not registre_path.exists()  # aucune preuve scellée sur échec


def test_wizard_ci_profil_insuffisant_retourne_7(wired, monkeypatch):
    tmp_path, registre_path = wired
    from forgeai.planner.profile import ProfileError
    def refuse(hw):
        raise ProfileError("RAM insuffisante", code="ERR_HW_MIN")
    monkeypatch.setattr(cli, "derive_profile", refuse)
    assert cli.main(_argv(tmp_path, registre_path)) == 7


def test_wizard_ci_echec_deploiement_retourne_8(wired, monkeypatch):
    tmp_path, registre_path = wired
    from forgeai.deploy.compose import DeployError
    def boom(f):
        raise DeployError("docker indisponible")
    monkeypatch.setattr(cli, "compose_up", boom)
    assert cli.main(_argv(tmp_path, registre_path)) == 8


# --- BUG teardown orphelin (trouvé en session, jamais couvert par l'audit v7.1) -----------
# `compose_up`/`k3s_apply` s'exécutaient AVANT le `try/finally` protecteur de wizard_ci. Un
# échec PENDANT la création (donc potentiellement APRÈS que des ressources aient déjà été
# créées, ex. certains conteneurs démarrés par un `compose up -d` qui échoue en cours de route)
# sortait de la fonction sans jamais atteindre le `finally` — --teardown n'était alors JAMAIS
# honoré, laissant des ressources orphelines sur l'hôte/le cluster.
def test_wizard_ci_teardown_appele_meme_si_echec_avant_lancien_try(wired, monkeypatch):
    """Preuve de la garde (RED avant correctif, GREEN après) : `compose_up` échoue — c'est
    l'étape de création la plus précoce protégeable en backend compose (avant elle, seuls le
    plan/les rendus de fichiers sont écrits, rien n'existe encore sur l'hôte). --teardown est
    demandé -> compose_down DOIT être appelé malgré l'échec, pour ne jamais laisser de
    ressources orphelines."""
    tmp_path, registre_path = wired
    from forgeai.deploy.compose import DeployError
    appels_down = []
    monkeypatch.setattr(cli, "compose_down",
                        lambda f, volumes=False: appels_down.append((f, volumes)))
    def boom(f):
        raise DeployError("docker indisponible EN COURS de création")
    monkeypatch.setattr(cli, "compose_up", boom)
    code = cli.main(_argv(tmp_path, registre_path))  # --teardown déjà dans _argv par défaut
    assert code == 8
    assert appels_down, (
        "compose_down DOIT être appelé même si compose_up échoue AVANT l'ancien try/finally "
        "— sinon --teardown ne nettoie rien sur cet échec (ressources orphelines)"
    )


def test_wizard_ci_teardown_appele_meme_si_echec_avant_lancien_try_k3s(wired, monkeypatch):
    """Même garde, backend k3s : `k3s_apply` échoue avant l'ancien try/finally -> le namespace
    DOIT quand même être nettoyé si --teardown est demandé (même classe de bug que compose)."""
    tmp_path, registre_path = wired
    from forgeai.deploy.compose import DeployError
    appels_delete = []
    monkeypatch.setattr(cli, "k3s_delete_namespace", lambda ns: appels_delete.append(ns))
    monkeypatch.setattr(cli, "k3s_wait_deployments", lambda ns, timeout_s: None)
    def boom(manifest):
        raise DeployError("kubectl apply EN ECHEC")
    monkeypatch.setattr(cli, "k3s_apply", boom)
    code = cli.main(_argv(tmp_path, registre_path, **{"--backend": "k3s"}))
    assert code == 8
    assert appels_delete, (
        "k3s_delete_namespace DOIT être appelé même si k3s_apply échoue AVANT l'ancien "
        "try/finally — sinon --teardown ne nettoie rien sur cet échec (namespace orphelin)"
    )


def test_wizard_ci_sans_teardown_aucun_nettoyage_sur_echec(wired, monkeypatch):
    """Non-régression : SANS --teardown, un échec de compose_up ne doit déclencher AUCUN
    nettoyage — élargir le try/finally ne doit pas faire apparaître un nettoyage non demandé."""
    tmp_path, registre_path = wired
    from forgeai.deploy.compose import DeployError
    appels_down = []
    monkeypatch.setattr(cli, "compose_down",
                        lambda f, volumes=False: appels_down.append((f, volumes)))
    def boom(f):
        raise DeployError("docker indisponible")
    monkeypatch.setattr(cli, "compose_up", boom)
    argv = [a for a in _argv(tmp_path, registre_path) if a != "--teardown"]
    code = cli.main(argv)
    assert code == 8
    assert not appels_down, "sans --teardown, aucun nettoyage ne doit être déclenché sur échec"


def test_sous_commande_hardware_affiche_le_json(capsys):
    assert cli.main(["hardware"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert "cpu_model" in data and "ram_gb" in data


def test_wizard_ci_dry_run_ok(wired):
    """I18N-031 : couvre `cli.wizard.dry_run_ok` (return anticipé avant tout déploiement) —
    jamais exercé par aucun test avant, alors que --dry-run est le mode le plus sûr d'essayer
    le wizard (aucun conteneur, aucun manifeste appliqué)."""
    tmp_path, registre_path = wired
    code = cli.main(_argv(tmp_path, registre_path) + ["--dry-run"])
    assert code == 0
    assert not registre_path.exists(), "--dry-run ne doit sceller aucune preuve e2e"


def test_wizard_ci_selection_happy_path(wired, tmp_path):
    """I18N-031 : chemin --selection valide de bout en bout (aucune branche d'erreur) —
    couvre `cli.wizard.selection_resume`, jamais exercé par aucun test avant I18N-031."""
    selection = tmp_path / "selection.json"
    selection.write_text(json.dumps({
        "bricks": [], "models": [], "embeddings": [], "rag_node": None, "adopt": {},
    }), encoding="utf-8")
    run_tmp, registre_path = wired
    code = cli.main(_argv(run_tmp, registre_path, **{"--selection": str(selection)})
                     + ["--dry-run"])
    assert code == 0


@pytest.mark.parametrize("selection_payload,rc_attendu", [
    ("PAS_DU_JSON_VALIDE", 8),
    ({"bricks": ["brique-totalement-inconnue-xyz"]}, 8),
    ({"models": [{"hf_id": "modele-inconnu-xyz", "node": "auto", "engine": "vllm"}]}, 8),
    ({"models": [{"hf_id": "meta-llama/Llama-3.3-70B-Instruct", "node": "auto",
                  "engine": "moteur-inconnu-xyz"}]}, 8),
    ({"models": [{"hf_id": "meta-llama/Llama-3.3-70B-Instruct",
                  "node": "NOEUD INVALIDE ESPACES", "engine": "vllm"}]}, 8),
    ({"embeddings": [{"hf_id": "meta-llama/Llama-3.3-70B-Instruct", "node": "auto",
                      "engine": "vllm"}]}, 8),
    ({"rag_node": "NOEUD INVALIDE"}, 8),
    ({"adopt": {"service-jamais-dans-le-plan-xyz": "http://x"}}, 8),
])
def test_wizard_ci_selection_branches_erreur(wired, tmp_path, selection_payload, rc_attendu):
    """I18N-031 : chaque branche de validation de --selection retourne le code documenté et
    imprime un message bilingue (`cli.wizard.abort_selection_*`) — 8 branches jamais exercées
    par aucun test avant cette story, découvertes en cartographiant la couverture manquante."""
    selection = tmp_path / "selection.json"
    if isinstance(selection_payload, str):
        selection.write_text(selection_payload, encoding="utf-8")
    else:
        selection.write_text(json.dumps(selection_payload), encoding="utf-8")
    run_tmp, registre_path = wired
    code = cli.main(_argv(run_tmp, registre_path, **{"--selection": str(selection)}))
    assert code == rc_attendu


def test_wizard_ci_selection_rag_node_distant_refuse_en_compose(wired, tmp_path):
    """I18N-031 : branche spécifique — un rag_node DISTANT (hostname valide) avec le backend
    compose (mono-machine) est refusé avec RC=9, distinct des autres erreurs de sélection (8)."""
    selection = tmp_path / "selection.json"
    selection.write_text(json.dumps({"rag_node": "noeud-distant-valide"}), encoding="utf-8")
    run_tmp, registre_path = wired
    code = cli.main(_argv(run_tmp, registre_path, **{"--selection": str(selection)}))
    assert code == 9
