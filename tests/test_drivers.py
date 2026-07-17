import pytest
from forgeai.hardware.drivers import (
    DriverError,
    VENDORS,
    DriverRecommendation,
    DriverState,
    DriverOpPlan,
    recommend_driver,
    detect_driver_state,
    plan_driver_op,
)
from forgeai.core.runner import FixtureRunner


def test_recommend_par_vendor():
    nvidia = recommend_driver("nvidia")
    assert nvidia.runtime == "cuda"
    assert nvidia.operator == "nvidia-gpu-operator"

    amd = recommend_driver("amd")
    assert amd.runtime == "vulkan"
    assert amd.rocm_allowed is False

    intel = recommend_driver("intel")
    assert intel.runtime == "openvino"
    assert intel.operator == "intel-device-plugins"


def test_amd_rocm_jamais_propose():
    rec = recommend_driver("amd")
    assert rec.rocm_allowed is False

    plan = plan_driver_op("amd", "install")
    all_argv = plan.install_argv + plan.rollback_argv
    assert not any("rocm" in arg.lower() for arg in all_argv)


def test_vendor_inconnu_leve():
    with pytest.raises(DriverError):
        recommend_driver("s3")

    with pytest.raises(DriverError):
        plan_driver_op("nvidia", "reboot")


def test_detect_state_via_runner():
    fx = FixtureRunner({"nvidia-smi": "550.90.07\n"})
    state = detect_driver_state("nvidia", fx)
    assert state.present is True
    assert state.version == "550.90.07"
    assert state.recommendation.runtime == "cuda"


def test_detect_absent():
    # Absence de la commande dans le FixtureRunner -> code != 0
    fx = FixtureRunner({})
    state = detect_driver_state("amd", fx)
    assert state.present is False


def test_plan_a_toujours_un_rollback():
    for vendor in VENDORS:
        plan = plan_driver_op(vendor, "install")
        assert plan.rollback_argv, f"Rollback vide pour {vendor}"


def test_nvidia_rollback_differe_de_install():
    """Un vrai rollback vise une version DIFFÉRENTE de l'installation."""
    from forgeai.hardware.drivers import plan_driver_op
    p = plan_driver_op("nvidia", "install", version="550")
    assert p.install_argv != p.rollback_argv
    assert p.install_argv[-1] != p.rollback_argv[-1]


def test_cli_gpu_drivers_amd(tmp_path, capsys):
    """Chemin CLI : AMD recommande Vulkan (pas de paquet ROCm), journalise."""
    from forgeai.cli import main
    reg = tmp_path / "r.jsonl"
    assert main(["gpu", "drivers", "--vendor", "amd", "--action", "install",
                 "--registre", str(reg)]) == 0
    out = capsys.readouterr().out
    assert "vulkan" in out and "mesa-vulkan-drivers" in out
    assert "gpu_drivers" in reg.read_text(encoding="utf-8")
