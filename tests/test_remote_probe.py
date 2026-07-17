"""Tests pour remote_probe.py — sonde matérielle distante via SSH (fixtures réelles)."""
import json
import sys
from pathlib import Path
from typing import Dict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest
from forgeai.core.runner import FixtureRunner
from forgeai.network.remote_probe import (
    NodeProbe,
    RemoteProbeError,
    probe_remote_node,
)

FIXTURES = Path(__file__).parent / "fixtures" / "hardware"


def _make_fixture_runner(overrides: Dict[str, str] = None) -> FixtureRunner:
    """Crée un FixtureRunner avec les sorties capturées (docker OK, kubectl indispo)."""
    outputs = {
        "cat": (FIXTURES / "meminfo_46g.txt").read_text(encoding="utf-8"),
        "lscpu": (FIXTURES / "lscpu_amd64.json").read_text(encoding="utf-8"),
        "nvidia-smi": (FIXTURES / "nvidia_smi_rtx5090.txt").read_text(encoding="utf-8"),
        "lspci": (FIXTURES / "lspci_nn_gpu.txt").read_text(encoding="utf-8"),
        "df": (FIXTURES / "df_root.txt").read_text(encoding="utf-8"),
        "docker": "Docker version 27.0.3, build ...",
        # kubectl ABSENT du dict => FixtureRunner renvoie 127 (indisponible) ; un override
        # {"kubectl": "..."} le rend disponible (=> backend k3s).
    }
    if overrides:
        outputs.update(overrides)
    return FixtureRunner(outputs)


def test_probe_journalise_fiche_et_profil(tmp_path):
    """La sonde journalise la fiche matérielle et renvoie un profil."""
    fx = _make_fixture_runner()
    registre = tmp_path / "registre.jsonl"
    result = probe_remote_node("n1", runner=fx, registre_path=str(registre))

    assert isinstance(result, NodeProbe)
    assert result.node_host == "n1"
    assert isinstance(result.profile, str) and result.profile != ""
    assert isinstance(result.backends, list)
    assert isinstance(result.hardware, dict)

    hw = result.hardware
    assert hw.get("cpu_cores", 0) > 0
    assert 40 < hw.get("ram_gb", 0) < 50  # fixture = ~46.1 GiB

    # Vérification du registre jsonl
    assert registre.exists()
    entries = registre.read_text(encoding="utf-8").strip().splitlines()
    assert len(entries) >= 1
    first = json.loads(entries[0])
    assert first["type"] == "node_hardware"
    assert first["actor"] == "network"
    payload = first["payload"]
    assert payload["node_host"] == "n1"
    assert payload["profile"] == result.profile
    assert payload["backends"] == result.backends
    assert payload["hardware"] == result.hardware


def test_backends_derives_de_la_fiche(tmp_path):
    """Les backends sont déduits des préchecks (docker => compose, kubectl => k3s)."""
    # Cas 1 : docker OK, kubectl absent
    fx = _make_fixture_runner()
    registre = tmp_path / "registre1.jsonl"
    probe = probe_remote_node("n1", runner=fx, registre_path=str(registre))
    assert probe.backends == ["compose"], f"Attendu ['compose'], obtenu {probe.backends}"

    # Cas 2 : docker OK + kubectl OK
    fx_kube = _make_fixture_runner({"kubectl": "kubectl v1.30 ..."})
    registre2 = tmp_path / "registre2.jsonl"
    probe2 = probe_remote_node("n2", runner=fx_kube, registre_path=str(registre2))
    assert "k3s" in probe2.backends
    assert "compose" in probe2.backends


def test_meminfo_distant_illisible_leve(tmp_path):
    """Si le `cat /proc/meminfo` échoue, lève RemoteProbeError."""

    class FailingRunner:
        def run(self, argv):
            if argv == ["cat", "/proc/meminfo"]:
                return 1, ""
            return 0, ""

    with pytest.raises(RemoteProbeError, match="meminfo distant illisible"):
        probe_remote_node("n1", runner=FailingRunner(), registre_path=str(tmp_path / "r.jsonl"))


def test_detection_passe_par_le_runner(tmp_path):
    """Preuve que l'Étape 0 délègue les commandes au runner (distant)."""
    fx = _make_fixture_runner()
    registre = tmp_path / "r.jsonl"
    _ = probe_remote_node("n1", runner=fx, registre_path=str(registre))

    # Vérification des appels enregistrés dans le FixtureRunner
    assert any("lscpu" in cmd for cmd in fx.calls), "lscpu absent des appels"
    assert any(cmd == ["cat", "/proc/meminfo"] for cmd in fx.calls), \
        "Appel exact ['cat', '/proc/meminfo'] manquant"
    # On peut aussi vérifier que le runner a bien été utilisé pour les autres commandes
    commands_called = [call[0] for call in fx.calls]
    assert "nvidia-smi" in commands_called or "lspci" in commands_called or "df" in commands_called


def test_cli_node_probe(tmp_path, monkeypatch):
    """Chemin CLI : forgeai node probe utilise un runner (ici FixtureRunner) et journalise la fiche."""
    import forgeai.network.remote_probe as rp
    from forgeai.cli import main

    fx = _make_fixture_runner()
    monkeypatch.setattr(rp, "SshRunner", lambda *a, **k: fx)
    reg = tmp_path / "r.jsonl"
    rc = main(["node", "probe", "--node-host", "n1", "--user", "forge",
               "--keyfile", str(tmp_path / "k"), "--registre", str(reg)])
    assert rc == 0
    content = reg.read_text(encoding="utf-8")
    assert "node_hardware" in content and "n1" in content and "compose" in content
