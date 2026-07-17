from dataclasses import dataclass

VENDORS = ("nvidia", "amd", "intel")


class DriverError(Exception):
    """Erreur de driver."""


@dataclass(frozen=True)
class DriverRecommendation:
    vendor: str
    runtime: str
    operator: str
    rocm_allowed: bool
    notes: str


@dataclass(frozen=True)
class DriverState:
    vendor: str
    present: bool
    version: str
    recommendation: DriverRecommendation


@dataclass(frozen=True)
class DriverOpPlan:
    vendor: str
    action: str
    install_argv: list[str]
    rollback_argv: list[str]
    notes: str


def recommend_driver(vendor: str) -> DriverRecommendation:
    if vendor not in VENDORS:
        raise DriverError(f"Unknown vendor: {vendor}")
    if vendor == "nvidia":
        return DriverRecommendation(
            vendor="nvidia",
            runtime="cuda",
            operator="nvidia-gpu-operator",
            rocm_allowed=False,
            notes="",
        )
    elif vendor == "amd":
        return DriverRecommendation(
            vendor="amd",
            runtime="vulkan",
            operator="none",
            rocm_allowed=False,
            notes="Vulkan forcé, ROCm non proposé",
        )
    elif vendor == "intel":
        return DriverRecommendation(
            vendor="intel",
            runtime="openvino",
            operator="intel-device-plugins",
            rocm_allowed=False,
            notes="",
        )
    # Dead branch – kept for completeness
    raise DriverError(f"Unknown vendor: {vendor}")


def detect_driver_state(vendor: str, runner) -> DriverState:
    if vendor not in VENDORS:
        raise DriverError(f"Unknown vendor: {vendor}")
    cmd_map = {
        "nvidia": ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"],
        "amd": ["cat", "/sys/module/amdgpu/version"],
        "intel": ["clinfo", "--list"],
    }
    cmd = cmd_map[vendor]
    code, out = runner.run(cmd)
    present = (code == 0) and bool(out.strip())
    if present:
        if vendor == "nvidia":
            version = out.strip().splitlines()[0].strip()
        elif vendor == "amd":
            version = out.strip()
        else:  # intel
            version = ""
    else:
        version = ""
    recommendation = recommend_driver(vendor)
    return DriverState(
        vendor=vendor,
        present=present,
        version=version,
        recommendation=recommendation,
    )


def plan_driver_op(vendor: str, action: str, *, version: str | None = None) -> DriverOpPlan:
    if action not in {"install", "update"}:
        raise DriverError(f"Unsupported action: {action}")
    if vendor not in VENDORS:
        raise DriverError(f"Unknown vendor: {vendor}")
    if vendor == "nvidia":
        target = version or "550"
        prior = "535"  # LTS stable précédente : le rollback DOIT viser une version différente
        install_argv = ["apt-get", "install", "-y", f"nvidia-driver-{target}"]
        rollback_argv = ["apt-get", "install", "-y", "--allow-downgrades",
                         f"nvidia-driver-{prior}"]
        notes = ""
    elif vendor == "amd":
        install_argv = ["apt-get", "install", "-y", "mesa-vulkan-drivers", "vulkan-tools"]
        rollback_argv = ["apt-get", "install", "-y", "--reinstall", "mesa-vulkan-drivers"]
        notes = "Vulkan forcé, ROCm non proposé"
    else:  # intel
        install_argv = ["apt-get", "install", "-y", "intel-opencl-icd"]
        rollback_argv = ["apt-get", "install", "-y", "--reinstall", "intel-opencl-icd"]
        notes = ""
    return DriverOpPlan(
        vendor=vendor,
        action=action,
        install_argv=install_argv,
        rollback_argv=rollback_argv,
        notes=notes,
    )
