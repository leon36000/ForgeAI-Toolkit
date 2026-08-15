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
from contextlib import contextmanager
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
from forgeai.models import vault as vault_module
from forgeai.secrets.openbao_init import ensure_openbao_ready
from forgeai.secrets.vault import VaultError, renew_self


@contextmanager
def _observe_mkdir_requests(path: Path):
    """Observe les modes demandés lors des créations réelles par mkdir."""
    expected = os.fspath(path)
    requested_modes: list[int] = []
    enabled = True

    def observe(event, arguments):
        if not enabled or event != "os.mkdir":
            return
        candidate, mode, _dir_fd = arguments
        if os.fspath(candidate) == expected and not os.path.exists(candidate):
            requested_modes.append(mode)

    sys.addaudithook(observe)
    try:
        yield requested_modes
    finally:
        enabled = False


# --- 1. prepare_key_store ---------------------------------------------------

def test_prepare_key_store_creates_and_chmod(tmp_path) -> None:
    d = tmp_path / "keys"
    assert prepare_key_store(d) == d
    assert d.is_dir()
    assert oct(d.stat().st_mode & 0o777) == "0o711"


def test_prepare_key_store_idempotent(tmp_path) -> None:
    d = tmp_path / "keys"
    d.mkdir(parents=True)
    os.chmod(d, 0o700)
    prepare_key_store(d)
    assert oct(d.stat().st_mode & 0o777) == "0o711"


@pytest.mark.parametrize("initial_mode", [0, 0o500])
def test_prepare_key_store_restores_exact_mode_from_restrictive_directory(
    tmp_path, initial_mode
) -> None:
    keys_dir = tmp_path / "keys"
    keys_dir.mkdir()
    os.chmod(keys_dir, initial_mode)

    prepare_key_store(keys_dir)

    assert stat.S_IMODE(keys_dir.stat().st_mode) == 0o711


def test_prepare_key_store_uses_nofollow_descriptor_not_pathname_chmod(
    tmp_path, monkeypatch
) -> None:
    keys_dir = tmp_path / "keys"
    observed_flags: list[int] = []
    real_open = os.open
    real_chmod = os.chmod

    def observe_directory_open(path, flags, *args, **kwargs):
        descriptor = real_open(path, flags, *args, **kwargs)
        if Path(path) == keys_dir:
            observed_flags.append(flags)
        return descriptor

    def reject_pathname_chmod(path, mode, *args, **kwargs):
        if Path(path) == keys_dir:
            raise AssertionError("prepare_key_store used pathname chmod")
        return real_chmod(path, mode, *args, **kwargs)

    monkeypatch.setattr(vault_module.os, "open", observe_directory_open)
    monkeypatch.setattr(vault_module.os, "chmod", reject_pathname_chmod)
    previous_umask = os.umask(0)
    try:
        assert prepare_key_store(keys_dir) == keys_dir
    finally:
        os.umask(previous_umask)

    required = os.O_NOFOLLOW | os.O_DIRECTORY
    if len(observed_flags) != 1 or observed_flags[0] & required != required:
        raise AssertionError("prepare_key_store did not validate one directory descriptor")
    assert stat.S_IMODE(keys_dir.stat().st_mode) == 0o711


def test_prepare_key_store_refuses_symlink_without_changing_referent(
    tmp_path,
) -> None:
    external = tmp_path / "external-keys"
    external.mkdir()
    os.chmod(external, 0o750)
    external_mode = stat.S_IMODE(external.stat().st_mode)
    marker = external / "marker"
    marker.write_bytes(token_hex(32).encode("ascii"))
    marker_digest = sha256(marker.read_bytes()).digest()
    keys_dir = tmp_path / "keys"
    keys_dir.symlink_to(external, target_is_directory=True)
    original_link = os.readlink(keys_dir)

    with pytest.raises(OSError):
        prepare_key_store(keys_dir)

    assert keys_dir.is_symlink()
    assert os.readlink(keys_dir) == original_link
    assert stat.S_IMODE(external.stat().st_mode) == external_mode
    if {entry.name for entry in external.iterdir()} != {"marker"}:
        raise AssertionError("prepare_key_store wrote through a symlink")
    if sha256(marker.read_bytes()).digest() != marker_digest:
        raise AssertionError("prepare_key_store changed symlink referent content")


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

    entries = list(keys_dir.iterdir())
    assert [e.name for e in entries] == ["unseal_key"]
    unseal = (keys_dir / "unseal_key").read_text(encoding="utf-8").strip()
    assert unseal == "UNSEAL" and "ROOT" not in unseal
    assert root_path.read_text(encoding="utf-8").strip() == "ROOT"

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


def test_unseal_key_0640_et_groupe_quand_groupe_present(tmp_path, monkeypatch) -> None:
    import forgeai.deploy.openbao_flow as flow

    monkeypatch.setattr(flow, "resolve_openbao_gid", lambda: os.getgid())
    keys_dir = tmp_path / "keys"
    root_path = tmp_path / "secrets" / "root_token"
    flow.FileKeyStore(keys_dir, root_path).write({"unseal_key": "UNSEAL", "root_token": "ROOT"})

    unseal = keys_dir / "unseal_key"
    assert stat.S_IMODE(unseal.stat().st_mode) == 0o640
    assert unseal.stat().st_gid == os.getgid()
    assert stat.S_IMODE(root_path.stat().st_mode) == 0o600


def test_unseal_key_repli_0644_quand_groupe_absent(tmp_path, monkeypatch) -> None:
    import forgeai.deploy.openbao_flow as flow

    monkeypatch.setattr(flow, "resolve_openbao_gid", lambda: None)
    keys_dir = tmp_path / "keys"
    root_path = tmp_path / "secrets" / "root_token"
    flow.FileKeyStore(keys_dir, root_path).write({"unseal_key": "UNSEAL", "root_token": "ROOT"})

    assert stat.S_IMODE((keys_dir / "unseal_key").stat().st_mode) == 0o644


def test_unseal_key_repli_si_chown_echoue(tmp_path, monkeypatch) -> None:
    import forgeai.deploy.openbao_flow as flow

    monkeypatch.setattr(flow, "resolve_openbao_gid", lambda: os.getgid())

    def _chown_refuse(*a, **k):
        raise PermissionError("simulé : groupe présent mais chown interdit")

    monkeypatch.setattr(flow.os, "chown", _chown_refuse)
    keys_dir = tmp_path / "keys"
    root_path = tmp_path / "secrets" / "root_token"
    flow.FileKeyStore(keys_dir, root_path).write({"unseal_key": "UNSEAL", "root_token": "ROOT"})

    assert stat.S_IMODE((keys_dir / "unseal_key").stat().st_mode) == 0o644


def test_keys_dir_0750_avec_groupe_sinon_0711(tmp_path, monkeypatch) -> None:
    import forgeai.deploy.openbao_flow as flow

    monkeypatch.setattr(flow, "resolve_openbao_gid", lambda: os.getgid())
    d1 = flow.prepare_key_store(tmp_path / "avec_groupe")
    assert stat.S_IMODE(d1.stat().st_mode) == 0o750 and d1.stat().st_gid == os.getgid()

    monkeypatch.setattr(flow, "resolve_openbao_gid", lambda: None)
    d2 = flow.prepare_key_store(tmp_path / "sans_groupe")
    assert stat.S_IMODE(d2.stat().st_mode) == 0o711


def test_resolve_openbao_gid_none_sans_grp(monkeypatch) -> None:
    import forgeai.deploy.openbao_flow as flow

    monkeypatch.setattr(flow, "grp", None)
    assert flow.resolve_openbao_gid() is None


@pytest.mark.parametrize("initial_mode", [0, 0o500])
def test_file_key_store_restores_unsealer_access_on_restrictive_keys_directory(
    tmp_path, initial_mode
) -> None:
    keys_dir = tmp_path / "keys"
    keys_dir.mkdir()
    os.chmod(keys_dir, initial_mode)
    root_path = tmp_path / "root-secrets" / "root_token"

    FileKeyStore(keys_dir, root_path).write(
        {"unseal_key": "UNSEAL", "root_token": "ROOT"}
    )

    assert stat.S_IMODE(keys_dir.stat().st_mode) == 0o711
    assert stat.S_IMODE((keys_dir / "unseal_key").stat().st_mode) == 0o644
    assert stat.S_IMODE(root_path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(root_path.stat().st_mode) == 0o600


@pytest.mark.parametrize("requested_umask", [0, 0o777])
def test_file_key_store_parent_modes_are_secure_from_first_creation(
    tmp_path, requested_umask
) -> None:
    keys_dir = tmp_path / "keys"
    root_parent = tmp_path / "root-secrets"
    root_path = root_parent / "root_token"
    expected_modes = {keys_dir: 0o711, root_parent: 0o700}

    previous_umask = os.umask(requested_umask)
    try:
        with _observe_mkdir_requests(keys_dir) as key_modes, _observe_mkdir_requests(
            root_parent
        ) as root_modes:
            FileKeyStore(keys_dir, root_path).write(
                {"unseal_key": "UNSEAL", "root_token": "ROOT"}
            )
    finally:
        os.umask(previous_umask)

    observed_modes = {keys_dir: key_modes, root_parent: root_modes}
    for candidate, expected_mode in expected_modes.items():
        modes = observed_modes[candidate]
        if not modes or any(mode & ~expected_mode for mode in modes):
            raise AssertionError(
                f"file key store parent creation was unsafe: {candidate.name}"
            )
        assert stat.S_IMODE(candidate.stat().st_mode) == expected_mode
    assert stat.S_IMODE((keys_dir / "unseal_key").stat().st_mode) == 0o644
    assert stat.S_IMODE(root_path.stat().st_mode) == 0o600


def test_file_key_store_refuses_root_parent_symlink_without_external_change(
    tmp_path,
) -> None:
    external = tmp_path / "external-root"
    external.mkdir()
    os.chmod(external, 0o750)
    external_mode = stat.S_IMODE(external.stat().st_mode)
    marker = external / "marker"
    marker.write_bytes(token_hex(32).encode("ascii"))
    marker_digest = sha256(marker.read_bytes()).digest()
    root_parent = tmp_path / "root-secrets"
    root_parent.symlink_to(external, target_is_directory=True)

    with pytest.raises(OSError):
        FileKeyStore(tmp_path / "keys", root_parent / "root_token").write(
            {"unseal_key": "UNSEAL", "root_token": "ROOT"}
        )

    assert stat.S_IMODE(external.stat().st_mode) == external_mode
    if {entry.name for entry in external.iterdir()} != {"marker"}:
        raise AssertionError("file key store wrote through root-parent symlink")
    if sha256(marker.read_bytes()).digest() != marker_digest:
        raise AssertionError("file key store changed root-parent referent")


def test_file_key_store_refuses_keys_parent_symlink_before_secret_write(
    tmp_path,
) -> None:
    external = tmp_path / "external-keys"
    external.mkdir()
    os.chmod(external, 0o750)
    external_mode = stat.S_IMODE(external.stat().st_mode)
    marker = external / "marker"
    marker.write_bytes(token_hex(32).encode("ascii"))
    marker_digest = sha256(marker.read_bytes()).digest()
    keys_dir = tmp_path / "keys"
    keys_dir.symlink_to(external, target_is_directory=True)
    root_path = tmp_path / "root-secrets" / "root_token"

    with pytest.raises(OSError):
        FileKeyStore(keys_dir, root_path).write(
            {"unseal_key": "UNSEAL", "root_token": "ROOT"}
        )

    assert not root_path.exists()
    assert stat.S_IMODE(external.stat().st_mode) == external_mode
    if {entry.name for entry in external.iterdir()} != {"marker"}:
        raise AssertionError("file key store wrote through keys-parent symlink")
    if sha256(marker.read_bytes()).digest() != marker_digest:
        raise AssertionError("file key store changed keys-parent referent")


def test_file_key_store_read_refuses_target_symlink_before_referent_read(
    tmp_path, monkeypatch
) -> None:
    keys_dir = tmp_path / "keys"
    keys_dir.mkdir()
    external = tmp_path / "external-unseal"
    external.write_text("UNSEAL\n", encoding="utf-8")
    external_digest = sha256(external.read_bytes()).digest()
    unseal_path = keys_dir / "unseal_key"
    unseal_path.symlink_to(external)
    root_path = tmp_path / "root-secrets" / "root_token"
    root_path.parent.mkdir()
    root_path.write_text("ROOT\n", encoding="utf-8")
    referent_was_read = False
    real_read_text = Path.read_text

    def observe_completed_read(path, *args, **kwargs):
        nonlocal referent_was_read
        content = real_read_text(path, *args, **kwargs)
        if Path(path) == unseal_path:
            referent_was_read = True
        return content

    monkeypatch.setattr(Path, "read_text", observe_completed_read)

    with pytest.raises(OSError):
        FileKeyStore(keys_dir, root_path).read()

    if referent_was_read:
        raise AssertionError("file key store read a target-symlink referent")
    if sha256(external.read_bytes()).digest() != external_digest:
        raise AssertionError("file key store changed target-symlink referent")


def test_file_key_store_read_refuses_fifo_without_blocking(
    tmp_path, monkeypatch
) -> None:
    keys_dir = tmp_path / "keys"
    keys_dir.mkdir()
    unseal_path = keys_dir / "unseal_key"
    unseal_path.write_text("UNSEAL\n", encoding="utf-8")
    root_path = tmp_path / "root-secrets" / "root_token"
    root_path.parent.mkdir()
    os.mkfifo(root_path)
    observed_flags: list[int] = []
    path_read_attempted = False
    real_open = os.open
    real_read_text = Path.read_text

    def observe_real_open(path, flags, *args, **kwargs):
        if Path(path) == root_path:
            observed_flags.append(flags)
            required = os.O_NOFOLLOW | os.O_NONBLOCK
            if flags & required != required:
                raise OSError("unsafe root-token open flags")
        return real_open(path, flags, *args, **kwargs)

    def reject_blocking_path_read(path, *args, **kwargs):
        nonlocal path_read_attempted
        if Path(path) == root_path:
            path_read_attempted = True
            raise OSError("blocking root-token read refused by test")
        return real_read_text(path, *args, **kwargs)

    monkeypatch.setattr(vault_module.os, "open", observe_real_open)
    monkeypatch.setattr(Path, "read_text", reject_blocking_path_read)

    with pytest.raises(OSError):
        FileKeyStore(keys_dir, root_path).read()

    if path_read_attempted:
        raise AssertionError("file key store attempted a blocking FIFO read")
    if len(observed_flags) != 1:
        raise AssertionError("file key store did not perform one bounded root open")


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


@pytest.mark.parametrize("requested_umask", [0, 0o777])
def test_file_secret_store_parent_is_secure_from_first_creation(
    tmp_path, requested_umask
) -> None:
    parent = tmp_path / "app-secrets"
    target = parent / "app_token.json"

    previous_umask = os.umask(requested_umask)
    try:
        with _observe_mkdir_requests(parent) as observed_creation_modes:
            FileSecretStore(target).write({"token": token_hex(32)})
    finally:
        os.umask(previous_umask)

    if not observed_creation_modes or any(
        mode & ~0o700 for mode in observed_creation_modes
    ):
        raise AssertionError("file secret store parent creation was unsafe")
    assert stat.S_IMODE(parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(target.stat().st_mode) == 0o600


def test_file_secret_store_refuses_parent_symlink_before_external_change(
    tmp_path,
) -> None:
    external = tmp_path / "external-app-secrets"
    external.mkdir()
    os.chmod(external, 0o750)
    external_mode = stat.S_IMODE(external.stat().st_mode)
    marker = external / "marker"
    marker.write_bytes(token_hex(32).encode("ascii"))
    marker_digest = sha256(marker.read_bytes()).digest()
    parent = tmp_path / "app-secrets"
    parent.symlink_to(external, target_is_directory=True)

    with pytest.raises(OSError):
        FileSecretStore(parent / "app_token.json").write(
            {"token": token_hex(32)}
        )

    assert stat.S_IMODE(external.stat().st_mode) == external_mode
    if {entry.name for entry in external.iterdir()} != {"marker"}:
        raise AssertionError("file secret store wrote through parent symlink")
    if sha256(marker.read_bytes()).digest() != marker_digest:
        raise AssertionError("file secret store changed parent-symlink referent")


def test_file_secret_store_read_refuses_symlink_before_referent_read(
    tmp_path, monkeypatch
) -> None:
    external = tmp_path / "external-app-token"
    external.write_text('{"token":"external"}\n', encoding="utf-8")
    external_digest = sha256(external.read_bytes()).digest()
    target = tmp_path / "app_token.json"
    target.symlink_to(external)
    referent_was_read = False
    real_read_text = Path.read_text

    def observe_completed_read(path, *args, **kwargs):
        nonlocal referent_was_read
        content = real_read_text(path, *args, **kwargs)
        if Path(path) == target:
            referent_was_read = True
        return content

    monkeypatch.setattr(Path, "read_text", observe_completed_read)

    with pytest.raises(OSError):
        FileSecretStore(target).read()

    if referent_was_read:
        raise AssertionError("file secret store read a target-symlink referent")
    if sha256(external.read_bytes()).digest() != external_digest:
        raise AssertionError("file secret store changed target-symlink referent")


def test_file_secret_store_read_refuses_fifo_without_blocking(
    tmp_path, monkeypatch
) -> None:
    target = tmp_path / "app-token.fifo"
    os.mkfifo(target)
    observed_flags: list[int] = []
    path_read_attempted = False
    real_open = os.open
    real_read_text = Path.read_text

    def observe_real_open(path, flags, *args, **kwargs):
        if Path(path) == target:
            observed_flags.append(flags)
            required = os.O_NOFOLLOW | os.O_NONBLOCK
            if flags & required != required:
                raise OSError("unsafe app-token open flags")
        return real_open(path, flags, *args, **kwargs)

    def reject_blocking_path_read(path, *args, **kwargs):
        nonlocal path_read_attempted
        if Path(path) == target:
            path_read_attempted = True
            raise OSError("blocking app-token read refused by test")
        return real_read_text(path, *args, **kwargs)

    monkeypatch.setattr(vault_module.os, "open", observe_real_open)
    monkeypatch.setattr(Path, "read_text", reject_blocking_path_read)

    with pytest.raises(OSError):
        FileSecretStore(target).read()

    if path_read_attempted:
        raise AssertionError("file secret store attempted a blocking FIFO read")
    if len(observed_flags) != 1:
        raise AssertionError("file secret store did not perform one bounded target open")


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

    monkeypatch.setattr(vault_module.os, "fsync", record_real_fsync)
    monkeypatch.setattr(vault_module.os, "replace", fail_before_replace)
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

    monkeypatch.setattr(vault_module.os, "fsync", record_real_fsync)
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
    assert [e.name for e in keys_dir.iterdir()] == ["unseal_key"]
    assert "ROOT" not in (keys_dir / "unseal_key").read_text(encoding="utf-8")


def test_ensure_openbao_ready_reutilise_token_valide(tmp_path) -> None:
    keys_dir = tmp_path / "keys"
    prepare_key_store(keys_dir)
    key_store = FileKeyStore(keys_dir, tmp_path / "secrets" / "root_token")
    key_store.write({"unseal_key": "UNSEAL", "root_token": "ROOT"})
    secret_store = FileSecretStore(tmp_path / "app_token.json")
    secret_store.write({"token": "APPTOKEN"})

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
    assert "BROKEN-SECRET" not in str(exc.value)


# --- 6. KubectlKeyStore (k3s : Secret, secrets par STDIN jamais argv) --------

class _FakeKubectl:
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
    assert store.read() is None
    store.write({"unseal_key": "UNSEAL-SECRET", "root_token": "ROOT-SECRET"})
    assert store.read() == {"unseal_key": "UNSEAL-SECRET", "root_token": "ROOT-SECRET"}
    for argv in run.argv_seen:
        joined = " ".join(argv)
        assert "UNSEAL-SECRET" not in joined and "ROOT-SECRET" not in joined
    b64_unseal = base64.b64encode(b"UNSEAL-SECRET").decode()
    assert any(b64_unseal in m for m in run.apply_inputs)
    assert all("UNSEAL-SECRET" not in m for m in run.apply_inputs)


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
    token = initialize_openbao(
        "http://openbao:8200", key_store, secret_store,
        request_factory=lambda url, timeout: _fake_transport(),
    )
    assert token == "APPTOKEN"


def test_wait_reachable_returns_when_probe_true() -> None:
    calls = {"n": 0}

    def probe(url):
        calls["n"] += 1
        return calls["n"] >= 3

    slept = []
    wait_reachable("http://openbao:8200/health", probe=probe, attempts=10,
                   delay=0.5, sleep=slept.append)
    assert calls["n"] == 3 and slept == [0.5, 0.5]


def test_wait_reachable_raises_after_attempts() -> None:
    with pytest.raises(OpenBaoFlowError):
        wait_reachable("http://x/health", probe=lambda u: False, attempts=3,
                       delay=0, sleep=lambda d: None)


# --- 8. Intégration wizard : _provision_openbao_compose ----------------------

def test_provision_openbao_compose_sequence(tmp_path, monkeypatch) -> None:
    import forgeai.cli as cli

    calls = {"up": []}
    monkeypatch.setattr(cli, "compose_up", lambda cf, services=None: calls["up"].append(services))
    monkeypatch.setattr(cli, "wait_reachable", lambda url, **kw: calls.__setitem__("waited", url))
    monkeypatch.setattr(cli, "initialize_openbao", lambda url, ks, ss: "APP-TOK")
    tok = cli._provision_openbao_compose(tmp_path / "compose.yml", tmp_path, "http://127.0.0.1:8200")
    assert tok == "APP-TOK"
    assert calls["up"] == [["openbao", "openbao-unsealer"]]
    assert "8200" in calls["waited"]
    assert (tmp_path / "openbao-keys").is_dir()


def test_flux_reel_prepare_puis_write_garde_keys_dir_0750(tmp_path, monkeypatch) -> None:
    import forgeai.deploy.openbao_flow as flow

    monkeypatch.setattr(flow, "resolve_openbao_gid", lambda: os.getgid())
    keys_dir = tmp_path / "keys"
    root_path = tmp_path / "secrets" / "root_token"
    flow.prepare_key_store(keys_dir)
    flow.FileKeyStore(keys_dir, root_path).write(
        {"unseal_key": "U", "root_token": "R"}
    )
    assert stat.S_IMODE(keys_dir.stat().st_mode) == 0o750
    assert keys_dir.stat().st_gid == os.getgid()


def test_keys_dir_repli_0711_si_chown_echoue(tmp_path, monkeypatch) -> None:
    import forgeai.deploy.openbao_flow as flow

    monkeypatch.setattr(flow, "resolve_openbao_gid", lambda: os.getgid())

    def _chown_refuse(*a, **k):
        raise PermissionError("simulé")

    monkeypatch.setattr(flow.os, "chown", _chown_refuse)
    d = flow.prepare_key_store(tmp_path / "keys")
    assert stat.S_IMODE(d.stat().st_mode) == 0o711
