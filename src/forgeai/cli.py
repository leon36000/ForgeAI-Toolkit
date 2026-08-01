"""Story P1-S10 — wizard mode --ci : enchaîne S01→S09 et scelle la preuve (codeur : fable).

Chaîne : détection → profil → catalogue (hash) → assemblage → bootstrap →
rendu → déploiement → santé réelle → modèles → ingestion → question →
VÉRIFICATION DU FAIT → preuve au registre hash-chaîné. Arrêt à la première
erreur avec code de sortie non nul — jamais de faux succès.
"""
from __future__ import annotations

import argparse
import json
import importlib.resources
import os
import socket
from datetime import datetime, timezone
import sys
import time
from dataclasses import replace
from pathlib import Path
from urllib.parse import urlparse

from forgeai.bootstrap.secrets import bootstrap_secrets
from forgeai.catalogue.loader import load_catalogue, verify_catalogue
from forgeai.core import registre
from forgeai.core.redaction import redact_exception, redact_text
from forgeai.core.runner import SubprocessRunner
from forgeai.core.validation import NODE_NAME_RE
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
from forgeai.network.discover import charger_signatures, inventaire, DiscoverError
from forgeai.planner.assemble import assemble_plan
from forgeai.planner.profile import ProfileError, derive_profile, gpus_non_qualifies_ignores
from forgeai.rag.client import RagClient
from forgeai.rag.hardened import HardenedRagClient
from forgeai.secrets.vault import read as vault_read, store as vault_store
from forgeai.deploy.openbao_flow import (
    FileKeyStore,
    FileSecretStore,
    initialize_openbao,
    prepare_key_store,
    wait_reachable,
)
from forgeai.audit import immudb as ledger
from forgeai.observability import langfuse as obs
from forgeai.eval import rag_eval
from forgeai.renderers.compose import render_compose
from forgeai.renderers.k3s import NAMESPACE, node_port_for, render_k3s
from forgeai.resources import catalogue_path, deploy_overlay_path, forgeai_home
from forgeai.i18n import t, set_locale, available_locales
from forgeai.ide import SUPPORTED_IDES
from forgeai.stacks import load_stack

# Données embarquées dans le paquet → portables après pip install (P3).
DEFAULT_CATALOGUE = catalogue_path()
DATA_PKG = "forgeai.data"  # package des données embarquées (specs, overlays, smoke docs, locales)
VAULT_SECRET_PATH = "forgeai/litellm"  # chemin KV v2 openbao de la master key passerelle (E3b)
IMMUDB_COLLECTION = "forgeai_audit"  # collection immudb du ledger d'audit du déploiement (E3c)
# immudb dev-chassis : identifiants PUBLICS par défaut d'immudb (documentés mondialement, pas un
# secret forgeai). La valeur d'immudb ici = l'immuabilité tamper-evident, pas le contrôle d'accès
# local/LAN ; la rotation du mot de passe admin relève du durcissement production (hors E3c).
IMMUDB_USER = "immudb"
IMMUDB_PASSWORD = "immudb"  # noqa: S105  proof:allow — défaut PUBLIC immudb (dev), pas un secret
DEFAULT_OVERLAY = deploy_overlay_path()


def default_registre() -> Path:
    """Emplacement portable et persistant du registre (revue P3, convergence
    Gemini+Qwen) : $FORGEAI_HOME si défini, sinon ~/.forgeai/ — jamais lié au
    répertoire courant (fragile, éphémère depuis /tmp). `--registre` reste
    disponible pour un registre projet-local."""
    return forgeai_home() / "Registres" / "mission.jsonl"


DEFAULT_REGISTRE = default_registre()

_NODE_RE = NODE_NAME_RE  # source unique partagée (FAI-0016)


def _node_type(value: str) -> str:
    """Validateur argparse pour --node : local, auto, ou hostname RFC 1123."""
    if value in ("local", "auto"):
        return value
    if not _NODE_RE.match(value):
        raise argparse.ArgumentTypeError(
            f"node invalide : '{value}' (attendu 'local', 'auto' ou un hostname minuscule)"
        )
    return value


def _step(label: str) -> None:
    print(f"[forgeai] {label}", flush=True)


def _k3s_probe_paths(plan, rag_ports=None) -> dict[str, str]:
    """Chemins de health-check par service, dérivés DU PLAN (jamais codés en dur).
    Seuls les services portant un healthcheck_url — ET exposés dans `rag_ports` si fourni —
    sont gatés en santé. Un service sans probe (ou non exposé) n'entraîne aucun KeyError,
    ni sur le chemin ni sur le port (finding Sentinelle)."""
    paths = {s.name: urlparse(s.healthcheck_url).path
             for s in plan.services if s.healthcheck_url}
    if rag_ports is not None:
        paths = {name: path for name, path in paths.items() if name in rag_ports}
    return paths


def _svc_url(host: str, port: int) -> str:
    """URL d'un service LOCAL du socle déployé (127.0.0.1 / hôte LAN, ports Docker publiés).
    Le trafic est local/LAN entre briques du même déploiement — pas de transmission réseau
    externe ; le TLS inter-briques est hors périmètre de la série E."""
    return f"http://{host}:{port}"  # NOSONAR S5332 — service local/LAN, cf. docstring


# openbao PRODUCTION (FAI-0005 S5) : chemin de santé tolérant au coffre scellé (le process vit scellé).
_OPENBAO_HEALTH = "/v1/sys/health?standbyok=true&sealedcode=200&uninitcode=200"


def _has_openbao(plan) -> bool:
    return any(s.name == "openbao" for s in plan.services)


def _provision_openbao_compose(compose_file: Path, workdir: Path, bao_url: str) -> str:
    """Amorçage openbao PRODUCTION (compose) AVANT les consommateurs — sans lui ils resteraient bloqués
    en `depends_on service_healthy` (le healthcheck = coffre descellé, or c'est l'init qui descelle).
    Prépare le key-store hôte (root ISOLÉ hors du répertoire monté à l'unsealer), démarre openbao + son
    unsealer seuls, attend la joignabilité (process up, même scellé), init/unseal via le cœur S2, renvoie
    le token applicatif scopé (jamais le root). Isolé pour être mocké en bloc dans les tests du wizard."""
    keys_dir = prepare_key_store(workdir / "openbao-keys")
    key_store = FileKeyStore(keys_dir, workdir / "secrets" / "openbao_root")
    secret_store = FileSecretStore(workdir / "secrets" / "openbao_app_token.json")
    compose_up(compose_file, services=["openbao", "openbao-unsealer"])
    wait_reachable(f"{bao_url}{_OPENBAO_HEALTH}", probe=http_ok)
    return initialize_openbao(bao_url, key_store, secret_store)


def wizard_ci(args: argparse.Namespace) -> int:
    workdir = Path(args.workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()

    # E2c — profil RAG DURCI : le flag bascule le wizard sur embed TEI + génération passerelle +
    # rerank. Applique overlay durci, briques forcées et défauts d'ancrage OOD (non surchargés).
    rag_durci = getattr(args, "rag_durci", False)
    rag_durci_bricks: tuple[str, ...] = ()
    if rag_durci:
        if args.overlay == str(DEFAULT_OVERLAY):
            args.overlay = str(importlib.resources.files(DATA_PKG) / "deploy-hardened.json")
        rag_durci_bricks = ("text-embeddings-inference-tei",
                            "text-embeddings-inference-reranker", "litellm", "redis", "openbao",
                            "immudb", "postgres", "langfuse")
        if args.document is None:
            args.document = str(
                importlib.resources.files(DATA_PKG) / "smoke" / "verification-durci.md")
        if args.question == "Quelle est la capitale de la France ?":
            args.question = ("Comment s'appelle le protocole de synchronisation interne "
                             "de ForgeAI Toolkit ?")
        if args.expected_fact == "Paris":
            args.expected_fact = "Vornak-9"

    _step(t("wizard.s01"))
    hw = HardwareDetector(SubprocessRunner()).full_report()
    (workdir / "hardware.json").write_text(hw.to_json(), encoding="utf-8")

    _step(t("wizard.s02"))
    try:
        profile = derive_profile(hw)
    except ProfileError as exc:
        if getattr(args, "dry_run", False):
            # dry-run = valider l'assemblage/rendu du plan, pas la machine COURANTE :
            # le plan peut viser un AUTRE nœud du réseau (exigence universelle).
            profile = "Minimal"
            print(f"  profil: Minimal (repli dry-run — machine courante sous les minima : {exc})")
        else:
            print(f"ABORT [{exc.code}] {exc}", file=sys.stderr)
            return 7
    else:
        print(f"  profil: {profile}")
        for nom in gpus_non_qualifies_ignores(hw):
            print(f"  ⚠ GPU NVIDIA ignoré (non qualifié, nvidia-smi indisponible) : {nom} — déploiement sur {profile} à la place. Vérifiez le driver NVIDIA si vous vouliez l'utiliser.")

    _step(t("wizard.s03"))
    digest = verify_catalogue(Path(args.catalogue))
    bricks = load_catalogue(Path(args.catalogue))
    print(f"  {len(bricks)} briques, sha256 {digest[:16]}…")

    stack = None
    stack_label = "minimal"
    if args.stack:
        try:
            stack = load_stack(args.stack)
        except FileNotFoundError:
            print(f"ABORT [STACK] stack inconnu : {args.stack}", file=sys.stderr)
            return 8
        stack_label = stack.get("name", args.stack)

    # P0.3b/N1b — sélection utilisateur v2 : briques + {modèle, nœud, moteur} + embeddings + rag_node
    selection_bricks: list[str] = []
    selection_models: list[dict] = []
    selection_embeddings: list[dict] = []
    adopt: dict = {}
    rag_node: str | None = None
    if getattr(args, "selection", None):
        from importlib import resources as _res

        def _normalise(entree, engine_defaut: str) -> dict:
            if isinstance(entree, str):
                return {"hf_id": entree, "node": "auto", "engine": engine_defaut}
            return {"hf_id": str(entree.get("hf_id", "")),
                    "node": str(entree.get("node", "auto")),
                    "engine": str(entree.get("engine", engine_defaut))}

        try:
            sel = json.loads(Path(args.selection).read_text(encoding="utf-8"))
            selection_bricks = [str(b) for b in (sel.get("bricks") or [])]
            selection_models = [_normalise(m, "vllm") for m in (sel.get("models") or [])]
            selection_embeddings = [_normalise(m, "llama-cpp") for m in (sel.get("embeddings") or [])]
            rag_node = sel.get("rag_node")
            adopt = sel.get("adopt") or {}
        except (OSError, ValueError, AttributeError) as exc:
            print(f"ABORT [SEL] sélection illisible : {exc}", file=sys.stderr)
            return 8
        ids_catalogue = {e.id for e in bricks}
        inconnues = sorted(b for b in selection_bricks if b not in ids_catalogue)
        if inconnues:
            print(f"ABORT [SEL] briques inconnues au catalogue : {inconnues}", file=sys.stderr)
            return 8
        registre_modeles = json.loads(
            (_res.files(DATA_PKG) / "modeles-locaux.json").read_text(encoding="utf-8"))
        hf_ids = {m["hf_id"] for m in registre_modeles["modeles"]}
        familles = {m["hf_id"]: m["famille"] for m in registre_modeles["modeles"]}
        moteurs = {m["id"] for m in json.loads(
            (_res.files(DATA_PKG) / "moteurs-inference.json").read_text(encoding="utf-8"))["moteurs"]}
        node_re = NODE_NAME_RE  # source unique partagée (FAI-0016)

        toutes = selection_models + selection_embeddings
        inconnus_m = sorted(e["hf_id"] for e in toutes if e["hf_id"] not in hf_ids)
        if inconnus_m:
            print(f"ABORT [SEL] modèles inconnus au registre : {inconnus_m}", file=sys.stderr)
            return 8
        mauvais_moteurs = sorted({e["engine"] for e in toutes} - moteurs)
        if mauvais_moteurs:
            print(f"ABORT [SEL] moteurs inconnus au registre des moteurs : {mauvais_moteurs}",
                  file=sys.stderr)
            return 8
        # S4 : « au choix » FILTRÉ — un moteur incompatible avec le vendor du nœud cible est refusé
        # (ex. tensorrt-llm sur un nœud AMD). Le vendor est lu des entrées BRUTES (non persisté au
        # manifeste) ; une entrée sans vendor connu est ignorée (pas de faux rejet).
        def _paires_vendor(brut, engine_defaut):
            return [{"engine": str(e.get("engine", engine_defaut)), "vendor": str(e["vendor"])}
                    for e in (brut or []) if isinstance(e, dict) and e.get("vendor")]
        from forgeai.engines import incompatible_selections
        incompat = incompatible_selections(
            _paires_vendor(sel.get("models"), "vllm")
            + _paires_vendor(sel.get("embeddings"), "llama-cpp"))
        if incompat:
            print(f"ABORT [SEL] moteur incompatible avec le vendor du nœud : {incompat}",
                  file=sys.stderr)
            return 8
        mauvais_noeuds = sorted({e["node"] for e in toutes if e["node"] not in ("local", "auto")
                                 and not node_re.match(e["node"])})
        if mauvais_noeuds:
            print(f"ABORT [SEL] nœuds invalides : {mauvais_noeuds}", file=sys.stderr)
            return 8
        pas_embed = sorted(e["hf_id"] for e in selection_embeddings
                           if familles.get(e["hf_id"]) != "embeddings-rerank")
        if pas_embed:
            print(f"ABORT [SEL] entrées 'embeddings' hors famille embeddings-rerank : {pas_embed}",
                  file=sys.stderr)
            return 8
        if rag_node is not None:
            rag_node = str(rag_node)
            if rag_node not in ("local", "auto") and not node_re.match(rag_node):
                print(f"ABORT [SEL] rag_node invalide : {rag_node!r}", file=sys.stderr)
                return 8
            if args.backend == "compose" and rag_node not in ("local", "auto"):
                # auto == la seule machine en compose ; seul un hostname DISTANT est impossible
                print("ABORT [RAG] compose est mono-machine : utilisez le backend k3s "
                      "pour placer le RAG sur un autre nœud", file=sys.stderr)
                return 9

    _step(t("wizard.s04"))
    plan = assemble_plan(profile, Path(args.overlay), stack=stack,
                         extra_bricks=tuple(selection_bricks) + rag_durci_bricks)
    if adopt:
        # Maillon final de la chaine d adoption : le choix valide par l API et transmis par le
        # fichier de selection est ici APPLIQUE au plan. Sans ce bloc, il serait valide, ecrit,
        # puis perdu — defaut releve par la revue scellee.
        noms_plan = {s.name for s in plan.services}
        inconnues = sorted(k for k in adopt if k not in noms_plan)
        if inconnues:
            print(f"ABORT [SEL] adopt reference des services absents du plan : {inconnues}",
                  file=sys.stderr)
            return 8
        services = tuple(
            replace(s, adopted_endpoint=adopt[s.name]) if s.name in adopt else s
            for s in plan.services
        )
        plan = replace(plan, services=services)
    (workdir / "plan.json").write_text(plan.to_json(), encoding="utf-8")
    ports = {s.name: s.host_port for s in plan.services}
    print(f"  stack: {stack_label} | services: {ports} | modèle: {plan.model}")
    if getattr(args, "selection", None):
        from importlib import resources as _res
        specs_ids = set(json.loads(
            (_res.files(DATA_PKG) / "deploy-specs.json").read_text(encoding="utf-8")))
        deployables = [b for b in selection_bricks if b in specs_ids]
        (workdir / "selection.json").write_text(json.dumps({
            "stack": args.stack,
            "bricks": selection_bricks,
            "models": selection_models,
            "embeddings": selection_embeddings,
            "rag_node": rag_node or "local",
            "deployables": deployables,
            "provisionnement_futur": [b for b in selection_bricks if b not in specs_ids],
        }, ensure_ascii=False, indent=1), encoding="utf-8")
        cible_rag = rag_node or "local"
        print(f"  sélection: {len(selection_bricks)} briques "
              f"({len(deployables)} déployables maintenant) + {len(selection_models)} modèles "
              f"+ {len(selection_embeddings)} embeddings | RAG -> {cible_rag}")

    _step(t("wizard.s05"))
    bootstrap_secrets(workdir)

    compose_file = workdir / "docker-compose.yaml"
    compose_file.write_text(render_compose(plan), encoding="utf-8")

    config_files: dict[str, str] = {}

    # E1b — si LiteLLM est dans le plan, générer sa config (routage modèles→backends)
    # à côté du compose : le conteneur la monte en lecture seule et démarre avec --config.
    # FAI-0006 : le contenu est aussi passé à render_k3s pour émettre un ConfigMap (k8s ne
    # sait pas monter un fichier hôte).
    if any(s.name == "litellm" for s in plan.services):
        from forgeai.renderers.litellm_config import render_litellm_config
        litellm_config = render_litellm_config(plan)
        (workdir / "litellm-config.yaml").write_text(litellm_config, encoding="utf-8")
        config_files["litellm-config.yaml"] = litellm_config

    # FAI-0005 (S1) — si openbao est dans le plan (mode PRODUCTION), fournir sa config HCL
    # (storage fichier) : écrite à côté du compose (bind-mount RO) ET passée en ConfigMap k3s.
    # Asset statique ; l'init/unseal du coffre est orchestré en S3/S4/S5, pas ici.
    if any(s.name == "openbao" for s in plan.services):
        openbao_hcl = (importlib.resources.files(DATA_PKG) / "openbao.hcl").read_text(
            encoding="utf-8")
        (workdir / "openbao.hcl").write_text(openbao_hcl, encoding="utf-8")
        config_files["openbao.hcl"] = openbao_hcl

    node_arg = args.node
    if rag_node is not None:
        # N1b — le placement du RAG choisi dans la sélection prime sur --node
        node_arg = rag_node
    probe_host = getattr(args, "probe_host", "127.0.0.1")

    if node_arg == "auto":
        effective_node = None
        node_label = "scheduler libre"
    elif node_arg == "local":
        effective_node = socket.gethostname().lower()
        node_label = effective_node
    else:
        effective_node = node_arg
        node_label = node_arg

    # Le manifeste k3s n'est rendu que s'il a un sens. En backend compose c'est un artefact
    # de commodite : le refuser au point de faire echouer tout le deploiement serait absurde,
    # alors que l'adoption compose est parfaitement supportee. Sans cette condition, la garde
    # AdoptionNonSupporteeK3s (D2) bloquait le chemin COMPOSE — defaut mesure : returncode 1
    # sur `wizard --backend compose` avec adoption.
    plan_a_adoptes = any(getattr(sv, "adopted_endpoint", None) for sv in plan.services)
    if args.backend in ("k3s", "k8s") or not plan_a_adoptes:
        (workdir / "k3s.yaml").write_text(
            render_k3s(plan, node=effective_node,
                       service_type=getattr(args, "service_type", "NodePort"),
                       config_files=config_files or None), encoding="utf-8")

    if args.dry_run:
        print(f"DRY-RUN OK: {len(plan.services)} services, stack={stack_label}, node={node_label}, "
              f"selection={len(selection_bricks)}+{len(selection_models)}+{len(selection_embeddings)}, "
              f"rag={(rag_node or 'local')}", flush=True)
        return 0

    backend = args.backend
    if not args.skip_preflight:
        from forgeai.preflight import available_backends, run_checks
        backends = available_backends(
            run_checks(SubprocessRunner(), HardwareDetector(SubprocessRunner()), http_ok))
        if backend not in backends:
            print(f"ABORT: backend '{backend}' indisponible sur cette machine. "
                  f"Backends prêts : {backends or 'aucun'}. "
                  f"Lancez `forgeai doctor` pour le détail, ou --skip-preflight pour forcer.",
                  file=sys.stderr)
            return 6

    immudb_witness = None  # E3c — témoin d'inscription au ledger d'audit immudb (RAG durci)
    langfuse_witness = None  # E5 — témoin de trace d'observabilité langfuse (RAG durci)
    eval_witness = None  # E6 — score d'éval RAG déterministe (« optimal » mesuré)
    openbao_app_token = ""  # FAI-0005 S5 : token applicatif scopé émis à l'amorçage (jamais le root)
    if backend == "compose":
        _step(t("wizard.s06"))
        if rag_durci and _has_openbao(plan):
            # openbao PROD : init/unseal AVANT les consommateurs (qui attendent service_healthy =
            # coffre descellé ; sans amorçage préalable = interblocage au premier boot).
            openbao_app_token = _provision_openbao_compose(
                compose_file, workdir, _svc_url(probe_host, ports["openbao"]))
        compose_up(compose_file)
        rag_ports = ports
    else:
        _step(t("wizard.s07", node=node_label))
        if rag_durci and _has_openbao(plan):
            # openbao est ClusterIP (interne, #113) : l'amorçage PROD k3s exige un port-forward
            # opérateur -> openbao. Flux documenté (Docs/how-to/openbao-migration.md) ; échec RAPIDE
            # ici plutôt qu'un `wait deployments` bloqué indéfiniment sur un coffre jamais descellé.
            raise DeployError(
                "openbao production sur k3s : l'amorçage passe par le flux opérateur "
                "(port-forward + forge, cf. Docs/how-to/openbao-migration.md) — pas encore câblé "
                "au wizard k3s. Utiliser le backend compose pour un déploiement RAG durci clé en main.")
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
            probe_paths = _k3s_probe_paths(plan, rag_ports)
            health = {name: "waiting" for name in probe_paths}
            while probe_paths and time.monotonic() < deadline and set(health.values()) != {"healthy"}:
                for name, path in probe_paths.items():
                    if http_ok(f"http://{probe_host}:{rag_ports[name]}{path}"):
                        health[name] = "healthy"
                time.sleep(2.0)
            if probe_paths and set(health.values()) != {"healthy"}:
                raise DeployError(f"Healthchecks K3s incomplets : {health}")
        print(f"  santé: {health}")

        _step(t("wizard.s08"))
        if rag_durci:
            env_vals: dict[str, str] = {}
            env_path = workdir / ".env"
            if env_path.exists():
                for raw_line in env_path.read_text(encoding="utf-8").splitlines():
                    line = raw_line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    ekey, eval_ = line.split("=", 1)
                    # valeur : sans espaces ni guillemets (sinon la clé passe au Bearer avec ses
                    # quotes -> 401 côté passerelle, finding CodeRabbit #80).
                    env_vals[ekey.strip()] = eval_.strip().strip('"').strip("'")
            # E3b — openbao branché comme coffre PORTEUR : on écrit la master key de la passerelle
            # dans le coffre, puis on la RELIT ; c'est la valeur relue qui authentifie la passerelle.
            # Conséquence : si openbao est absent/en panne, la lecture échoue et le RAG n'a pas de clé
            # (le coffre est dans le chemin critique, pas un simple double de .env).
            gateway_key = env_vals.get("FORGEAI_LITELLM_KEY", "")
            # PRODUCTION : le token n'est plus un dev-root pré-partagé du .env — c'est le token
            # applicatif SCOPÉ émis par l'amorçage (_provision_openbao_compose), policy forgeai-app.
            bao_url = _svc_url(probe_host, rag_ports['openbao'])
            vault_store(bao_url, openbao_app_token, VAULT_SECRET_PATH, {"master_key": gateway_key})
            gateway_key = vault_read(bao_url, openbao_app_token, VAULT_SECRET_PATH).get("master_key", "")
            print(f"  coffre openbao: master key écrite puis relue ({'ok' if gateway_key else 'VIDE'})")
            rag = HardenedRagClient(
                ollama_url=_svc_url(probe_host, rag_ports['ollama']),
                qdrant_url=_svc_url(probe_host, rag_ports['vector-store']),
                tei_url=_svc_url(probe_host, rag_ports['text-embeddings-inference-tei']),
                gateway_url=_svc_url(probe_host, rag_ports['litellm']),
                gateway_key=gateway_key,
                reranker_url=_svc_url(probe_host, rag_ports['text-embeddings-inference-reranker']),
                llm_model=plan.model,
                embed_model=plan.embed_model,
            )
        else:
            rag = RagClient(
                ollama_url=_svc_url(probe_host, rag_ports['ollama']),
                qdrant_url=_svc_url(probe_host, rag_ports['vector-store']),
                llm_model=plan.model,
                embed_model=plan.embed_model,
            )
        rag.pull_models()

        if args.document:
            doc_path = Path(args.document)
            source_name = doc_path.name
        else:
            doc_path = importlib.resources.files(DATA_PKG) / "smoke" / "verification.md"
            source_name = "verification.md"
        doc = doc_path.read_text(encoding="utf-8")

        chunks = rag.ingest(doc, source=source_name)
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

        # E6 — éval RAG DÉTERMINISTE (« optimal » mesuré) : ancrage lexical de la réponse dans le
        # document ingéré (source du RAG) + présence du fait. Aucun LLM n'écrit ce score (invariant
        # PROOF). Le score est journalisé au registre comme mesure objective de qualité.
        eval_witness = rag_eval.evaluate(answer, doc, args.expected_fact)
        print(f"  éval RAG (déterministe): groundedness={eval_witness['groundedness']} "
              f"fait={eval_witness['fact_present']} score_optimal={eval_witness['score']}")

        # E3c — immudb branché comme ledger d'audit IMMUABLE : on inscrit l'événement
        # « déploiement RAG durci vérifié » dans le ledger append-only d'immudb, puis on relit sa
        # piste de révisions (transactionId + revision = preuve d'inscription inviolable, horodatée
        # côté serveur). immudb porteur : sans le ledger, le déploiement vérifié n'est pas attesté.
        if rag_durci and "immudb" in rag_ports:
            immu_url = _svc_url(probe_host, rag_ports["immudb"])
            token = ledger.open_session(immu_url, IMMUDB_USER, IMMUDB_PASSWORD)
            ledger.ensure_collection(immu_url, token, IMMUDB_COLLECTION, [
                {"name": "event", "type": "STRING"}, {"name": "fact", "type": "STRING"},
                {"name": "plan_id", "type": "STRING"}])
            rec = ledger.record(immu_url, token, IMMUDB_COLLECTION, {
                "event": "rag_durci_verified", "fact": args.expected_fact,
                "question": args.question, "plan_id": plan.plan_id, "source": source_name})
            revisions = ledger.history(immu_url, token, IMMUDB_COLLECTION, rec["documentId"])
            immudb_witness = {"tx": rec["transactionId"], "doc": rec["documentId"],
                              "revisions": len(revisions)}
            print(f"  ledger immudb: audit inscrit tx={rec['transactionId']} "
                  f"doc={rec['documentId'][:16]}… révisions={len(revisions)}")

        # E5 — langfuse branché comme observabilité : la génération RAG passe par la passerelle
        # LiteLLM qui émet une trace (success_callback langfuse). On VÉRIFIE côté déploiement que la
        # trace atterrit dans langfuse (le callback flush en asynchrone -> attente bornée).
        if rag_durci and "langfuse" in rag_ports:
            lf_url = _svc_url(probe_host, rag_ports["langfuse"])
            trace = obs.wait_for_trace(lf_url, env_vals.get("FORGEAI_LANGFUSE_PK", ""),
                                       env_vals.get("FORGEAI_LANGFUSE_SK", ""),
                                       timeout=90.0, interval=3.0)
            langfuse_witness = {"trace_present": bool(trace),
                                "name": trace.get("name") if trace else None}
            print(f"  observabilité langfuse: trace "
                  f"{'présente' if trace else 'ABSENTE'} ({langfuse_witness['name']})")
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
        "immudb_audit": immudb_witness,  # E3c — témoin ledger immuable (tx/doc/révisions) ou None
        "langfuse_trace": langfuse_witness,  # E5 — témoin observabilité (trace présente) ou None
        "rag_eval": eval_witness,  # E6 — score d'éval déterministe (groundedness/fait/score) ou None
        "duree_s": round(time.monotonic() - started, 1),
    })
    print(f"CI_WITNESS={entry['hash']}")
    print("RAG_OK=true")
    return 0


_STATUS_MARK = {"ok": "OK ", "degraded": "!! ", "missing": "-- "}


def _gpu_drivers(args: argparse.Namespace) -> int:
    from forgeai.hardware.drivers import detect_driver_state, plan_driver_op, DriverError
    from forgeai.core.runner import SubprocessRunner
    try:
        state = detect_driver_state(args.vendor, SubprocessRunner())
        rec = state.recommendation
        print(f"[forgeai] driver {args.vendor} — présent: {state.present} "
              f"v{state.version or '-'}")
        ordre = " > ".join(rec.runtimes)
        print(f"  recommandation : runtime {rec.runtime}, operator {rec.operator} (runtimes: {ordre})")
        if rec.notes:
            print(f"  note : {rec.notes}")
        payload = {"vendor": args.vendor, "present": state.present, "version": state.version,
                   "runtime": rec.runtime, "operator": rec.operator,
                   "rocm_allowed": rec.rocm_allowed,
                   "runtimes": list(rec.runtimes)}
        if args.action:
            plan = plan_driver_op(args.vendor, args.action)
            print(f"  plan {args.action} : {' '.join(plan.install_argv)}")
            print(f"  rollback : {' '.join(plan.rollback_argv)}")
            payload["plan"] = {"action": plan.action, "install": plan.install_argv,
                               "rollback": plan.rollback_argv}
    except DriverError as exc:
        print(f"ECHEC GPU: {exc}", file=sys.stderr)
        return 12
    registre.append(Path(args.registre), "gpu_drivers", "hardware", payload)
    return 0


def _logs(args) -> int:
    """OPS-031B : `forgeai logs` — relecture du dernier déploiement SANS serveur web.

    Sortie toujours BORNÉE (défaut + plafond dur) et RÉDIGÉE. Absence de fichier d'état = cas
    normal (aucun déploiement encore lancé) : on sort proprement, pas par une trace.
    """
    import json as _json
    from forgeai.web.server import LOGS_TAIL_DEFAUT, lire_logs_deploiement

    tail = getattr(args, "tail", None) or LOGS_TAIL_DEFAUT
    lignes = lire_logs_deploiement(tail=tail, grep=getattr(args, "grep", None))
    if getattr(args, "json", False):
        print(_json.dumps({"lines": lignes}, ensure_ascii=False))
    elif not lignes:
        print("aucune ligne de déploiement disponible")
    else:
        print("\n".join(lignes))
    return 0


def _etat_execution_local() -> dict:
    """Câblage LOCAL de `collect_status` — source UNIQUE partagée par `status` et `diagnostic`.

    Factorisé (OPS-031C) pour qu'une seule définition de « l'état d'exécution » existe côté CLI :
    deux câblages divergents finiraient par décrire deux réalités différentes.
    """
    import json as _json
    from forgeai.network.nodes import cluster_status as _cluster_status
    from forgeai.preflight import available_backends as _available, run_checks as _run_checks
    from forgeai.deploy.compose import http_ok as _http_ok
    from forgeai.hardware.detect import HardwareDetector as _Detector
    from forgeai.status import collect_status

    runner = SubprocessRunner()
    detecteur = _Detector(runner)
    return collect_status(
        backends=lambda: _available(_run_checks(runner, detecteur, _http_ok)),
        cluster=lambda: _cluster_status(runner),
        deploiement=lambda: {"en_cours": False, "source": "cli"},
        materiel=lambda: _json.loads(detecteur.full_report().to_json()),
    )


def _status(args) -> int:
    """OPS-031A : `forgeai status` — MÊME agrégat que GET /api/status (source unique
    `collect_status`), mais calculé LOCALEMENT : aucun serveur web requis."""
    import json as _json
    from forgeai.status import format_status_humain

    etat = _etat_execution_local()
    print(_json.dumps(etat, ensure_ascii=False) if getattr(args, "json", False)
          else format_status_humain(etat))
    return 0


def _diagnostic(args) -> int:
    """OPS-031C : `forgeai diagnostic` — bundle reproductible et rédigé.

    L'horodatage est calculé UNE fois ici puis INJECTÉ : le module de construction ne lit jamais
    l'horloge, ce qui rend le bundle reproductible à état constant (et la propriété testable).
    """
    from pathlib import Path as _Path
    from forgeai.diagnostic import collect_diagnostic, rendre
    from forgeai.web.server import LOGS_TAIL_DEFAUT, lire_logs_deploiement

    horodatage = datetime.now(timezone.utc).isoformat()
    tail = getattr(args, "tail", None) or LOGS_TAIL_DEFAUT

    bundle = collect_diagnostic(
        horodatage=horodatage,
        etat=_etat_execution_local,
        logs=lambda: lire_logs_deploiement(tail=tail),
    )
    representation = rendre(bundle)
    if getattr(args, "out", None):
        _Path(args.out).write_text(representation, encoding="utf-8")
    else:
        print(representation)
    return 0


def _doctor(args: argparse.Namespace) -> int:
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


def _operators(args: argparse.Namespace) -> int:
    """Opérateurs K8s du châssis : détecte l'existant (ADOPTE) ou propose l'install Helm."""
    from forgeai.deploy.operators import OPERATORS, plan
    runner = SubprocessRunner()
    names = [args.name] if getattr(args, "name", None) else list(OPERATORS)
    print("[forgeai operators] détection sur le cluster courant (jamais de réinstallation) :")
    for name in names:
        if name not in OPERATORS:
            print(f"  {name} : inconnu (connus : {', '.join(sorted(OPERATORS))})", file=sys.stderr)
            return 8
        p = plan(name, runner)
        st = p["status"]
        if p["action"] == "adopt":
            print(f"  [ADOPTÉ] {name} — déjà présent ({st.source}, {st.version or 'CRD'}) ; intact")
        else:
            print(f"  [ABSENT] {name} — installable via Helm : "
                  f"{' ; '.join(' '.join(c) for c in p['commands'])}")
    return 0


def _node_probe(args: argparse.Namespace) -> int:
    from forgeai.network.remote_probe import probe_remote_node, SshRunner, RemoteProbeError
    runner = SshRunner(args.user, args.node_host, args.keyfile, args.hostkey)
    try:
        probe = probe_remote_node(args.node_host, runner=runner, registre_path=args.registre)
    except RemoteProbeError as exc:
        print(f"ECHEC PROBE: {exc}", file=sys.stderr)
        return 12
    print(f"[forgeai] sonde '{probe.node_host}' — profil {probe.profile} | "
          f"backends {', '.join(probe.backends) or 'aucun'}")
    return 0


def _node_cluster(args: argparse.Namespace) -> int:
    # S7 : vue cluster agrégée « quel vendor GPU sur quels nœuds » depuis les sondes du registre.
    from forgeai.cluster import cluster_view, read_probes
    view = cluster_view(read_probes(args.registre))
    if not view["nodes"]:
        print("[forgeai] vue cluster : aucune sonde node_hardware au registre")
        return 0
    print("[forgeai] vue cluster — vendors GPU par nœud :")
    for n in view["nodes"]:
        print(f"  {n['node']} : profil {n['profile']} | vendors {', '.join(n['vendors']) or 'aucun'}")
    print("[forgeai] quel vendor où :")
    for vendor, hosts in sorted(view["vendors"].items()):
        print(f"  {vendor} -> {', '.join(hosts)}")
    return 0


def _node_tailscale(args: argparse.Namespace) -> int:
    from forgeai.network.tailscale import render_node_network, TailscaleError
    from forgeai.network.bootstrap import BootstrapError
    try:
        plan = render_node_network(args.controller_host, args.node_host, args.hostkey,
                                   tailscale_version=args.version, tailscale_tag=args.tag,
                                   lan_only=args.lan_only)
    except (TailscaleError, BootstrapError) as exc:
        print(f"ECHEC TAILSCALE: {exc}", file=sys.stderr)
        return 12
    mode = "LAN-seulement" if plan.lan_only else "tailnet"
    print(f"[forgeai] plan réseau '{plan.node_host}' — {mode}")
    print(f"  install: {' '.join(plan.install_argv)}")
    if plan.up_argv:
        print(f"  up: {' '.join(plan.up_argv)}")
    registre.append(Path(args.registre), "node_network", "network",
                    {"node_host": plan.node_host, "lan_only": plan.lan_only,
                     "tailscale_version": args.version, "up": plan.up_argv, "acl": plan.acl})
    return 0


def _node_add(args: argparse.Namespace) -> int:
    from forgeai.network.node_add import add_node, SshBootstrapper, NodeAddError
    from forgeai.network.remote_probe import RemoteProbeError
    from forgeai.core.runner import SubprocessRunner
    passwd = os.environ.get(args.password_env)
    if not passwd:
        print(f"ECHEC NODE: variable d'env '{args.password_env}' vide ou absente "
              f"(le mot de passe ne passe jamais en argv)", file=sys.stderr)
        return 12
    try:
        rec = add_node(args.ip, args.user, passwd,
                       pubkey=Path(args.pubkey), privkey=Path(args.privkey),
                       bootstrapper=SshBootstrapper(hostkey_sha256=args.hostkey),
                       runner=SubprocessRunner(),
                       registre_path=Path(args.registre))
    except (NodeAddError, RemoteProbeError) as exc:
        print(f"ECHEC NODE: {exc}", file=sys.stderr)
        return 12
    print(f"[forgeai] nœud ajouté — {rec.user}@{rec.ip} | empreinte {rec.key_fingerprint}")
    return 0


def _node_prepare(args: argparse.Namespace) -> int:
    """Prépare un nœud Kubernetes en réceptacle ForgeAI (dry-run par défaut)."""
    import shutil
    from forgeai.network.prepare import PrepareError, preparer_noeud

    runner = SubprocessRunner()
    helm_present = shutil.which("helm") is not None
    try:
        result = preparer_noeud(
            runner, args.hostname, appliquer=args.apply, helm_present=helm_present
        )
    except PrepareError as exc:
        print(f"ECHEC PREPARATION: {exc}", file=sys.stderr)
        return 11

    etapes = result["etapes"]
    for i, etape in enumerate(etapes, 1):
        statut = etape.get("statut", "planifiee")
        print(f"[{i}/{len(etapes)}] {etape['titre_fr']} — {statut}")

    print(f"[forgeai] nœud '{result['hostname']}' -> réceptacle {result['receptacle']}")
    registre.append(Path(args.registre), "node_prepare", "node", {
        "hostname": result["hostname"],
        "receptacle": result["receptacle"],
        "etapes": [{"id": e["id"], "statut": e.get("statut", "planifiee")} for e in etapes],
    })
    return 0


def _node_discover(args: argparse.Namespace) -> int:
    """Découvre l'infrastructure logicielle déjà installée sur le nœud cible."""
    from forgeai.network.remote_probe import SshRunner

    if args.hostname == "local":
        runner = SubprocessRunner()
    else:
        if not args.hostkey:
            print("ECHEC DISCOVER: --hostkey requis pour un nœud distant (SSH-007)",
                  file=sys.stderr)
            return 12
        if not args.user or not args.keyfile:
            print("ECHEC DISCOVER: --user et --keyfile requis pour un nœud distant",
                  file=sys.stderr)
            return 12
        runner = SshRunner(args.user, args.hostname, args.keyfile, args.hostkey)

    try:
        signatures = charger_signatures()
        inv = inventaire(runner, signatures)
    except DiscoverError as exc:
        print(f"ECHEC DISCOVER: {exc}", file=sys.stderr)
        return 12

    for svc in inv["services"]:
        mark = "✓" if svc["detecte"] else "✗"
        endpoint = f" [{svc['endpoint']}]" if svc.get("endpoint") else ""
        via = ", ".join(svc.get("via", []))
        via_str = f" (via {via})" if via else ""
        print(f"{mark} {svc['id']}{endpoint}{via_str}")

    registre.append(Path(args.registre), "node_discover", "network", {
        "hostname": args.hostname,
        "detectes": inv["resume"]["detectes"],
        "services": [
            {"id": s["id"], "detecte": s["detecte"], "endpoint": s["endpoint"]}
            for s in inv["services"]
        ],
    })
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
    return forgeai_home() / "models"


def _read_secret(env_var: str | None, prompt: str) -> str:
    """Lit un secret depuis une variable d'environnement (CI) ou une invite sans écho.
    JAMAIS depuis argv (fuite dans la liste des processus / l'historique shell)."""
    if env_var:
        value = os.environ.get(env_var, "")
        if not value:
            raise RouteError(f"variable d'environnement '{env_var}' vide ou absente")
        return value
    import getpass
    try:
        return getpass.getpass(prompt)
    except EOFError:  # proof:allow (message d'erreur, aucune valeur secrète)
        raise RouteError(
            "aucune source disponible pour lire ce champ : ni variable "  # proof:allow
            "d'environnement (--*-env) ni terminal interactif"
        )


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


def _ide_list(args: argparse.Namespace) -> int:
    from forgeai.ide import list_ides
    for ide in list_ides():
        print(ide)
    return 0


def _ide_configure(args: argparse.Namespace) -> int:
    from forgeai.ide import generate_ide_config, write_ide_config, IDEError
    from forgeai.models.gateway import GatewayStore, GatewayError
    if args.gateway_url:
        gateway_url, key_env = args.gateway_url, args.key_env
    else:
        try:
            gw = GatewayStore(Path(args.home)).get_gateway()
        except GatewayError as exc:
            print(f"ECHEC IDE: gateway non configuré ({exc}) — fournir --gateway-url",
                  file=sys.stderr)
            return 12
        gateway_url, key_env = gw.base_url, gw.key_env
    try:
        cfg = generate_ide_config(args.ide, gateway_url, args.model, key_env=key_env)
    except IDEError as exc:
        print(f"ECHEC IDE: {exc}", file=sys.stderr)
        return 12
    path = write_ide_config(cfg, args.dest)
    print(f"[forgeai] config {args.ide} écrite → {path}")
    print(f"  gateway {gateway_url} | modèle {args.model} | clé via ${{{key_env}}}")
    registre.append(Path(args.registre), "ide_configure", "ide",
                    {"ide": args.ide, "path": str(path), "gateway": gateway_url,
                     "model": args.model})
    return 0


def _ide_mcp(args: argparse.Namespace) -> int:
    from forgeai.ide import IDEError, write_ide_config
    from forgeai.ide.bootstrap import generate_mcp_config, McpServer
    try:
        servers = []
        for spec in args.server:
            if "=" not in spec:
                print(f"ECHEC IDE: --server attend name=url (reçu '{spec}')", file=sys.stderr)
                return 12
            name, url = spec.split("=", 1)
            servers.append(McpServer(name=name, url=url, transport=args.transport))
        cfg = generate_mcp_config(args.ide, servers)
    except IDEError as exc:
        print(f"ECHEC IDE: {exc}", file=sys.stderr)
        return 12
    path = write_ide_config(cfg, args.dest)
    print(f"[forgeai] config MCP {args.ide} écrite → {path} ({len(servers)} serveur(s))")
    registre.append(Path(args.registre), "ide_mcp", "ide",
                    {"ide": args.ide, "path": str(path), "servers": [s.name for s in servers]})
    return 0


def _ide_governance(args: argparse.Namespace) -> int:
    from forgeai.ide import IDEError, write_ide_config
    from forgeai.ide.bootstrap import generate_governance_config
    try:
        cfg = generate_governance_config(skills=args.skill, hooks=args.hook, ide=args.ide)
    except IDEError as exc:
        print(f"ECHEC IDE: {exc}", file=sys.stderr)
        return 12
    path = write_ide_config(cfg, args.dest)
    print(f"[forgeai] config gouvernance {args.ide} écrite → {path} "
          f"({len(args.skill)} skill(s), {len(args.hook)} hook(s))")
    registre.append(Path(args.registre), "ide_governance", "ide",
                    {"ide": args.ide, "path": str(path), "skills": args.skill, "hooks": args.hook})
    return 0


def _loop_run(args: argparse.Namespace) -> int:
    from forgeai.loop import run_loop, make_command_step, make_command_check, LoopError
    from forgeai.core.proc import timed_runner, RunnerTimeoutError, RunnerCancelledError

    runner = timed_runner(getattr(args, "timeout", None))

    def on_iter(i: int, done: bool) -> None:
        print(f"  itération {i}/{args.max_iter} — {'complété' if done else 'en cours'}")

    step = make_command_step(args.step, runner)
    is_complete = make_command_check(args.until, runner)
    try:
        result = run_loop(step, is_complete, args.max_iter, on_iteration=on_iter)
    except RunnerTimeoutError as exc:
        print(f"ECHEC LOOP (timeout): {redact_text(str(exc))}", file=sys.stderr)
        return 14
    except RunnerCancelledError as exc:
        print(f"LOOP ANNULE: {redact_text(str(exc))}", file=sys.stderr)
        return 15
    except LoopError as exc:
        print(f"ECHEC LOOP: {exc}", file=sys.stderr)
        return 12
    registre.append(Path(args.registre), "ralph_loop", "loop",
                    {"max_iterations": args.max_iter, "completed": result.completed,
                     "iterations": result.iterations, "reason": result.reason,
                     "step": args.step, "until": args.until})
    print(f"[forgeai] boucle terminée — {result.reason} après {result.iterations} itération(s)")
    return 0 if result.completed else 13


def _export(args: argparse.Namespace) -> int:
    from forgeai.portability import export_setup, PortabilityError
    try:
        bundle = export_setup(args.home, args.out)
    except PortabilityError as exc:
        print(f"ECHEC EXPORT: {exc}", file=sys.stderr)
        return 11
    files = sorted(bundle["files"])
    print(f"[forgeai] setup exporté → {args.out}")
    print(f"  fichiers: {', '.join(files) or 'aucun'} | sha256 {bundle['sha256'][:16]}…")
    registre.append(Path(args.registre), "setup_exporte", "portability",
                    {"out": args.out, "fichiers": files, "sha256": bundle["sha256"]})
    return 0


def _import(args: argparse.Namespace) -> int:
    from forgeai.portability import import_setup, PortabilityError
    try:
        report = import_setup(args.bundle, args.home, force=args.force)
    except PortabilityError as exc:
        print(f"ECHEC IMPORT: {exc}", file=sys.stderr)
        return 11
    print(f"[forgeai] setup importé dans {report['home']}")
    print(f"  restaurés: {', '.join(report['restored']) or 'aucun'}")
    secrets = report["secrets_to_reprovision"]
    if secrets:
        print(f"  secrets à re-saisir (clés jamais incluses): {', '.join(secrets)}")
    registre.append(Path(args.registre), "setup_importe", "portability",
                    {"home": report["home"], "restaures": report["restored"],
                     "secrets_a_resaisir": secrets})
    return 0


def _template_list(args: argparse.Namespace) -> int:
    from forgeai.templates import DEPRECATION_NOTE, LEGACY_ALIASES, list_templates
    print(DEPRECATION_NOTE)
    inverses = {v: k for k, v in LEGACY_ALIASES.items()}
    for stack_id in list_templates():
        alias = f" (alias hérité : {inverses[stack_id]})" if stack_id in inverses else ""
        print(f"{stack_id}{alias}")
    return 0


def _template_show(args: argparse.Namespace) -> int:
    from forgeai.stacks import deploy_ids
    from forgeai.templates import DEPRECATION_NOTE, TemplateError, load_template, resolve_alias
    try:
        stack = load_template(args.name)
        stack_id = resolve_alias(args.name)
    except TemplateError as exc:
        print(f"ECHEC TEMPLATE: {exc}", file=sys.stderr)
        return 12
    print(DEPRECATION_NOTE)
    print(f"Stack '{stack.get('name', stack_id)}' — {len(deploy_ids(stack))} briques déployées")
    print(f"  {stack.get('description_fr', '')}")
    return 0


def _template_resolve(args: argparse.Namespace) -> int:
    from forgeai.stacks import deploy_ids
    from forgeai.templates import DEPRECATION_NOTE, TemplateError, load_template, resolve_alias
    try:
        stack = load_template(args.name)
        stack_id = resolve_alias(args.name)
    except TemplateError as exc:
        print(f"ECHEC TEMPLATE: {exc}", file=sys.stderr)
        return 12
    print(DEPRECATION_NOTE)
    ids = deploy_ids(stack)
    print(f"Stack '{stack.get('name', stack_id)}' : {len(ids)} briques déployées "
          f"(déploiement : forgeai wizard --ci --stack {stack_id})")
    for brick_id in ids:
        print(f"  ⚙ {brick_id}")
    registre.append(Path(args.registre), "template_resolve", "template",
                    {"template": args.name, "stack": stack_id, "bricks": len(ids)})
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


def _run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="forgeai")
    _langs = available_locales() or ["fr", "en"]
    _default_lang = os.environ.get("FORGEAI_LANG", "fr")
    if _default_lang not in _langs:   # env invalide → défaut sûr, jamais de crash au démarrage
        _default_lang = "fr"
    parser.add_argument("--lang", choices=_langs, default=_default_lang,
                        help="langue de l'interface (défaut: fr ; ou $FORGEAI_LANG)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_hw = sub.add_parser("hardware", help="détection hardware (S01)")
    p_hw.set_defaults(func=lambda a: print(
        HardwareDetector(SubprocessRunner()).full_report().to_json()) or 0)

    p_logs = sub.add_parser("logs", help="lignes du dernier déploiement (bornées, filtrées, rédigées)")
    p_logs.add_argument("--tail", type=int, default=None, help="nombre de lignes (borné)")
    p_logs.add_argument("--grep", default=None, help="filtre par SOUS-CHAÎNE littérale (pas de regex)")
    p_logs.add_argument("--json", action="store_true", help="sortie machine")
    p_logs.set_defaults(func=_logs)

    p_diag = sub.add_parser("diagnostic", help="bundle de diagnostic reproductible et rédigé")
    p_diag.add_argument("--out", default=None, help="fichier de sortie (défaut : stdout)")
    p_diag.add_argument("--tail", type=int, default=None, help="lignes de logs incluses (borné)")
    p_diag.set_defaults(func=_diagnostic)

    p_st = sub.add_parser("status", help="état d'exécution : backends, cluster, dernier déploiement")
    p_st.add_argument("--json", action="store_true", help="sortie machine")
    p_st.set_defaults(func=_status)

    p_doctor = sub.add_parser("doctor", help="préflight : ce que votre machine peut faire")
    p_doctor.set_defaults(func=_doctor)

    p_ops = sub.add_parser("operators",
                           help="opérateurs K8s du châssis : détecter+adopter l'existant ou installer (Helm)")
    p_ops.add_argument("name", nargs="?", help="opérateur précis (défaut : tous les opérateurs connus)")
    p_ops.set_defaults(func=_operators)

    p_gpu = sub.add_parser("gpu", help="cycle de vie des drivers GPU NVIDIA/AMD/Intel (B-04)")
    gpu_sub = p_gpu.add_subparsers(dest="gpu_cmd", required=True)
    p_gpu_drv = gpu_sub.add_parser("drivers", help="détecte + recommande (+ plan install/update)")
    p_gpu_drv.add_argument("--vendor", required=True, choices=["nvidia", "amd", "intel"])
    p_gpu_drv.add_argument("--action", choices=["install", "update"], default=None,
                           help="produit aussi un plan install/update avec rollback")
    p_gpu_drv.add_argument("--registre", default=str(DEFAULT_REGISTRE))
    p_gpu_drv.set_defaults(func=_gpu_drivers)

    p_node = sub.add_parser("node", help="multi-nœuds (P2)")
    node_sub = p_node.add_subparsers(dest="node_cmd", required=True)
    p_status = node_sub.add_parser("status", help="état du cluster + preuve (F22)")
    p_status.add_argument("--registre", default=str(DEFAULT_REGISTRE))
    p_status.add_argument("--witness", action="store_true",
                          help="scelle l'état au registre hash-chaîné")
    p_status.set_defaults(func=_node_status)
    p_node_add = node_sub.add_parser("add", help="ajoute un nœud : bootstrap clé, secret éphémère (B-05)")
    p_node_add.add_argument("--ip", required=True)
    p_node_add.add_argument("--user", required=True)
    p_node_add.add_argument("--password-env", required=True, dest="password_env",
                            help="variable d'env portant le mot de passe éphémère (jamais en argv)")
    p_node_add.add_argument("--pubkey", required=True)
    p_node_add.add_argument("--privkey", required=True)
    p_node_add.add_argument("--hostkey", required=True,
                            help="empreinte SHA256 de la clé d'hôte (SSH-021 : 'SHA256:...', pas de TOFU)")
    p_node_add.add_argument("--registre", default=str(DEFAULT_REGISTRE))
    p_node_add.set_defaults(func=_node_add)
    p_node_ts = node_sub.add_parser("tailscale",
                                    help="plan réseau Tailscale d'un nœud : version épinglée, LAN-only (B-06)")
    p_node_ts.add_argument("--node-host", required=True, dest="node_host")
    p_node_ts.add_argument("--controller-host", required=True, dest="controller_host")
    p_node_ts.add_argument("--hostkey", required=True, help="empreinte 'SHA256:...' de la clé d'hôte (EX-1)")
    p_node_ts.add_argument("--version", required=True, help="version Tailscale épinglée (pas 'latest')")
    p_node_ts.add_argument("--tag", default="tag:forgeai-node")
    p_node_ts.add_argument("--lan-only", action="store_true", dest="lan_only")
    p_node_ts.add_argument("--registre", default=str(DEFAULT_REGISTRE))
    p_node_ts.set_defaults(func=_node_tailscale)
    p_node_probe = node_sub.add_parser("probe", help="sonde matérielle distante d'un nœud via SSH (B-07)")
    p_node_probe.add_argument("--node-host", required=True, dest="node_host")
    p_node_probe.add_argument("--user", required=True)
    p_node_probe.add_argument("--keyfile", required=True, help="clé privée SSH d'accès au nœud")
    p_node_probe.add_argument("--hostkey", required=True,
                              help="empreinte SHA256 de la clé d'hôte (SSH-007 : 'SHA256:...', pas de TOFU)")
    p_node_probe.add_argument("--registre", default=str(DEFAULT_REGISTRE))
    p_node_probe.set_defaults(func=_node_probe)
    p_node_prepare = node_sub.add_parser(
        "prepare", help="prépare un nœud en réceptacle GPU/CPU (dry-run par défaut)"
    )
    p_node_prepare.add_argument("hostname", help="nom du nœud Kubernetes")
    p_node_prepare.add_argument(
        "--apply", action="store_true",
        help="applique le plan (sans ce flag, seul le plan est affiché)"
    )
    p_node_prepare.add_argument("--registre", default=str(DEFAULT_REGISTRE))
    p_node_prepare.set_defaults(func=_node_prepare)
    p_node_discover = node_sub.add_parser(
        "discover", help="découvre l'infrastructure déjà installée sur un nœud"
    )
    p_node_discover.add_argument("hostname", help="'local' ou nom d'hôte du nœud distant")
    p_node_discover.add_argument("--user", default=None,
                                 help="utilisateur SSH (requis si distant)")
    p_node_discover.add_argument("--keyfile", default=None,
                                 help="clé privée SSH (requis si distant)")
    p_node_discover.add_argument("--hostkey", default=None,
                                 help="empreinte SHA256 de la clé d'hôte distante (requis si hostname != local)")
    p_node_discover.add_argument("--registre", default=str(DEFAULT_REGISTRE))
    p_node_discover.set_defaults(func=_node_discover)
    p_node_cluster = node_sub.add_parser(
        "cluster", help="vue cluster agrégée : quel vendor GPU sur quels nœuds (S7)")
    p_node_cluster.add_argument("--registre", default=str(DEFAULT_REGISTRE))
    p_node_cluster.set_defaults(func=_node_cluster)

    p_wiz = sub.add_parser("wizard", help="wizard bout-en-bout")
    p_wiz.add_argument("--ci", action="store_true", required=True)
    p_wiz.add_argument("--backend", choices=["compose", "k3s", "k8s"], default="compose",
                       help="cible de déploiement : compose (mono-machine), k3s (léger/edge) "
                            "ou k8s (Kubernetes standard) — k3s/k8s partagent les mêmes manifestes")
    p_wiz.add_argument("--service-type", dest="service_type",
                       choices=["NodePort", "LoadBalancer"], default="NodePort",
                       help="exposition des services k3s/k8s : NodePort (portable, défaut) ou "
                            "LoadBalancer (cloud). Sans effet en compose.")
    p_wiz.add_argument("--workdir", default="run")
    p_wiz.add_argument("--catalogue", default=str(DEFAULT_CATALOGUE))
    p_wiz.add_argument("--overlay", default=str(DEFAULT_OVERLAY))
    p_wiz.add_argument("--rag-durci", dest="rag_durci", action="store_true",
                       help="déploie le RAG DURCI : embed TEI + rerank + génération via la "
                            "passerelle LiteLLM (overlay hardened, ancrage OOD par défaut)")
    p_wiz.add_argument("--stack", default=None,
                       help="stack à déployer (défaut : plan minimal)")
    p_wiz.add_argument("--node", type=_node_type, default="local",
                       help="cible K3s : 'local' (hostname courant), 'auto' (scheduler libre), ou hostname exact")
    p_wiz.add_argument("--probe-host", default="127.0.0.1", dest="probe_host",
                       help="hôte de sondage santé/RAG (défaut 127.0.0.1)")
    p_wiz.add_argument("--selection", default=None,
                       help="JSON {bricks:[ids], models:[hf_ids]} — sélection UI validée puis tracée (selection.json)")
    p_wiz.add_argument("--dry-run", action="store_true",
                       help="génère les manifestes et s'arrête sans déployer")
    p_wiz.add_argument("--registre", default=str(DEFAULT_REGISTRE))
    p_wiz.add_argument("--document", default=None,
                       help="document de test (défaut : smoke embarqué)")
    p_wiz.add_argument("--question", default="Quelle est la capitale de la France ?")
    p_wiz.add_argument("--expected-fact", default="Paris")
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

    p_export = sub.add_parser("export", help="exporte le setup portable, sans secrets (B-16)")
    p_export.add_argument("--out", required=True, help="chemin du bundle à écrire")
    p_export.add_argument("--home", default=str(default_models_home()))
    p_export.add_argument("--registre", default=str(DEFAULT_REGISTRE))
    p_export.set_defaults(func=_export)

    p_import = sub.add_parser("import", help="importe un bundle de setup (re-demande les secrets) (B-16)")
    p_import.add_argument("--bundle", required=True, help="chemin du bundle à importer")
    p_import.add_argument("--home", default=str(default_models_home()))
    p_import.add_argument("--force", action="store_true", help="écrase les fichiers existants")
    p_import.add_argument("--registre", default=str(DEFAULT_REGISTRE))
    p_import.set_defaults(func=_import)

    p_ide = sub.add_parser("ide", help="branche un IDE/CLI sur le gateway local (B-17)")
    ide_sub = p_ide.add_subparsers(dest="ide_cmd", required=True)
    p_ide_list = ide_sub.add_parser("list", help="liste les IDE supportés")
    p_ide_list.set_defaults(func=_ide_list)
    p_ide_cfg = ide_sub.add_parser("configure", help="génère+écrit la config de branchement IDE")
    p_ide_cfg.add_argument("--ide", required=True, choices=list(SUPPORTED_IDES))
    p_ide_cfg.add_argument("--model", required=True)
    p_ide_cfg.add_argument("--dest", default=".", help="répertoire cible (défaut: courant)")
    p_ide_cfg.add_argument("--gateway-url", default=None,
                           help="URL du gateway (sinon lue depuis la config gateway)")
    p_ide_cfg.add_argument("--key-env", default="FORGEAI_GATEWAY_KEY")
    p_ide_cfg.add_argument("--home", default=str(default_models_home()))
    p_ide_cfg.add_argument("--registre", default=str(DEFAULT_REGISTRE))
    p_ide_cfg.set_defaults(func=_ide_configure)
    p_ide_mcp = ide_sub.add_parser("mcp", help="préconfigure les serveurs MCP du stack (B-18)")
    p_ide_mcp.add_argument("--ide", required=True, choices=list(SUPPORTED_IDES))
    p_ide_mcp.add_argument("--server", action="append", required=True, metavar="NAME=URL",
                           help="serveur MCP name=url (répétable)")
    p_ide_mcp.add_argument("--transport", choices=["http", "sse"], default="http")
    p_ide_mcp.add_argument("--dest", default=".")
    p_ide_mcp.add_argument("--registre", default=str(DEFAULT_REGISTRE))
    p_ide_mcp.set_defaults(func=_ide_mcp)
    p_ide_gov = ide_sub.add_parser("governance",
                                   help="préconfigure skills allowlist + hooks gouvernance (claude-code) (B-18)")
    p_ide_gov.add_argument("--ide", default="claude-code", choices=list(SUPPORTED_IDES))
    p_ide_gov.add_argument("--skill", action="append", default=[], help="skill allowlisté (répétable)")
    p_ide_gov.add_argument("--hook", action="append", default=[], help="hook de gouvernance (répétable)")
    p_ide_gov.add_argument("--dest", default=".")
    p_ide_gov.add_argument("--registre", default=str(DEFAULT_REGISTRE))
    p_ide_gov.set_defaults(func=_ide_governance)

    p_cat = sub.add_parser("catalogue", help="explore le catalogue de briques")
    p_cat.add_argument("--defaults", action="store_true",
                       help="liste la brique par défaut de chaque catégorie")
    p_cat.add_argument("--catalogue", default=str(DEFAULT_CATALOGUE),
                       help="chemin vers le catalogue JSON")
    p_cat.set_defaults(func=_catalogue)

    p_loop = sub.add_parser("loop", help="boucle d'agent gouvernée : budget+complétion+journal (B-19)")
    loop_sub = p_loop.add_subparsers(dest="loop_cmd", required=True)
    p_loop_run = loop_sub.add_parser("run", help="répète --step jusqu'à --until (exit 0) ou budget")
    p_loop_run.add_argument("--max-iter", type=int, required=True, dest="max_iter",
                            help="budget d'itérations maximum")
    p_loop_run.add_argument("--step", required=True, help="commande exécutée à chaque itération")
    p_loop_run.add_argument("--until", required=True, help="commande de complétion (exit 0 = terminé)")
    p_loop_run.add_argument("--timeout", type=float, default=None,
                            help="durée max (s) par commande ; kill d'arbre au-delà (défaut : illimité)")
    p_loop_run.add_argument("--registre", default=str(DEFAULT_REGISTRE))
    p_loop_run.set_defaults(func=_loop_run)

    p_tmpl = sub.add_parser("template", help="alias hérités vers les stacks (fusion P1 — un seul système de profils)")
    tmpl_sub = p_tmpl.add_subparsers(dest="template_cmd", required=True)
    p_tmpl_list = tmpl_sub.add_parser("list", help="liste les templates disponibles")
    p_tmpl_list.set_defaults(func=_template_list)
    p_tmpl_show = tmpl_sub.add_parser("show", help="affiche + valide un template contre le catalogue")
    p_tmpl_show.add_argument("name")
    p_tmpl_show.add_argument("--catalogue", default=str(DEFAULT_CATALOGUE))
    p_tmpl_show.set_defaults(func=_template_show)
    p_tmpl_res = tmpl_sub.add_parser("resolve", help="résout le template (filtrage hardware) → cœur déployable")
    p_tmpl_res.add_argument("name")
    p_tmpl_res.add_argument("--registre", default=str(DEFAULT_REGISTRE))
    p_tmpl_res.set_defaults(func=_template_resolve)

    p_web = sub.add_parser("web", help="interface web locale (stdlib, hors-ligne) — B-02a")
    p_web.add_argument("--host", default="127.0.0.1",
                       help="bind (défaut 127.0.0.1 — jamais exposé sans action explicite)")
    p_web.add_argument("--port", type=int, default=8765)
    p_web.add_argument("--no-browser", action="store_true", dest="no_browser",
                       help="ne pas ouvrir le navigateur automatiquement")
    from forgeai.web import web_command
    p_web.set_defaults(func=web_command)

    args = parser.parse_args(argv)
    set_locale(args.lang)   # bascule la langue de l'interface avant dispatch
    try:
        return args.func(args)
    except DeployError as exc:
        print(f"ECHEC DEPLOIEMENT: {redact_text(str(exc))}", file=sys.stderr)
        return 8


def main(argv: list[str] | None = None) -> int:
    """Frontière d'erreurs unique (CLI-013). Toute exception inattendue est rédigée
    (jamais de traceback brute, jamais de secret) et convertie en code non nul.
    ``FORGEAI_DEBUG`` réactive la traceback complète pour le diagnostic."""
    try:
        return _run(argv)
    except KeyboardInterrupt:
        print("Interrompu.", file=sys.stderr)
        return 130
    except Exception as exc:  # noqa: BLE001 — frontière volontaire ; SystemExit (exit
        # argparse code 2) n'est PAS une Exception et traverse donc intacte.
        if os.environ.get("FORGEAI_DEBUG"):
            raise
        print(f"ERREUR: {redact_exception(exc)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
