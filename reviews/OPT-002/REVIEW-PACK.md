# PACK DE REVUE (v2) — OPT-002 : borner les sondes du chemin web
## v1 : APPROVE 2/3 ; Qwen a relevé (mineure) que la 3e sonde (cluster_status dans _summary_payload)
## n'avait PAS de test dédié. OBJECTION JUSTE -> test ajouté, avec PREUVE BIDIRECTIONNELLE :
## sans la borne le test ÉCHOUE, avec la borne il PASSE. Les 3 sondes sont désormais couvertes.
## Défaut : SubprocessRunner borne à 20 s/commande (OK en déploiement) mais s'appliquait aux sondes de
## LECTURE d'une requête HTTP -> 1er appel /api/summary hors budget -> échec CI systématique (3 PR bloquées).
## Fix : _PROBE_TIMEOUT_S=3.0 sur les 3 sondes de lecture ; les 5 runners de déploiement gardent 20 s.
## Preuve : 'sleep 30' coupé à 3.0 s. Suite COMPLÈTE verte. Diff minimal.

```diff
diff --git a/src/forgeai/web/server.py b/src/forgeai/web/server.py
index e26b6f7..a976c85 100644
--- a/src/forgeai/web/server.py
+++ b/src/forgeai/web/server.py
@@ -72,6 +72,7 @@ def _asset_bytes(name: str) -> bytes | None:
 # Mesuré : /api/summary 940→1583 ms (dont _available_backends 801 ms) vs 1 ms /api/stacks ;
 # saturation ~8 clients (p99>1 s à 16). Un seul cache TTL thread-safe, invalidation explicite.
 _HARDWARE_TTL_S = 60.0  # matériel stable ; TTL borné pour hotplug/driver
+_PROBE_TIMEOUT_S = 3.0  # OPT-002 : sondes du chemin HTTP bornées court (20 s reste pour le déploiement)
 
 _hardware_profile_cache = None
 _hardware_profile_cache_time: float = 0.0
@@ -109,7 +110,7 @@ def _hardware_report():
             and now - _hardware_profile_cache_time < _HARDWARE_TTL_S
         ):
             return _hardware_profile_cache
-        report = HardwareDetector(SubprocessRunner()).full_report()
+        report = HardwareDetector(SubprocessRunner(timeout_s=_PROBE_TIMEOUT_S)).full_report()
         _hardware_profile_cache = report
         _hardware_profile_cache_time = now
         return report
@@ -144,7 +145,7 @@ def _available_backends() -> list[str]:
         # `run_checks` attend un DÉTECTEUR (il appelle .full_report()) : on lui passe un adaptateur
         # qui sert le rapport DÉJÀ mémoïsé — évite la 3e sonde matérielle redondante.
         backends = available_backends(
-            run_checks(SubprocessRunner(), _CachedDetector(), http_ok)
+            run_checks(SubprocessRunner(timeout_s=_PROBE_TIMEOUT_S), _CachedDetector(), http_ok)
         )
         _backends_cache = backends
         _backends_cache_time = now
@@ -398,7 +399,7 @@ def _summary_payload(stack_id: str) -> dict:
     profile = _hardware_report()  # OPT-001 : mêmes sondes, mémoïsées
     nodes: list[str] = []
     try:
-        nodes = [n["name"] for n in cluster_status(SubprocessRunner())]
+        nodes = [n["name"] for n in cluster_status(SubprocessRunner(timeout_s=_PROBE_TIMEOUT_S))]
     except ClusterError:
         pass
     return {
diff --git a/tests/test_server_cache.py b/tests/test_server_cache.py
index 7ec56fa..9953b02 100644
--- a/tests/test_server_cache.py
+++ b/tests/test_server_cache.py
@@ -166,3 +166,68 @@ def test_backends_et_hardware_sans_interblocage(monkeypatch):
     t = _th.Thread(target=_appel, daemon=True)
     t.start()
     assert fini.wait(timeout=10), "INTERBLOCAGE : _available_backends bloqué sur le verrou du cache"
+
+
+# ── OPT-002 — les sondes du CHEMIN WEB doivent être BORNÉES court ─────────────
+# `SubprocessRunner` a un timeout par défaut de 20 s/commande (core/runner.py). Le PREMIER appel
+# (non caché) de /api/summary enchaîne lscpu, lspci, nvidia-smi, df, docker, kubectl : une seule
+# sonde lente dépasse le budget d'une requête HTTP (test client à 10 s) -> échec CI systématique.
+# Spécification : les sondes déclenchées par une REQUÊTE HTTP utilisent un timeout court et borné.
+def test_sondes_du_chemin_web_ont_un_timeout_court():
+    """Constante dédiée, nettement inférieure au défaut 20 s du runner."""
+    from forgeai.core.runner import SubprocessRunner
+    assert hasattr(server, "_PROBE_TIMEOUT_S"), "aucune borne dédiée aux sondes du chemin web"
+    assert 0 < server._PROBE_TIMEOUT_S <= 5.0, server._PROBE_TIMEOUT_S
+    assert server._PROBE_TIMEOUT_S < SubprocessRunner().timeout_s
+
+
+def test_hardware_report_utilise_un_runner_borne(monkeypatch):
+    """La détection matérielle du serveur borne son runner (pas le défaut 20 s)."""
+    server._hardware_cache_clear()
+    vus = {}
+
+    class _FauxDetecteur:
+        def __init__(self, runner, *a, **k):
+            vus["timeout"] = getattr(runner, "timeout_s", None)
+
+        def full_report(self):
+            class _P:
+                def to_json(self_inner):
+                    return "{}"
+            return _P()
+
+    monkeypatch.setattr(server, "HardwareDetector", _FauxDetecteur)
+    server._hardware_report()
+    assert vus["timeout"] == server._PROBE_TIMEOUT_S, vus
+
+
+def test_available_backends_utilise_un_runner_borne(monkeypatch):
+    """Les sondes docker/k3s du serveur bornent aussi leur runner."""
+    server._hardware_cache_clear()
+    vus = {}
+
+    def _faux_run_checks(runner, detector, http_ok):
+        vus["timeout"] = getattr(runner, "timeout_s", None)
+        return {}
+
+    monkeypatch.setattr(server, "run_checks", _faux_run_checks)
+    monkeypatch.setattr(server, "available_backends", lambda checks: ["compose"])
+    server._available_backends()
+    assert vus["timeout"] == server._PROBE_TIMEOUT_S, vus
+
+
+def test_cluster_status_utilise_un_runner_borne(monkeypatch):
+    """3e sonde du chemin web (relevé en revue : elle n'était pas testée) — cluster_status
+    doit aussi recevoir un runner borné, pas le défaut 20 s."""
+    server._hardware_cache_clear()
+    vus = {}
+
+    def _faux_cluster_status(runner):
+        vus["timeout"] = getattr(runner, "timeout_s", None)
+        return [{"name": "node-a"}]
+
+    monkeypatch.setattr(server, "cluster_status", _faux_cluster_status)
+    monkeypatch.setattr(server, "_hardware_report", lambda: type("P", (), {})())
+    monkeypatch.setattr(server, "_available_backends", lambda: ["compose"])
+    server._summary_payload("agentique")
+    assert vus["timeout"] == server._PROBE_TIMEOUT_S, vus
```
