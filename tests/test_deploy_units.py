"""Tests unitaires S06/S07 (déploiement) — services externes docker/kubectl mockés
(autorisé §8bis : tests/ uniquement, simulation d'exécutables absents du CI)."""
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from forgeai.core.models import DeploymentPlan, RenderTarget, ServiceSpec
from forgeai.deploy import compose as dc
from forgeai.deploy import k3s as dk


def _plan_with_health():
    return DeploymentPlan(
        plan_id="t", profile="minimal-cpu", target=RenderTarget.COMPOSE,
        services=(
            ServiceSpec(name="a", image="i:1", host_port=1, container_port=1,
                        healthcheck_url="http://x/health"),
            ServiceSpec(name="b", image="i:1", host_port=2, container_port=2,
                        healthcheck_url="http://y/health"),
        ),
        model="m", embed_model="e",
    )


def _proc(code=0, stderr=""):
    return subprocess.CompletedProcess(args=[], returncode=code, stdout="", stderr=stderr)


def test_wait_healthy_tous_sains():
    status = dc.wait_healthy(_plan_with_health(), timeout_s=5.0, probe=lambda url: True)
    assert status == {"a": "healthy", "b": "healthy"}


def test_wait_healthy_echec_rapporte_l_etat_exact():
    healthy_urls = {"http://x/health"}
    with pytest.raises(dc.DeployError) as exc:
        dc.wait_healthy(_plan_with_health(), timeout_s=3.0,
                        probe=lambda url: url in healthy_urls)
    assert "'a': 'healthy'" in str(exc.value)
    assert "'b': 'waiting'" in str(exc.value)


def test_compose_up_echec_leve_avec_stderr(monkeypatch, tmp_path):
    monkeypatch.setattr(dc, "_compose", lambda a, f: _proc(1, "boom réseau"))
    with pytest.raises(dc.DeployError, match="boom réseau"):
        dc.compose_up(tmp_path / "c.yaml")


def test_compose_down_ok(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(dc, "_compose", lambda a, f: calls.append(a) or _proc(0))
    dc.compose_down(tmp_path / "c.yaml", volumes=True)
    assert calls == [["down", "-v"]]


def test_http_ok_url_invalide():
    assert dc.http_ok("http://127.0.0.1:1/definitely-down", timeout_s=0.2) is False


def test_k3s_apply_echec(monkeypatch, tmp_path):
    monkeypatch.setattr(dk, "_kubectl", lambda a, timeout_s=300.0: _proc(1, "refusé"))
    with pytest.raises(dc.DeployError, match="refusé"):
        dk.k3s_apply(tmp_path / "m.yaml")


def test_k3s_wait_echec_inclut_l_etat_des_pods(monkeypatch):
    def fake(args, timeout_s=300.0):
        if args[0] == "wait":
            return _proc(1, "timed out")
        return subprocess.CompletedProcess(args=[], returncode=0,
                                           stdout="pod-a Pending", stderr="")
    monkeypatch.setattr(dk, "_kubectl", fake)
    with pytest.raises(dc.DeployError, match="pod-a Pending"):
        dk.k3s_wait_deployments("ns", timeout_s=1.0)


def test_k3s_delete_namespace_ok(monkeypatch):
    monkeypatch.setattr(dk, "_kubectl", lambda a, timeout_s=300.0: _proc(0))
    dk.k3s_delete_namespace("ns")  # ne lève pas
