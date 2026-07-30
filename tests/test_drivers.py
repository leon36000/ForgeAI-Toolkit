import pytest
from forgeai.core.runner import FixtureRunner
from forgeai.hardware.drivers import (
    VENDORS,
    DriverError,
    detect_driver_state,
    plan_driver_op,
    recommend_driver,
)


def test_recommend_par_vendor():
    nvidia = recommend_driver("nvidia")
    assert nvidia.runtime == "cuda"
    assert nvidia.operator == "nvidia-gpu-operator"

    amd = recommend_driver("amd")
    assert amd.runtime == "vulkan"  # arch inconnue -> defaut Vulkan (sur)
    assert amd.rocm_allowed is True  # S1 : ROCm debloque (offert au choix)

    intel = recommend_driver("intel")
    assert intel.runtime == "openvino"
    assert intel.operator == "intel-device-plugins"


def test_amd_rocm_debloque_host_install_reste_vulkan():
    """S1 : ROCm est DÉBLOQUÉ (offert au choix), mais l'install driver HÔTE par défaut
    reste Vulkan (mesa) — l'install des drivers ROCm est gérée côté cluster par l'AMD
    GPU Operator (network/prepare.py), pas par apt hôte. Frontière de périmètre S1."""
    rec = recommend_driver("amd")
    assert rec.rocm_allowed is True
    assert "rocm" in rec.runtimes  # ROCm bien proposé

    plan = plan_driver_op("amd", "install")
    all_argv = plan.install_argv + plan.rollback_argv
    assert not any("rocm" in arg.lower() for arg in all_argv)  # host apt reste vulkan (S1)


def test_vendor_inconnu_leve():
    with pytest.raises(DriverError):
        recommend_driver("s3")

    with pytest.raises(DriverError):
        plan_driver_op("nvidia", "reboot")


def test_detect_state_via_runner():
    # HW-037 : detect_driver_state interroge desormais aussi detect_gpus
    # (nvidia-smi name,memory.total puis lspci -nn). Le fake route par cmd[0] :
    # la commande d'origine garde sa reponse actuelle, lspci et tout nvidia-smi
    # non prevu renvoient (1, "") -> model=None, recommandation par defaut.
    fx = _RunnerRoute({("nvidia-smi", "--query-gpu=driver_version"): (0, "550.90.07\n")})
    state = detect_driver_state("nvidia", fx)
    assert state.present is True
    assert state.version == "550.90.07"
    assert state.recommendation.runtime == "cuda"


def test_detect_absent():
    # Absence de la commande dans le fake route -> (1, "") partout : code != 0
    fx = _RunnerRoute({})
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


class _RunnerRoute:
    """Runner fake : route par commande, (1, "") pour tout le reste."""

    def __init__(self, reponses):
        self._reponses = reponses  # dict: cle = cmd[0] ou tuple(cmd[:2]), valeur = (code, out)

    def run(self, cmd):
        for cle, rep in self._reponses.items():
            attendu = cle if isinstance(cle, tuple) else (cle,)
            if tuple(cmd[: len(attendu)]) == attendu:
                return rep
        return (1, "")


def test_chemin_reel_instinct_recommande_rocm():
    """Prouve le branchement du modèle détecté sur le chemin RÉEL : un Instinct
    détecté via lspci (même runner injecté) fait recommander rocm par
    detect_driver_state, sans aucun model= passé à la main. Ce test échoue sur
    le code d'avant HW-037 (défaut vulkan) : c'est sa raison d'être."""
    runner = _RunnerRoute({
        ("cat", "/sys/module/amdgpu/version"): (0, "6.8.5"),
        ("lspci",): (0, "0000:03:00.0 3D controller [0302]: AMD Instinct MI300X [1002:74a1]"),
    })
    state = detect_driver_state("amd", runner)
    assert state.recommendation.runtime == "rocm", (
        f"recommandation inattendue : {state.recommendation}")


def test_chemin_reel_radeon_reste_vulkan():
    """Un Radeon (RDNA) détecté sur le chemin réel garde vulkan en runtime
    recommandé, rocm restant proposé en alternative."""
    runner = _RunnerRoute({
        ("cat", "/sys/module/amdgpu/version"): (0, "6.8.5"),
        ("lspci",): (0, "0000:03:00.0 VGA compatible controller [0300]: AMD Radeon RX 7900 XTX [1002:744c]"),
    })
    state = detect_driver_state("amd", runner)
    assert state.recommendation.runtime == "vulkan", (
        f"recommandation inattendue : {state.recommendation}")
    assert "rocm" in state.recommendation.runtimes


def test_cli_amd_instinct_affiche_rocm_sans_message_mort(monkeypatch, tmp_path, capsys):
    """Chemin CLI public complet sur Instinct : la sortie affiche la
    recommandation rocm issue du moteur et l'ordre des runtimes ; le message
    mort ' (ROCm jamais proposé)' a disparu et ne doit jamais revenir."""
    from forgeai.cli import main
    routeur = _RunnerRoute({
        ("cat", "/sys/module/amdgpu/version"): (0, "6.8.5"),
        ("lspci",): (0, "0000:03:00.0 3D controller [0302]: AMD Instinct MI300X [1002:74a1]"),
    })
    monkeypatch.setattr("forgeai.core.runner.SubprocessRunner.run",
                        lambda self, cmd: routeur.run(cmd))
    assert main(["gpu", "drivers", "--vendor", "amd",
                 "--registre", str(tmp_path / "r.jsonl")]) == 0
    out = capsys.readouterr().out
    assert "jamais proposé" not in out
    assert "runtime rocm" in out
    assert "rocm > vulkan" in out


def test_cli_nvidia_sans_mention_rocm(monkeypatch, tmp_path, capsys):
    """Chemin CLI nvidia : la sortie ne mentionne ROCm nulle part et affiche
    la recommandation cuda issue du moteur."""
    from forgeai.cli import main
    routeur = _RunnerRoute({
        ("nvidia-smi", "--query-gpu=driver_version"): (0, "560.35.03"),
    })
    monkeypatch.setattr("forgeai.core.runner.SubprocessRunner.run",
                        lambda self, cmd: routeur.run(cmd))
    assert main(["gpu", "drivers", "--vendor", "nvidia",
                 "--registre", str(tmp_path / "r.jsonl")]) == 0
    out = capsys.readouterr().out
    assert "ROCm" not in out
    assert "runtime cuda" in out
