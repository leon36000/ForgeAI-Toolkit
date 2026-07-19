# P0.2b — delta post-scellage : elimination des 2 skips pytest (gate no-stub §8bis)
CI no-stub a bloque la PR #58 : 2 skips sans justification dans test_multinoeud.py (codeur crew). Correctif : (1) cible de noeud construite hostname_local+'-autre-noeud' — garantie distante sur toute machine, plus besoin de skip, assertion renforcee ; (2) skip 'aucun stack' -> assertion dure. 8/8 tests verts, scanner 158 fichiers OK.

## DIFF DELTA
```diff
commit 2ff165a152d0d598ee265a133ece96cafdd57846
Author: Forge GRS <216249790+leon36000@users.noreply.github.com>
Date:   Sun Jul 19 08:53:42 2026 -0400

    fix(tests): P0.2 — elimine les 2 skips pytest (gate no-stub CI)
    
    Cible de noeud construite garantie != hostname local (prouve le ciblage distant sur toute machine, sans skip) ; skip 'aucun stack' remplace par assertion dure (les 6 stacks embarques sont toujours servis). Le scan local tournait sur main par erreur — lecon : scanner la branche de la story.
    
    Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>

diff --git a/tests/test_multinoeud.py b/tests/test_multinoeud.py
index f8931d4..d48a10d 100644
--- a/tests/test_multinoeud.py
+++ b/tests/test_multinoeud.py
@@ -86,14 +86,15 @@ def test_wizard_node_auto_dry_run(tmp_path: Path) -> None:
 
 
 def test_wizard_node_cible_dry_run(tmp_path: Path) -> None:
-    if socket.gethostname().lower() == "worker-2":
-        pytest.skip("le hostname local est worker-2 ; impossible de prouver le ciblage distant")
-    res = _run_wizard("--node", "worker-2", workdir=tmp_path)
+    # Cible construite pour être GARANTIE différente du hostname local : le test
+    # prouve le ciblage distant sur n'importe quelle machine, sans skip.
+    cible = socket.gethostname().lower() + "-autre-noeud"
+    res = _run_wizard("--node", cible, workdir=tmp_path)
     assert res.returncode == 0, res.stderr
     k3s_yaml = tmp_path / "run" / "k3s.yaml"
     assert k3s_yaml.exists()
     text = k3s_yaml.read_text(encoding="utf-8")
-    assert "kubernetes.io/hostname: worker-2" in text
+    assert f"kubernetes.io/hostname: {cible}" in text
 
 
 def test_wizard_node_invalide(tmp_path: Path) -> None:
@@ -212,8 +213,7 @@ def test_web_deploy_node_invalide(live_server) -> None:
 def test_summary_nodes(live_server) -> None:
     # Choisit un stack réellement présent pour éviter un 404.
     code, stacks = _get_json(live_server, "/api/stacks")
-    if code != 200 or not stacks:
-        pytest.skip("aucun stack disponible pour tester /api/summary")
+    assert code == 200 and stacks, "les 6 stacks embarqués doivent toujours être servis"
     stack_id = stacks[0]["id"]
     code, payload = _get_json(live_server, f"/api/summary?stack={stack_id}")
     assert code == 200
```
