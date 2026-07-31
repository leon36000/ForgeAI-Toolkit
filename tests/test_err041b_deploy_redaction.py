import subprocess, sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import forgeai.deploy.compose as compose
import forgeai.deploy.k3s as k3s
from forgeai.deploy.compose import DeployError
from forgeai.core.redaction import REDACTED


def _fake_proc(stderr, code=1, stdout=""):
    return subprocess.CompletedProcess(args=["x"], returncode=code, stdout=stdout, stderr=stderr)


# G1
def test_compose_up_redacts_secret_in_stderr(monkeypatch):
    monkeypatch.setattr(compose, "_compose", lambda a, f: _fake_proc("env FORGEAI_API_TOKEN=" + "h" * 32))  # proof:allow
    with pytest.raises(DeployError) as e:
        compose.compose_up(Path("x.yml"))
    msg = str(e.value)
    assert "docker compose up a échoué" in msg
    assert ("h" * 32) not in msg
    # Fenêtre de 8 caractères absente
    assert "h" * 8 not in msg
    assert REDACTED in msg


# G2
def test_compose_down_redacts_secret(monkeypatch):
    monkeypatch.setattr(compose, "_compose", lambda a, f: _fake_proc("Bearer " + "e" * 40))  # proof:allow
    with pytest.raises(DeployError) as e:
        compose.compose_down(Path("x.yml"))
    msg = str(e.value)
    assert "docker compose down a échoué" in msg
    assert ("e" * 40) not in msg
    assert REDACTED in msg


# G3
def test_k3s_apply_redacts_secret(monkeypatch):
    monkeypatch.setattr(k3s, "_kubectl", lambda a, **k: _fake_proc("sk-" + "z" * 40))  # proof:allow
    with pytest.raises(DeployError) as e:
        k3s.k3s_apply(Path("m.yaml"))
    msg = str(e.value)
    assert "kubectl apply a échoué" in msg
    assert ("z" * 40) not in msg
    assert REDACTED in msg


# G4
def test_k3s_wait_deployments_redacts_secret(monkeypatch):
    class MockKubectl:
        def __init__(self):
            self.calls = 0

        def __call__(self, args, **kwargs):
            self.calls += 1
            if self.calls == 1:
                # premier appel: wait échoue avec secret
                return _fake_proc("password=" + "f" * 24, code=1)  # proof:allow
            else:
                # deuxième appel: get pods réussit
                return _fake_proc("", code=0, stdout="pod1   1/1   Running")

    monkeypatch.setattr(k3s, "_kubectl", MockKubectl())
    with pytest.raises(DeployError) as e:
        k3s.k3s_wait_deployments("ns")
    msg = str(e.value)
    assert "Déploiements non disponibles" in msg
    assert ("f" * 24) not in msg
    assert REDACTED in msg


# G5
def test_k3s_delete_namespace_redacts_secret(monkeypatch):
    monkeypatch.setattr(k3s, "_kubectl", lambda a, **k: _fake_proc("api_key=" + "h" * 32))  # proof:allow
    with pytest.raises(DeployError) as e:
        k3s.k3s_delete_namespace("ns")
    msg = str(e.value)
    assert "kubectl delete namespace a échoué" in msg
    assert ("h" * 32) not in msg
    assert REDACTED in msg


# G6
def test_no_redaction_on_non_secret_stderr(monkeypatch):
    error_msg = "erreur réseau timeout"
    monkeypatch.setattr(compose, "_compose", lambda a, f: _fake_proc(error_msg))
    with pytest.raises(DeployError) as e:
        compose.compose_up(Path("x.yml"))
    msg = str(e.value)
    assert error_msg in msg
    assert REDACTED not in msg


# G7
def test_compose_up_success_no_error(monkeypatch):
    monkeypatch.setattr(compose, "_compose", lambda a, f: _fake_proc("", code=0))
    # Ne doit pas lever
    compose.compose_up(Path("x.yml"))
