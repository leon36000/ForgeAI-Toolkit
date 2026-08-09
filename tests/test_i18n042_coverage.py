"""Tests ciblés I18N-042 — couverture des branches raise() nouvellement routées vers t().

Chaque test déclenche une branche `raise` précise convertie par I18N-042 (lot 2) et
laissée non exercée par la suite existante (mesuré : diff des lignes modifiées croisé
avec le rapport de couverture — même méthode que le §7 d'I18N-041). Ne teste PAS le
texte traduit lui-même (déjà couvert par la parité stricte fr/en et par
tests/test_i18n_catalogue.py) : chaque test déclenche la branche réelle et vérifie
que l'exception attendue est bien levée.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from forgeai.audit.immudb import LedgerError, open_session, record
import forgeai.audit.immudb as immudb_module
from forgeai.catalogue.loader import CatalogueError, minimal_stack
from forgeai.ide import bootstrap as bootstrap_module
from forgeai.ide.bootstrap import IDEError, _normalize_hook
from forgeai.ide import guard_fs as guard_fs_module
from forgeai.ide.guard_fs import generate_guard_fs
from forgeai.loop import LoopError, run_loop
from forgeai.models._locking import file_lock
from forgeai.models.budget import BudgetError, BudgetTracker
from forgeai.models.local import LocalModelError, LocalModel, deploy
from forgeai.models.strategy import StrategyError, resolve_spec
from forgeai.network.keys import KeyError_, generate_keypair
from forgeai.network.node_add import NodeAddError, SshBootstrapper
from forgeai.network.nodes import ClusterError, cluster_status
from forgeai.network.prepare import PrepareError, sonder_noeud
from forgeai.network.remote_probe import RemoteProbeError, enroll_hostkey
from forgeai.observability.langfuse import ObservabilityError, count_traces
import forgeai.observability.langfuse as langfuse_module
from forgeai.planner.assemble import _next_chassis_port
from forgeai.rag.hardened import HardenedRagClient
from forgeai.secrets.vault import VaultError, read as vault_read
import forgeai.secrets.vault as secrets_vault_module


class _FakeResp:
    """Context manager minimal simulant urllib.request.urlopen(...)."""

    def __init__(self, body: bytes) -> None:
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self) -> bytes:
        return self._body


class _Runner:
    """Runner de test générique : retourne (code, sortie) fixes, journalise les appels."""

    def __init__(self, code: int, out: str = "") -> None:
        self.code = code
        self.out = out
        self.calls: list[list[str]] = []

    def run(self, argv: list[str]):
        self.calls.append(argv)
        return self.code, self.out


class _SeqRunner:
    """Runner de test retournant une réponse différente à chaque appel, dans l'ordre."""

    def __init__(self, responses: list[tuple[int, str]]) -> None:
        self._responses = list(responses)
        self.calls: list[list[str]] = []

    def run(self, argv: list[str]):
        self.calls.append(argv)
        return self._responses.pop(0)


# ---------------------------------------------------------------------------
# audit/immudb.py
# ---------------------------------------------------------------------------

def test_immudb_request_reponse_illisible(monkeypatch):
    monkeypatch.setattr(
        immudb_module.urllib.request, "urlopen",
        lambda req, timeout: _FakeResp(b"ceci n'est pas du JSON"),
    )
    with pytest.raises(LedgerError, match="réponse illisible"):
        immudb_module._request("POST", "http://x/y", None, {"a": 1}, 1.0)


def test_immudb_open_session_sessionid_absent(monkeypatch):
    monkeypatch.setattr(immudb_module, "_request", lambda *a, **k: {})
    with pytest.raises(LedgerError, match="sessionID"):
        open_session("http://x", "user", "pw")


def test_immudb_record_transaction_absent(monkeypatch):
    monkeypatch.setattr(immudb_module, "_request", lambda *a, **k: {"documentIds": []})
    with pytest.raises(LedgerError, match="transactionId"):
        record("http://x", "tok", "coll", {"a": 1})


# ---------------------------------------------------------------------------
# catalogue/loader.py
# ---------------------------------------------------------------------------

def test_minimal_stack_champs_manquants(tmp_path):
    deploy_path = tmp_path / "deploy-minimal.json"
    deploy_path.write_text(
        json.dumps({"services": [{"name": "svc-incomplet"}]}), encoding="utf-8"
    )
    with pytest.raises(CatalogueError, match="champs manquants"):
        minimal_stack(deploy_path)


# ---------------------------------------------------------------------------
# cli.py — _read_secret
# ---------------------------------------------------------------------------

def test_cli_read_secret_env_var_vide(monkeypatch):
    from forgeai.cli import _read_secret
    from forgeai.models.routes import RouteError

    monkeypatch.delenv("FORGEAI_TEST_EMPTY_SECRET", raising=False)
    with pytest.raises(RouteError, match="vide ou absente"):
        _read_secret("FORGEAI_TEST_EMPTY_SECRET", "prompt")


# ---------------------------------------------------------------------------
# ide/bootstrap.py
# ---------------------------------------------------------------------------

def test_normalize_hook_type_invalide_leve_ideerror():
    with pytest.raises(IDEError, match="type de hook invalide"):
        _normalize_hook(42)  # ni str ni HookSpec


def test_generate_mcp_config_ide_non_supporte_via_derive_future(monkeypatch):
    """MCP_CAPABLE étendu artificiellement à un IDE non géré par l'if/elif —
    simule la dérive future que la garde `else` anticipe (branche inatteignable
    via l'API publique actuelle, même motif que I18N-041 §7 sur portability.py)."""
    monkeypatch.setattr(bootstrap_module, "MCP_CAPABLE", ("claude-code", "cline", "cursor", "opencode", "futur-ide"))
    servers = [bootstrap_module.McpServer(name="s", url="http://x")]
    with pytest.raises(IDEError, match="non supporté"):
        bootstrap_module.generate_mcp_config("futur-ide", servers)


# ---------------------------------------------------------------------------
# ide/guard_fs.py
# ---------------------------------------------------------------------------

def test_generate_guard_fs_emplacement_absent_du_template(tmp_path, monkeypatch):
    monkeypatch.setattr(guard_fs_module, "_SCRIPT_TEMPLATE", "script sans les 3 jetons attendus")
    with pytest.raises(IDEError, match="__FORGEAI_ROOT__"):
        generate_guard_fs(tmp_path)


# ---------------------------------------------------------------------------
# loop.py
# ---------------------------------------------------------------------------

def test_run_loop_max_iterations_invalide():
    with pytest.raises(LoopError, match="max_iterations"):
        run_loop(step=lambda i: None, is_complete=lambda: True, max_iterations=0)


# ---------------------------------------------------------------------------
# models/_locking.py — recontrôle post-open (TOCTOU)
# ---------------------------------------------------------------------------

def test_file_lock_verrou_non_regulier_apres_ouverture(tmp_path, monkeypatch):
    """Le contrôle avant-ouverture (lstat) passe (fichier absent), mais le fd
    fraîchement ouvert est simulé non-régulier : exerce le RECONTRÔLE après
    os.open, distinct du contrôle avant-ouverture (déjà couvert ailleurs)."""
    from forgeai.models import _locking as locking_module

    class _FakeStatResult:
        st_mode = 0  # aucun bit S_ISREG

    def fake_fstat(fd):
        return _FakeStatResult()

    monkeypatch.setattr(locking_module.os, "fstat", fake_fstat)
    target = tmp_path / "verrou-cible"
    with pytest.raises(OSError, match="fichier régulier"):
        with file_lock(target):
            pass


def test_journal_vault_path_identite_invalide(tmp_path):
    from forgeai.models._locking import _journal_vault_path

    with pytest.raises(ValueError, match="identité de coffre invalide"):
        _journal_vault_path(tmp_path, {"vault_name": "autre-fichier.json"})


def test_restore_models_transaction_locked_coffre_ne_correspond_pas(tmp_path):
    from forgeai.models._locking import restore_models_transaction_locked

    home = tmp_path / "home"
    home.mkdir()
    vault_path_inattendu = tmp_path / "ailleurs" / "vault.json"
    with pytest.raises(ValueError, match="ne correspond pas au journal"):
        restore_models_transaction_locked(home, vault_path_inattendu, {"vault_name": "vault.json"})


# ---------------------------------------------------------------------------
# models/budget.py
# ---------------------------------------------------------------------------

def test_budget_load_structure_inattendue(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    (home / "budgets.json").write_text("[1, 2, 3]", encoding="utf-8")
    tracker = BudgetTracker(home)
    with pytest.raises(BudgetError, match="structure inattendue"):
        tracker.status("agent-x")


# ---------------------------------------------------------------------------
# models/local.py
# ---------------------------------------------------------------------------

def test_deploy_moteur_inconnu():
    model = LocalModel(
        name="m", engine="moteur-fantome", vram_required_mb=100,
        model_ref="ref", download_url="http://x", sha256="0" * 64,
    )
    with pytest.raises(LocalModelError, match="moteur inconnu"):
        deploy(model, _Runner(0))


# ---------------------------------------------------------------------------
# models/strategy.py
# ---------------------------------------------------------------------------

def test_resolve_spec_liste_roles_vide():
    with pytest.raises(StrategyError, match="liste de rôles vide"):
        resolve_spec("cerveau-unique", custom_roles=["   ", ""])


# ---------------------------------------------------------------------------
# network/keys.py
# ---------------------------------------------------------------------------

def test_generate_keypair_ssh_keygen_echec(tmp_path):
    with pytest.raises(KeyError_, match="ssh-keygen a échoué"):
        generate_keypair(tmp_path, _Runner(1, "erreur simulée"))


# ---------------------------------------------------------------------------
# network/node_add.py
# ---------------------------------------------------------------------------

def test_install_key_timeout(monkeypatch, tmp_path):
    import subprocess as subprocess_module
    from forgeai.network import node_add as node_add_module

    monkeypatch.setattr(node_add_module, "enroll_hostkey", lambda *a, **k: str(tmp_path / "kh"))
    (tmp_path / "kh").write_text("", encoding="utf-8")

    def fake_run(cmd, **kwargs):
        raise subprocess_module.TimeoutExpired(cmd=cmd, timeout=1)

    monkeypatch.setattr(node_add_module.subprocess, "run", fake_run)
    bootstrapper = SshBootstrapper(timeout_s=1.0, hostkey_sha256="SHA256:abc")
    with pytest.raises(NodeAddError, match="Timeout"):
        bootstrapper.install_key("1.2.3.4", "user", "pw", tmp_path / "pubkey")


# ---------------------------------------------------------------------------
# network/nodes.py
# ---------------------------------------------------------------------------

def test_cluster_status_sortie_illisible():
    with pytest.raises(ClusterError, match="sortie kubectl illisible"):
        cluster_status(_Runner(0, "{ceci n'est pas du JSON"))


def test_cluster_status_aucun_noeud():
    with pytest.raises(ClusterError, match="aucun nœud"):
        cluster_status(_Runner(0, json.dumps({"items": []})))


# ---------------------------------------------------------------------------
# network/prepare.py
# ---------------------------------------------------------------------------

def test_sonder_noeud_sortie_illisible():
    runner = _Runner(0, "{pas du JSON valide")
    with pytest.raises(PrepareError, match="sortie kubectl illisible"):
        sonder_noeud(runner, "hote-x")


def test_sonder_noeud_rc_non_nul_liste_noeuds_connus():
    """CAND-015 — quand `kubectl get node <hostname>` échoue (rc != 0), sonder_noeud
    doit interroger `kubectl get nodes` pour lister les nœuds connus et lever
    PrepareError en citant le hostname absent ET les noms trouvés (message
    network.prepare.sonder_noeud.noeud_absent). Non pinné avant CAND-015 : sans la
    garde `if rc != 0:`, le stdout vide de l'échec est passé tel quel à json.loads()
    et produit une erreur "sortie kubectl illisible" (message DIFFÉRENT) au lieu du
    diagnostic attendu."""
    runner = _SeqRunner([
        (1, ""),  # kubectl get node hote-x -o json : échec
        (0, json.dumps({"items": [{"metadata": {"name": "n1"}},
                                   {"metadata": {"name": "n2"}}]})),
    ])
    with pytest.raises(PrepareError) as exc_info:
        sonder_noeud(runner, "hote-x")

    message = str(exc_info.value)
    assert "hote-x" in message
    assert "absent ou injoignable" in message
    assert "n1" in message and "n2" in message
    assert runner.calls == [
        ["kubectl", "get", "node", "hote-x", "-o", "json"],
        ["kubectl", "get", "nodes", "-o", "json"],
    ]


# ---------------------------------------------------------------------------
# network/remote_probe.py
# ---------------------------------------------------------------------------

def test_enroll_hostkey_keyscan_timeout(monkeypatch):
    import subprocess as subprocess_module
    from forgeai.network import remote_probe as remote_probe_module

    def fake_run(cmd, **kwargs):
        raise subprocess_module.TimeoutExpired(cmd=cmd, timeout=1)

    monkeypatch.setattr(remote_probe_module.subprocess, "run", fake_run)
    with pytest.raises(RemoteProbeError, match="timeout"):
        enroll_hostkey("hote-x", "SHA256:abc", timeout_s=1.0)


def test_enroll_hostkey_keyscan_vide(monkeypatch):
    from forgeai.network import remote_probe as remote_probe_module

    class _EmptyScan:
        stdout = ""

    monkeypatch.setattr(remote_probe_module.subprocess, "run", lambda *a, **k: _EmptyScan())
    with pytest.raises(RemoteProbeError, match="n'a retourné aucune clé"):
        enroll_hostkey("hote-x", "SHA256:abc", timeout_s=1.0)


# ---------------------------------------------------------------------------
# observability/langfuse.py
# ---------------------------------------------------------------------------

def test_langfuse_get_reponse_illisible(monkeypatch):
    monkeypatch.setattr(
        langfuse_module.urllib.request, "urlopen",
        lambda req, timeout: _FakeResp(b"pas du JSON"),
    )
    with pytest.raises(ObservabilityError, match="réponse illisible"):
        count_traces("http://x", "pk", "sk")


# ---------------------------------------------------------------------------
# planner/assemble.py
# ---------------------------------------------------------------------------

def test_next_chassis_port_aucun_port_libre():
    with pytest.raises(RuntimeError, match="Aucun port libre"):
        _next_chassis_port(used_ports=set(), is_free=lambda port: False)


# ---------------------------------------------------------------------------
# rag/hardened.py
# ---------------------------------------------------------------------------

def test_hardened_rag_client_champs_obligatoires_gateway_key_absente():
    with pytest.raises(ValueError, match="obligatoires"):
        HardenedRagClient(
            ollama_url="http://x", qdrant_url="http://y",
            llm_model="m", embed_model="e",
            tei_url="http://tei", gateway_url="http://gw", gateway_key="",
        )


# ---------------------------------------------------------------------------
# secrets/vault.py
# ---------------------------------------------------------------------------

def test_vault_request_reponse_illisible(monkeypatch):
    monkeypatch.setattr(
        secrets_vault_module.urllib.request, "urlopen",
        lambda req, timeout: _FakeResp(b"pas du JSON"),
    )
    with pytest.raises(VaultError, match="réponse illisible"):
        vault_read("http://x", "token", "chemin/secret")
