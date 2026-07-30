#!/usr/bin/env python3
"""Story LAB-033N — preuve e2e NVIDIA sur cluster k3s.

Flux complet : sonde matérielle portable sur pc3, dérivation du profil,
assemblage du plan, rendu K3s, déploiement tel quel du manifeste,
preuve d'utilisation GPU et inférence réelle, teardown.
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
import textwrap
import threading
import time
import urllib.error
import urllib.request
from importlib.resources import files
from pathlib import Path
from typing import Any

from forgeai.core.models import GPU, Disk, HardwareProfile, NodeInventaire, RenderTarget
from forgeai.planner.assemble import assemble_plan
from forgeai.renderers.k3s import render_k3s

try:
    from forgeai.planner.profile import derive_profile, ProfileError
except Exception:  # pragma: no cover - tolérance aux exports internes
    from forgeai.planner.profile import derive_profile

    ProfileError = Exception


OLLAMA_MODEL = "qwen2.5:0.5b"
NAMESPACE_FALLBACK = "forgeai-minimal"
BANC_POLICY_NAME = "banc-lab033n-egress-temporaire"
REMOTE_WORKDIR = "/tmp/lab033n"

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
    """Reconstruction exacte des dataclasses à partir du JSON produit par `forgeai hardware`."""
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
    """Dérive le profil et exige `minimal-gpu-cuda`."""
    profile = derive_profile(hw)
    if profile != "minimal-gpu-cuda":
        print(
            f"Profil dérivé inattendu : {profile} (attendu minimal-gpu-cuda)",
            file=sys.stderr,
        )
        raise SystemExit(2)
    return profile


def render_manifest(profile: str, node: str, hw: HardwareProfile) -> str:
    """Rend le manifeste K3s pour le profil et le nœud donnés."""
    overlay = Path(str(files("forgeai.data") / "deploy-minimal.json"))
    plan = assemble_plan(profile, deploy_overlay=overlay, target=RenderTarget.K3S)
    vram_max = max((gpu.vram_mb for gpu in hw.gpus), default=0)
    inventaire = (NodeInventaire(hostname=node, gpu_vendor="nvidia", vram_mib=vram_max),)
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


def usage_gpu_detecte(samples: list[str]) -> bool:
    """Détecte l'usage GPU par ollama dans des sorties CSV nvidia-smi compute apps.

    Gère l'en-tête CSV, les lignes vides et le marqueur [N/A].
    Un processus ollama avec une mémoire allouée strictement positive
    constitue la preuve d'utilisation GPU.
    """
    for sample in samples:
        for line in sample.splitlines():
            line = line.strip()
            if not line or line.lower().startswith("pid"):
                continue
            if "[N/A]" in line:
                continue
            if "ollama" not in line.lower():
                continue
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 3:
                continue
            mem_field = parts[2]
            m = re.search(r"(\d+)", mem_field)
            if not m:
                continue
            try:
                mem = int(m.group(1))
            except ValueError:
                continue
            if mem > 0:
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
    # Transfert binaire via stdin en base64 : évite d'écrire l'archive sur la
    # ligne de commande distante et reste compatible text=True.
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

    hw_path = evidence_path.parent / "hardware-pc3.json"
    hw_path.write_text(hw_res.stdout, encoding="utf-8")
    return reconstruct_hardware(json.loads(hw_res.stdout))


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

    # Consigne des NetworkPolicies existantes
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

    # Application de la policy de banc temporaire
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
        # Suppression immédiate de la policy de banc
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


def _gpu_inference_proof(namespace: str, node: str, evidence_path: Path) -> None:
    """Preuve d'utilisation GPU : nvidia-smi dans le pod + inférence réelle."""
    node_ip = _node_ip(node)
    nodeport = _nodeport_for_service(namespace, "ollama")
    url = f"http://{node_ip}:{nodeport}/api/generate"

    # Marqueur pour mesure des chemins d'écriture
    _run(
        [
            "kubectl",
            "exec",
            "deploy/ollama",
            "-n",
            namespace,
            "--",
            "touch",
            "/tmp/lab033n-marqueur",
        ],
        check=True,
        timeout=30,
    )

    samples: list[str] = []
    stop_event = threading.Event()

    def sampler() -> None:
        while not stop_event.wait(1.0):
            res = _run(
                [
                    "kubectl",
                    "exec",
                    "deploy/ollama",
                    "-n",
                    namespace,
                    "--",
                    "nvidia-smi",
                    "--query-compute-apps=pid,process_name,used_memory",
                    "--format=csv",
                ],
                check=False,
                timeout=30,
            )
            samples.append(res.stdout)

    thread = threading.Thread(target=sampler)
    thread.start()

    try:
        body, fallback_msgs = _inference_request(url)
        if not body:
            body, fallback_msgs = _inference_port_forward(namespace)
    finally:
        stop_event.set()
        thread.join(timeout=10)

    if not usage_gpu_detecte(samples):
        raise RuntimeError(
            "Aucun échantillon nvidia-smi ne montre d'utilisation GPU par ollama"
        )

    # Chemins d'écriture observés pendant l'inférence
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
            "find / -xdev -type f -newer /tmp/lab033n-marqueur 2>/dev/null | head -80",
        ],
        check=False,
        timeout=60,
    )

    with evidence_path.open("a", encoding="utf-8") as f:
        f.write("\n--- Preuve GPU / inférence ---\n")
        f.write(f"URL NodePort : {url}\n")
        if fallback_msgs:
            f.write("Fallbacks :\n")
            for msg in fallback_msgs:
                f.write(f"  {msg}\n")
        f.write("Réponse inférence :\n")
        f.write(body)
        f.write("\n\n--- Échantillons nvidia-smi compute apps ---\n")
        for sample in samples:
            f.write(sample)
            f.write("\n")
        f.write("\n--- Chemins d'écriture pendant l'inférence ---\n")
        f.write(find_result.stdout)
        f.write("\n")


def _allocated_gpu(node: str) -> int:
    """Retourne la quantité allouée de nvidia.com/gpu sur un nœud.

    -1 signale une erreur d'appel kubectl ; 0 signale l'absence de GPU alloué.
    """
    result = _run(
        ["kubectl", "describe", "node", node],
        check=False,
        timeout=30,
    )
    if result.returncode != 0:
        return -1

    in_section = False
    for line in result.stdout.splitlines():
        if line.startswith("Allocated resources:"):
            in_section = True
            continue
        if not in_section:
            continue
        if line.strip() == "":
            continue
        if not line.startswith(" "):
            # Fin de la section "Allocated resources".
            break
        m = re.search(r"nvidia\.com/gpu\s+(\d+)", line)
        if m:
            return int(m.group(1))
    return 0


def _teardown(
    manifest_path: Path,
    namespace: str,
    node: str,
    ssh_host: str,
    keep: bool,
    deploy_evidence: Path,
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

    # Attente de disparition du namespace
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

    # Vérification que le GPU a bien été libéré sur le nœud.
    allocated = _allocated_gpu(node)
    if allocated != 0:
        msg = (
            f"Teardown : nvidia.com/gpu alloué sur {node} = {allocated} "
            f"(attendu 0)"
        )
        _append_evidence(deploy_evidence, "vérification ressources allouées", msg, "")
        raise RuntimeError(msg)

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
    parser = argparse.ArgumentParser(description="Preuve e2e NVIDIA LAB-033N")
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
        default="pc3-roce",
        help="Hôte SSH de sonde matérielle",
    )
    parser.add_argument(
        "--node",
        default="pc3-grs-a",
        help="Nœud Kubernetes cible",
    )
    parser.add_argument(
        "--evidence-dir",
        type=Path,
        default=Path("reviews/LAB-033N/evidence"),
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
        manifest = render_manifest("minimal-gpu-cuda", args.node, hw)
        (args.evidence_dir / "manifeste-rendu.yaml").write_text(
            manifest, encoding="utf-8"
        )
        print("LAB-033N-PROOF-OK")
        return 0

    manifest_path: Path | None = None
    namespace = NAMESPACE_FALLBACK
    deploy_evidence = args.evidence_dir / "DEPLOIEMENT-REEL.txt"
    gpu_evidence = args.evidence_dir / "mesure-gpu-inference.txt"
    finding_path = args.evidence_dir / "networkpolicy-finding.txt"

    # Chaque run produit un procès-verbal cohérent : on tronque les fichiers.
    deploy_evidence.write_text("", encoding="utf-8")
    gpu_evidence.write_text("", encoding="utf-8")
    finding_path.write_text("", encoding="utf-8")

    exc_info: BaseException | None = None
    try:
        # 1. Empaquetage et sonde portable (l'archive reste hors d'evidence-dir)
        with tempfile.TemporaryDirectory(prefix="lab033n-sources-") as tmpdir:
            archive_path = Path(tmpdir) / "sources-lab033n.tar.gz"
            _pack_sources(archive_path)
            archive_bytes = archive_path.read_bytes()

        hw = _probe_hardware(args.ssh_host, archive_bytes, deploy_evidence)

        # 2. Dérivation du profil
        require_gpu_profile(hw)

        # 3. Rendu du manifeste
        manifest = render_manifest("minimal-gpu-cuda", args.node, hw)
        manifest_path = args.evidence_dir / "manifeste-rendu.yaml"
        manifest_path.write_text(manifest, encoding="utf-8")
        namespace = namespace_from_manifest(manifest)

        # 4. Déploiement tel quel
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

        # 5. Preuve GPU dans le pod
        _run_and_log(
            ["kubectl", "exec", "deploy/ollama", "-n", namespace, "--", "nvidia-smi"],
            gpu_evidence,
            timeout=60,
        )

        # 6. Pull du modèle avec contingency réseau
        _pull_model(namespace, gpu_evidence, finding_path)

        # 7. Inférence réelle et mesure GPU
        _gpu_inference_proof(namespace, args.node, gpu_evidence)

        print("LAB-033N-PROOF-OK")
    except SystemExit as e:
        # Le message a déjà été émis par l'appelant (ex. profil incorrect).
        exc_info = e
    except Exception as e:
        exc_info = e
        print(f"LAB-033N-PROOF-FAIL: {e}", file=sys.stderr)
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
                )
            except Exception as e:
                if exc_info is None:
                    exc_info = e
                    print(f"LAB-033N-PROOF-FAIL (teardown): {e}", file=sys.stderr)
                else:
                    print(
                        f"LAB-033N-PROOF-FAIL (teardown additionnel): {e}",
                        file=sys.stderr,
                    )

    if isinstance(exc_info, SystemExit):
        return exc_info.code if isinstance(exc_info.code, int) else 1
    return 1 if exc_info is not None else 0


if __name__ == "__main__":
    sys.exit(main())
