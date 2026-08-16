# P0.1b — delta post-scellage : dry-run tolere une machine sous les minima
Contexte : P0-1-civ APPROVE 3/3 ; la CI GitHub (runner 2c/7GB) echouait en ProfileError exit 7 sur les tests e2e reels. Regle produit (permanente, Nathan) : universel — le dry-run valide l assemblage du plan, pas la machine courante (le plan peut viser un autre noeud).
Critere : hors dry-run, comportement inchange (abort 7). En dry-run : repli profil Minimal, message explicite.

## DIFF DELTA (seul commit apres scellage)
```diff
commit 3cd0f3c131a0797766130f3b53351033444aa787
Author: Forge GRS <216249790+leon36000@users.noreply.github.com>
Date:   Sun Jul 19 08:33:52 2026 -0400

    fix(wizard): dry-run tolere une machine sous les minima (repli profil Minimal)
    
    CI GitHub (2 coeurs/7GB) sortait en ProfileError exit 7 sur les tests e2e reels. Regle universelle : le dry-run valide l assemblage du plan, pas la machine courante — le plan peut viser un autre noeud du reseau. Hors dry-run, l abort 7 reste inchange.
    
    Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>

diff --git a/src/forgeai/cli.py b/src/forgeai/cli.py
index b0f1256..518e888 100644
--- a/src/forgeai/cli.py
+++ b/src/forgeai/cli.py
@@ -91,9 +91,16 @@ def wizard_ci(args: argparse.Namespace) -> int:
     try:
         profile = derive_profile(hw)
     except ProfileError as exc:
-        print(f"ABORT [{exc.code}] {exc}", file=sys.stderr)
-        return 7
-    print(f"  profil: {profile}")
+        if getattr(args, "dry_run", False):
+            # dry-run = valider l'assemblage/rendu du plan, pas la machine COURANTE :
+            # le plan peut viser un AUTRE nœud du réseau (exigence universelle).
+            profile = "Minimal"
+            print(f"  profil: Minimal (repli dry-run — machine courante sous les minima : {exc})")
+        else:
+            print(f"ABORT [{exc.code}] {exc}", file=sys.stderr)
+            return 7
+    else:
+        print(f"  profil: {profile}")
 
     _step(t("wizard.s03"))
     digest = verify_catalogue(Path(args.catalogue))
```

## PREUVE : suite complete locale verte (193) ; CI relancee sur le push.
