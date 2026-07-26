# PACK DE REVUE — K8S-008 (FAI-U-008) : suppression de privileged:true pour les GPU AMD/Intel
## Défaut : _security_block renvoyait 'privileged: true' pour amd/intel EN LIEU ET PLACE du bloc durci.
## Or l'accès aux devices passe DÉJÀ par les montages hostPath (/dev/kfd, /dev/dri) émis plus bas :
## privileged était un SUR-PRIVILÈGE (CIS 5.2.1). Fix : durcissement uniforme + refus des vendors inconnus
## + limitation vendor visible dans le manifeste.
## POINT D'ATTENTION : ce PR met à jour tests/test_k3s_hardening_fai0004.py, qui assertait l'ANTI-comportement
## ('privileged: true' in out). C'était l'attente du finding FAI-0004, SUPERSÉDÉE par FAI-U-008. Le package
## avait été mis en STOP contractuel (hors périmètre) ; l'élargissement a été accordé explicitement par le cockpit.
## Preuve : 3 tests RED -> verts ; suite COMPLÈTE verte ; NVIDIA inchangé (device-plugin, aucun hostPath).

```diff
diff --git a/src/forgeai/renderers/k3s.py b/src/forgeai/renderers/k3s.py
index b35ece0..e02862f 100644
--- a/src/forgeai/renderers/k3s.py
+++ b/src/forgeai/renderers/k3s.py
@@ -82,16 +82,16 @@ def _resources_block(vendor: str | None) -> str:
 
 
 def _security_block(vendor: str | None) -> str:
-    """Durcissement du securityContext. Les conteneurs GPU amd/intel nécessitent privileged
-    pour le passthrough de devices et sont exclus du durcissement standard.
+    """Durcissement du securityContext pour tous les conteneurs. Le passthrough hostPath des
+    devices GPU amd/intel suffit pour l'accès aux devices (/dev/kfd, /dev/dri) ; privileged
+    n'est pas requis et violerait le principe du moindre privilège.
     runAsNonRoot ET capabilities.drop:[ALL] ne sont PAS émis : de nombreuses images tournent en
     root et ont besoin de capabilities (ex. redis chown /data) ; les forcer ferait échouer les
     pods — PREUVE RUNTIME (K3s réel) : redis:7-alpine avec drop:[ALL] -> CrashLoopBackOff
     « chown: Operation not permitted ». Un runAsUser spécifique par image est hors périmètre.
     Durcissement retenu (vérifié : redis atteint Ready) = allowPrivilegeEscalation:false +
     seccompProfile RuntimeDefault."""
-    if vendor in ("amd", "intel"):
-        return "\n          securityContext:\n            privileged: true"
+    _ = vendor  # gardé pour la stabilité de l'API interne ; le durcissement est uniforme.
     block = (
         "\n          securityContext:"
         "\n            allowPrivilegeEscalation: false"
@@ -174,9 +174,17 @@ def _deployment(svc: ServiceSpec, effective_node: str | None = None,
                 config_files: dict[str, str] | None = None) -> str:
     name = _safe(svc.name, "name")
     image = _safe(svc.image, "image")
+
+    # Vérification explicite du vendor GPU avant tout rendu du bloc GPU.
+    if svc.gpu and svc.gpu_vendor is not None and svc.gpu_vendor not in {"nvidia", "amd", "intel"}:
+        raise ValueError(
+            f"vendor GPU non supporté : {svc.gpu_vendor} — combinaison refusée "
+            f"(nvidia/amd/intel uniquement)"
+        )
     # GPU par vendor (S3) : nvidia -> ressource device-plugin ; amd/intel -> passthrough hostPath
-    # des devices noyau + privileged (marche sur un nœud NU, sans device-plugin installé).
+    # des devices noyau (pas de privileged, K8S-008).
     vendor = (svc.gpu_vendor or "nvidia") if svc.gpu else None
+
     resources_block = _resources_block(vendor)
     security_block = _security_block(vendor)
     probes_block = _probes_block(svc)
@@ -272,12 +280,24 @@ def _deployment(svc: ServiceSpec, effective_node: str | None = None,
     volume_def = ""
     if vols:
         items = ""
+        passthrough_comment_emitted = False
         for claim, payload, kind in vols:
             if kind == "pvc":
                 items += (f"\n        - name: {claim}"
                           f"\n          persistentVolumeClaim:"
                           f"\n            claimName: {claim}")
             elif kind == "hostPath":
+                if vendor in ("amd", "intel") and not passthrough_comment_emitted:
+                    if vendor == "amd":
+                        devices = "/dev/kfd,/dev/dri"
+                    else:
+                        devices = "/dev/dri"
+                    items += (
+                        f"\n        # forgeai: GPU {vendor} en passthrough hostPath "
+                        f"({devices}) — nécessite ces devices sur le nœud ; "
+                        f"pas de device-plugin (limitation vendor)."
+                    )
+                    passthrough_comment_emitted = True
                 items += (f"\n        - name: {claim}"
                           f"\n          hostPath:\n            path: {payload}")
             elif kind == "configMap":
diff --git a/tests/test_k3s_gpu_vendor.py b/tests/test_k3s_gpu_vendor.py
index 05e733e..f4d996a 100644
--- a/tests/test_k3s_gpu_vendor.py
+++ b/tests/test_k3s_gpu_vendor.py
@@ -32,11 +32,28 @@ def test_k3s_nvidia_garde_resource():
     assert "/dev/kfd" not in out
 
 
-def test_k3s_amd_passthrough_kfd_dri_privileged():
+def test_k3s_amd_passthrough_kfd_dri_sans_privileged():
+    # K8S-008 (FAI-U-008) : le passthrough AMD reste (hostPath /dev/kfd + /dev/dri) mais SANS
+    # privileged:true — securityContext durci (allowPrivilegeEscalation:false) + limitation visible.
     out = render_k3s(_plan(_gpu("amd")))
     assert "/dev/kfd" in out and "/dev/dri" in out
-    assert "privileged: true" in out
-    assert "nvidia.com/gpu" not in out
+    assert "privileged: true" not in out
+    assert "allowPrivilegeEscalation: false" in out
+    assert "passthrough hostPath" in out  # limitation vendor visible dans le plan
+
+
+def test_k3s_intel_sans_privileged():
+    out = render_k3s(_plan(_gpu("intel")))
+    assert "/dev/dri" in out and "/dev/kfd" not in out
+    assert "privileged: true" not in out
+    assert "allowPrivilegeEscalation: false" in out
+
+
+def test_k3s_gpu_vendor_inconnu_refuse():
+    # combinaison non supportée : un vendor GPU inconnu est refusé au rendu (pas de privileged muet).
+    import pytest
+    with pytest.raises((ValueError, KeyError)):
+        render_k3s(_plan(_gpu("exotic-vendor")))
 
 
 def test_k3s_intel_passthrough_dri():
diff --git a/tests/test_k3s_hardening_fai0004.py b/tests/test_k3s_hardening_fai0004.py
index bc68977..36a922c 100644
--- a/tests/test_k3s_hardening_fai0004.py
+++ b/tests/test_k3s_hardening_fai0004.py
@@ -123,9 +123,12 @@ def test_gpu_amd_passthrough_pas_de_hardening():
         gpu_vendor="amd",
     )
     out = render_k3s(_plan(amd))
-    assert "privileged: true" in out
+    # K8S-008 (FAI-U-008) SUPERSÈDE l'attente d'origine de FAI-0004 : le passthrough AMD reste
+    # (hostPath /dev/kfd + /dev/dri) mais SANS privileged:true — l'accès aux devices suffit et
+    # privileged était un sur-privilège (CIS 5.2.1). Le securityContext durci s'applique désormais
+    # aussi aux GPU amd/intel. Périmètre élargi accordé par le cockpit pour lever cette contradiction.
+    assert "privileged: true" not in out
     assert "/dev/kfd" in out
     assert "/dev/dri" in out
-    assert "drop:" not in out
-    assert "allowPrivilegeEscalation: false" not in out
+    assert "allowPrivilegeEscalation: false" in out
     assert "nvidia.com/gpu" not in out
```
