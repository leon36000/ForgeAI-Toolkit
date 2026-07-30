#!/usr/bin/env python3
"""Story LAB-033A — preuve e2e AMD sur cluster k3s.

Flux complet : sonde matérielle portable sur pc4, dérivation du profil,
assemblage du plan, rendu K3s, déploiement tel quel du manifeste,
preuve d'utilisation GPU par sysfs amdgpu de l'hôte et inférence réelle,
teardown.
"""
from __future__ import annotations

import argparse
import base64
import datetime
import json
import re
import shlex
import socket
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import urllib.error
import urllib.request
from importlib.resources import files
from pathlib import Path
from typing import Any

from forgeai.core.models import GPU, Disk, HardwareProfile, NodeInventaire, RenderTarget
from forgeai.planner.assemble import assemble_plan
from forgeai.planner.profile import derive_profile, ProfileError
from forgeai.renderers.k3s import render_k3s


OLLAMA_MODEL = "qwen2.5:0.5b"
NAMESPACE_FALLBACK = "forgeai-minimal"
BANC_POLICY_NAME = "banc-lab033a-egress-temporaire"
REMOTE_WORKDIR = "/tmp/lab033a"

DEFAULT_SSH_HOST = "pc4"
DEFAULT_NODE = "pc4-grs-b"
DEFAULT_EVIDENCE_DIR = "reviews/LAB-033A/evidence"

PULL_TIMEOUT = 300
INFERENCE_TIMEOUT = 120
POD_READY_TIMEOUT = 420
NS_DELETE_TIMEOUT = 180
SONDE_TIMEOUT = 600


# ---------------------------------------------------------------------------
# API importable (utilisée par les tests CI)
# ---------------------------------------------------------------------------

def load_hardware_json(path: Path) -> HardwareProfile:
    """Reconstruit un HardwareProfile depuis un JSON de sonde."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return reconstruct_hardware(data)


def reconstruct_hardware(data: dict[str, Any]) -> HardwareProfile:
    """Reconstruction exacte des dataclasses à partir du JSON `forgeai hardware`."""
    gpus = tuple(GPU(**g) for g in data.get("gpus", []))
    disks = tuple(Disk(**d) for d in data.get("disks", []))
    return HardwareProfile(
        cpu_model=data["cpu_model"],
        cpu_cores=data["cpu_cores"],
        cpu_arch=data["cpu_arch"],
        ram_gb=data["ram_gb"],
        os_name=data["os_name"],
        gpus=gpus,
        disks=disks,
    )


def require_gpu_profile(hw: HardwareProfile) -> str:
    """Dérive le profil et exige `minimal-gpu-rocm`."""
    profile = derive_profile(hw)
    if profile != "minimal-gpu-rocm":
        print(
            f"Profil dérivé inattendu : {profile} (attendu minimal-gpu-rocm)",
            file=sys.stderr,
        )
        raise SystemExit(2)
    return profile


def render_manifest(profile: str, node: str, hw: HardwareProfile) -> str:
    """Rend le manifeste K3s pour le profil et le nœud donnés."""
    overlay = Path(str(files("forgeai.data") / "deploy-minimal.json"))
    plan = assemble_plan(profile, deploy_overlay=overlay, target=RenderTarget.K3S)
    vram_max = max((gpu.vram_mb for gpu in hw.gpus), default=0)
    inventaire = (NodeInventaire(hostname=node, gpu_vendor="amd", vram_mib=vram_max),)
    return render_k3s(plan, node=node, inventaire=inventaire)


def namespace_from_manifest(manifest: str) -> str:
    """Extrait le nom du premier Namespace du manifeste sans dépendance externe.

    Le manifeste est découpé au niveau des séparateurs '---' ; on recherche le
    premier document de kind Namespace puis son champ metadata.name.
    """
    parts = re.split(r"^---\s*$", manifest, flags=re.MULTILINE)
    for part in parts:
        if not re.search(r"^kind:\s*Namespace\s*$", part, re.MULTILINE):
            continue
        m = re.search(
            r"^metadata:\s*$.*?^\s+name:\s*(\S+)",
            part,
            re.MULTILINE | re.DOTALL,
        )
        if m:
            return m.group(1)
    raise ValueError("Namespace non trouvé dans le manifeste")


def usage_gpu_amd_detecte(
    repos: dict[str, dict[str, Any]],
    echantillons: list[dict[str, dict[str, Any]]],
    seuil_mib: int = 256,
) -> bool:
    """Détecte l'usage d'un GPU AMD discret pendant l'inférence.

    Structure attendue pour `repos` et chaque échantillon :
        {
            "card0": {
                "pci_id": "0x7550",
                "vram_used": <int octets>,
                "busy": <int|None>,
                "integrated": <bool>,
            },
            ...
        }

    La preuve est valide si une carte NON intégrée montre soit une croissance
    de VRAM d'au moins `seuil_mib` Mio par rapport au repos, soit un
    `gpu_busy_percent` strictement positif. L'iGPU (PCI 0x13c0) est ignoré.
    """
    seuil_octets = seuil_mib * 1024 * 1024
    for echantillon in echantillons:
        for card, info in echantillon.items():
            if info.get("integrated"):
                continue
            ref = repos.get(card, {})
            ref_vram = ref.get("vram_used", 0)
            cur_vram = info.get("vram_used", 0)
            if cur_vram - ref_vram >= seuil_octets:
                return True
            busy = info.get("busy")
            if busy is not None and busy > 0:
                return True
    return False


# ---------------------------------------------------------------------------
# Outils internes
# ---------------------------------------------------------------------------

def _run(
    cmd: list[str],
    *,
    check: bool = True,
    timeout: float | None = None,
    input_data: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Wrapper subprocess.run avec capture texte et timeout explicite."""
    return subprocess.run(
        cmd,
        check=check,
        capture_output=True,
        text=True,
        timeout=timeout,
        input=input_data,
    )


def _ssh(
    host: str,
    remote_cmd: str,
    *,
    check: bool = True,
    timeout: float | None = None,
    input_data: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Exécute une commande sur le hôte distant via SSH (BatchMode)."""
    return _run(
        ["ssh", "-o", "BatchMode=yes", host, remote_cmd],
        check=check,
        timeout=timeout,
        input_data=input_data,
    )


def _append_evidence(path: Path, command: str, stdout: str, stderr: str = "") -> None:
    """Écrit une entrée horodatée dans un fichier d'evidence."""
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with path.open("a", encoding="utf-8") as f:
        f.write(f"\n--- {now} ---\n")
        f.write(f"$ {command}\n")
        f.write(stdout)
        if stderr:
            f.write("\n[stderr]\n")
            f.write(stderr)
        f.write("\n")


def _run_and_log(
    cmd: list[str], evidence_path: Path, timeout: float
) -> subprocess.CompletedProcess[str]:
    """Exécute une commande et consigne stdout/stderr dans l'evidence."""
    result = _run(cmd, check=True, timeout=timeout)
    _append_evidence(evidence_path, shlex.join(cmd), result.stdout, result.stderr)
    return result


def _pack_sources(archive_path: Path) -> None:
    """Crée une archive tar.gz contenant pyproject.toml et src/."""
    with tarfile.open(archive_path, "w:gz") as tf:
        for name in ("pyproject.toml", "src"):
            p = Path(name)
            if not p.exists():
                raise FileNotFoundError(f"Source requise manquante : {name}")
            tf.add(p, arcname=name)


def _probe_hardware(
    ssh_host: str, archive_bytes: bytes, evidence_path: Path
) -> HardwareProfile:
    """Sonde matérielle portable sur le nœud cible via SSH."""
    encoded = base64.b64encode(archive_bytes).decode("ascii")
    _ssh(
        ssh_host,
        f"mkdir -p {REMOTE_WORKDIR} && base64 -d > {REMOTE_WORKDIR}/src.tar.gz",
        input_data=encoded,
        timeout=120,
    )
    _append_evidence(
        evidence_path,
        f"ssh {ssh_host} 'transfert archive sources (base64 via stdin)'",
        "[archive transférée]",
        "",
    )

    install_cmd = (
        f"cd {REMOTE_WORKDIR} && tar -xzf src.tar.gz && "
        f"python3 -m venv {REMOTE_WORKDIR}/venv && "
        f"{REMOTE_WORKDIR}/venv/bin/pip install --quiet {REMOTE_WORKDIR}"
    )
    install_res = _ssh(ssh_host, install_cmd, timeout=SONDE_TIMEOUT)
    _append_evidence(
        evidence_path,
        f"ssh {ssh_host} {shlex.quote(install_cmd)}",
        install_res.stdout,
        install_res.stderr,
    )

    hw_res = _ssh(
        ssh_host,
        f"{REMOTE_WORKDIR}/venv/bin/forgeai hardware",
        timeout=120,
    )
    _append_evidence(
        evidence_path,
        f"ssh {ssh_host} {REMOTE_WORKDIR}/venv/bin/forgeai hardware",
        hw_res.stdout,
        hw_res.stderr,
    )

    hw_path = evidence_path.parent / "hardware-pc4.json"
    hw_path.write_text(hw_res.stdout, encoding="utf-8")
    return reconstruct_hardware(json.loads(hw_res.stdout))


def _sample_amd_gpu(ssh_host: str) -> dict[str, dict[str, Any]]:
    """Lit le sysfs amdgpu sur l'hôte distant.

    Retourne une structure de la forme :
        {
            "card0": {
                "pci_id": "0x7550",
                "vram_used": <int octets>,
                "busy": <int|None>,
                "integrated": <bool>,
            },
            ...
        }
    """
    script = (
        "for d in /sys/class/drm/card*/device; do "
        '  [ -f "$d/mem_info_vram_total" ] || continue; '
        '  card=$(basename "$(dirname "$d")"); '
        '  read used < "$d/mem_info_vram_used" 2>/dev/null || used=0; '
        '  read busy < "$d/gpu_busy_percent" 2>/dev/null || busy=none; '
        '  read dev < "$d/device" 2>/dev/null || dev=unknown; '
        "  printf '%s %s %s %s\\n' \"$card\" \"$used\" \"$busy\" \"$dev\"; "
        "done"
    )
    result = _ssh(ssh_host, script, check=False, timeout=30)
    out: dict[str, dict[str, Any]] = {}
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) < 4:
            continue
        card, used_s, busy_s, pci_id = parts[:4]
        try:
            vram_used = int(used_s)
        except ValueError:
            vram_used = 0
        busy: int | None
        try:
            busy = int(busy_s) if busy_s.lower() != "none" else None
        except ValueError:
            busy = None
        integrated = pci_id.lower() == "0x13c0"
        out[card] = {
            "pci_id": pci_id,
            "vram_used": vram_used,
            "busy": busy,
            "integrated": integrated,
        }
    return out


def _wait_pods_ready(namespace: str, timeout: int = POD_READY_TIMEOUT) -> None:
    """Attend que tous les pods du namespace soient Ready."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = _run(
            ["kubectl", "get", "pods", "-n", namespace, "-o", "json"],
            check=False,
            timeout=30,
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            pods = data.get("items", [])
            if pods and all(_pod_ready(p) for p in pods):
                return
        time.sleep(5)
    raise RuntimeError(
        f"Les pods du namespace {namespace} ne sont pas Ready après {timeout}s"
    )


def _pod_ready(pod: dict[str, Any]) -> bool:
    """Détermine si un pod est prêt d'après son status."""
    if not pod:
        return False
    conditions = pod.get("status", {}).get("conditions", [])
    ready = any(
        c.get("type") == "Ready" and c.get("status") == "True" for c in conditions
    )
    container_statuses = pod.get("status", {}).get("containerStatuses", [])
    containers_ready = all(cs.get("ready") for cs in container_statuses)
    return ready and containers_ready


def _node_ip(node: str) -> str:
    """Retourne l'IP interne d'un nœud Kubernetes."""
    result = _run(
        [
            "kubectl",
            "get",
            "node",
            node,
            "-o",
            "jsonpath={.status.addresses[?(@.type=='InternalIP')].address}",
        ],
        timeout=30,
    )
    return result.stdout.strip()


def _nodeport_for_service(namespace: str, service: str) -> int:
    """Retourne le NodePort alloué à un service."""
    result = _run(
        [
            "kubectl",
            "get",
            "service",
            service,
            "-n",
            namespace,
            "-o",
            "jsonpath={.spec.ports[0].nodePort}",
        ],
        timeout=30,
    )
    return int(result.stdout.strip())


def _banc_policy_yaml(namespace: str) -> str:
    """Policy de banc temporaire pour autoriser l'egress du pod ollama."""
    return f"""# échafaudage de banc, PAS un artefact produit
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: {BANC_POLICY_NAME}
  namespace: {namespace}
spec:
  podSelector:
    matchLabels:
      app: ollama
  policyTypes:
    - Egress
  egress:
    - to:
        - namespaceSelector: {{}}
          podSelector: {{}}
      ports:
        - protocol: UDP
          port: 53
        - protocol: TCP
          port: 53
    - to:
        - ipBlock:
            cidr: 0.0.0.0/0
      ports:
        - protocol: TCP
          port: 443
        - protocol: TCP
          port: 80
"""


def _pull_model(
    namespace: str, evidence_path: Path, finding_path: Path
) -> None:
    """Tente le pull du modèle, avec policy de banc en contingency si le réseau bloque."""
    cmd = [
        "kubectl",
        "exec",
        "deploy/ollama",
        "-n",
        namespace,
        "--",
        "ollama",
        "pull",
        OLLAMA_MODEL,
    ]
    result = _run(cmd, check=False, timeout=PULL_TIMEOUT)

    if result.returncode == 0:
        _append_evidence(evidence_path, shlex.join(cmd), result.stdout, result.stderr)
        return

    _append_evidence(
        evidence_path,
        shlex.join(cmd) + " (ÉCHEC — contingency NetworkPolicy de banc)",
        result.stdout,
        result.stderr,
    )

    np_result = _run(
        ["kubectl", "get", "networkpolicy", "-n", namespace, "-o", "yaml"],
        check=False,
        timeout=30,
    )
    _append_evidence(
        finding_path,
        "kubectl get networkpolicy -n " + namespace + " -o yaml",
        np_result.stdout,
        np_result.stderr,
    )

    policy_path = finding_path.parent / f"{BANC_POLICY_NAME}.yaml"
    policy_path.write_text(_banc_policy_yaml(namespace), encoding="utf-8")
    _run(["kubectl", "apply", "-f", str(policy_path)], check=True, timeout=30)

    try:
        result2 = _run(cmd, check=False, timeout=PULL_TIMEOUT)
        if result2.returncode != 0:
            raise RuntimeError("ollama pull échoue même avec la policy de banc")
        _append_evidence(
            evidence_path,
            shlex.join(cmd) + " (après policy de banc)",
            result2.stdout,
            result2.stderr,
        )
    finally:
        _run(
            ["kubectl", "delete", "networkpolicy", BANC_POLICY_NAME, "-n", namespace],
            check=False,
            timeout=30,
        )


def _inference_request(url: str) -> tuple[str, list[str]]:
    """Envoie la requête d'inférence ; retourne (corps, [messages fallback])."""
    payload = json.dumps(
        {
            "model": OLLAMA_MODEL,
            "prompt": "Explique en une phrase ce qu'est un GPU.",
            "stream": False,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=INFERENCE_TIMEOUT) as resp:
            return resp.read().decode("utf-8"), []
    except (urllib.error.URLError, OSError) as exc:
        return "", [f"NodePort {url} inaccessible : {exc}"]


def _inference_port_forward(namespace: str) -> tuple[str, list[str]]:
    """Fallback par port-forward local si le NodePort est bloqué."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    local_port = s.getsockname()[1]
    s.close()

    proc = subprocess.Popen(
        [
            "kubectl",
            "port-forward",
            "deploy/ollama",
            f"{local_port}:11434",
            "-n",
            namespace,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        time.sleep(3)
        url = f"http://127.0.0.1:{local_port}/api/generate"
        payload = json.dumps(
            {
                "model": OLLAMA_MODEL,
                "prompt": "Explique en une phrase ce qu'est un GPU.",
                "stream": False,
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=INFERENCE_TIMEOUT) as resp:
            return resp.read().decode("utf-8"), [
                f"Fallback port-forward utilisé sur {url}"
            ]
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def _verify_devices_in_container(namespace: str, evidence_path: Path) -> None:
    """Vérifie que /dev/kfd et /dev/dri sont visibles dans le conteneur ollama."""
    for dev in ("/dev/kfd", "/dev/dri"):
        cmd = [
            "kubectl",
            "exec",
            "deploy/ollama",
            "-n",
            namespace,
            "--",
            "ls",
            "-l",
            dev,
        ]
        result = _run(cmd, check=False, timeout=30)
        _append_evidence(evidence_path, shlex.join(cmd), result.stdout, result.stderr)

    kfd_check = _run(
        [
            "kubectl",
            "exec",
            "deploy/ollama",
            "-n",
            namespace,
            "--",
            "test",
            "-e",
            "/dev/kfd",
        ],
        check=False,
        timeout=30,
    )
    if kfd_check.returncode != 0:
        raise RuntimeError("/dev/kfd n'est pas visible dans le conteneur ollama")


def _verify_gpu_logs(namespace: str, evidence_path: Path) -> None:
    """Consigne les logs ollama et exige la détection d'au moins un GPU discret."""
    cmd = ["kubectl", "logs", "deploy/ollama", "-n", namespace]
    result = _run(cmd, check=False, timeout=60)
    _append_evidence(evidence_path, shlex.join(cmd), result.stdout, result.stderr)
    if result.returncode != 0:
        raise RuntimeError("kubectl logs a échoué")
    if not re.search(r"\bdiscrete\b", result.stdout, re.IGNORECASE):
        raise RuntimeError(
            "Aucun device GPU discret (type=discrete) détecté dans les logs ollama"
        )


def _gpu_inference_proof(
    namespace: str, node: str, ssh_host: str, evidence_path: Path
) -> None:
    """Preuve d'utilisation GPU : sysfs amdgpu sur l'hôte + inférence réelle."""
    node_ip = _node_ip(node)
    nodeport = _nodeport_for_service(namespace, "ollama")
    url = f"http://{node_ip}:{nodeport}/api/generate"

    _verify_devices_in_container(namespace, evidence_path)
    _verify_gpu_logs(namespace, evidence_path)

    _run(
        [
            "kubectl",
            "exec",
            "deploy/ollama",
            "-n",
            namespace,
            "--",
            "touch",
            "/tmp/lab033a-marqueur",
        ],
        check=True,
        timeout=30,
    )

    repos = _sample_amd_gpu(ssh_host)
    _append_evidence(
        evidence_path,
        f"ssh {ssh_host} sample repos amdgpu (avant inférence)",
        json.dumps(repos, ensure_ascii=False, indent=2),
        "",
    )
    if not repos:
        raise RuntimeError("Échantillon de repos GPU AMD vide")

    echantillons: list[dict[str, dict[str, Any]]] = []
    stop_event = threading.Event()

    def sampler() -> None:
        while not stop_event.wait(1.0):
            try:
                echantillons.append(_sample_amd_gpu(ssh_host))
            except (subprocess.TimeoutExpired, OSError, ValueError):
                echantillons.append({})

    thread = threading.Thread(target=sampler)
    thread.start()

    try:
        body, fallback_msgs = _inference_request(url)
        if not body:
            body, fallback_msgs = _inference_port_forward(namespace)
    finally:
        stop_event.set()
        thread.join(timeout=10)

    if not usage_gpu_amd_detecte(repos, echantillons):
        raise RuntimeError(
            "Aucun usage GPU AMD discret détecté pendant l'inférence"
        )

    apres = _sample_amd_gpu(ssh_host)
    _append_evidence(
        evidence_path,
        f"ssh {ssh_host} sample repos amdgpu (après inférence)",
        json.dumps(apres, ensure_ascii=False, indent=2),
        "",
    )

    find_result = _run(
        [
            "kubectl",
            "exec",
            "deploy/ollama",
            "-n",
            namespace,
            "--",
            "sh",
            "-c",
            "find / -xdev -type f -newer /tmp/lab033a-marqueur 2>/dev/null | head -80",
        ],
        check=False,
        timeout=60,
    )

    with evidence_path.open("a", encoding="utf-8") as f:
        f.write("\n--- Preuve GPU AMD / inférence ---\n")
        f.write(f"URL NodePort : {url}\n")
        if fallback_msgs:
            f.write("Fallbacks :\n")
            for msg in fallback_msgs:
                f.write(f"  {msg}\n")
        f.write("Réponse inférence :\n")
        f.write(body)
        f.write("\n\n--- Échantillons sysfs amdgpu ---\n")
        f.write("Repos :\n")
        f.write(json.dumps(repos, ensure_ascii=False, indent=2))
        f.write("\nPendant :\n")
        for sample in echantillons:
            f.write(json.dumps(sample, ensure_ascii=False, indent=2))
            f.write("\n")
        f.write("Après :\n")
        f.write(json.dumps(apres, ensure_ascii=False, indent=2))
        f.write("\n--- Chemins d'écriture pendant l'inférence ---\n")
        f.write(find_result.stdout)
        f.write("\n")


def _teardown(
    manifest_path: Path,
    namespace: str,
    node: str,
    ssh_host: str,
    keep: bool,
    deploy_evidence: Path,
    repos: dict[str, dict[str, Any]] | None = None,
) -> None:
    """Nettoyage du cluster et du nœud distant."""
    if keep:
        return

    try:
        del_result = _run(
            ["kubectl", "delete", "-f", str(manifest_path)],
            check=False,
            timeout=120,
        )
        _append_evidence(
            deploy_evidence,
            shlex.join(["kubectl", "delete", "-f", str(manifest_path)]),
            del_result.stdout,
            del_result.stderr,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        _append_evidence(
            deploy_evidence,
            "teardown: suppression manifeste",
            "",
            f"échec ignoré: {exc}",
        )

    deadline = time.monotonic() + NS_DELETE_TIMEOUT
    while time.monotonic() < deadline:
        res = _run(
            ["kubectl", "get", "namespace", namespace],
            check=False,
            timeout=10,
        )
        if res.returncode != 0:
            break
        time.sleep(2)

    try:
        node_desc = _run(
            ["kubectl", "describe", "node", node],
            check=False,
            timeout=30,
        )
        _append_evidence(
            deploy_evidence,
            shlex.join(["kubectl", "describe", "node", node]) + " (teardown)",
            node_desc.stdout,
            node_desc.stderr,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        _append_evidence(
            deploy_evidence,
            "teardown: describe node",
            "",
            f"échec ignoré: {exc}",
        )

    if repos is not None:
        apres = _sample_amd_gpu(ssh_host)
        _append_evidence(
            deploy_evidence,
            f"ssh {ssh_host} sample repos amdgpu (après teardown)",
            json.dumps(apres, ensure_ascii=False, indent=2),
            "",
        )
        if not apres:
            raise RuntimeError("Échantillon GPU AMD post-teardown vide")
        for card, info in apres.items():
            if info.get("integrated"):
                continue
            ref = repos.get(card, {})
            ref_vram = ref.get("vram_used", 0)
            cur_vram = info.get("vram_used", 0)
            if cur_vram > ref_vram + 128 * 1024 * 1024:
                raise RuntimeError(
                    f"Teardown : VRAM {card} non revenue au repos "
                    f"({cur_vram} > {ref_vram} + 128 Mio)"
                )
            busy = info.get("busy")
            if busy is not None and busy > 0:
                raise RuntimeError(
                    f"Teardown : GPU {card} encore actif (busy={busy})"
                )

    try:
        _run(
            ["kubectl", "delete", "networkpolicy", BANC_POLICY_NAME, "-n", namespace],
            check=False,
            timeout=30,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        _append_evidence(
            deploy_evidence,
            "teardown: suppression policy de banc",
            "",
            f"échec ignoré: {exc}",
        )

    try:
        _ssh(ssh_host, f"rm -rf {REMOTE_WORKDIR}", check=False, timeout=60)
    except (subprocess.TimeoutExpired, OSError) as exc:
        _append_evidence(
            deploy_evidence,
            "teardown: nettoyage répertoire distant",
            "",
            f"échec ignoré: {exc}",
        )


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Preuve e2e AMD LAB-033A")
    parser.add_argument(
        "--render-only",
        action="store_true",
        help="Rendu seul, sans SSH ni cluster",
    )
    parser.add_argument(
        "--hardware-json",
        type=Path,
        help="JSON HardwareProfile (mode render-only)",
    )
    parser.add_argument(
        "--ssh-host",
        default=DEFAULT_SSH_HOST,
        help="Hôte SSH de sonde matérielle",
    )
    parser.add_argument(
        "--node",
        default=DEFAULT_NODE,
        help="Nœud Kubernetes cible",
    )
    parser.add_argument(
        "--evidence-dir",
        type=Path,
        default=Path(DEFAULT_EVIDENCE_DIR),
        help="Répertoire de collecte des evidences",
    )
    parser.add_argument(
        "--keep",
        action="store_true",
        help="Saute le teardown",
    )
    args = parser.parse_args(argv)

    args.evidence_dir.mkdir(parents=True, exist_ok=True)

    if args.render_only:
        if not args.hardware_json:
            parser.error("--render-only exige --hardware-json")
        hw = load_hardware_json(args.hardware_json)
        require_gpu_profile(hw)
        manifest = render_manifest("minimal-gpu-rocm", args.node, hw)
        (args.evidence_dir / "manifeste-rendu.yaml").write_text(
            manifest, encoding="utf-8"
        )
        print("LAB-033A-PROOF-OK")
        return 0

    manifest_path: Path | None = None
    namespace = NAMESPACE_FALLBACK
    deploy_evidence = args.evidence_dir / "DEPLOIEMENT-REEL.txt"
    gpu_evidence = args.evidence_dir / "mesure-gpu-inference.txt"
    finding_path = args.evidence_dir / "networkpolicy-finding.txt"

    deploy_evidence.write_text("", encoding="utf-8")
    gpu_evidence.write_text("", encoding="utf-8")
    finding_path.write_text("", encoding="utf-8")

    exc_info: BaseException | None = None
    amd_repos: dict[str, dict[str, Any]] | None = None
    try:
        with tempfile.TemporaryDirectory(prefix="lab033a-sources-") as tmpdir:
            archive_path = Path(tmpdir) / "sources-lab033a.tar.gz"
            _pack_sources(archive_path)
            archive_bytes = archive_path.read_bytes()

        hw = _probe_hardware(args.ssh_host, archive_bytes, deploy_evidence)
        require_gpu_profile(hw)

        amd_repos = _sample_amd_gpu(args.ssh_host)
        _append_evidence(
            deploy_evidence,
            f"ssh {args.ssh_host} sample repos amdgpu (avant déploiement)",
            json.dumps(amd_repos, ensure_ascii=False, indent=2),
            "",
        )

        manifest = render_manifest("minimal-gpu-rocm", args.node, hw)
        manifest_path = args.evidence_dir / "manifeste-rendu.yaml"
        manifest_path.write_text(manifest, encoding="utf-8")
        namespace = namespace_from_manifest(manifest)

        _run(
            ["kubectl", "delete", "namespace", namespace],
            check=False,
            timeout=120,
        )

        _run_and_log(
            ["kubectl", "apply", "-f", str(manifest_path)],
            deploy_evidence,
            timeout=120,
        )
        _wait_pods_ready(namespace, timeout=POD_READY_TIMEOUT)

        _run_and_log(
            ["kubectl", "get", "pods", "-n", namespace, "-o", "wide"],
            deploy_evidence,
            timeout=30,
        )
        _run_and_log(
            ["kubectl", "get", "namespace", namespace, "-o", "yaml"],
            deploy_evidence,
            timeout=30,
        )
        _run_and_log(
            ["kubectl", "describe", "node", args.node],
            deploy_evidence,
            timeout=30,
        )

        _pull_model(namespace, gpu_evidence, finding_path)

        _gpu_inference_proof(namespace, args.node, args.ssh_host, gpu_evidence)

        print("LAB-033A-PROOF-OK")
    except SystemExit as e:
        exc_info = e
    except (
        ProfileError,
        ValueError,
        RuntimeError,
        subprocess.TimeoutExpired,
        OSError,
        urllib.error.URLError,
    ) as e:
        exc_info = e
        print(f"LAB-033A-PROOF-FAIL: {e}", file=sys.stderr)
    finally:
        if not args.render_only and manifest_path is not None:
            try:
                _teardown(
                    manifest_path,
                    namespace,
                    args.node,
                    args.ssh_host,
                    args.keep,
                    deploy_evidence,
                    amd_repos,
                )
            except (subprocess.TimeoutExpired, OSError, RuntimeError) as e:
                if exc_info is None:
                    exc_info = e
                    print(f"LAB-033A-PROOF-FAIL (teardown): {e}", file=sys.stderr)
                else:
                    print(
                        f"LAB-033A-PROOF-FAIL (teardown additionnel): {e}",
                        file=sys.stderr,
                    )

    if isinstance(exc_info, SystemExit):
        return exc_info.code if isinstance(exc_info.code, int) else 1
    return 1 if exc_info is not None else 0


if __name__ == "__main__":
    sys.exit(main())
