"""Tests S04 (assemblage) et S05 (bootstrap secrets)."""
import os
import stat
import sys
from hashlib import sha256
from pathlib import Path
from secrets import token_hex

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from forgeai.bootstrap import secrets as bootstrap_secrets_module
from forgeai.bootstrap.secrets import bootstrap_secrets
from forgeai.core.models import RenderTarget
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


def test_secrets_generes_permissions_0600(tmp_path):
    paths = bootstrap_secrets(tmp_path)
    for p in (paths["env"], paths["token_key"]):
        assert p.exists()
        assert stat.S_IMODE(p.stat().st_mode) == 0o600
    content = paths["env"].read_text(encoding="utf-8")
    assert "FORGEAI_API_TOKEN=" in content
    token = content.splitlines()[0].split("=", 1)[1]
    assert len(token) == 64  # 256 bits hex


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


def test_existing_token_key_hardlink_is_refused_without_touching_external_inode(
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

    with pytest.raises(OSError):
        bootstrap_secrets(out_dir)

    assert key_path.stat().st_ino == external.stat().st_ino
    assert stat.S_IMODE(external.stat().st_mode) == external_mode
    if sha256(external.read_bytes()).digest() != external_digest:
        raise AssertionError("writer changed external hardlink content")
