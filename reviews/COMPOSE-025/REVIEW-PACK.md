# PACK DE REVUE — COMPOSE-025 (FAI-U-025) — durcissement Compose no-new-privileges
## Contexte : renderer compose.py n'émettait aucun durcissement conteneur (asymétrie vs k3s _security_block).
## Changement : security_opt:[no-new-privileges:true] par service. cap_drop/read_only/user DIFFÉRÉS (preuve runtime par-service requise, pull hors-ligne bloqué), miroir de la borne déjà retenue par k3s.

## DIFF INTÉGRAL vs origin/main
```diff
diff --git a/src/forgeai/renderers/compose.py b/src/forgeai/renderers/compose.py
index d8c8f72..d389579 100644
--- a/src/forgeai/renderers/compose.py
+++ b/src/forgeai/renderers/compose.py
@@ -21,6 +21,12 @@ def _openbao_unsealer_block(image: str) -> list[str]:
         "  openbao-unsealer:",
         f"    image: {image}",  # même image openbao (binaire `bao` présent)
         "    restart: unless-stopped",
+        # Durcissement universel : empêche toute élévation de privilèges via setuid/sudo/cap.
+        # Équivalent Compose de allowPrivilegeEscalation:false du renderer k3s
+        # (voir renderers/k3s.py::_security_block). Consciemment limité à cette option car
+        # cap_drop:[ALL] / read_only / user cassent certaines images à état (prouvé runtime).
+        "    security_opt:",
+        "      - no-new-privileges:true",
         "    depends_on:",
         "      openbao:",
         "        condition: service_started",
@@ -57,6 +63,12 @@ def render_compose(plan: DeploymentPlan, project: str = "forgeai-minimal") -> st
             f"  {svc.name}:",
             f"    image: {svc.image}",
             "    restart: unless-stopped",
+            # Durcissement universel : empêche toute élévation de privilèges via setuid/sudo/cap.
+            # Équivalent Compose de allowPrivilegeEscalation:false du renderer k3s
+            # (voir renderers/k3s.py::_security_block). Consciemment limité à cette option car
+            # cap_drop:[ALL] / read_only / user cassent certaines images à état (prouvé runtime).
+            "    security_opt:",
+            "      - no-new-privileges:true",
             "    env_file: .env",
             "    ports:",
             f"      - \"127.0.0.1:{svc.host_port}:{svc.container_port}\"",
diff --git a/tests/test_renderers.py b/tests/test_renderers.py
index eaa3bbf..2802ef2 100644
--- a/tests/test_renderers.py
+++ b/tests/test_renderers.py
@@ -98,6 +98,28 @@ def test_compose_valide_par_docker_compose_config(tmp_path):
     assert proc.returncode == 0, proc.stderr
 
 
+# COMPOSE-025 (FAI-U-025) — durcissement conteneur par défaut.
+# `no-new-privileges` est l'analogue compose de `allowPrivilegeEscalation:false` de k3s
+# (renderers/k3s.py:_security_block) : universellement sûr (n'exige ni non-root, ni drop de
+# capabilities), donc appliqué à TOUS les services par défaut. Preuve d'absence = défaut FAI-U-025.
+def test_compose_durcissement_no_new_privileges_par_defaut():
+    out = render_compose(_plan())
+    # un bloc security_opt: no-new-privileges:true par service (2 services applicatifs)
+    assert out.count("no-new-privileges:true") >= 2, out
+    assert "security_opt:" in out
+
+
+def test_compose_no_new_privileges_couvre_chaque_service():
+    # Une directive no-new-privileges par service du plan (aucun openbao ici -> pas d'unsealer).
+    plan = _plan()
+    out = render_compose(plan)
+    assert "openbao" not in {s.name for s in plan.services}
+    # séquence RENDUE exacte : restart immédiatement suivi du bloc de durcissement, une fois/service
+    sequence = "    restart: unless-stopped\n    security_opt:\n      - no-new-privileges:true"
+    assert out.count(sequence) == len(plan.services), out
+    assert out.count("no-new-privileges:true") == len(plan.services)
+
+
 def test_chunking_regroupe_les_paragraphes():
     text = "\n\n".join(f"Paragraphe {i} " + "x" * 100 for i in range(10))
     chunks = chunk_text(text, max_chars=300)
```

## PREUVE ROUGE (avant patch)
```
        blocs = out.split("\n  ")  # segmentation grossière par service (indent 2)
        for svc in plan.services:
            seg = next((b for b in blocs if b.startswith(f"{svc.name}:")), None)
            assert seg is not None, f"service {svc.name} absent"
>           assert "no-new-privileges:true" in seg, f"{svc.name} sans no-new-privileges"
E           AssertionError: ollama sans no-new-privileges
E           assert 'no-new-privileges:true' in 'ollama:'

tests/test_renderers.py:119: AssertionError
=========================== short test summary info ============================
FAILED tests/test_renderers.py::test_compose_durcissement_no_new_privileges_par_defaut
FAILED tests/test_renderers.py::test_compose_no_new_privileges_couvre_chaque_service
```
## PREUVE VERTE (après patch, tests ciblés)
```
..................                                                       [100%]
```
## docker compose config exit 0 (extrait)
```
    security_opt:
      - no-new-privileges:true
    volumes:
```
## Rollback (baseline verte sans le changement)
```
................                                                         [100%]
```
## Suite complète : verte (0 régression). gitleaks : 0 fuite.
