"""Story P1-S10 — wizard mode --ci : enchaîne S01→S09 et scelle la preuve (codeur : fable).

Chaîne : détection → profil → catalogue (hash) → assemblage → bootstrap →
rendu → déploiement → santé réelle → modèles → ingestion → question →
VÉRIFICATION DU FAIT → preuve au registre hash-chaîné. Arrêt à la première
erreur avec code de sortie non nul — jamais de faux succès.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from forgeai.bootstrap.secrets import bootstrap_secrets
from forgeai.catalogue.loader import load_catalogue, verify_catalogue
from forgeai.core import registre
from forgeai.core.models import RenderTarget
from forgeai.core.runner import SubprocessRunner
from forgeai.deploy.compose import DeployError, compose_down, compose_up, wait_healthy
from forgeai.hardware.detect import HardwareDetector
from forgeai.planner.assemble import assemble_plan
from forgeai.planner.profile import ProfileError, derive_profile
from forgeai.rag.client import RagClient
from forgeai.renderers.compose import render_compose
from forgeai.renderers.k3s import render_k3s

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_CATALOGUE = REPO_ROOT / "catalogue" / "catalogue.json"
DEFAULT_OVERLAY = REPO_ROOT / "catalogue" / "deploy-minimal.json"
DEFAULT_REGISTRE = REPO_ROOT / "Registres" / "mission.jsonl"


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

    _step("S06 rendu + déploiement Docker Compose")
    compose_file = workdir / "docker-compose.yaml"
    compose_file.write_text(render_compose(plan), encoding="utf-8")
    (workdir / "k3s.yaml").write_text(render_k3s(plan), encoding="utf-8")
    compose_up(compose_file)
    try:
        health = wait_healthy(plan, timeout_s=args.health_timeout)
        print(f"  santé: {health}")

        _step("S08 modèles + ingestion du document de preuve")
        rag = RagClient(
            ollama_url=f"http://127.0.0.1:{ports['ollama']}",
            qdrant_url=f"http://127.0.0.1:{ports['vector-store']}",
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
            compose_down(compose_file, volumes=args.teardown_volumes)

    _step("S10 preuve au registre hash-chaîné")
    entry = registre.append(Path(args.registre), "preuve_e2e", "wizard-ci", {
        "plan_id": plan.plan_id, "profile": profile, "services": ports,
        "model": plan.model, "chunks": chunks, "question": args.question,
        "fait_attendu": args.expected_fact, "reponse": answer,
        "duree_s": round(time.monotonic() - started, 1),
    })
    print(f"CI_WITNESS={entry['hash']}")
    print("RAG_OK=true")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="forgeai")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_hw = sub.add_parser("hardware", help="détection hardware (S01)")
    p_hw.set_defaults(func=lambda a: print(
        HardwareDetector(SubprocessRunner()).full_report().to_json()) or 0)

    p_wiz = sub.add_parser("wizard", help="wizard bout-en-bout")
    p_wiz.add_argument("--ci", action="store_true", required=True)
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
    p_wiz.set_defaults(func=wizard_ci)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except DeployError as exc:
        print(f"ECHEC DEPLOIEMENT: {exc}", file=sys.stderr)
        return 8


if __name__ == "__main__":
    sys.exit(main())
