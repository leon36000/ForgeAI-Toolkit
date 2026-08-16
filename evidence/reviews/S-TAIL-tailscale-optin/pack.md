# Story S-TAIL — enrôlement mesh opt-in au add-node : Tailscale SaaS + Headscale souverain

## Contexte / décisions Nathan (2026-07-21)
Réponse à la question « faut-il déployer Tailscale à la connexion SSH ? » : OUI mais OPT-IN.
Décisions : opt-in DÉFAUT-ACTIVÉ en multi-nœud ; les DEUX voies (Tailscale SaaS + Headscale souverain).
SÉCURITÉ (préserve EX-1/2/3 de la revue multi-nœuds) : auth key TOUJOURS une référence env
(${TAILSCALE_AUTHKEY}), JAMAIS en clair/argv/log. Vocation universelle : Headscale = zéro dépendance SaaS.

## Changements (network/bootstrap.py — étend la JoinPlan P2-F21 existante)
- JoinPlan.login_server (Headscale) : si défini, tailscale_up_argv ajoute `--login-server <url>`
  (control plane self-hosted souverain) ; None => SaaS Tailscale. authkey reste une référence env.
- render_join_plan(login_server=...) valide l'URL http(s):// (sinon BootstrapError).
- should_enroll_default(node_count) : True dès 2 nœuds (opt-in coché par défaut), False en mono-nœud.

## Critères (tous testés — tests/test_tailscale_optin.py)
1. SaaS : argv = tailscale up ... ${TAILSCALE_AUTHKEY} ..., PAS de --login-server.
2. Headscale : argv contient --login-server <url> ; authkey toujours une référence.
3. authkey jamais en clair (pas de 'tskey-' dans l'argv) ; authkey_env == TAILSCALE_AUTHKEY.
4. opt-in défaut : node_count 1 -> False, 2 -> True, 5 -> True.
5. login_server non-URL -> BootstrapError.

## Périmètre / preuve
Story = capacité de PLAN d'enrôlement (déterministe, prouvée par tests). L'enrôlement RÉEL
(tailscale up avec un vrai authkey) est exécuté par Nathan avec SA clé (T3 : secret prod) — la
toolkit ne matérialise jamais la clé. Câblage UI/CLI interactif du choix = surface (S6). Codeur : orchestrateur.
## Diff intégral (origin/main..HEAD)
```diff
diff --git a/src/forgeai/network/bootstrap.py b/src/forgeai/network/bootstrap.py
index 6395e5b..9293644 100644
--- a/src/forgeai/network/bootstrap.py
+++ b/src/forgeai/network/bootstrap.py
@@ -23,6 +23,7 @@ class JoinPlan:
     node_hostkey_sha256: str      # EX-1 : empreinte connue à l'avance (pas de TOFU)
     tailscale_tag: str            # EX-2 : tag ACL (ex. "tag:forgeai-node")
     authkey_env: str = "TAILSCALE_AUTHKEY"  # EX-2 : référence, jamais la valeur
+    login_server: str | None = None  # Headscale souverain (self-hosted) ; None = SaaS Tailscale
 
     def ssh_options(self) -> list[str]:
         return [
@@ -32,12 +33,15 @@ class JoinPlan:
         ]
 
     def tailscale_up_argv(self) -> list[str]:
-        return [
-            "tailscale", "up",
-            "--auth-key", f"${{{self.authkey_env}}}",  # EX-2 : substitué à l'exécution
+        argv = ["tailscale", "up"]
+        if self.login_server:  # Headscale : pointe le control plane souverain au lieu du SaaS
+            argv += ["--login-server", self.login_server]
+        argv += [
+            "--auth-key", f"${{{self.authkey_env}}}",  # EX-2 : référence env, jamais la valeur
             "--advertise-tags", self.tailscale_tag,
             "--ssh=false",
         ]
+        return argv
 
     def acl_deny_all_default(self) -> dict:
         """EX-3 : politique deny-all, seul le contrôleur atteint le nœud."""
@@ -52,15 +56,28 @@ class JoinPlan:
 
 
 def render_join_plan(controller_host: str, node_host: str, node_hostkey_sha256: str,
-                     tailscale_tag: str = "tag:forgeai-node") -> JoinPlan:
+                     tailscale_tag: str = "tag:forgeai-node",
+                     login_server: str | None = None) -> JoinPlan:
     if not node_hostkey_sha256 or ":" not in node_hostkey_sha256:
         raise BootstrapError(
             "empreinte de clé d'hôte requise (EX-1 : pas de TOFU) — format 'SHA256:...'")
     if not tailscale_tag.startswith("tag:"):
         raise BootstrapError("le tag Tailscale doit commencer par 'tag:' (EX-3)")
+    # Headscale souverain : le control plane doit être une URL http(s):// (EX-2, jamais un secret).
+    if login_server is not None and not login_server.startswith(("http://", "https://")):
+        raise BootstrapError(
+            "login-server Headscale invalide : URL http(s):// attendue (ex. https://headscale.local)")
     return JoinPlan(
         controller_host=controller_host,
         node_host=node_host,
         node_hostkey_sha256=node_hostkey_sha256,
         tailscale_tag=tailscale_tag,
+        login_server=login_server,
     )
+
+
+def should_enroll_default(node_count: int) -> bool:
+    """Opt-in DÉFAUT-ACTIVÉ en multi-nœud (décision Nathan 2026-07-21) : dès le 2e nœud, le mesh
+    devient utile → enrôlement proposé COCHÉ par défaut. Mono-nœud (< 2) → OFF (le LAN/SSH suffit).
+    Toujours surchargeable par l'utilisateur."""
+    return node_count >= 2
diff --git a/tests/test_tailscale_optin.py b/tests/test_tailscale_optin.py
new file mode 100644
index 0000000..f2e8520
--- /dev/null
+++ b/tests/test_tailscale_optin.py
@@ -0,0 +1,50 @@
+"""Story S-TAIL — enrôlement mesh opt-in au add-node : Tailscale SaaS + Headscale souverain.
+
+Décisions Nathan (2026-07-21) : opt-in DÉFAUT-ACTIVÉ en multi-nœud ; les DEUX voies (Tailscale
+SaaS + Headscale self-hosted souverain) ; l'auth key est TOUJOURS une référence env, JAMAIS en
+clair/argv (préserve EX-2 de la revue sécurité multi-nœuds).
+"""
+import sys
+from pathlib import Path
+
+import pytest
+
+sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
+
+from forgeai.network.bootstrap import BootstrapError, render_join_plan, should_enroll_default
+
+
+def test_tailscale_saas_argv():
+    p = render_join_plan("ctrl", "node1", "SHA256:abc")
+    argv = p.tailscale_up_argv()
+    assert argv[:2] == ["tailscale", "up"]
+    assert "--advertise-tags" in argv
+    assert "${TAILSCALE_AUTHKEY}" in " ".join(argv)  # référence env, jamais la valeur
+    assert "--login-server" not in argv  # SaaS => pas de control plane self-hosted
+
+
+def test_headscale_souverain_argv():
+    p = render_join_plan("ctrl", "node1", "SHA256:abc", login_server="https://headscale.local")
+    argv = p.tailscale_up_argv()
+    assert "--login-server" in argv
+    assert argv[argv.index("--login-server") + 1] == "https://headscale.local"
+    assert "${TAILSCALE_AUTHKEY}" in " ".join(argv)  # authkey toujours une référence
+
+
+def test_authkey_jamais_en_clair():
+    p = render_join_plan("ctrl", "node1", "SHA256:abc")
+    joined = " ".join(p.tailscale_up_argv())
+    assert "tskey-" not in joined  # aucune vraie clé Tailscale matérialisée
+    assert p.authkey_env == "TAILSCALE_AUTHKEY"
+
+
+def test_optin_defaut_active_en_multinoeud():
+    # opt-in défaut-activé DÈS le 2e nœud (le mesh devient utile) ; off en mono-nœud.
+    assert should_enroll_default(node_count=1) is False
+    assert should_enroll_default(node_count=2) is True
+    assert should_enroll_default(node_count=5) is True
+
+
+def test_login_server_invalide_leve():
+    with pytest.raises(BootstrapError):
+        render_join_plan("ctrl", "node1", "SHA256:abc", login_server="pas-une-url")
```
## Preuve déterministe
```
......................                                                   [100%]
....................................................................s... [ 90%]
.............................................................            [100%]
All checks passed!
```
