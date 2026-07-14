"""Tests CLI P3 — `forgeai doctor` et l'abort préflight du wizard (portabilité)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import forgeai.cli as cli
from forgeai.core.runner import FixtureRunner
from forgeai.hardware.detect import HardwareDetector

FIXTURES = Path(__file__).parent / "fixtures" / "hardware"
DOC = Path(__file__).parent / "fixtures" / "rag" / "faits_forgeai.txt"


def _fake_detector():
    outputs = {
        "lscpu": (FIXTURES / "lscpu_amd64.json").read_text(encoding="utf-8"),
        "nvidia-smi": "", "lspci": "",
        "df": (FIXTURES / "df_root.txt").read_text(encoding="utf-8"),
    }
    return HardwareDetector(FixtureRunner(outputs),
                            meminfo_path=str(FIXTURES / "meminfo_46g.txt"))


class BareRunner:
    """Aucun outil installé : tout retourne 127."""
    def run(self, argv):
        return 127, ""


def test_doctor_machine_nue_affiche_tout_et_ne_plante_pas(monkeypatch, capsys):
    monkeypatch.setattr(cli, "SubprocessRunner", BareRunner)
    monkeypatch.setattr(cli, "HardwareDetector", lambda runner: _fake_detector())
    # http_ok importé dans _doctor depuis deploy.compose → forcer un échec propre
    import forgeai.deploy.compose as dc
    monkeypatch.setattr(dc, "http_ok", lambda url, timeout_s=3.0: False)
    code = cli.main(["doctor"])
    out = capsys.readouterr().out
    assert code == 0
    assert "docker" in out and "kubectl" in out and "ollama" in out
    assert "Aucun backend de déploiement prêt" in out


def test_wizard_abort_si_backend_indisponible(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli, "SubprocessRunner", BareRunner)
    monkeypatch.setattr(cli, "HardwareDetector", lambda runner: _fake_detector())
    import forgeai.deploy.compose as dc
    monkeypatch.setattr(dc, "http_ok", lambda url, timeout_s=3.0: False)
    code = cli.main([
        "wizard", "--ci", "--backend", "compose", "--workdir", str(tmp_path / "run"),
        "--registre", str(tmp_path / "r.jsonl"), "--document", str(DOC),
        "--question", "Q ?", "--expected-fact", "3.10",
    ])
    err = capsys.readouterr().err
    assert code == 6
    assert "indisponible" in err
