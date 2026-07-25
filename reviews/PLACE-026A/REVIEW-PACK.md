# PACK DE REVUE — PLACE-026A (FAI-U-026) : câbler le placement par service
## Défaut : assemble_plan ne peuplait JAMAIS ServiceSpec.node (capacité morte) ; rag_node relocalisait TOUT le plan.
## Fix : params keyword-only placement/rag_node (défauts -> rétro-compatible), _RAG_SERVICES explicite,
## node= dans les 2 boucles de construction, plan.placement_reasons pour la traçabilité.
## Preuve : 3 tests RED -> 17/17 verts, suite complète verte, no-stub OK, gitleaks 0, rollback baseline vert.

```diff
diff --git a/src/forgeai/planner/assemble.py b/src/forgeai/planner/assemble.py
index ba38602..3c22390 100644
--- a/src/forgeai/planner/assemble.py
+++ b/src/forgeai/planner/assemble.py
@@ -6,6 +6,7 @@ de l'overlay curé, et fige le tout en DeploymentPlan sérialisable.
 """
 from __future__ import annotations
 
+import dataclasses
 import importlib.resources
 import json
 import socket
@@ -27,6 +28,16 @@ _PROFILE_VENDOR = {
     "minimal-gpu-intel": "intel",
 }
 
+# Services RAG connus : définition explicite du périmètre relocalisable par rag_node.
+_RAG_SERVICES = frozenset({
+    "vector-store",
+    "rag",
+    "rag-hardened",
+    "tei-embed",
+    "tei-rerank",
+    "embeddings",
+})
+
 
 def _profile_vendor(profile: str) -> str | None:
     """Vendor GPU d'un profil de déploiement (None hors profil GPU)."""
@@ -72,6 +83,27 @@ def _load_deploy_specs() -> dict[str, dict]:
     return {k: v for k, v in raw.items() if not k.startswith("_")}
 
 
+def _node_for(
+    name: str,
+    placement: dict[str, str] | None,
+    rag_node: str | None,
+) -> tuple[str | None, str | None]:
+    """Détermine le nœud cible d'un service et la raison du placement."""
+    if placement is not None and name in placement:
+        return placement[name], "placement explicite"
+    if rag_node is not None and name in _RAG_SERVICES:
+        return rag_node, "service RAG relocalisé via rag_node"
+    return None, None
+
+
+def _attach_placement_reasons(plan: DeploymentPlan, reasons: dict[str, str]) -> None:
+    """Attache le dict de traçabilité au plan, y compris quand il est vide."""
+    if dataclasses.is_dataclass(plan) and plan.__dataclass_params__.frozen:
+        object.__setattr__(plan, "placement_reasons", reasons)
+    else:
+        plan.placement_reasons = reasons  # type: ignore[attr-defined]
+
+
 def assemble_plan(
     profile: str,
     deploy_overlay: Path,
@@ -80,12 +112,19 @@ def assemble_plan(
     stack: dict | None = None,
     extra_bricks: tuple[str, ...] = (),
     is_free=port_is_free,
+    placement: dict[str, str] | None = None,
+    rag_node: str | None = None,
 ) -> DeploymentPlan:
     overlay = json.loads(deploy_overlay.read_text(encoding="utf-8"))
     services = []
+    placement_reasons: dict[str, str] = {}
+
     for svc in minimal_stack(deploy_overlay):
         host_port = find_free_port(svc["container_port"] + PREFERRED_PORT_OFFSET, is_free)
         svc_gpu = bool(svc.get("gpu_capable")) and profile in _GPU_PROFILES
+        node, reason = _node_for(svc["name"], placement, rag_node)
+        if node is not None:
+            placement_reasons[svc["name"]] = reason
         services.append(ServiceSpec(
             name=svc["name"],
             image=svc["image"],
@@ -98,6 +137,7 @@ def assemble_plan(
             ),
             gpu=svc_gpu,
             gpu_vendor=_profile_vendor(profile) if svc_gpu else None,
+            node=node,
         ))
 
     if stack is not None or extra_bricks:
@@ -128,6 +168,9 @@ def assemble_plan(
             # plan final (indépendant de l'ordre de traitement des briques).
             depends = tuple(d for d in spec.get("depends", []) if d in planned_names)
             brick_gpu = bool(spec.get("gpu", False))
+            node, reason = _node_for(brick_id, placement, rag_node)
+            if node is not None:
+                placement_reasons[brick_id] = reason
             services.append(ServiceSpec(
                 name=brick_id,
                 image=spec["image"],
@@ -140,10 +183,11 @@ def assemble_plan(
                 command=tuple(spec.get("command", [])),
                 gpu=brick_gpu,
                 gpu_vendor=_profile_vendor(profile) if brick_gpu else None,
+                node=node,
             ))
             existing_names.add(brick_id)
 
-    return DeploymentPlan(
+    plan = DeploymentPlan(
         plan_id=f"p1-{uuid.uuid4().hex[:8]}",
         profile=profile,
         target=target,
@@ -151,3 +195,5 @@ def assemble_plan(
         model=overlay["models"]["llm"],
         embed_model=overlay["models"]["embed"],
     )
+    _attach_placement_reasons(plan, placement_reasons)
+    return plan
diff --git a/tests/test_placement_noeud.py b/tests/test_placement_noeud.py
index 814f15b..3958d82 100644
--- a/tests/test_placement_noeud.py
+++ b/tests/test_placement_noeud.py
@@ -107,3 +107,43 @@ def test_choix_jamais_impose() -> None:
     for moteur in moteurs["moteurs"]:
         vendors.update(moteur["gpu_vendors"])
     assert {"nvidia", "amd", "cpu"} <= vendors
+
+
+# PLACE-026A (FAI-U-026) — l'intention de placement par service doit être CÂBLÉE dans assemble_plan.
+def _plan_minimal(**kw):
+    from importlib import resources
+    from pathlib import Path
+    from forgeai.planner.assemble import assemble_plan
+    overlay = Path(str(resources.files("forgeai.data") / "deploy-minimal.json"))
+    return assemble_plan("minimal-cpu", overlay, **kw)
+
+
+def test_placement_par_service_cable_depuis_decision_explicite():
+    """`placement` explicite {service: noeud} -> ServiceSpec.node peuplé pour CE service seulement."""
+    plan = _plan_minimal(placement={"vector-store": "node-rag"})
+    par_nom = {s.name: s for s in plan.services}
+    assert par_nom["vector-store"].node == "node-rag"
+    assert par_nom["ollama"].node is None  # non ciblé -> inchangé
+
+
+def test_rag_node_ne_deplace_que_les_services_rag():
+    """`rag_node` ne relocalise QUE les services RAG définis, jamais tout le plan (défaut FAI-U-026)."""
+    plan = _plan_minimal(rag_node="node-rag")
+    par_nom = {s.name: s for s in plan.services}
+    assert par_nom["vector-store"].node == "node-rag"   # service RAG -> déplacé
+    assert par_nom["ollama"].node is None               # NON-RAG -> jamais relocalisé silencieusement
+
+
+def test_plan_expose_la_raison_du_placement():
+    """Le plan expose la RAISON de chaque placement (traçabilité, critère d'acceptation)."""
+    plan = _plan_minimal(rag_node="node-rag")
+    raisons = getattr(plan, "placement_reasons", None)
+    assert raisons, "le plan n'expose aucune raison de placement"
+    assert "vector-store" in raisons and "rag" in str(raisons["vector-store"]).lower()
+
+
+def test_plan_sans_placement_reste_documente():
+    """Sans placement explicite : node=None partout, aucune raison inventée (rétro-compat)."""
+    plan = _plan_minimal()
+    assert all(s.node is None for s in plan.services)
+    assert not getattr(plan, "placement_reasons", {})
```
