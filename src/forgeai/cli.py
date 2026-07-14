"""Story P1-S10 — wizard mode --ci : enchaîne S01→S09 et scelle la preuve (codeur : fable).

Chaîne : détection → profil → catalogue (hash) → assemblage → bootstrap →
rendu → déploiement → santé réelle → modèles → ingestion → question →
VÉRIFICATION DU FAIT → preuve au registre hash-chaîné. Arrêt à la première
erreur avec code de sortie non nul — jamais de faux succès.
"""
from __future__ import annotations

import argparse
import os
import socket
import sys
import time
from pathlib import Path

from forgeai.bootstrap.secrets import bootstrap_secrets
from forgeai.catalogue.loader import load_catalogue, verify_catalogue
from forgeai.core import registre
from forgeai.core.models import RenderTarget
from forgeai.core.runner import SubprocessRunner
from forgeai.deploy.compose import (
    DeployError,
    compose_down,
    compose_up,
    http_ok,
    wait_healthy,
)
from forgeai.deploy.k3s import k3s_apply, k3s_delete_namespace, k3s_wait_deployments
from forgeai.hardware.detect import HardwareDetector
from forgeai.planner.assemble import assemble_plan
from forgeai.planner.profile import ProfileError, derive_profile
from forgeai.rag.client import RagClient
from forgeai.renderers.compose import render_compose
from forgeai.renderers.k3s import NAMESPACE, node_port_for, render_k3s
from forgeai.resources import catalogue_path, deploy_overlay_path

# Données embarquées dans le paquet → portables après pip install (P3).
DEFAULT_CATALOGUE = catalogue_path()
DEFAULT_OVERLAY = deploy_overlay_path()


def default_registre() -> Path:
    """Emplacement portable et persistant du registre (revue P3, convergence
    Gemini+Qwen) : $FORGEAI_HOME si défini, sinon ~/.forgeai/ — jamais lié au
    répertoire courant (fragile, éphémère depuis /tmp). `--registre` reste
    disponible pour un registre projet-local."""
    home = os.environ.get("FORGEAI_HOME")
    base = Path(home) if home else Path.home() / ".forgeai"
    return base / "Registres" / "mission.jsonl"


DEFAULT_REGISTRE = default_registre()


def _step(label: str) -> None:
    print(f"[forgeai] {label}", flush=True)


def wizard_ci(args: argparse.Namespace) -> int:
    workdir = Path(args.workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()

    _step("S01 détection hardware")
    hw = HardwareDetector(SubprocessRunner()).full_report()
    (workdir / "hardware.json").write_text(hw.to_json(), encoding="utf-8")

    _step("S02 dérivation du profil")
    try:
        profile = derive_profile(hw)
    except ProfileError as exc:
        print(f"ABORT [{exc.code}] {exc}", file=sys.stderr)
        return 7
    print(f"  profil: {profile}")

    _step("S03 vérification du catalogue (hash)")
    digest = verify_catalogue(Path(args.catalogue))
    bricks = load_catalogue(Path(args.catalogue))
    print(f"  {len(bricks)} briques, sha256 {digest[:16]}…")

    _step("S04 assemblage du plan Minimal")
    plan = assemble_plan(profile, Path(args.overlay))
    (workdir / "plan.json").write_text(plan.to_json(), encoding="utf-8")
    ports = {s.name: s.host_port for s in plan.services}
    print(f"  services: {ports} | modèle: {plan.model}")

    _step("S05 bootstrap sécurisé")
    bootstrap_secrets(workdir)

    backend = args.backend
    if not args.skip_preflight:
        from forgeai.deploy.compose import http_ok
        from forgeai.preflight import available_backends, run_checks
        backends = available_backends(
            run_checks(SubprocessRunner(), HardwareDetector(SubprocessRunner()), http_ok))
        if backend not in backends:
            print(f"ABORT: backend '{backend}' indisponible sur cette machine. "
                  f"Backends prêts : {backends or 'aucun'}. "
                  f"Lancez `forgeai doctor` pour le détail, ou --skip-preflight pour forcer.",
                  file=sys.stderr)
            return 6

    compose_file = workdir / "docker-compose.yaml"
    compose_file.write_text(render_compose(plan), encoding="utf-8")
    local_node = socket.gethostname().lower()
    (workdir / "k3s.yaml").write_text(render_k3s(plan, node=local_node), encoding="utf-8")

    if backend == "compose":
        _step("S06 rendu + déploiement Docker Compose")
        compose_up(compose_file)
        rag_ports = ports
    else:
        _step(f"S07 rendu + déploiement K3s (nodeSelector: {local_node} — Minimal single-node)")
        k3s_apply(workdir / "k3s.yaml")
        k3s_wait_deployments(NAMESPACE, timeout_s=args.health_timeout)
        used_node_ports: set[int] = set()
        rag_ports = {s.name: node_port_for(s, used_node_ports) for s in plan.services}
        print(f"  NodePorts: {rag_ports}")
    try:
        if backend == "compose":
            health = wait_healthy(plan, timeout_s=args.health_timeout)
        else:
            deadline = time.monotonic() + args.health_timeout
            health = {name: "waiting" for name in rag_ports}
            probes = {"ollama": "/api/tags", "vector-store": "/readyz"}
            while time.monotonic() < deadline and set(health.values()) != {"healthy"}:
                for name, port in rag_ports.items():
                    if http_ok(f"http://127.0.0.1:{port}{probes[name]}"):
                        health[name] = "healthy"
                time.sleep(2.0)
            if set(health.values()) != {"healthy"}:
                raise DeployError(f"Healthchecks K3s incomplets : {health}")
        print(f"  santé: {health}")

        _step("S08 modèles + ingestion du document de preuve")
        rag = RagClient(
            ollama_url=f"http://127.0.0.1:{rag_ports['ollama']}",
            qdrant_url=f"http://127.0.0.1:{rag_ports['vector-store']}",
            llm_model=plan.model,
            embed_model=plan.embed_model,
        )
        rag.pull_models()
        doc = Path(args.document).read_text(encoding="utf-8")
        chunks = rag.ingest(doc, source=Path(args.document).name)
        print(f"  {chunks} chunks ingérés")

        _step("S09 question → réponse → vérification du fait")
        result = rag.ask(args.question)
        answer = result["answer"]
        print(f"  Q: {args.question}")
        print(f"  R: {answer}")
        fact_ok = args.expected_fact.lower() in answer.lower()
        if not fact_ok:
            print(f"ECHEC: le fait attendu « {args.expected_fact} » est absent de la réponse",
                  file=sys.stderr)
            return 9
    finally:
        if args.teardown:
            _step("teardown (backends séquentiels — règle round 1)")
            if backend == "compose":
                compose_down(compose_file, volumes=args.teardown_volumes)
            else:
                k3s_delete_namespace(NAMESPACE)

    _step("S10 preuve au registre hash-chaîné")
    entry = registre.append(Path(args.registre), "preuve_e2e", "wizard-ci", {
        "backend": backend,
        "plan_id": plan.plan_id, "profile": profile, "services": rag_ports,
        "model": plan.model, "chunks": chunks, "question": args.question,
        "fait_attendu": args.expected_fact, "reponse": answer,
        "duree_s": round(time.monotonic() - started, 1),
    })
    print(f"CI_WITNESS={entry['hash']}")
    print("RAG_OK=true")
    return 0


_STATUS_MARK = {"ok": "OK ", "degraded": "!! ", "missing": "-- "}


def _doctor(args: argparse.Namespace) -> int:
    from forgeai.deploy.compose import http_ok
    from forgeai.preflight import available_backends, run_checks
    checks = run_checks(SubprocessRunner(), HardwareDetector(SubprocessRunner()), http_ok)
    print("[forgeai doctor] état de votre environnement :")
    for c in checks:
        print(f"  [{_STATUS_MARK.get(c.status, '?  ')}] {c.name:9} — {c.detail}")
        print(f"              → {c.enables}")
    backends = available_backends(checks)
    if backends:
        print(f"\nBackends de déploiement disponibles : {', '.join(backends)}")
    else:
        print("\nAucun backend de déploiement prêt. Installez Docker (le plus simple) "
              "ou configurez un cluster K3s, puis relancez `forgeai doctor`.")
    return 0


def _node_status(args: argparse.Namespace) -> int:
    from forgeai.network.nodes import ClusterError, cluster_status
    try:
        nodes = cluster_status(SubprocessRunner())
    except ClusterError as exc:
        print(f"ECHEC: {exc}", file=sys.stderr)
        return 8
    ready = [n for n in nodes if n["ready"]]
    for n in nodes:
        print(f"  {n['name']}: ready={n['ready']} roles={n['roles']} gpu={n['gpu_allocatable']}")
    print(f"{len(ready)}/{len(nodes)} nœuds Ready")
    if args.witness:
        entry = registre.append(Path(args.registre), "jonction_prouvee", "node-status", {
            "total": len(nodes), "ready": len(ready),
            "nodes": [{"name": n["name"], "ready": n["ready"], "roles": n["roles"]}
                      for n in nodes],
        })
        print(f"NODE_WITNESS={entry['hash']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="forgeai")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_hw = sub.add_parser("hardware", help="détection hardware (S01)")
    p_hw.set_defaults(func=lambda a: print(
        HardwareDetector(SubprocessRunner()).full_report().to_json()) or 0)

    p_doctor = sub.add_parser("doctor", help="préflight : ce que votre machine peut faire")
    p_doctor.set_defaults(func=_doctor)

    p_node = sub.add_parser("node", help="multi-nœuds (P2)")
    node_sub = p_node.add_subparsers(dest="node_cmd", required=True)
    p_status = node_sub.add_parser("status", help="état du cluster + preuve (F22)")
    p_status.add_argument("--registre", default=str(DEFAULT_REGISTRE))
    p_status.add_argument("--witness", action="store_true",
                          help="scelle l'état au registre hash-chaîné")
    p_status.set_defaults(func=_node_status)

    p_wiz = sub.add_parser("wizard", help="wizard bout-en-bout")
    p_wiz.add_argument("--ci", action="store_true", required=True)
    p_wiz.add_argument("--backend", choices=["compose", "k3s"], default="compose")
    p_wiz.add_argument("--workdir", default="run")
    p_wiz.add_argument("--catalogue", default=str(DEFAULT_CATALOGUE))
    p_wiz.add_argument("--overlay", default=str(DEFAULT_OVERLAY))
    p_wiz.add_argument("--registre", default=str(DEFAULT_REGISTRE))
    p_wiz.add_argument("--document", required=True)
    p_wiz.add_argument("--question", required=True)
    p_wiz.add_argument("--expected-fact", required=True)
    p_wiz.add_argument("--health-timeout", type=float, default=180.0)
    p_wiz.add_argument("--teardown", action="store_true")
    p_wiz.add_argument("--teardown-volumes", action="store_true")
    p_wiz.add_argument("--skip-preflight", action="store_true",
                       help="ne pas vérifier la disponibilité du backend avant déploiement")
    p_wiz.set_defaults(func=wizard_ci)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except DeployError as exc:
        print(f"ECHEC DEPLOIEMENT: {exc}", file=sys.stderr)
        return 8


if __name__ == "__main__":
    sys.exit(main())
