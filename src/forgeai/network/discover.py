"""Découverte d'infrastructure logicielle déjà installée sur un nœud.

Utilise un runner injectable (SubprocessRunner local, SshRunner distant) pour
sonder binaires, conteneurs, ports d'écoute et GPU NVIDIA.
"""
from __future__ import annotations

import importlib.resources
import json
import re
from typing import Any


class DiscoverError(Exception):
    """Erreur lors de la découverte d'infrastructure."""


def _normalize_image(image: str) -> str:
    """Retire tag/digest d'une image conteneur pour comparaison."""
    return image.split("@")[0].split(":")[0]


def _image_match(container_image: str | None, signature_image: str | None) -> bool:
    """Vérifie si une image de conteneur correspond au motif de signature."""
    if container_image is None or signature_image is None:
        return False
    container_image = container_image.strip()
    signature_image = signature_image.strip()
    if not container_image or not signature_image:
        return False

    norm_container = _normalize_image(container_image)
    norm_signature = _normalize_image(signature_image)

    if norm_container == norm_signature:
        return True

    # Correspondance sur le nom de repo final (ex. docker.io/library/redis -> redis)
    if norm_container.split("/")[-1] == norm_signature.split("/")[-1]:
        return True

    # Correspondance explicite avec namespace
    if norm_container.endswith("/" + norm_signature) or norm_signature.endswith(
        "/" + norm_container
    ):
        return True

    return False


def _parse_ss_ports(stdout: str) -> set[int]:
    """Extrait les ports en écoute depuis la sortie de `ss -tlnH`/`ss -tln`."""
    ports: set[int] = set()
    for line in stdout.splitlines():
        line = line.strip()
        if not line or line.lower().startswith("state"):
            continue
        parts = line.split()
        if len(parts) < 4:
            continue
        addr = parts[3]
        match = re.search(r":(\d+)$", addr)
        if match:
            try:
                ports.add(int(match.group(1)))
            except ValueError:
                continue
    return ports


def _sonder(runner) -> dict[str, Any]:
    """Sonde le nœud et retourne les données brutes de détection."""
    signatures = charger_signatures()

    binaires: dict[str, bool] = {}
    for sig in signatures:
        binaire = sig.get("binaire")
        if binaire:
            code, _ = runner.run(["sh", "-c", f"command -v {binaire}"])
            binaires[sig["id"]] = code == 0

    conteneurs: list[dict[str, str]] = []
    if binaires.get("docker", False):
        code, out = runner.run(
            ["docker", "ps", "--format", "{{.Image}}|{{.Names}}|{{.Ports}}"]
        )
        if code == 0:
            for line in out.splitlines():
                line = line.strip()
                if not line:
                    continue
                parts = line.split("|")
                if len(parts) >= 3:
                    conteneurs.append(
                        {"image": parts[0], "names": parts[1], "ports": parts[2]}
                    )

    ports_ecoute: set[int] = set()
    for ss_argv in (["ss", "-tlnH"], ["ss", "-tln"]):
        code, out = runner.run(ss_argv)
        if code == 0:
            ports_ecoute = _parse_ss_ports(out)
            break

    gpu_nvidia = 0
    code, out = runner.run(["nvidia-smi", "-L"])
    if code == 0:
        gpu_nvidia = sum(1 for line in out.splitlines() if "GPU" in line)

    return {
        "binaires": binaires,
        "conteneurs": conteneurs,
        "ports_ecoute": sorted(ports_ecoute),
        "gpu_nvidia": gpu_nvidia,
    }


def inventaire(runner, signatures: list[dict]) -> dict[str, Any]:
    """Croise les signatures avec les données sondées sur le nœud."""
    sonde = _sonder(runner)
    binaires = sonde["binaires"]
    conteneurs = sonde["conteneurs"]
    ports_ecoute = set(sonde["ports_ecoute"])
    gpu_nvidia = sonde["gpu_nvidia"]

    services: list[dict[str, Any]] = []
    detectes = 0
    for sig in signatures:
        via: list[str] = []
        endpoint: str | None = None

        if sig.get("binaire") and binaires.get(sig["id"], False):
            via.append("binaire")

        port = sig.get("port")
        if port is not None and port in ports_ecoute:
            via.append("port")
            endpoint = f"127.0.0.1:{port}"

        image = sig.get("image")
        if image is not None:
            for cont in conteneurs:
                if _image_match(cont.get("image"), image):
                    via.append("conteneur")
                    break

        detecte = len(via) > 0
        if detecte:
            detectes += 1

        services.append(
            {
                **sig,
                "detecte": detecte,
                "via": via,
                "endpoint": endpoint,
            }
        )

    return {
        "services": services,
        "gpu_nvidia": gpu_nvidia,
        "resume": {"detectes": detectes, "total": len(signatures)},
    }


def charger_signatures() -> list[dict]:
    """Charge le registre des signatures embarquées."""
    raw = (
        importlib.resources.files("forgeai.data") / "signatures-infra.json"
    ).read_text(encoding="utf-8")
    data = json.loads(raw)
    return data["signatures"]
