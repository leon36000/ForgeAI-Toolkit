"""Tests S04 (assemblage) et S05 (bootstrap secrets)."""
import os
import stat
import sys
import threading
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
from queue import Queue
from secrets import token_hex

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from forgeai.bootstrap import secrets as bootstrap_secrets_module
from forgeai.bootstrap.secrets import bootstrap_secrets
from forgeai.core.models import RenderTarget
from forgeai.models import vault as vault_module
from forgeai.planner.assemble import assemble_plan, find_free_port
from forgeai.resources import deploy_overlay_path

DEPLOY = deploy_overlay_path()


def test_plan_minimal_assemble_deux_services():
    plan = assemble_plan("minimal-gpu-cuda", DEPLOY, is_free=lambda p: True)
    assert {s.name for s in plan.services} == {"ollama", "vector-store"}
    assert plan.model == "qwen2.5:0.5b"
    assert plan.target is RenderTarget.COMPOSE


def test_ports_alloues_evitent_les_occupes():
    occupied = {21434, 21435}
    plan = assemble_plan("minimal-cpu", DEPLOY, is_free=lambda p: p not in occupied)
    ollama = next(s for s in plan.services if s.name == "ollama")
    assert ollama.host_port == 21436  # 21434 et 21435 occupés → suivant libre


def test_gpu_seulement_si_profil_cuda_et_service_capable():
    cuda = assemble_plan("minimal-gpu-cuda", DEPLOY, is_free=lambda p: True)
    cpu = assemble_plan("minimal-cpu", DEPLOY, is_free=lambda p: True)
    assert next(s for s in cuda.services if s.name == "ollama").gpu is True
    assert next(s for s in cuda.services if s.name == "vector-store").gpu is False
    assert all(not s.gpu for s in cpu.services)


def test_find_free_port_epuise_leve():
    import pytest
    with pytest.raises(RuntimeError):
        find_free_port(30000, is_free=lambda p: False)


def _assert_generated_env_contract(content: str) -> None:
    if "FORGEAI_API_TOKEN=" not in content:
        raise AssertionError("generated env is missing API token")
    token = content.splitlines()[0].split("=", 1)[1]
    if len(token) != 64:  # 256 bits hex
        raise AssertionError("generated API token length is invalid")


def test_secrets_generes_permissions_0600(tmp_path):
    paths = bootstrap_secrets(tmp_path)
    for p in (paths["env"], paths["token_key"]):
        assert p.exists()
        assert stat.S_IMODE(p.stat().st_mode) == 0o600
    content = paths["env"].read_text(encoding="utf-8")
    _assert_generated_env_contract(content)


def test_secrets_directory_is_private_at_its_first_creation(
    tmp_path, monkeypatch
):
    out_dir = tmp_path / "out"
    secrets_dir = out_dir / "secrets"
    observed_creation_modes: list[int] = []
    real_mkdir = os.mkdir

    def observe_real_mkdir(path, mode=0o777, *args, **kwargs):
        result = real_mkdir(path, mode, *args, **kwargs)
        if Path(path) == secrets_dir:
            observed_creation_modes.append(
                stat.S_IMODE(os.lstat(path).st_mode)
            )
        return result

    monkeypatch.setattr(bootstrap_secrets_module.os, "mkdir", observe_real_mkdir)
    previous_umask = os.umask(0)
    try:
        bootstrap_secrets(out_dir)
    finally:
        os.umask(previous_umask)

    if observed_creation_modes != [0o700]:
        raise AssertionError("secret directory was not private at creation")


def test_generated_env_contract_failures_never_disclose_content():
    sentinel = token_hex(20)
    cases = (
        (
            f"UNRELATED={sentinel}\n",
            "generated env is missing API token",
        ),
        (
            f"FORGEAI_API_TOKEN={sentinel}\n",
            "generated API token length is invalid",
        ),
    )
    for content, expected_message in cases:
        with pytest.raises(AssertionError) as caught:
            _assert_generated_env_contract(content)
        if sentinel in str(caught.value):
            raise AssertionError("env contract failure disclosed secret content")
        if str(caught.value) != expected_message:
            raise AssertionError("env contract failure was not neutral")


def test_bootstrap_idempotent_sans_regen(tmp_path):
    first = bootstrap_secrets(tmp_path)["env"].read_text(encoding="utf-8")
    second = bootstrap_secrets(tmp_path)["env"].read_text(encoding="utf-8")
    if first != second:
        raise AssertionError("bootstrap changed existing secrets without regen")


def test_regen_change_les_secrets(tmp_path):
    first = bootstrap_secrets(tmp_path)["env"].read_text(encoding="utf-8")
    regen = bootstrap_secrets(tmp_path, regen=True)["env"].read_text(encoding="utf-8")
    if first == regen:
        raise AssertionError("bootstrap regen did not replace existing secrets")


def test_bootstrap_refuses_env_symlink_without_touching_referent(tmp_path):
    referent = tmp_path / "external-env"
    referent.write_text("EXTERNAL=unchanged\n", encoding="utf-8")
    target = tmp_path / ".env"
    target.symlink_to(referent)
    original_link = os.readlink(target)

    with pytest.raises(OSError):
        bootstrap_secrets(tmp_path, regen=True)

    assert target.is_symlink()
    assert os.readlink(target) == original_link
    assert referent.read_text(encoding="utf-8") == "EXTERNAL=unchanged\n"


def test_non_regen_refuses_env_symlink_before_reading_referent(
    tmp_path, monkeypatch
):
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    referent = tmp_path / "external-env"
    referent.write_text(
        f"FORGEAI_API_TOKEN={token_hex(32)}\n", encoding="utf-8"
    )
    referent_digest = sha256(referent.read_bytes()).digest()
    env_path = out_dir / ".env"
    env_path.symlink_to(referent)
    referent_was_read = False
    real_read_text = Path.read_text

    def observe_completed_read(path, *args, **kwargs):
        nonlocal referent_was_read
        content = real_read_text(path, *args, **kwargs)
        if Path(path) == env_path:
            referent_was_read = True
        return content

    monkeypatch.setattr(Path, "read_text", observe_completed_read)

    with pytest.raises(OSError):
        bootstrap_secrets(out_dir)

    if referent_was_read:
        raise AssertionError("bootstrap read an env symlink referent")
    if sha256(referent.read_bytes()).digest() != referent_digest:
        raise AssertionError("bootstrap changed an env symlink referent")


def test_bootstrap_refuses_secrets_directory_symlink_before_any_write(tmp_path):
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    external_dir = tmp_path / "external-secrets"
    external_dir.mkdir()
    os.chmod(external_dir, 0o750)
    external_mode = stat.S_IMODE(external_dir.stat().st_mode)
    external_key = external_dir / "forgeai_token.key"
    external_key.write_text(token_hex(32) + "\n", encoding="utf-8")
    os.chmod(external_key, 0o640)
    external_key_mode = stat.S_IMODE(external_key.stat().st_mode)
    external_key_digest = sha256(external_key.read_bytes()).digest()
    secrets_dir = out_dir / "secrets"
    secrets_dir.symlink_to(external_dir, target_is_directory=True)
    original_link = os.readlink(secrets_dir)

    with pytest.raises(OSError):
        bootstrap_secrets(out_dir)

    assert secrets_dir.is_symlink()
    assert os.readlink(secrets_dir) == original_link
    assert stat.S_IMODE(external_dir.stat().st_mode) == external_mode
    assert stat.S_IMODE(external_key.stat().st_mode) == external_key_mode
    if sha256(external_key.read_bytes()).digest() != external_key_digest:
        raise AssertionError("bootstrap changed a secret-directory referent")
    if (out_dir / ".env").exists():
        raise AssertionError("bootstrap wrote env before directory validation")


def test_existing_token_key_symlink_swap_cannot_touch_external_inode(
    tmp_path, monkeypatch
):
    out_dir = tmp_path / "out"
    secrets_dir = out_dir / "secrets"
    secrets_dir.mkdir(parents=True)
    key_path = secrets_dir / "forgeai_token.key"
    saved_key = secrets_dir / "original-token.key"
    key_path.write_text(token_hex(32) + "\n", encoding="utf-8")
    os.chmod(key_path, 0o640)
    key_digest = sha256(key_path.read_bytes()).digest()

    external = tmp_path / "external-token.key"
    external.write_text(token_hex(32) + "\n", encoding="utf-8")
    os.chmod(external, 0o640)
    external_digest = sha256(external.read_bytes()).digest()
    external_mode = stat.S_IMODE(external.stat().st_mode)

    real_open = os.open
    real_chmod = os.chmod
    swapped = False

    def swap_target_once() -> None:
        nonlocal swapped
        if swapped:
            return
        key_path.rename(saved_key)
        key_path.symlink_to(external)
        swapped = True

    def open_after_swap(path, flags, *args, **kwargs):
        if Path(path) == key_path:
            swap_target_once()
        return real_open(path, flags, *args, **kwargs)

    def chmod_after_swap(path, mode, *args, **kwargs):
        if Path(path) == key_path:
            swap_target_once()
        return real_chmod(path, mode, *args, **kwargs)

    monkeypatch.setattr(bootstrap_secrets_module.os, "open", open_after_swap)
    monkeypatch.setattr(bootstrap_secrets_module.os, "chmod", chmod_after_swap)

    with pytest.raises(OSError):
        bootstrap_secrets(out_dir)

    assert swapped, "test did not inject the target swap"
    assert key_path.is_symlink(), "swapped target is no longer a symlink"
    assert stat.S_IMODE(external.stat().st_mode) == external_mode
    if sha256(external.read_bytes()).digest() != external_digest:
        raise AssertionError("writer changed external symlink referent content")
    if sha256(saved_key.read_bytes()).digest() != key_digest:
        raise AssertionError("writer changed the displaced original key content")


def test_existing_token_key_hardlink_is_safely_broken_without_touching_external_inode(
    tmp_path,
):
    out_dir = tmp_path / "out"
    secrets_dir = out_dir / "secrets"
    secrets_dir.mkdir(parents=True)
    external = tmp_path / "external-token.key"
    external.write_text(token_hex(32) + "\n", encoding="utf-8")
    os.chmod(external, 0o640)
    external_digest = sha256(external.read_bytes()).digest()
    external_mode = stat.S_IMODE(external.stat().st_mode)
    key_path = secrets_dir / "forgeai_token.key"
    os.link(external, key_path)

    paths = bootstrap_secrets(out_dir)

    assert paths["token_key"] == key_path
    assert key_path.stat().st_ino != external.stat().st_ino
    assert stat.S_IMODE(key_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(external.stat().st_mode) == external_mode
    if sha256(external.read_bytes()).digest() != external_digest:
        raise AssertionError("writer changed external hardlink content")
    if sha256(key_path.read_bytes()).digest() != external_digest:
        raise AssertionError("writer did not preserve hardlinked key content")


def test_existing_token_key_unlinked_after_open_republishes_without_mutating_alias(
    tmp_path, monkeypatch
):
    out_dir = tmp_path / "out"
    secrets_dir = out_dir / "secrets"
    secrets_dir.mkdir(parents=True)
    external = tmp_path / "external-token.key"
    external.write_text(token_hex(32) + "\n", encoding="utf-8")
    os.chmod(external, 0o640)
    external_digest = sha256(external.read_bytes()).digest()
    external_mode = stat.S_IMODE(external.stat().st_mode)
    key_path = secrets_dir / "forgeai_token.key"
    os.link(external, key_path)

    descriptor_opened = threading.Event()
    resume_writer = threading.Event()
    writer_errors: list[str] = []
    real_open = os.open

    def open_then_pause(path, flags, *args, **kwargs):
        descriptor = real_open(path, flags, *args, **kwargs)
        if Path(path) == key_path:
            descriptor_opened.set()
            if not resume_writer.wait(timeout=5):
                os.close(descriptor)
                raise RuntimeError("writer did not resume after descriptor open")
        return descriptor

    monkeypatch.setattr(bootstrap_secrets_module.os, "open", open_then_pause)

    def run_bootstrap() -> None:
        try:
            bootstrap_secrets(out_dir)
        except (OSError, RuntimeError) as exc:
            writer_errors.append(type(exc).__name__)

    writer = threading.Thread(target=run_bootstrap, daemon=True)
    writer.start()
    assert descriptor_opened.wait(timeout=5), "key descriptor was not opened"
    key_path.unlink()
    resume_writer.set()
    writer.join(timeout=5)

    assert not writer.is_alive(), "bootstrap writer did not stop"
    assert not writer_errors, f"bootstrap writer errors: {writer_errors}"
    assert stat.S_IMODE(external.stat().st_mode) == external_mode
    if sha256(external.read_bytes()).digest() != external_digest:
        raise AssertionError("writer changed the remaining external alias content")
    assert key_path.exists(), "bootstrap did not republish the key path"
    assert key_path.stat().st_ino != external.stat().st_ino
    assert stat.S_IMODE(key_path.stat().st_mode) == 0o600
    if sha256(key_path.read_bytes()).digest() != external_digest:
        raise AssertionError("writer did not preserve the republished key content")


def test_non_regen_snapshot_cannot_overwrite_concurrent_regen_rotation(
    tmp_path, monkeypatch
):
    out_dir = tmp_path / "out"
    key_path = bootstrap_secrets(out_dir)["token_key"]
    initial_digest = sha256(key_path.read_bytes()).digest()

    snapshot_captured = threading.Event()
    resume_non_regen = threading.Event()
    start_regen = threading.Barrier(2)
    serialization_state: Queue[str] = Queue()
    rotated_digests: list[bytes] = []
    worker_errors: list[str] = []
    real_read = vault_module.os.read
    real_atomic_write = bootstrap_secrets_module.atomic_write_secret_text
    real_file_lock = vault_module.file_lock
    non_regen_thread: threading.Thread | None = None
    regen_thread: threading.Thread | None = None

    def read_then_pause(descriptor: int, size: int) -> bytes:
        chunk = real_read(descriptor, size)
        if (
            threading.current_thread() is non_regen_thread
            and not chunk
            and not snapshot_captured.is_set()
        ):
            snapshot_captured.set()
            if not resume_non_regen.wait(timeout=5):
                raise RuntimeError("non-regen bootstrap did not resume after snapshot")
        return chunk

    @contextmanager
    def observed_file_lock(path):
        if threading.current_thread() is regen_thread:
            serialization_state.put("lock-attempted")
        with real_file_lock(path):
            yield

    def observed_atomic_write(path, payload, *, mode=0o600):
        real_atomic_write(path, payload, mode=mode)
        if threading.current_thread() is regen_thread and Path(path) == key_path:
            rotated_digests.append(sha256(payload.encode("utf-8")).digest())
            serialization_state.put("published")

    monkeypatch.setattr(vault_module.os, "read", read_then_pause)
    monkeypatch.setattr(
        bootstrap_secrets_module, "file_lock", observed_file_lock, raising=False
    )
    monkeypatch.setattr(
        bootstrap_secrets_module, "atomic_write_secret_text", observed_atomic_write
    )

    def run_non_regen() -> None:
        try:
            bootstrap_secrets(out_dir)
        except (OSError, RuntimeError) as exc:
            worker_errors.append(type(exc).__name__)

    def run_regen() -> None:
        try:
            start_regen.wait(timeout=5)
            bootstrap_secrets(out_dir, regen=True)
        except (OSError, RuntimeError) as exc:
            worker_errors.append(type(exc).__name__)

    non_regen_thread = threading.Thread(target=run_non_regen, daemon=True)
    regen_thread = threading.Thread(target=run_regen, daemon=True)
    non_regen_thread.start()
    assert snapshot_captured.wait(timeout=5), "non-regen descriptor snapshot was not captured"
    regen_thread.start()
    start_regen.wait(timeout=5)

    state = serialization_state.get(timeout=5)
    try:
        if state == "published":
            if not rotated_digests or rotated_digests[0] == initial_digest:
                raise AssertionError("regen did not publish a genuinely new token key")
        elif state != "lock-attempted":
            raise AssertionError("unexpected bootstrap serialization state")
    finally:
        resume_non_regen.set()

    non_regen_thread.join(timeout=5)
    regen_thread.join(timeout=5)
    assert not non_regen_thread.is_alive(), "non-regen bootstrap did not stop"
    assert not regen_thread.is_alive(), "regen bootstrap did not stop"
    assert not worker_errors, f"bootstrap worker errors: {worker_errors}"
    if not rotated_digests or rotated_digests[0] == initial_digest:
        raise AssertionError("regen did not publish a genuinely new token key")
    if sha256(key_path.read_bytes()).digest() != rotated_digests[0]:
        raise AssertionError("stale non-regen snapshot replaced the rotated token key")


def test_regen_then_non_regen_serialization_preserves_latest_rotation(
    tmp_path, monkeypatch
):
    out_dir = tmp_path / "out"
    key_path = bootstrap_secrets(out_dir)["token_key"]
    initial_digest = sha256(key_path.read_bytes()).digest()

    ordering: Queue[str] = Queue()
    start_non_regen = threading.Barrier(2)
    non_regen_lock_attempted = threading.Event()
    resume_regen = threading.Event()
    rotated_digests: list[bytes] = []
    worker_errors: list[str] = []
    real_atomic_write = bootstrap_secrets_module.atomic_write_secret_text
    real_file_lock = vault_module.file_lock
    regen_thread: threading.Thread | None = None
    non_regen_thread: threading.Thread | None = None

    @contextmanager
    def ordered_file_lock(path):
        if threading.current_thread() is non_regen_thread:
            non_regen_lock_attempted.set()
        with real_file_lock(path):
            if threading.current_thread() is regen_thread:
                ordering.put("locked")
                if not resume_regen.wait(timeout=5):
                    raise RuntimeError("regen bootstrap did not resume while holding lock")
            yield

    def observed_atomic_write(path, payload, *, mode=0o600):
        real_atomic_write(path, payload, mode=mode)
        if threading.current_thread() is regen_thread and Path(path) == key_path:
            rotated_digests.append(sha256(payload.encode("utf-8")).digest())
            ordering.put("key-published")

    monkeypatch.setattr(
        bootstrap_secrets_module, "file_lock", ordered_file_lock, raising=False
    )
    monkeypatch.setattr(
        bootstrap_secrets_module, "atomic_write_secret_text", observed_atomic_write
    )

    def run_regen() -> None:
        try:
            bootstrap_secrets(out_dir, regen=True)
        except (OSError, RuntimeError) as exc:
            worker_errors.append(type(exc).__name__)

    def run_non_regen() -> None:
        try:
            start_non_regen.wait(timeout=5)
            bootstrap_secrets(out_dir)
        except (OSError, RuntimeError) as exc:
            worker_errors.append(type(exc).__name__)

    regen_thread = threading.Thread(target=run_regen, daemon=True)
    non_regen_thread = threading.Thread(target=run_non_regen, daemon=True)
    regen_thread.start()
    first_state = ordering.get(timeout=5)
    if first_state != "locked":
        regen_thread.join(timeout=5)
        raise AssertionError("regen bootstrap did not acquire the serialization lock")

    non_regen_thread.start()
    start_non_regen.wait(timeout=5)
    assert non_regen_lock_attempted.wait(timeout=5), "non-regen did not attempt the lock"
    resume_regen.set()
    regen_thread.join(timeout=5)
    non_regen_thread.join(timeout=5)

    assert not regen_thread.is_alive(), "regen bootstrap did not stop"
    assert not non_regen_thread.is_alive(), "non-regen bootstrap did not stop"
    assert not worker_errors, f"bootstrap worker errors: {worker_errors}"
    if not rotated_digests or rotated_digests[0] == initial_digest:
        raise AssertionError("regen did not publish a genuinely new token key")
    if sha256(key_path.read_bytes()).digest() != rotated_digests[0]:
        raise AssertionError("last serialized bootstrap did not preserve the rotated token key")
    if {entry.name for entry in (out_dir / "secrets").iterdir()} != {
        "forgeai_token.key"
    }:
        raise AssertionError("bootstrap lock artifact entered the secret directory")
