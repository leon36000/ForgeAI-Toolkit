"""S5 (#146) — stores fichier + amorçage du flux openbao, et renew_self de vault.py.

Prouve (déterministe, sans cluster) : (1) FileKeyStore isole le root_token HORS du répertoire des clés
monté à l'unsealer ; (2) FileSecretStore persiste le token applicatif en 0600 ; (3) bout-en-bout avec le
VRAI `ensure_openbao_ready` (S2) sur un faux transport -> token applicatif rendu, stores peuplés, root jamais
dans keys_dir ; (4) renew_self appelle POST renew-self et ne fuit jamais le token.
"""
from __future__ import annotations

import base64
import os
import stat
import subprocess
import sys
import threading
from hashlib import sha256
from pathlib import Path
from secrets import token_hex

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from forgeai.deploy import openbao_flow
from forgeai.deploy.openbao_flow import (
    FileKeyStore,
    FileSecretStore,
    KubectlKeyStore,
    OpenBaoFlowError,
    initialize_openbao,
    prepare_key_store,
    wait_reachable,
)
from forgeai.secrets.openbao_init import ensure_openbao_ready
from forgeai.secrets.vault import VaultError, renew_self

# --- 1. prepare_key_store ---------------------------------------------------

def test_prepare_key_store_creates_and_chmod(tmp_path) -> None:
    d = tmp_path / "keys"
    assert prepare_key_store(d) == d
    assert d.is_dir()
    assert oct(d.stat().st_mode & 0o777) == "0o711"


def test_prepare_key_store_idempotent(tmp_path) -> None:
    d = tmp_path / "keys"
    d.mkdir(parents=True)
    os.chmod(d, 0o700)  # trop restrictif au départ (l'unsealer non-root ne pourrait pas traverser)
    prepare_key_store(d)
    assert oct(d.stat().st_mode & 0o777) == "0o711"


# --- 2. FileKeyStore (isolation du root) ------------------------------------

def test_file_key_store_read_none_before_write(tmp_path) -> None:
    store = FileKeyStore(tmp_path / "keys", tmp_path / "secrets" / "root_token")
    assert store.read() is None


def test_file_key_store_write_read_and_root_isolation(tmp_path) -> None:
    keys_dir = tmp_path / "keys"
    root_path = tmp_path / "secrets" / "root_token"
    store = FileKeyStore(keys_dir, root_path)
    store.write({"unseal_key": "UNSEAL", "root_token": "ROOT"})
    assert store.read() == {"unseal_key": "UNSEAL", "root_token": "ROOT"}

    # INVARIANT : le répertoire monté à l'unsealer ne contient QUE unseal_key, jamais le root.
    entries = list(keys_dir.iterdir())
    assert [e.name for e in entries] == ["unseal_key"]
    unseal = (keys_dir / "unseal_key").read_text(encoding="utf-8").strip()
    assert unseal == "UNSEAL" and "ROOT" not in unseal
    assert root_path.read_text(encoding="utf-8").strip() == "ROOT"

    # unseal_key 0644 (lisible par le conteneur unsealer non-root) ; root_token 0600 (owner seul, isolé)
    assert stat.S_IMODE((keys_dir / "unseal_key").stat().st_mode) == 0o644
    assert stat.S_IMODE(root_path.stat().st_mode) == 0o600


def test_file_key_store_modes_are_independent_of_permissive_umask(tmp_path) -> None:
    keys_dir = tmp_path / "keys"
    root_path = tmp_path / "secrets" / "root_token"
    previous_umask = os.umask(0)
    try:
        FileKeyStore(keys_dir, root_path).write(
            {"unseal_key": "UNSEAL", "root_token": "ROOT"}
        )
    finally:
        os.umask(previous_umask)

    assert stat.S_IMODE((keys_dir / "unseal_key").stat().st_mode) == 0o644
    assert stat.S_IMODE(root_path.stat().st_mode) == 0o600


# --- 3. FileSecretStore -----------------------------------------------------

def test_file_secret_store_roundtrip_and_mode(tmp_path) -> None:
    p = tmp_path / "app_token.json"
    store = FileSecretStore(p)
    assert store.read() is None
    store.write({"token": "APPTOKEN"})
    assert store.read() == {"token": "APPTOKEN"}
    assert stat.S_IMODE(p.stat().st_mode) == 0o600


def test_file_secret_store_overwrite(tmp_path) -> None:
    store = FileSecretStore(tmp_path / "t.json")
    store.write({"token": "OLD"})
    store.write({"token": "NEW"})
    assert store.read() == {"token": "NEW"}


@pytest.mark.parametrize("requested_mode", [0o600, 0o644])
def test_write_file_failure_before_replace_preserves_old_target_and_cleans_temp(
    tmp_path, monkeypatch, requested_mode
) -> None:
    target = tmp_path / "secret"
    target.write_text("old-value\n", encoding="utf-8")
    sentinel = token_hex(32)
    file_fsynced = False
    replacement_mode = None
    real_fsync = os.fsync

    def record_real_fsync(descriptor: int) -> None:
        nonlocal file_fsynced
        real_fsync(descriptor)
        if stat.S_ISREG(os.fstat(descriptor).st_mode):
            file_fsynced = True

    def fail_before_replace(source, destination) -> None:
        nonlocal replacement_mode
        if not file_fsynced:
            raise AssertionError("replacement attempted before the temporary file was fsynced")
        replacement_mode = stat.S_IMODE(Path(source).stat().st_mode)
        raise OSError("injected failure after file fsync")

    monkeypatch.setattr(openbao_flow.os, "fsync", record_real_fsync)
    monkeypatch.setattr(openbao_flow.os, "replace", fail_before_replace)
    previous_umask = os.umask(0)
    try:
        with pytest.raises(OSError) as caught:
            openbao_flow._write_file(target, sentinel, requested_mode)
    finally:
        os.umask(previous_umask)

    if sentinel in str(caught.value):
        raise AssertionError("writer exception disclosed the secret payload")
    assert replacement_mode == requested_mode
    assert target.read_text(encoding="utf-8") == "old-value\n"
    assert [entry.name for entry in tmp_path.iterdir()] == ["secret"]


def test_write_file_fsyncs_file_then_parent_directory(tmp_path, monkeypatch) -> None:
    fsync_targets: list[str] = []
    real_fsync = os.fsync

    def record_real_fsync(descriptor: int) -> None:
        target_mode = os.fstat(descriptor).st_mode
        real_fsync(descriptor)
        fsync_targets.append("directory" if stat.S_ISDIR(target_mode) else "file")

    monkeypatch.setattr(openbao_flow.os, "fsync", record_real_fsync)
    openbao_flow._write_file(tmp_path / "secret", "non-secret-test-value", 0o600)

    assert fsync_targets == ["file", "directory"]


def test_file_secret_store_refuses_target_symlink_without_touching_referent(
    tmp_path,
) -> None:
    referent = tmp_path / "external"
    referent.write_text("external-old\n", encoding="utf-8")
    target = tmp_path / "app-token.json"
    target.symlink_to(referent)
    original_link = os.readlink(target)
    sentinel = token_hex(32)

    with pytest.raises(OSError) as caught:
        FileSecretStore(target).write({"token": sentinel})

    if sentinel in str(caught.value):
        raise AssertionError("writer exception disclosed the secret payload")
    assert target.is_symlink()
    assert os.readlink(target) == original_link
    assert referent.read_text(encoding="utf-8") == "external-old\n"


def test_file_secret_store_replacements_never_expose_partial_content(tmp_path) -> None:
    target = tmp_path / "app-token.json"
    store = FileSecretStore(target)
    token_a = "A" * 65_536
    token_b = "B" * 65_536
    complete_a = '{"token": "' + token_a + '"}\n'
    complete_b = '{"token": "' + token_b + '"}\n'
    allowed_digests = {
        sha256(complete_a.encode("utf-8")).digest(),
        sha256(complete_b.encode("utf-8")).digest(),
    }
    store.write({"token": token_a})

    start = threading.Barrier(3)
    readers_started = [threading.Event(), threading.Event()]
    stop = threading.Event()
    observed_digests: set[bytes] = set()
    read_errors: list[str] = []
    observation_lock = threading.Lock()

    def reader(started: threading.Event) -> None:
        try:
            start.wait()
            first = sha256(target.read_bytes()).digest()
            with observation_lock:
                observed_digests.add(first)
            started.set()
            while not stop.is_set():
                digest = sha256(target.read_bytes()).digest()
                with observation_lock:
                    observed_digests.add(digest)
        except (OSError, RuntimeError) as exc:
            with observation_lock:
                read_errors.append(type(exc).__name__)
            started.set()

    readers = [
        threading.Thread(target=reader, args=(started,), daemon=True)
        for started in readers_started
    ]
    for thread in readers:
        thread.start()
    start.wait()
    for started in readers_started:
        assert started.wait(timeout=5), "reader did not reach the synchronized start"

    try:
        for index in range(1_000):
            store.write({"token": token_a if index % 2 == 0 else token_b})
    finally:
        stop.set()
        for thread in readers:
            thread.join(timeout=5)

    assert all(not thread.is_alive() for thread in readers), "reader did not stop"
    assert not read_errors, f"reader errors: {read_errors}"
    assert observed_digests
    unexpected_digests = observed_digests - allowed_digests
    assert not unexpected_digests, (
        f"readers observed {len(unexpected_digests)} incomplete content digest(s)"
    )


def test_file_secret_store_unwritable_directory_fails_without_secret_leak(
    tmp_path,
) -> None:
    directory = tmp_path / "locked"
    directory.mkdir()
    target = directory / "app-token.json"
    sentinel = token_hex(32)
    os.chmod(directory, 0o500)
    try:
        try:
            FileSecretStore(target).write({"token": sentinel})
        except OSError as exc:
            if sentinel in str(exc):
                raise AssertionError("writer exception disclosed the secret payload")
            assert not target.exists()
        else:
            target.unlink(missing_ok=True)
            effective_uid = getattr(os, "geteuid", lambda: -1)()
            assert effective_uid == 0, (
                "non-root process unexpectedly bypassed directory permissions"
            )
    finally:
        os.chmod(directory, 0o700)


# --- 4. Bout-en-bout avec le VRAI ensure_openbao_ready (S2) ------------------

def _fake_transport():
    """request(method, path, *, token=None, payload=None) -> (status, body) simulant openbao."""
    state = {"mounts": False, "policy": False}

    def request(method, path, *, token=None, payload=None):
        if path == "/v1/sys/seal-status":
            return (200, {"initialized": False, "sealed": True})
        if path == "/v1/sys/init":
            return (200, {"keys": ["UNSEAL"], "root_token": "ROOT"})
        if path == "/v1/sys/unseal":
            return (200, {"sealed": payload.get("key") != "UNSEAL"})
        if path == "/v1/sys/mounts":
            return (200, {"data": {"secret/": {}} if state["mounts"] else {}})
        if path == "/v1/sys/mounts/secret":
            state["mounts"] = True
            return (204, {})
        if path == "/v1/sys/policies/acl/forgeai-app":
            state["policy"] = True
            return (204, {})
        if path == "/v1/auth/token/lookup-self":
            if token == "APPTOKEN" and state["policy"]:
                return (200, {"data": {"policies": ["forgeai-app"]}})
            return (403, {"errors": ["permission denied"]})
        if path == "/v1/auth/token/create":
            return (200, {"auth": {"client_token": "APPTOKEN"}})
        if path == "/v1/auth/token/revoke":
            return (204, {})
        return (404, {"errors": ["unknown"]})

    return request


def test_ensure_openbao_ready_with_file_stores(tmp_path) -> None:
    keys_dir = tmp_path / "keys"
    root_path = tmp_path / "secrets" / "root_token"
    prepare_key_store(keys_dir)
    key_store = FileKeyStore(keys_dir, root_path)
    secret_store = FileSecretStore(tmp_path / "app_token.json")

    token = ensure_openbao_ready(_fake_transport(), key_store, secret_store)
    assert token == "APPTOKEN"
    assert key_store.read() == {"unseal_key": "UNSEAL", "root_token": "ROOT"}
    assert secret_store.read() == {"token": "APPTOKEN"}
    # le root n'est jamais tombé dans le répertoire monté à l'unsealer
    assert [e.name for e in keys_dir.iterdir()] == ["unseal_key"]
    assert "ROOT" not in (keys_dir / "unseal_key").read_text(encoding="utf-8")


def test_ensure_openbao_ready_reutilise_token_valide(tmp_path) -> None:
    keys_dir = tmp_path / "keys"
    prepare_key_store(keys_dir)
    key_store = FileKeyStore(keys_dir, tmp_path / "secrets" / "root_token")
    key_store.write({"unseal_key": "UNSEAL", "root_token": "ROOT"})
    secret_store = FileSecretStore(tmp_path / "app_token.json")
    secret_store.write({"token": "APPTOKEN"})  # token déjà valide -> réutilisé (lookup-self 200)

    assert ensure_openbao_ready(_fake_transport(), key_store, secret_store) == "APPTOKEN"


# --- 5. renew_self ----------------------------------------------------------

class _FakeRequest:
    def __init__(self, response=None, side_effect=None):
        self.calls = []
        self.response = response
        self.side_effect = side_effect

    def __call__(self, method, url, token, payload, timeout):
        self.calls.append((method, url, token, payload, timeout))
        if self.side_effect:
            raise self.side_effect
        return self.response


def test_renew_self_success(monkeypatch) -> None:
    fake = _FakeRequest(response={"auth": {"lease_duration": 2592000}})
    monkeypatch.setattr("forgeai.secrets.vault._request", fake)
    assert renew_self("http://openbao:8200", "TOKEN123") == 2592000
    method, url, token, payload, timeout = fake.calls[0]
    assert method == "POST"
    assert url == "http://openbao:8200/v1/auth/token/renew-self"
    assert token == "TOKEN123" and payload == {} and timeout == 10.0


def test_renew_self_custom_timeout(monkeypatch) -> None:
    fake = _FakeRequest(response={"auth": {"lease_duration": 100}})
    monkeypatch.setattr("forgeai.secrets.vault._request", fake)
    assert renew_self("http://localhost:8200", "T", timeout=5) == 100
    assert fake.calls[0][4] == 5


def test_renew_self_propage_vault_error_sans_fuite(monkeypatch) -> None:
    fake = _FakeRequest(side_effect=VaultError("openbao POST .../renew-self -> HTTP 403"))
    monkeypatch.setattr("forgeai.secrets.vault._request", fake)
    with pytest.raises(VaultError) as exc:
        renew_self("http://vault:8200", "BROKEN-SECRET")
    assert "openbao POST" in str(exc.value)
    assert "BROKEN-SECRET" not in str(exc.value)  # invariant : jamais le token dans le message


# --- 6. KubectlKeyStore (k3s : Secret, secrets par STDIN jamais argv) --------

class _FakeKubectl:
    """Faux runner kubectl : simule un unique Secret en mémoire (data base64)."""

    def __init__(self):
        self.stored: dict[str, str] | None = None
        self.apply_inputs: list[str] = []
        self.argv_seen: list[list[str]] = []

    def __call__(self, args, *, input=None):
        self.argv_seen.append(args)
        if args[:3] == ["kubectl", "get", "secret"]:
            jsonpath = args[-1]
            key = jsonpath.split(".data.")[1].rstrip("}")
            if self.stored is None or key not in self.stored:
                return subprocess.CompletedProcess(args, 1, stdout="", stderr="NotFound")
            return subprocess.CompletedProcess(args, 0, stdout=self.stored[key], stderr="")
        if args[:3] == ["kubectl", "apply", "-f"]:
            self.apply_inputs.append(input or "")
            # parse le manifeste stdin -> mémorise les data base64
            data = {}
            for line in (input or "").splitlines():
                s = line.strip()
                for k in ("unseal_key:", "root_token:"):
                    if s.startswith(k):
                        data[k[:-1]] = s.split(":", 1)[1].strip()
            self.stored = data
            return subprocess.CompletedProcess(args, 0, stdout="secret/x configured", stderr="")
        return subprocess.CompletedProcess(args, 1, stdout="", stderr="unexpected")


def test_kubectl_key_store_roundtrip_and_no_secret_in_argv() -> None:
    run = _FakeKubectl()
    store = KubectlKeyStore("forgeai-openbao-keys", "forgeai-minimal", run=run)
    assert store.read() is None  # Secret absent
    store.write({"unseal_key": "UNSEAL-SECRET", "root_token": "ROOT-SECRET"})
    assert store.read() == {"unseal_key": "UNSEAL-SECRET", "root_token": "ROOT-SECRET"}
    # INVARIANT : aucun secret en clair dans un argv kubectl (ils passent par STDIN)
    for argv in run.argv_seen:
        joined = " ".join(argv)
        assert "UNSEAL-SECRET" not in joined and "ROOT-SECRET" not in joined
    # le manifeste appliqué porte les valeurs en base64 (jamais en clair)
    b64_unseal = base64.b64encode(b"UNSEAL-SECRET").decode()
    assert any(b64_unseal in m for m in run.apply_inputs)
    assert all("UNSEAL-SECRET" not in m for m in run.apply_inputs)  # jamais en clair, même en stdin


def test_kubectl_key_store_write_failure_raises() -> None:
    def failing_run(args, *, input=None):
        if args[:3] == ["kubectl", "apply", "-f"]:
            return subprocess.CompletedProcess(args, 1, stdout="", stderr="forbidden")
        return subprocess.CompletedProcess(args, 1, stdout="", stderr="")
    store = KubectlKeyStore("s", "ns", run=failing_run)
    with pytest.raises(OpenBaoFlowError):
        store.write({"unseal_key": "U", "root_token": "R"})


# --- 7. initialize_openbao (wrapper) + wait_reachable -----------------------

def test_initialize_openbao_wraps_ensure(tmp_path) -> None:
    keys_dir = tmp_path / "keys"
    prepare_key_store(keys_dir)
    key_store = FileKeyStore(keys_dir, tmp_path / "secrets" / "root")
    secret_store = FileSecretStore(tmp_path / "app.json")
    # request_factory injecté -> renvoie le faux transport (openbao simulé)
    token = initialize_openbao(
        "http://openbao:8200", key_store, secret_store,
        request_factory=lambda url, timeout: _fake_transport(),
    )
    assert token == "APPTOKEN"


def test_wait_reachable_returns_when_probe_true() -> None:
    calls = {"n": 0}

    def probe(url):
        calls["n"] += 1
        return calls["n"] >= 3  # joignable à la 3e tentative

    slept = []
    wait_reachable("http://openbao:8200/health", probe=probe, attempts=10,
                   delay=0.5, sleep=slept.append)
    assert calls["n"] == 3 and slept == [0.5, 0.5]  # 2 attentes avant succès


def test_wait_reachable_raises_after_attempts() -> None:
    with pytest.raises(OpenBaoFlowError):
        wait_reachable("http://x/health", probe=lambda u: False, attempts=3,
                       delay=0, sleep=lambda d: None)


# --- 8. Intégration wizard : _provision_openbao_compose (séquence anti-interblocage) --------

def test_provision_openbao_compose_sequence(tmp_path, monkeypatch) -> None:
    import forgeai.cli as cli
    calls = {"up": []}
    monkeypatch.setattr(cli, "compose_up", lambda cf, services=None: calls["up"].append(services))
    monkeypatch.setattr(cli, "wait_reachable", lambda url, **kw: calls.__setitem__("waited", url))
    monkeypatch.setattr(cli, "initialize_openbao", lambda url, ks, ss: "APP-TOK")
    tok = cli._provision_openbao_compose(tmp_path / "compose.yml", tmp_path, "http://127.0.0.1:8200")
    assert tok == "APP-TOK"
    # openbao + son unsealer démarrés SEULS et d'abord (avant les consommateurs = anti-interblocage)
    assert calls["up"] == [["openbao", "openbao-unsealer"]]
    assert "8200" in calls["waited"]
    assert (tmp_path / "openbao-keys").is_dir()  # key-store hôte préparé
