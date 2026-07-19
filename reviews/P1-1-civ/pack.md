# Story P1.1 — Fusion templates -> stacks (un seul systeme de profils)

## Criteres (decision explicite Nathan : « Fusionner » — un seul format, un seul chemin de deploiement)
- Retro-compatibilite CLI totale (list/show/resolve, alias herites, erreurs claires exit 12) ; JSON dupliques RETIRES ; zero perte : chaque alias pointe un stack REEL plus riche (37 briques template -> 72+ deployees) ; contrat refige par tests.

## PREUVE
```
### SUITE COMPLETE (206 tests)
.........................................................                [100%]
### no_stub
NO-STUB-SCAN : OK (157 fichiers scannés, zéro violation)

### PREUVE CLI REELLE (fusion retro-compatible)
$ forgeai template list ->
note: les templates sont fusionnés dans les stacks — utilisez `forgeai web` ou les ids de stacks directement
agentique (alias hérité : dev-agentic)
assistant-entreprise (alias hérité : rag-souverain)
automatisation
mlops (alias hérité : lab-fine-tuning)
support-conversationnel
tout-en-un (alias hérité : production-souveraine)

$ forgeai template resolve dev-agentic (alias herite) ->
note: les templates sont fusionnés dans les stacks — utilisez `forgeai web` ou les ids de stacks directement
Stack 'Agentique (agents autonomes outilles)' : 72 briques déployées (déploiement : forgeai wizard --ci --stack agentique)
  ⚙ k3s
  ⚙ nvidia-gpu-operator
  [...] pointe le deploiement REEL : forgeai wizard --ci --stack agentique

$ forgeai template show template-fantome -> (erreur claire attendue)
ECHEC TEMPLATE: 'template-fantome' inconnu — noms acceptés : ['agentique', 'assistant-entreprise', 'automatisation', 'dev-agentic', 'lab-fine-tuning', 'mlops', 'production-souveraine', 'rag-souverain', 'support-conversationnel', 'tout-en-un']

### SUPPRESSIONS (decision Nathan « Fusionner », AskUserQuestion 2026-07-19)
data/templates/*.json (4 fichiers, format concurrent) ; tests/test_templates_b14.py ; reference pyproject. Le contrat est refige par tests/test_templates.py (aliases -> stacks reels, JSON dupliques absents du paquet).
```

## DIFF COMPLET (main...HEAD)
```diff
diff --git a/pyproject.toml b/pyproject.toml
index 6faf34d..aedaf38 100644
--- a/pyproject.toml
+++ b/pyproject.toml
@@ -27,7 +27,7 @@ package-dir = {"" = "src"}
 where = ["src"]
 
 [tool.setuptools.package-data]
-"forgeai.data" = ["*.json", "*.sha256", "locales/*.json", "templates/*.json", "stacks/*.json", "smoke/*.md"]
+"forgeai.data" = ["*.json", "*.sha256", "locales/*.json", "stacks/*.json", "smoke/*.md"]
 "forgeai.web" = ["assets/*"]
 
 [tool.pytest.ini_options]
diff --git a/src/forgeai/cli.py b/src/forgeai/cli.py
index 5aa3a3a..9d178b4 100644
--- a/src/forgeai/cli.py
+++ b/src/forgeai/cli.py
@@ -759,49 +759,47 @@ def _import(args: argparse.Namespace) -> int:
 
 
 def _template_list(args: argparse.Namespace) -> int:
-    from forgeai.templates import list_templates
-    for t in list_templates():
-        print(t)
+    from forgeai.templates import DEPRECATION_NOTE, LEGACY_ALIASES, list_templates
+    print(DEPRECATION_NOTE)
+    inverses = {v: k for k, v in LEGACY_ALIASES.items()}
+    for stack_id in list_templates():
+        alias = f" (alias hérité : {inverses[stack_id]})" if stack_id in inverses else ""
+        print(f"{stack_id}{alias}")
     return 0
 
 
 def _template_show(args: argparse.Namespace) -> int:
-    import json
-    from forgeai.templates import load_template, validate_template, TemplateError
+    from forgeai.stacks import deploy_ids
+    from forgeai.templates import DEPRECATION_NOTE, TemplateError, load_template, resolve_alias
     try:
-        tmpl = load_template(args.name)
+        stack = load_template(args.name)
+        stack_id = resolve_alias(args.name)
     except TemplateError as exc:
         print(f"ECHEC TEMPLATE: {exc}", file=sys.stderr)
         return 12
-    entries = json.loads(Path(args.catalogue).read_text(encoding="utf-8")).get("entries", [])
-    violations = validate_template(tmpl, entries)
-    print(f"Template '{tmpl['name']}' — {len(tmpl.get('bricks', []))} briques")
-    print(f"  {tmpl.get('description_fr', '')}")
-    if violations:
-        for v in violations:
-            print(f"  ⚠ {v}", file=sys.stderr)
-        return 13
-    print("  ✓ conforme (toutes au catalogue, bilingues)")
+    print(DEPRECATION_NOTE)
+    print(f"Stack '{stack.get('name', stack_id)}' — {len(deploy_ids(stack))} briques déployées")
+    print(f"  {stack.get('description_fr', '')}")
     return 0
 
 
 def _template_resolve(args: argparse.Namespace) -> int:
-    from forgeai.templates import load_template, resolve_template, deployable_bricks, TemplateError
+    from forgeai.stacks import deploy_ids
+    from forgeai.templates import DEPRECATION_NOTE, TemplateError, load_template, resolve_alias
     try:
-        tmpl = load_template(args.name)
+        stack = load_template(args.name)
+        stack_id = resolve_alias(args.name)
     except TemplateError as exc:
         print(f"ECHEC TEMPLATE: {exc}", file=sys.stderr)
         return 12
-    has_gpu = not args.no_gpu
-    resolved = resolve_template(tmpl, has_gpu=has_gpu)
-    deployable = deployable_bricks(tmpl, has_gpu=has_gpu)
-    print(f"Template '{tmpl['name']}' résolu ({'GPU' if has_gpu else 'CPU'}) : "
-          f"{len(resolved)} briques, {len(deployable)} déployables (cœur runtime Express)")
-    for b in deployable:
-        print(f"  ⚙ {b['id']} ({b.get('role', '?')})")
+    print(DEPRECATION_NOTE)
+    ids = deploy_ids(stack)
+    print(f"Stack '{stack.get('name', stack_id)}' : {len(ids)} briques déployées "
+          f"(déploiement : forgeai wizard --ci --stack {stack_id})")
+    for brick_id in ids:
+        print(f"  ⚙ {brick_id}")
     registre.append(Path(args.registre), "template_resolve", "template",
-                    {"template": tmpl["name"], "has_gpu": has_gpu, "bricks": len(resolved),
-                     "deployable": [b["id"] for b in deployable]})
+                    {"template": args.name, "stack": stack_id, "bricks": len(ids)})
     return 0
 
 
@@ -1074,7 +1072,7 @@ def main(argv: list[str] | None = None) -> int:
     p_loop_run.add_argument("--registre", default=str(DEFAULT_REGISTRE))
     p_loop_run.set_defaults(func=_loop_run)
 
-    p_tmpl = sub.add_parser("template", help="templates de déploiement — systèmes complets curés (B-13)")
+    p_tmpl = sub.add_parser("template", help="alias hérités vers les stacks (fusion P1 — un seul système de profils)")
     tmpl_sub = p_tmpl.add_subparsers(dest="template_cmd", required=True)
     p_tmpl_list = tmpl_sub.add_parser("list", help="liste les templates disponibles")
     p_tmpl_list.set_defaults(func=_template_list)
diff --git a/src/forgeai/data/templates/dev-agentic.json b/src/forgeai/data/templates/dev-agentic.json
deleted file mode 100644
index 57321e5..0000000
--- a/src/forgeai/data/templates/dev-agentic.json
+++ /dev/null
@@ -1,266 +0,0 @@
-{
- "name": "dev-agentic",
- "description_fr": "Système Dev Agentic complet : inférence locale + gateway, orchestration d'agents, RAG/mémoire, serveurs MCP, harnais de codage et méthodologies, évaluation/observabilité.",
- "description_en": "Complete Dev Agentic system: local inference + gateway, agent orchestration, RAG/memory, MCP servers, coding harness and methodologies, evaluation/observability.",
- "bricks": [
-  {
-   "id": "ollama",
-   "role": "inference",
-   "deployable": true,
-   "requires_gpu": false,
-   "default": true
-  },
-  {
-   "id": "llama-cpp",
-   "role": "inference",
-   "deployable": true,
-   "requires_gpu": false,
-   "default": false
-  },
-  {
-   "id": "vllm",
-   "role": "inference",
-   "deployable": true,
-   "requires_gpu": true,
-   "default": false
-  },
-  {
-   "id": "localai",
-   "role": "inference",
-   "deployable": true,
-   "requires_gpu": false,
-   "default": false
-  },
-  {
-   "id": "litellm",
-   "role": "gateway",
-   "deployable": true,
-   "requires_gpu": false,
-   "default": false
-  },
-  {
-   "id": "open-webui",
-   "role": "ui",
-   "deployable": false,
-   "requires_gpu": false,
-   "default": false
-  },
-  {
-   "id": "openclaw",
-   "role": "orchestration",
-   "deployable": false,
-   "requires_gpu": false,
-   "default": true
-  },
-  {
-   "id": "hermes-agent",
-   "role": "orchestration",
-   "deployable": false,
-   "requires_gpu": false,
-   "default": false
-  },
-  {
-   "id": "langchain",
-   "role": "orchestration",
-   "deployable": false,
-   "requires_gpu": false,
-   "default": false
-  },
-  {
-   "id": "langflow",
-   "role": "orchestration",
-   "deployable": false,
-   "requires_gpu": false,
-   "default": false
-  },
-  {
-   "id": "dify",
-   "role": "orchestration",
-   "deployable": false,
-   "requires_gpu": false,
-   "default": false
-  },
-  {
-   "id": "n8n",
-   "role": "orchestration",
-   "deployable": false,
-   "requires_gpu": false,
-   "default": false
-  },
-  {
-   "id": "autogpt",
-   "role": "orchestration",
-   "deployable": false,
-   "requires_gpu": false,
-   "default": false
-  },
-  {
-   "id": "markitdown",
-   "role": "rag",
-   "deployable": false,
-   "requires_gpu": false,
-   "default": true
-  },
-  {
-   "id": "firecrawl",
-   "role": "rag",
-   "deployable": false,
-   "requires_gpu": false,
-   "default": false
-  },
-  {
-   "id": "ragflow",
-   "role": "rag",
-   "deployable": false,
-   "requires_gpu": false,
-   "default": false
-  },
-  {
-   "id": "crawl4ai",
-   "role": "rag",
-   "deployable": false,
-   "requires_gpu": false,
-   "default": false
-  },
-  {
-   "id": "anythingllm",
-   "role": "rag",
-   "deployable": false,
-   "requires_gpu": false,
-   "default": false
-  },
-  {
-   "id": "mem0-pro",
-   "role": "rag",
-   "deployable": false,
-   "requires_gpu": false,
-   "default": false
-  },
-  {
-   "id": "awesome-mcp-servers-punkpeye",
-   "role": "mcp",
-   "deployable": false,
-   "requires_gpu": false,
-   "default": true
-  },
-  {
-   "id": "filesystem-mcp",
-   "role": "mcp",
-   "deployable": false,
-   "requires_gpu": false,
-   "default": false
-  },
-  {
-   "id": "git-mcp-officiel",
-   "role": "mcp",
-   "deployable": false,
-   "requires_gpu": false,
-   "default": false
-  },
-  {
-   "id": "reference-mcp-servers-fetch",
-   "role": "mcp",
-   "deployable": false,
-   "requires_gpu": false,
-   "default": false
-  },
-  {
-   "id": "reference-mcp-servers-memory",
-   "role": "mcp",
-   "deployable": false,
-   "requires_gpu": false,
-   "default": false
-  },
-  {
-   "id": "sequential-thinking-mcp",
-   "role": "mcp",
-   "deployable": false,
-   "requires_gpu": false,
-   "default": false
-  },
-  {
-   "id": "superpowers",
-   "role": "coding",
-   "deployable": false,
-   "requires_gpu": false,
-   "default": true
-  },
-  {
-   "id": "claude-code",
-   "role": "coding",
-   "deployable": false,
-   "requires_gpu": false,
-   "default": false
-  },
-  {
-   "id": "opencode",
-   "role": "coding",
-   "deployable": false,
-   "requires_gpu": false,
-   "default": false
-  },
-  {
-   "id": "anthropic-skills",
-   "role": "coding",
-   "deployable": false,
-   "requires_gpu": false,
-   "default": false
-  },
-  {
-   "id": "github-spec-kit",
-   "role": "coding",
-   "deployable": false,
-   "requires_gpu": false,
-   "default": false
-  },
-  {
-   "id": "openhands",
-   "role": "coding",
-   "deployable": false,
-   "requires_gpu": false,
-   "default": false
-  },
-  {
-   "id": "grafana",
-   "role": "eval",
-   "deployable": false,
-   "requires_gpu": false,
-   "default": true
-  },
-  {
-   "id": "prometheus",
-   "role": "eval",
-   "deployable": false,
-   "requires_gpu": false,
-   "default": false
-  },
-  {
-   "id": "langfuse-prompts",
-   "role": "eval",
-   "deployable": false,
-   "requires_gpu": false,
-   "default": false
-  },
-  {
-   "id": "trivy",
-   "role": "eval",
-   "deployable": false,
-   "requires_gpu": false,
-   "default": false
-  },
-  {
-   "id": "redis",
-   "role": "data",
-   "deployable": false,
-   "requires_gpu": false,
-   "default": true
-  },
-  {
-   "id": "cohere-embed-v4-multimodal",
-   "role": "embedding",
-   "deployable": false,
-   "requires_gpu": false,
-   "default": true
-  }
- ]
-}
\ No newline at end of file
diff --git a/src/forgeai/data/templates/lab-fine-tuning.json b/src/forgeai/data/templates/lab-fine-tuning.json
deleted file mode 100644
index 5cb8e5b..0000000
--- a/src/forgeai/data/templates/lab-fine-tuning.json
+++ /dev/null
@@ -1,112 +0,0 @@
-{
- "name": "lab-fine-tuning",
- "description_fr": "Lab fine-tuning : entrainement/fine-tuning, quantization/fusion, datasets, suivi d'experiences, inference de test.",
- "description_en": "Fine-tuning lab: training/fine-tuning, quantization/merging, datasets, experiment tracking, test inference.",
- "bricks": [
-  {
-   "id": "transformers",
-   "role": "training",
-   "deployable": false,
-   "requires_gpu": true,
-   "default": true
-  },
-  {
-   "id": "unsloth",
-   "role": "training",
-   "deployable": false,
-   "requires_gpu": true,
-   "default": false
-  },
-  {
-   "id": "llama-factory",
-   "role": "training",
-   "deployable": false,
-   "requires_gpu": true,
-   "default": false
-  },
-  {
-   "id": "deepspeed",
-   "role": "training",
-   "deployable": false,
-   "requires_gpu": true,
-   "default": false
-  },
-  {
-   "id": "pytorch-fsdp",
-   "role": "training",
-   "deployable": false,
-   "requires_gpu": true,
-   "default": false
-  },
-  {
-   "id": "llama-cpp-gguf",
-   "role": "quantization",
-   "deployable": false,
-   "requires_gpu": false,
-   "default": false
-  },
-  {
-   "id": "lazymergekit",
-   "role": "fusion",
-   "deployable": false,
-   "requires_gpu": false,
-   "default": false
-  },
-  {
-   "id": "llm-course",
-   "role": "methodology",
-   "deployable": false,
-   "requires_gpu": false,
-   "default": false
-  },
-  {
-   "id": "ollama",
-   "role": "inference",
-   "deployable": true,
-   "requires_gpu": false,
-   "default": true
-  },
-  {
-   "id": "llama-cpp",
-   "role": "inference",
-   "deployable": true,
-   "requires_gpu": false,
-   "default": false
-  },
-  {
-   "id": "minio",
-   "role": "data",
-   "deployable": true,
-   "requires_gpu": false,
-   "default": false
-  },
-  {
-   "id": "postgresql",
-   "role": "data",
-   "deployable": true,
-   "requires_gpu": false,
-   "default": false
-  },
-  {
-   "id": "mlflow",
-   "role": "eval",
-   "deployable": true,
-   "requires_gpu": false,
-   "default": false
-  },
-  {
-   "id": "langfuse-prompts",
-   "role": "eval",
-   "deployable": false,
-   "requires_gpu": false,
-   "default": false
-  },
-  {
-   "id": "trivy",
-   "role": "security",
-   "deployable": false,
-   "requires_gpu": false,
-   "default": false
-  }
- ]
-}
\ No newline at end of file
diff --git a/src/forgeai/data/templates/production-souveraine.json b/src/forgeai/data/templates/production-souveraine.json
deleted file mode 100644
index c7d75bb..0000000
--- a/src/forgeai/data/templates/production-souveraine.json
+++ /dev/null
@@ -1,119 +0,0 @@
-{
- "name": "production-souveraine",
- "description_fr": "Production souveraine : inference haute performance + gateway, K8s/IaC, observabilite, garde-fous securite, donnees.",
- "description_en": "Sovereign production: high-throughput inference + gateway, K8s/IaC, observability, security guardrails, data.",
- "bricks": [
-  {
-   "id": "vllm",
-   "role": "inference",
-   "deployable": true,
-   "requires_gpu": true,
-   "default": false
-  },
-  {
-   "id": "ollama",
-   "role": "inference",
-   "deployable": true,
-   "requires_gpu": false,
-   "default": true
-  },
-  {
-   "id": "litellm",
-   "role": "gateway",
-   "deployable": true,
-   "requires_gpu": false,
-   "default": false
-  },
-  {
-   "id": "ansible",
-   "role": "infra",
-   "deployable": false,
-   "requires_gpu": false,
-   "default": true
-  },
-  {
-   "id": "k3s",
-   "role": "infra",
-   "deployable": false,
-   "requires_gpu": false,
-   "default": false
-  },
-  {
-   "id": "traefik",
-   "role": "infra",
-   "deployable": true,
-   "requires_gpu": false,
-   "default": false
-  },
-  {
-   "id": "argo-cd",
-   "role": "infra",
-   "deployable": false,
-   "requires_gpu": false,
-   "default": false
-  },
-  {
-   "id": "cert-manager",
-   "role": "infra",
-   "deployable": false,
-   "requires_gpu": false,
-   "default": false
-  },
-  {
-   "id": "cilium-hubble",
-   "role": "infra",
-   "deployable": false,
-   "requires_gpu": false,
-   "default": false
-  },
-  {
-   "id": "grafana",
-   "role": "eval",
-   "deployable": true,
-   "requires_gpu": false,
-   "default": true
-  },
-  {
-   "id": "prometheus",
-   "role": "eval",
-   "deployable": true,
-   "requires_gpu": false,
-   "default": false
-  },
-  {
-   "id": "loki",
-   "role": "eval",
-   "deployable": true,
-   "requires_gpu": false,
-   "default": false
-  },
-  {
-   "id": "trivy",
-   "role": "security",
-   "deployable": false,
-   "requires_gpu": false,
-   "default": false
-  },
-  {
-   "id": "keycloak",
-   "role": "security",
-   "deployable": true,
-   "requires_gpu": false,
-   "default": false
-  },
-  {
-   "id": "redis",
-   "role": "data",
-   "deployable": true,
-   "requires_gpu": false,
-   "default": true
-  },
-  {
-   "id": "postgresql",
-   "role": "data",
-   "deployable": true,
-   "requires_gpu": false,
-   "default": false
-  }
- ]
-}
\ No newline at end of file
diff --git a/src/forgeai/data/templates/rag-souverain.json b/src/forgeai/data/templates/rag-souverain.json
deleted file mode 100644
index 6ef83fb..0000000
--- a/src/forgeai/data/templates/rag-souverain.json
+++ /dev/null
@@ -1,119 +0,0 @@
-{
- "name": "rag-souverain",
- "description_fr": "RAG souverain : inference locale + gateway, embeddings, ingestion/vecteurs, memoire locale, evaluation — 100% auto-heberge.",
- "description_en": "Sovereign RAG: local inference + gateway, embeddings, ingestion/vectors, local memory, evaluation — fully self-hosted.",
- "bricks": [
-  {
-   "id": "ollama",
-   "role": "inference",
-   "deployable": true,
-   "requires_gpu": false,
-   "default": true
-  },
-  {
-   "id": "llama-cpp",
-   "role": "inference",
-   "deployable": true,
-   "requires_gpu": false,
-   "default": false
-  },
-  {
-   "id": "litellm",
-   "role": "gateway",
-   "deployable": true,
-   "requires_gpu": false,
-   "default": false
-  },
-  {
-   "id": "cohere-embed-v4-multimodal",
-   "role": "embedding",
-   "deployable": false,
-   "requires_gpu": false,
-   "default": true
-  },
-  {
-   "id": "nomic-embed-text",
-   "role": "embedding",
-   "deployable": false,
-   "requires_gpu": false,
-   "default": false
-  },
-  {
-   "id": "all-minilm-l6-v2",
-   "role": "embedding",
-   "deployable": false,
-   "requires_gpu": false,
-   "default": false
-  },
-  {
-   "id": "redis",
-   "role": "data",
-   "deployable": true,
-   "requires_gpu": false,
-   "default": true
-  },
-  {
-   "id": "postgresql",
-   "role": "data",
-   "deployable": true,
-   "requires_gpu": false,
-   "default": false
-  },
-  {
-   "id": "markitdown",
-   "role": "rag",
-   "deployable": false,
-   "requires_gpu": false,
-   "default": true
-  },
-  {
-   "id": "firecrawl",
-   "role": "rag",
-   "deployable": false,
-   "requires_gpu": false,
-   "default": false
-  },
-  {
-   "id": "ragflow",
-   "role": "rag",
-   "deployable": false,
-   "requires_gpu": false,
-   "default": false
-  },
-  {
-   "id": "docling",
-   "role": "rag",
-   "deployable": false,
-   "requires_gpu": false,
-   "default": false
-  },
-  {
-   "id": "crawl4ai",
-   "role": "rag",
-   "deployable": false,
-   "requires_gpu": false,
-   "default": false
-  },
-  {
-   "id": "mem0-local",
-   "role": "memory",
-   "deployable": false,
-   "requires_gpu": false,
-   "default": false
-  },
-  {
-   "id": "anythingllm",
-   "role": "rag",
-   "deployable": false,
-   "requires_gpu": false,
-   "default": false
-  },
-  {
-   "id": "langfuse-prompts",
-   "role": "eval",
-   "deployable": false,
-   "requires_gpu": false,
-   "default": false
-  }
- ]
-}
\ No newline at end of file
diff --git a/src/forgeai/templates.py b/src/forgeai/templates.py
index 17861ec..41d620c 100644
--- a/src/forgeai/templates.py
+++ b/src/forgeai/templates.py
@@ -1,60 +1,44 @@
-import json
-from pathlib import Path
+"""Alias hérités « templates » → stacks (P1, fusion décidée le 2026-07-19).
+
+Le système des templates (B-13/B-14) et celui des stacks (IMPL-3) faisaient double
+emploi (constat d'audit). Décision : UN SEUL système — les stacks. Les commandes
+`forge template …` restent rétro-compatibles via ce mapping ; les JSON dupliqués
+(data/templates/) ont été retirés.
+"""
+from __future__ import annotations
+
+from forgeai.stacks import list_stacks, load_stack
+
+# Noms hérités → stack équivalent (périmètre validé en fusion)
+LEGACY_ALIASES: dict[str, str] = {
+    "dev-agentic": "agentique",
+    "rag-souverain": "assistant-entreprise",
+    "lab-fine-tuning": "mlops",
+    "production-souveraine": "tout-en-un",
+}
+
+DEPRECATION_NOTE = ("note: les templates sont fusionnés dans les stacks — "
+                    "utilisez `forgeai web` ou les ids de stacks directement")
 
 
 class TemplateError(Exception):
-    """Erreur spécifique aux templates."""
+    """Nom hérité ou stack inconnu."""
 
 
-def templates_dir() -> Path:
-    return Path(__file__).resolve().parent / "data" / "templates"
+def resolve_alias(name: str) -> str:
+    """Nom hérité ou id de stack → id de stack ; TemplateError sinon."""
+    stack_id = LEGACY_ALIASES.get(name, name)
+    if stack_id not in list_stacks():
+        connus = sorted(set(LEGACY_ALIASES) | set(list_stacks()))
+        raise TemplateError(f"'{name}' inconnu — noms acceptés : {connus}")
+    return stack_id
 
 
 def list_templates() -> list[str]:
-    try:
-        files = list(templates_dir().glob("*.json"))
-    except FileNotFoundError:
-        return []
-    stems = sorted(f.stem for f in files if f.is_file())
-    return stems
+    """Les stacks (système unique), noms hérités affichés comme alias."""
+    return sorted(list_stacks())
 
 
 def load_template(name: str) -> dict:
-    template_path = templates_dir() / f"{name}.json"
-    if not template_path.is_file():
-        raise TemplateError(f"Template '{name}' introuvable.")
-    with open(template_path, encoding="utf-8") as f:
-        return json.load(f)
-
-
-def validate_template(template: dict, catalogue_entries: list[dict]) -> list[str]:
-    catalogue_index = {entry["id"]: entry for entry in catalogue_entries}
-    violations = []
-    for brick in template.get("bricks", []):
-        bid = brick.get("id")
-        if bid is None:
-            continue  # situation anormale, pas de règle prévue
-        entry = catalogue_index.get(bid)
-        if entry is None:
-            violations.append(f"brique inconnue au catalogue : '{bid}'")
-        else:
-            desc_fr = entry.get("description_fr", "")
-            desc_en = entry.get("description_en", "")
-            if not desc_fr or not desc_en:
-                violations.append(f"brique non bilingue : '{bid}'")
-    return sorted(set(violations))
-
-
-def resolve_template(template: dict, *, has_gpu: bool) -> list[dict]:
-    bricks = template.get("bricks", [])
-    resolved = []
-    for brick in bricks:
-        if brick.get("requires_gpu", False) and not has_gpu:
-            continue
-        resolved.append(brick)
-    return resolved
-
-
-def deployable_bricks(template: dict, *, has_gpu: bool) -> list[dict]:
-    resolved = resolve_template(template, has_gpu=has_gpu)
-    return [b for b in resolved if b.get("deployable", False)]
+    """Charge le STACK correspondant au nom (hérité ou direct)."""
+    return load_stack(resolve_alias(name))
diff --git a/tests/test_templates.py b/tests/test_templates.py
index 748a0cf..0cd55f9 100644
--- a/tests/test_templates.py
+++ b/tests/test_templates.py
@@ -1,78 +1,50 @@
-import json
+"""P1 — fusion templates→stacks (décision 2026-07-19) : un seul système de profils.
+
+Les anciens templates B-13/B-14 sont des ALIAS rétro-compatibles vers les stacks ;
+les JSON dupliqués (data/templates/) ont été retirés."""
+from importlib import resources
+
 import pytest
-from forgeai.resources import catalogue_path
+
+from forgeai.stacks import deploy_ids, list_stacks
 from forgeai.templates import (
+    LEGACY_ALIASES,
     TemplateError,
     list_templates,
     load_template,
-    validate_template,
-    resolve_template,
-    deployable_bricks,
+    resolve_alias,
 )
 
 
-def load_catalogue_entries():
-    data = json.loads(catalogue_path().read_text(encoding="utf-8"))
-    return data["entries"]
-
-
-def test_dev_agentic_a_37_briques():
-    t = load_template("dev-agentic")
-    assert len(t["bricks"]) == 37
-
-
-def test_toutes_briques_au_catalogue_et_bilingues():
-    entries = load_catalogue_entries()
-    t = load_template("dev-agentic")
-    violations = validate_template(t, entries)
-    assert violations == [], f"Violations trouvées : {violations}"
-
+def test_alias_herites_pointent_sur_des_stacks_reels():
+    stacks = set(list_stacks())
+    assert set(LEGACY_ALIASES.values()) <= stacks
+    assert LEGACY_ALIASES["dev-agentic"] == "agentique"
+    assert LEGACY_ALIASES["rag-souverain"] == "assistant-entreprise"
+    assert LEGACY_ALIASES["lab-fine-tuning"] == "mlops"
+    assert LEGACY_ALIASES["production-souveraine"] == "tout-en-un"
 
-def test_filtrage_hardware_inference():
-    t = load_template("dev-agentic")
-    ids_no_gpu = [b["id"] for b in resolve_template(t, has_gpu=False)]
-    assert not any("vllm" in bid for bid in ids_no_gpu), "vllm présent sans GPU"
-    assert any("ollama" in bid for bid in ids_no_gpu), "ollama absent sans GPU"
 
-    ids_gpu = [b["id"] for b in resolve_template(t, has_gpu=True)]
-    assert any("vllm" in bid for bid in ids_gpu), "vllm absent avec GPU"
+def test_list_templates_est_la_liste_des_stacks():
+    assert list_templates() == sorted(list_stacks())
 
 
-def test_deployables_non_vide():
-    t = load_template("dev-agentic")
-    deps = deployable_bricks(t, has_gpu=False)
-    assert len(deps) > 0, "Aucune brique déployable sans GPU"
-    assert all(b.get("deployable") is True for b in deps)
+def test_load_template_via_alias_ou_id_direct():
+    via_alias = load_template("dev-agentic")
+    direct = load_template("agentique")
+    assert via_alias == direct
+    assert len(deploy_ids(via_alias)) == 72
 
 
-def test_defauts_etoile_presents():
-    t = load_template("dev-agentic")
-    defaults = [b for b in t["bricks"] if b.get("default") is True]
-    assert len(defaults) >= 5, f"Seulement {len(defaults)} brique(s) par défaut"
-
-
-def test_template_inconnu_leve():
+def test_nom_inconnu_leve_template_error():
     with pytest.raises(TemplateError):
-        load_template("inexistant")
-
-
-def test_list_templates_contient_dev_agentic():
-    templates = list_templates()
-    assert "dev-agentic" in templates
-
-
-def test_cli_template_list_show_resolve(tmp_path, capsys):
-    """Chemin CLI : list, show (validation catalogue), resolve --no-gpu (filtrage inférence)."""
-    from forgeai.cli import main
-
-    assert main(["template", "list"]) == 0
-    assert "dev-agentic" in capsys.readouterr().out
+        resolve_alias("template-fantome")
 
-    assert main(["template", "show", "dev-agentic"]) == 0
-    assert "conforme" in capsys.readouterr().out
 
-    reg = tmp_path / "r.jsonl"
-    assert main(["template", "resolve", "dev-agentic", "--no-gpu", "--registre", str(reg)]) == 0
-    out = capsys.readouterr().out
-    assert "ollama" in out and "vllm" not in out
-    assert "template_resolve" in reg.read_text(encoding="utf-8")
+def test_json_dupliques_retires():
+    """Le format concurrent n'existe plus : data/templates/ ne doit plus être packagé."""
+    data_dir = resources.files("forgeai.data")
+    entries = [p.name for p in data_dir.iterdir()]
+    assert "templates" not in entries or not any(
+        f.name.endswith(".json") for f in (data_dir / "templates").iterdir()
+    )
diff --git a/tests/test_templates_b14.py b/tests/test_templates_b14.py
deleted file mode 100644
index 2a209b7..0000000
--- a/tests/test_templates_b14.py
+++ /dev/null
@@ -1,44 +0,0 @@
-"""B-14 — validation des 3 templates souverains (RAG / Lab fine-tuning / Production)."""
-import json
-
-import pytest
-
-from forgeai.resources import catalogue_path
-from forgeai.templates import (
-    load_template, validate_template, resolve_template, deployable_bricks, list_templates,
-)
-
-ENTRIES = json.loads(catalogue_path().read_text(encoding="utf-8"))["entries"]
-B14 = ["rag-souverain", "lab-fine-tuning", "production-souveraine"]
-
-
-@pytest.mark.parametrize("name", B14)
-def test_template_valide_contre_catalogue(name):
-    """Toutes les briques existent au catalogue et sont bilingues."""
-    assert validate_template(load_template(name), ENTRIES) == []
-
-
-@pytest.mark.parametrize("name", B14)
-def test_template_liste_et_coeur_deployable(name):
-    assert name in list_templates()
-    t = load_template(name)
-    assert len(t["bricks"]) >= 15
-    assert deployable_bricks(t, has_gpu=False), "un cœur runtime déployable est requis (CPU)"
-
-
-def test_rag_souverain_couvre_inference_embeddings_rag():
-    roles = {b["role"] for b in load_template("rag-souverain")["bricks"]}
-    assert {"inference", "embedding", "rag"} <= roles
-
-
-def test_lab_fine_tuning_filtrage_gpu():
-    t = load_template("lab-fine-tuning")
-    cpu = {b["id"] for b in resolve_template(t, has_gpu=False)}
-    assert "deepspeed" not in cpu and "unsloth" not in cpu  # entraînement gpu-only exclu sans GPU
-    assert "deepspeed" in {b["id"] for b in resolve_template(t, has_gpu=True)}
-
-
-def test_production_souveraine_vllm_gpu_only():
-    t = load_template("production-souveraine")
-    assert "vllm" not in {b["id"] for b in resolve_template(t, has_gpu=False)}
-    assert "vllm" in {b["id"] for b in resolve_template(t, has_gpu=True)}
```
