"""Story E3b / FAI-0005 S5 — preuve e2e RÉELLE : openbao PRODUCTION comme store de la master key.

Opt-in : ne s'exécute QUE si `FORGEAI_E2E=1` (skip par défaut, y compris CI — déploie 2 conteneurs
réels openbao + litellm). Reproductible :

    FORGEAI_E2E=1 python3 -m pytest tests/test_vault_e2e.py -s

PRODUCTION (plus de mode DEV) : openbao démarre SCELLÉ, non initialisé (storage fichier + openbao.hcl,
disable_mlock — posture conteneur standard). Le flux de déploiement RÉEL `forgeai.deploy.openbao_flow.initialize_openbao`
(cœur S2 `ensure_openbao_ready`) l'initialise, le descelle et émet un token applicatif SCOPÉ (policy
forgeai-app) — JAMAIS le root. Prouve, via le CODE RÉEL du wizard --rag-durci :
  1. AMORÇAGE : openbao scellé -> initialize_openbao -> descellé + token applicatif (root ISOLÉ du store) ;
  2. ROUND-TRIP : la master key écrite au coffre avec le token applicatif est relue à l'identique ;
  3. COFFRE PORTEUR D'AUTH : la clé RELUE authentifie la passerelle LiteLLM (HTTP 200) là où l'absence de
     clé est refusée (HTTP 401) — la valeur du coffre EST la créance qui déverrouille ;
  4. LOAD-BEARING : openbao arrêté -> `VaultError` (chemin critique) sans fuite de token/valeur.

Preuve d'exécution RÉELLE journalisée au registre Registres/mission.jsonl (événement tdad_green).
"""
from __future__ import annotations

import importlib.resources
import os
import secrets as pysecrets
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from forgeai.deploy.openbao_flow import FileKeyStore, FileSecretStore, initialize_openbao, prepare_key_store
from forgeai.secrets.vault import VaultError, read, store

pytestmark = pytest.mark.skipif(
    os.environ.get("FORGEAI_E2E") != "1",
    reason=(
        "preuve e2e Docker (openbao PROD + litellm réels) — skip par défaut ; preuve d'exécution RÉELLE "
        "journalisée au registre Registres/mission.jsonl (tdad_green) ; rejouable avec FORGEAI_E2E=1"
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


def _reachable(url: str) -> bool:
    """openbao PROD répond même SCELLÉ (501 non-init / 503 scellé) : toute réponse HTTP = process up."""
    try:
        with urllib.request.urlopen(url, timeout=2) as r:
            return r.status > 0
    except urllib.error.HTTPError:
        return True  # une réponse HTTP (même 5xx) = openbao joignable
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


def test_openbao_prod_store_master_key_e2e(tmp_path: Path):
    master_key = "sk-" + pysecrets.token_hex(24)  # gitleaks:allow — clé de run éphémère de test
    cfg = tmp_path / "litellm-config.yaml"
    cfg.write_text(_LITELLM_CONFIG, encoding="utf-8")
    hcl = tmp_path / "openbao.hcl"
    hcl.write_text(
        (importlib.resources.files("forgeai.data") / "openbao.hcl").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    # Volume NOMMÉ (pas un bind-mount hôte) : docker recopie les droits de /openbao/file (UID 100
    # openbao) sur le volume neuf -> inscriptible. Un bind-mount hôte serait possédé par le runner
    # (≠ UID 100) et openbao ne pourrait PAS y écrire (leçon e2e S6).
    subprocess.run(["docker", "volume", "rm", "s5-bao-data"], capture_output=True, text=True)

    subprocess.run(["docker", "rm", "-f", "s5-bao-test", "s5-litellm-test"],
                   capture_output=True, text=True)
    subprocess.run(["docker", "network", "create", "s5-test-net"], capture_output=True, text=True)
    try:
        # openbao PRODUCTION : storage fichier /openbao/file + openbao.hcl (disable_mlock) — démarre SCELLÉ.
        subprocess.run([
            "docker", "run", "-d", "--name", "s5-bao-test", "--network", "s5-test-net",
            "-p", "18201:8200",
            "-v", f"{hcl}:/openbao/config/openbao.hcl:ro",
            "-v", "s5-bao-data:/openbao/file",
            "openbao/openbao:2.6.0", "server", "-config=/openbao/config/openbao.hcl",
        ], check=True, capture_output=True, text=True, timeout=120)
        subprocess.run([
            "docker", "run", "-d", "--name", "s5-litellm-test", "--network", "s5-test-net",
            "-p", "14001:4000", "-e", f"LITELLM_MASTER_KEY={master_key}",
            "-v", f"{cfg}:/app/litellm-config.yaml:ro",
            "ghcr.io/berriai/litellm:main-stable", "--config", "/app/litellm-config.yaml",
            "--port", "4000",
        ], check=True, capture_output=True, text=True, timeout=120)

        bao = "http://127.0.0.1:18201"
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline and not _reachable(f"{bao}/v1/sys/health"):
            time.sleep(2)
        assert _reachable(f"{bao}/v1/sys/health"), "openbao (scellé) doit être joignable"

        # 1) AMORÇAGE : openbao scellé -> init/unseal + token applicatif scopé (le VRAI flux de déploiement)
        keys_dir = prepare_key_store(tmp_path / "openbao-keys")
        key_store = FileKeyStore(keys_dir, tmp_path / "secrets" / "openbao_root")
        secret_store = FileSecretStore(tmp_path / "secrets" / "openbao_app_token.json")
        app_token = initialize_openbao(bao, key_store, secret_store)
        assert app_token and app_token != key_store.read()["root_token"], \
            "le token applicatif doit être scopé, jamais le root"
        # le root n'est jamais tombé dans le répertoire monté à l'unsealer
        assert [e.name for e in keys_dir.iterdir()] == ["unseal_key"]

        deadline = time.monotonic() + 120
        while time.monotonic() < deadline and not (
                _ok(f"{bao}/v1/sys/health") and _ok("http://127.0.0.1:14001/health/liveliness")):
            time.sleep(2)
        assert _ok(f"{bao}/v1/sys/health"), "openbao DESCELLÉ doit être en santé (200)"
        assert _ok("http://127.0.0.1:14001/health/liveliness"), "litellm doit être en santé"

        # 2) round-trip contre openbao RÉEL avec le TOKEN APPLICATIF (chemin KV exact du wizard)
        store(bao, app_token, "forgeai/litellm", {"master_key": master_key})
        relu = read(bao, app_token, "forgeai/litellm").get("master_key")
        assert relu == master_key, "la master key relue du coffre doit être identique à l'écrite"

        # 3) la clé RELUE authentifie la passerelle (200) ; sans clé -> 401
        assert _gw(14001, relu) == 200, "la clé du coffre doit déverrouiller la passerelle"
        assert _gw(14001, None) == 401, "sans clé, la passerelle doit refuser (auth exigée)"

        # 4) load-bearing : coffre arrêté -> VaultError, sans fuite de secret
        subprocess.run(["docker", "stop", "s5-bao-test"], capture_output=True, text=True)
        with pytest.raises(VaultError) as exc:
            read(bao, app_token, "forgeai/litellm")
        assert app_token not in str(exc.value)
        assert master_key not in str(exc.value)
    finally:
        subprocess.run(["docker", "rm", "-f", "s5-bao-test", "s5-litellm-test"],
                       capture_output=True, text=True)
        subprocess.run(["docker", "volume", "rm", "s5-bao-data"], capture_output=True, text=True)
        subprocess.run(["docker", "network", "rm", "s5-test-net"], capture_output=True, text=True)
