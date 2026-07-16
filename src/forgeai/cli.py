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
from forgeai.models.routes import RouteError, RouteStore
from forgeai.models.probe import probe_route
from forgeai.models.gateway import GatewayConfig, GatewayError, GatewayStore
from forgeai.models.strategy import StrategyError, StrategyStore, resolve_spec
from forgeai.planner.assemble import assemble_plan
from forgeai.planner.profile import ProfileError, derive_profile
from forgeai.rag.client import RagClient
from forgeai.renderers.compose import render_compose
from forgeai.renderers.k3s import NAMESPACE, node_port_for, render_k3s
from forgeai.resources import catalogue_path, deploy_overlay_path
from forgeai.i18n import t, set_locale, get_translator

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

    _step(t("wizard.s01"))
    hw = HardwareDetector(SubprocessRunner()).full_report()
    (workdir / "hardware.json").write_text(hw.to_json(), encoding="utf-8")

    _step(t("wizard.s02"))
    try:
        profile = derive_profile(hw)
    except ProfileError as exc:
        print(f"ABORT [{exc.code}] {exc}", file=sys.stderr)
        return 7
    print(f"  profil: {profile}")

    _step(t("wizard.s03"))
    digest = verify_catalogue(Path(args.catalogue))
    bricks = load_catalogue(Path(args.catalogue))
    print(f"  {len(bricks)} briques, sha256 {digest[:16]}…")

    _step(t("wizard.s04"))
    plan = assemble_plan(profile, Path(args.overlay))
    (workdir / "plan.json").write_text(plan.to_json(), encoding="utf-8")
    ports = {s.name: s.host_port for s in plan.services}
    print(f"  services: {ports} | modèle: {plan.model}")

    _step(t("wizard.s05"))
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
        _step(t("wizard.s06"))
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

        _step(t("wizard.s08"))
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

        _step(t("wizard.s09"))
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
            _step(t("wizard.teardown"))
            if backend == "compose":
                compose_down(compose_file, volumes=args.teardown_volumes)
            else:
                k3s_delete_namespace(NAMESPACE)

    _step(t("wizard.s10"))
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


def default_models_home() -> Path:
    home = os.environ.get("FORGEAI_HOME")
    base = Path(home) if home else Path.home() / ".forgeai"
    return base / "models"


def _read_secret(env_var: str | None, prompt: str) -> str:
    """Lit un secret depuis une variable d'environnement (CI) ou une invite sans écho.
    JAMAIS depuis argv (fuite dans la liste des processus / l'historique shell)."""
    if env_var:
        value = os.environ.get(env_var, "")
        if not value:
            raise RouteError(f"variable d'environnement '{env_var}' vide ou absente")
        return value
    import getpass
    return getpass.getpass(prompt)


def _model_add_cloud(args: argparse.Namespace) -> int:
    store = RouteStore(Path(args.home))
    try:
        api_key = _read_secret(args.api_key_env, f"Clé API pour {args.name} : ")
        passphrase = _read_secret(args.passphrase_env, "Passphrase du coffre : ")
        route, result = store.add_cloud(
            args.name, args.provenance, args.model_id, api_key, passphrase,
            base_url=args.base_url)
    except RouteError as exc:
        print(f"ECHEC ROUTE: {exc}", file=sys.stderr)  # message clair, aucune clé
        return 9
    registre.append(Path(args.registre), "route_cloud_ajoutee", "model-cloud", {
        "name": route.name, "provenance": route.provenance,
        "model_id": route.model_id, "base_url": route.base_url,
        "key_fingerprint": route.key_fingerprint,  # empreinte SEULE, jamais la clé
    })
    print(f"[forgeai] route '{route.name}' {result.light} — {route.provenance} "
          f"/ {route.model_id} (clé {route.key_fingerprint})")
    return 0


def _model_add_local(args: argparse.Namespace) -> int:
    from forgeai.core.runner import SubprocessRunner
    from forgeai.models.local import (LocalModel, LocalModelError, UrllibFetcher, add_local)
    from forgeai.models.probe import UrllibTransport
    model = LocalModel(name=args.name, engine=args.engine,
                       vram_required_mb=args.vram_required_mb, model_ref=args.model_ref,
                       download_url=args.url, sha256=args.sha256)
    reg = Path(args.registre)
    try:
        result = add_local(
            model, Path(args.dest), args.engine_url,
            vram_mb=args.vram_mb, engines={args.engine},
            fetcher=UrllibFetcher(), runner=SubprocessRunner(timeout_s=args.timeout),
            transport=UrllibTransport(),
            journal=lambda step, data: registre.append(reg, step, "model-local", data))
    except LocalModelError as exc:
        print(f"ECHEC MODELE LOCAL: {exc}", file=sys.stderr)
        return 9
    print(f"[forgeai] modèle local '{model.name}' {result.light} — {model.engine}/{model.model_ref}")
    return 0


def _model_list(args: argparse.Namespace) -> int:
    routes = RouteStore(Path(args.home)).list()
    if not routes:
        print("(aucune route cloud)")
        return 0
    for r in routes:  # jamais de clé, empreinte seulement
        print(f"{r.name:24} {r.provenance:12} {r.model_id:32} {r.key_fingerprint}")
    return 0


def _model_test(args: argparse.Namespace) -> int:
    store = RouteStore(Path(args.home))
    try:
        route = store.get(args.name)
        passphrase = _read_secret(args.passphrase_env, "Passphrase du coffre : ")
        api_key = store.vault.get(route.name, passphrase)
    except (RouteError, KeyError) as exc:
        print(f"ECHEC: {exc}", file=sys.stderr)
        return 9
    result = probe_route(route.base_url, route.model_id, api_key)
    print(f"[forgeai] route '{route.name}' : {result.light} — {result.detail}")
    return 0 if result.ok else 9


def _gateway_set_url(args: argparse.Namespace) -> int:
    try:
        cfg = GatewayConfig(args.url, key_env=args.key_env)
    except GatewayError as exc:
        print(f"ECHEC GATEWAY: {exc}", file=sys.stderr)
        return 10
    GatewayStore(Path(args.home)).set_gateway(cfg)
    registre.append(Path(args.registre), "gateway_configure", "gateway",
                    {"base_url": cfg.base_url, "key_env": cfg.key_env})
    print(f"[forgeai] gateway unique = {cfg.base_url} (clé via ${{{cfg.key_env}}})")
    return 0


def _gateway_wire(args: argparse.Namespace) -> int:
    store = GatewayStore(Path(args.home))
    try:
        wiring = store.wire(args.brick, args.role, args.route)
    except GatewayError as exc:
        print(f"ECHEC CABLAGE: {exc}", file=sys.stderr)
        return 10
    registre.append(Path(args.registre), "brique_cablee_gateway", "gateway",
                    {"brick": wiring.brick_id, "role": wiring.role,
                     "base_url": wiring.env["OPENAI_API_BASE"],
                     "model": wiring.env["OPENAI_MODEL"]})  # jamais de clé
    print(f"[forgeai] brique '{wiring.brick_id}' ({wiring.role}) → gateway "
          f"{wiring.env['OPENAI_API_BASE']} modèle {wiring.env['OPENAI_MODEL']}")
    return 0


def _gateway_verify(args: argparse.Namespace) -> int:
    try:
        violations = GatewayStore(Path(args.home)).verify()
    except GatewayError as exc:
        print(f"ECHEC GATEWAY: {exc}", file=sys.stderr)
        return 10
    if violations:
        print("VIOLATION INVARIANT DM-6 (brique ne passant pas par le gateway unique) :",
              file=sys.stderr)
        for v in violations:
            print(f"  - {v}", file=sys.stderr)
        return 10
    print("[forgeai] invariant gateway OK — toutes les briques câblées passent par le gateway unique")
    return 0


def _strategy_set(args: argparse.Namespace) -> int:
    store = StrategyStore(Path(args.home))
    try:
        roles = [r for r in (args.roles.split(",") if args.roles else []) if r]
        spec = resolve_spec(args.strategy, roles or None)
    except StrategyError as exc:
        print(f"ECHEC STRATEGIE: {exc}", file=sys.stderr)
        return 10
    diff = store.plan_change(spec)
    already = store.get() is not None
    if already and diff.is_change and not args.confirm:
        print("Reconfiguration de la stratégie modèle — changement de slots :", file=sys.stderr)
        print(diff.render(), file=sys.stderr)
        print("Rien n'a été modifié. Relancez avec --confirm pour appliquer explicitement.",
              file=sys.stderr)
        return 10
    store.save(spec)
    registre.append(Path(args.registre), "strategie_modele", "strategy",
                    {"strategy": spec.strategy, "slots": list(spec.slots),
                     "slot_count": spec.slot_count})
    print(f"[forgeai] stratégie '{spec.strategy}' — {spec.slot_count} slot(s) : "
          f"{', '.join(spec.slots)}")
    return 0


def _strategy_show(args: argparse.Namespace) -> int:
    spec = StrategyStore(Path(args.home)).get()
    if spec is None:
        print("(aucune stratégie configurée)")
        return 0
    print(f"stratégie : {spec.strategy} | {spec.slot_count} slot(s) : {', '.join(spec.slots)}")
    return 0


def _route_configure(args: argparse.Namespace) -> int:
    store = RouteStore(Path(args.home))
    enabled = args.cache
    ttl_s = args.ttl
    prefix = args.prefix
    try:
        store.configure_cache(args.name, enabled, ttl_s, prefix)
    except RouteError as exc:
        print(f"ECHEC ROUTE: {exc}", file=sys.stderr)
        return 9
    registre.append(Path(args.registre), "route_cache_configuree", "route",
                    {"name": args.name, "cache": enabled,
                     "cache_ttl_s": ttl_s, "cache_prefix": prefix})
    print(f"[forgeai] route '{args.name}' configurée — "
          f"cache={'activé' if enabled else 'désactivé'}, ttl={ttl_s}s, prefix={prefix}")
    return 0


def _budget_set(args: argparse.Namespace) -> int:
    from forgeai.models.budget import BudgetTracker, BudgetError
    home = Path(args.home)
    try:
        BudgetTracker(home).set_budget(args.agent, args.quota, args.alert)
    except BudgetError as exc:
        print(f"ECHEC BUDGET: {exc}", file=sys.stderr)
        return 10
    registre.append(Path(args.registre), "budget_defini", "budget",
                    {"agent": args.agent, "quota_tokens": args.quota,
                     "alert_ratio": args.alert})
    print(f"[forgeai] budget '{args.agent}' défini — "
          f"quota={args.quota} tokens, alerte à {args.alert:.0%}")
    return 0


def _budget_status(args: argparse.Namespace) -> int:
    from forgeai.models.budget import BudgetTracker, BudgetError
    home = Path(args.home)
    try:
        if args.agent:
            states = [BudgetTracker(home).status(args.agent)]
        else:
            states = BudgetTracker(home).report()
    except BudgetError as exc:
        print(f"ECHEC BUDGET: {exc}", file=sys.stderr)
        return 10
    for s in states:
        print(f"{s.agent}: {s.used_tokens}/{s.quota_tokens} tokens "
              f"({s.ratio:.1%}) — {s.etat}")
    return 0


def _catalogue(args: argparse.Namespace) -> int:
    import json
    catalogue_path = Path(args.catalogue)
    raw = json.loads(catalogue_path.read_text(encoding="utf-8"))
    entries = raw if isinstance(raw, list) else raw.get("entries", [])

    if args.defaults:
        defaults = [e for e in entries if e.get("default") is True]
        defaults.sort(key=lambda e: (e.get("category", ""), e.get("name", "")))
        for e in defaults:
            pop = e.get("popularity")
            pop = "" if pop is None else pop   # n'affiche pas "None"; ne masque pas une valeur 0
            print(t("catalogue.default_line", name=e.get("name"),
                    category=e.get("category"), popularity=pop))
        return 0

    categories = sorted({e.get("category", "") for e in entries})
    print(t("catalogue.summary", n=len(entries), k=len(categories)))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="forgeai")
    parser.add_argument("--lang", choices=get_translator().available() or ["fr", "en"],
                        default=os.environ.get("FORGEAI_LANG", "fr"),
                        help="langue de l'interface (défaut: fr ; ou $FORGEAI_LANG)")
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

    p_model = sub.add_parser("model", help="routes modèle cloud/local (DM-5)")
    model_sub = p_model.add_subparsers(dest="model_cmd", required=True)
    p_add = model_sub.add_parser("add-cloud", help="ajoute une route cloud (test réel requis)")
    p_add.add_argument("--name", required=True)
    p_add.add_argument("--provenance", required=True,
                       choices=["openrouter", "deepinfra", "nim", "direct", "autre"])
    p_add.add_argument("--model-id", required=True)
    p_add.add_argument("--base-url", default=None,
                       help="requis pour provenance direct/autre (endpoint compatible OpenAI)")
    p_add.add_argument("--api-key-env", default=None,
                       help="variable d'env portant la clé (sinon invite sans écho) — jamais en argv")
    p_add.add_argument("--passphrase-env", default=None)
    p_add.add_argument("--home", default=str(default_models_home()))
    p_add.add_argument("--registre", default=str(DEFAULT_REGISTRE))
    p_add.set_defaults(func=_model_add_cloud)
    p_local = model_sub.add_parser("add-local", help="télécharge (hash-vérifié)+déploie+teste un modèle local")
    p_local.add_argument("--name", required=True)
    p_local.add_argument("--engine", required=True, choices=["ollama", "llamacpp", "vllm"])
    p_local.add_argument("--model-ref", required=True)
    p_local.add_argument("--url", required=True)
    p_local.add_argument("--sha256", required=True)
    p_local.add_argument("--vram-required-mb", type=int, required=True)
    p_local.add_argument("--vram-mb", type=int, required=True, help="VRAM du nœud cible")
    p_local.add_argument("--engine-url", required=True, help="endpoint compatible OpenAI du moteur")
    p_local.add_argument("--dest", default=str(default_models_home() / "local"))
    p_local.add_argument("--timeout", type=float, default=600.0)
    p_local.add_argument("--registre", default=str(DEFAULT_REGISTRE))
    p_local.set_defaults(func=_model_add_local)
    p_list = model_sub.add_parser("list", help="liste les routes (jamais les clés)")
    p_list.add_argument("--home", default=str(default_models_home()))
    p_list.set_defaults(func=_model_list)
    p_test = model_sub.add_parser("test", help="re-teste une route existante")
    p_test.add_argument("--name", required=True)
    p_test.add_argument("--passphrase-env", default=None)
    p_test.add_argument("--home", default=str(default_models_home()))
    p_test.set_defaults(func=_model_test)

    p_gw = sub.add_parser("gateway", help="branchement brique→gateway unique (DM-6)")
    gw_sub = p_gw.add_subparsers(dest="gw_cmd", required=True)
    p_gw_url = gw_sub.add_parser("set-url", help="définit le gateway unique")
    p_gw_url.add_argument("--url", required=True)
    p_gw_url.add_argument("--key-env", default="FORGEAI_GATEWAY_KEY")
    p_gw_url.add_argument("--home", default=str(default_models_home()))
    p_gw_url.add_argument("--registre", default=str(DEFAULT_REGISTRE))
    p_gw_url.set_defaults(func=_gateway_set_url)
    p_gw_wire = gw_sub.add_parser("wire", help="câble une brique (par rôle→route) vers le gateway")
    p_gw_wire.add_argument("--brick", required=True)
    p_gw_wire.add_argument("--role", required=True)
    p_gw_wire.add_argument("--route", required=True)
    p_gw_wire.add_argument("--home", default=str(default_models_home()))
    p_gw_wire.add_argument("--registre", default=str(DEFAULT_REGISTRE))
    p_gw_wire.set_defaults(func=_gateway_wire)
    p_gw_ver = gw_sub.add_parser("verify", help="vérifie l'invariant (aucune brique hors gateway)")
    p_gw_ver.add_argument("--home", default=str(default_models_home()))
    p_gw_ver.set_defaults(func=_gateway_verify)

    p_strat = sub.add_parser("strategy", help="stratégie modèle Cerveau/Équipe/Hybride (DM-5b)")
    strat_sub = p_strat.add_subparsers(dest="strat_cmd", required=True)
    p_s_set = strat_sub.add_parser("set", help="choisit la stratégie (détermine le nb de slots)")
    p_s_set.add_argument("--strategy", required=True,
                         choices=["cerveau-unique", "equipe", "hybride"])
    p_s_set.add_argument("--roles", default=None, help="rôles personnalisés séparés par des virgules")
    p_s_set.add_argument("--confirm", action="store_true",
                         help="applique une reconfiguration (changement de slots) explicitement")
    p_s_set.add_argument("--home", default=str(default_models_home()))
    p_s_set.add_argument("--registre", default=str(DEFAULT_REGISTRE))
    p_s_set.set_defaults(func=_strategy_set)
    p_s_show = strat_sub.add_parser("show", help="affiche la stratégie courante")
    p_s_show.add_argument("--home", default=str(default_models_home()))
    p_s_show.set_defaults(func=_strategy_show)

    p_route = sub.add_parser("route", help="configure les routes (B-12)")
    route_sub = p_route.add_subparsers(dest="route_cmd", required=True)
    p_rcfg = route_sub.add_parser("configure", help="configure le cache d'une route")
    p_rcfg.add_argument("name", help="nom de la route")
    cache_group = p_rcfg.add_mutually_exclusive_group()
    cache_group.add_argument("--cache", dest="cache", action="store_true", default=True,
                             help="activer le cache (défaut)")
    cache_group.add_argument("--no-cache", dest="cache", action="store_false",
                             help="désactiver le cache")
    p_rcfg.add_argument("--ttl", type=int, default=None, help="durée de vie du cache en secondes")
    p_rcfg.add_argument("--prefix", default=None, help="préfixe de cache")
    p_rcfg.add_argument("--home", default=str(default_models_home()))
    p_rcfg.add_argument("--registre", default=str(DEFAULT_REGISTRE))
    p_rcfg.set_defaults(func=_route_configure)

    p_budget = sub.add_parser("budget", help="gestion des budgets agents (B-20)")
    budget_sub = p_budget.add_subparsers(dest="budget_cmd", required=True)
    p_budget_set = budget_sub.add_parser("set", help="définit le quota d'un agent")
    p_budget_set.add_argument("--agent", required=True)
    p_budget_set.add_argument("--quota", type=int, required=True)
    p_budget_set.add_argument("--alert", type=float, default=0.8)
    p_budget_set.add_argument("--home", default=str(default_models_home()))
    p_budget_set.add_argument("--registre", default=str(DEFAULT_REGISTRE))
    p_budget_set.set_defaults(func=_budget_set)
    p_budget_status = budget_sub.add_parser("status", help="état des budgets agents")
    p_budget_status.add_argument("--agent", default=None)
    p_budget_status.add_argument("--home", default=str(default_models_home()))
    p_budget_status.set_defaults(func=_budget_status)

    p_cat = sub.add_parser("catalogue", help="explore le catalogue de briques")
    p_cat.add_argument("--defaults", action="store_true",
                       help="liste la brique par défaut de chaque catégorie")
    p_cat.add_argument("--catalogue", default=str(DEFAULT_CATALOGUE),
                       help="chemin vers le catalogue JSON")
    p_cat.set_defaults(func=_catalogue)

    args = parser.parse_args(argv)
    set_locale(args.lang)   # bascule la langue de l'interface avant dispatch
    try:
        return args.func(args)
    except DeployError as exc:
        print(f"ECHEC DEPLOIEMENT: {exc}", file=sys.stderr)
        return 8


if __name__ == "__main__":
    sys.exit(main())
