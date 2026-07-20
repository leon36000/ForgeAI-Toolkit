"""Story E3b — preuve e2e RÉELLE : openbao branché comme store de la master key passerelle.

Opt-in : ne s'exécute QUE si `FORGEAI_E2E=1` (skip par défaut, y compris CI — déploie 2 conteneurs
réels openbao + litellm). Reproductible :

    FORGEAI_E2E=1 python3 -m pytest tests/test_vault_e2e.py -s

Prouve, via le CODE RÉEL `forgeai.secrets.vault` (le chemin exact du wizard --rag-durci) :
  1. ROUND-TRIP contre un openbao RÉEL : la master key écrite au coffre est relue à l'identique ;
  2. COFFRE PORTEUR D'AUTH : la clé RELUE du coffre authentifie la passerelle LiteLLM (HTTP 200)
     là où l'absence de clé est refusée (HTTP 401) — la valeur du coffre EST la créance qui déverrouille ;
  3. LOAD-BEARING : openbao arrêté → `VaultError` (aucun repli silencieux ; le coffre est dans le
     chemin critique). Le message d'erreur ne fuit ni le token ni la valeur (invariant secrets).

Preuve d'exécution RÉELLE journalisée au registre Registres/mission.jsonl (événement tdad_green E3b).
"""
from __future__ import annotations

import os
import secrets as pysecrets
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from forgeai.secrets.vault import VaultError, read, store

pytestmark = pytest.mark.skipif(
    os.environ.get("FORGEAI_E2E") != "1",
    reason=(
        "preuve e2e Docker (openbao + litellm réels) — skip par défaut ; preuve d'exécution RÉELLE "
        "journalisée au registre Registres/mission.jsonl (tdad_green E3b) ; rejouable avec FORGEAI_E2E=1"
    ),
)

_LITELLM_CONFIG = (
    'model_list:\n'
    '  - model_name: "probe"\n'
    '    litellm_params:\n'
    '      model: "ollama_chat/probe"\n'
    '      api_base: "http://127.0.0.1:11434"\n'
    'general_settings:\n'
    '  master_key: "os.environ/LITELLM_MASTER_KEY"\n'
)


def _ok(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=2) as r:
            return 200 <= r.status < 300
    except (urllib.error.URLError, OSError, ValueError):
        return False


def _gw(port: int, key: str | None):
    hdr = {} if key is None else {"Authorization": f"Bearer {key}"}
    req = urllib.request.Request(f"http://127.0.0.1:{port}/v1/models", headers=hdr)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def test_openbao_store_master_key_e2e(tmp_path: Path):
    bao_token = pysecrets.token_hex(16)
    master_key = "sk-" + pysecrets.token_hex(24)  # gitleaks:allow — clé de run éphémère de test
    cfg = tmp_path / "litellm-config.yaml"
    cfg.write_text(_LITELLM_CONFIG, encoding="utf-8")

    subprocess.run(["docker", "rm", "-f", "e3b-bao-test", "e3b-litellm-test"],
                   capture_output=True, text=True)
    subprocess.run(["docker", "network", "create", "e3b-test-net"], capture_output=True, text=True)
    try:
        subprocess.run([
            "docker", "run", "-d", "--name", "e3b-bao-test", "--network", "e3b-test-net",
            "-p", "18201:8200", "-e", f"BAO_DEV_ROOT_TOKEN_ID={bao_token}",
            "openbao/openbao:2.6.0",
        ], check=True, capture_output=True, text=True, timeout=120)
        subprocess.run([
            "docker", "run", "-d", "--name", "e3b-litellm-test", "--network", "e3b-test-net",
            "-p", "14001:4000", "-e", f"LITELLM_MASTER_KEY={master_key}",
            "-v", f"{cfg}:/app/litellm-config.yaml:ro",
            "ghcr.io/berriai/litellm:main-stable", "--config", "/app/litellm-config.yaml",
            "--port", "4000",
        ], check=True, capture_output=True, text=True, timeout=120)

        deadline = time.monotonic() + 120
        while time.monotonic() < deadline and not (
                _ok("http://127.0.0.1:18201/v1/sys/health")
                and _ok("http://127.0.0.1:14001/health/liveliness")):
            time.sleep(2)
        assert _ok("http://127.0.0.1:18201/v1/sys/health"), "openbao doit être en santé"
        assert _ok("http://127.0.0.1:14001/health/liveliness"), "litellm doit être en santé"

        bao = "http://127.0.0.1:18201"
        # 1) round-trip contre openbao RÉEL (chemin KV exact du wizard)
        store(bao, bao_token, "forgeai/litellm", {"master_key": master_key})
        relu = read(bao, bao_token, "forgeai/litellm").get("master_key")
        assert relu == master_key, "la master key relue du coffre doit être identique à l'écrite"

        # 2) la clé RELUE authentifie la passerelle (200) ; sans clé -> 401
        assert _gw(14001, relu) == 200, "la clé du coffre doit déverrouiller la passerelle"
        assert _gw(14001, None) == 401, "sans clé, la passerelle doit refuser (auth exigée)"

        # 3) load-bearing : coffre arrêté -> VaultError, sans fuite de secret
        subprocess.run(["docker", "stop", "e3b-bao-test"], capture_output=True, text=True)
        with pytest.raises(VaultError) as exc:
            read(bao, bao_token, "forgeai/litellm")
        assert bao_token not in str(exc.value)
        assert master_key not in str(exc.value)
    finally:
        subprocess.run(["docker", "rm", "-f", "e3b-bao-test", "e3b-litellm-test"],
                       capture_output=True, text=True)
        subprocess.run(["docker", "network", "rm", "e3b-test-net"], capture_output=True, text=True)
