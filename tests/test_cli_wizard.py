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
    monkeypatch.setattr(cli, "k3s_apply", lambda manifest: None)
    monkeypatch.setattr(cli, "k3s_wait_deployments", lambda ns, timeout_s: None)
    monkeypatch.setattr(cli, "http_ok", lambda url, timeout_s=3.0: True)  # santé k3s OK immédiatement
    code = cli.main(_argv(tmp_path, registre_path, **{"--backend": "k3s"}))
    assert code == 0, "le chemin k3s --skip-preflight ne doit PLUS lever de NameError sur http_ok"
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


def test_sous_commande_hardware_affiche_le_json(capsys):
    assert cli.main(["hardware"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert "cpu_model" in data and "ram_gb" in data
