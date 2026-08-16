# PACK DE REVUE (v2) — OPT-001 : mémoïsation sondes matérielles/backends
## v1 : APPROVE 2/3 ; Gemini a signalé (majeure) que le test anti-interblocage était un FAUX POSITIF.
## OBJECTION CONFIRMÉE EXPÉRIMENTALEMENT (Lock réintroduit -> le test passait quand même) et CORRIGÉE :
## le faux run_checks appelle maintenant detector.full_report(), ce qui reprend réellement le verrou.
## PREUVE BIDIRECTIONNELLE : avec Lock -> le test ÉCHOUE par timeout ; avec RLock -> il PASSE.
## Reste inchangé : cache TTL 60s partagé (hardware+backends), _CachedDetector (run_checks attend un
## DÉTECTEUR), invalidation explicite, copie défensive. Mesure : _available_backends 330 ms -> 0.00 ms.
## Suite COMPLÈTE verte ; test_summary_nodes (qui bloquait la CI) vert 3/3 ; no-stub OK ; gitleaks 0.

```diff
diff --git a/src/forgeai/web/server.py b/src/forgeai/web/server.py
index 18400ec..e26b6f7 100644
--- a/src/forgeai/web/server.py
+++ b/src/forgeai/web/server.py
@@ -68,8 +68,87 @@ def _asset_bytes(name: str) -> bytes | None:
         return None
 
 
+# OPT-001 (OBS-A060-1) — sondes matérielles + backends relancées à CHAQUE requête.
+# Mesuré : /api/summary 940→1583 ms (dont _available_backends 801 ms) vs 1 ms /api/stacks ;
+# saturation ~8 clients (p99>1 s à 16). Un seul cache TTL thread-safe, invalidation explicite.
+_HARDWARE_TTL_S = 60.0  # matériel stable ; TTL borné pour hotplug/driver
+
+_hardware_profile_cache = None
+_hardware_profile_cache_time: float = 0.0
+
+_backends_cache: list[str] | None = None
+_backends_cache_time: float = 0.0
+
+# RLock (réentrant) : `_available_backends` appelle `_hardware_report()` en tenant déjà le verrou ;
+# un Lock simple provoquerait un INTERBLOCAGE (prouvé par test_backends_et_hardware_sans_interblocage).
+_hardware_lock = threading.RLock()
+
+
+def _hardware_cache_clear() -> None:
+    """Purge explicite du cache matériel et du cache backends."""
+    global _hardware_profile_cache, _hardware_profile_cache_time
+    global _backends_cache, _backends_cache_time
+    with _hardware_lock:
+        _hardware_profile_cache = None
+        _hardware_profile_cache_time = 0.0
+        _backends_cache = None
+        _backends_cache_time = 0.0
+
+
+def _hardware_report():
+    """HardwareProfile mémoïsé (TTL) — source unique des sondes matérielles."""
+    global _hardware_profile_cache, _hardware_profile_cache_time
+    now = time.monotonic()
+    cache = _hardware_profile_cache
+    if cache is not None and now - _hardware_profile_cache_time < _HARDWARE_TTL_S:
+        return cache
+    with _hardware_lock:
+        now = time.monotonic()
+        if (
+            _hardware_profile_cache is not None
+            and now - _hardware_profile_cache_time < _HARDWARE_TTL_S
+        ):
+            return _hardware_profile_cache
+        report = HardwareDetector(SubprocessRunner()).full_report()
+        _hardware_profile_cache = report
+        _hardware_profile_cache_time = now
+        return report
+
+
 def hardware_json() -> str:
-    return HardwareDetector(SubprocessRunner()).full_report().to_json()
+    """JSON mémoïsé de /api/detect."""
+    return _hardware_report().to_json()
+
+
+class _CachedDetector:
+    """Adaptateur : expose l'interface `full_report()` en servant le cache (aucune sonde)."""
+
+    def full_report(self):
+        return _hardware_report()
+
+
+def _available_backends() -> list[str]:
+    """Backends disponibles mémoïsés (TTL), avec copie défensive."""
+    global _backends_cache, _backends_cache_time
+    now = time.monotonic()
+    cache = _backends_cache
+    if cache is not None and now - _backends_cache_time < _HARDWARE_TTL_S:
+        return list(cache)
+    with _hardware_lock:
+        now = time.monotonic()
+        if (
+            _backends_cache is not None
+            and now - _backends_cache_time < _HARDWARE_TTL_S
+        ):
+            return list(_backends_cache)
+        # `run_checks` attend un DÉTECTEUR (il appelle .full_report()) : on lui passe un adaptateur
+        # qui sert le rapport DÉJÀ mémoïsé — évite la 3e sonde matérielle redondante.
+        backends = available_backends(
+            run_checks(SubprocessRunner(), _CachedDetector(), http_ok)
+        )
+        _backends_cache = backends
+        _backends_cache_time = now
+        return list(backends)
 
 
 @lru_cache(maxsize=1)  # parse mémoïsé (paquet immuable) — 1 seul parse/process (FAI-0014)
@@ -314,15 +393,9 @@ def _node_keys(runner: CommandRunner) -> tuple[Path, Path]:
     return public, private
 
 
-def _available_backends() -> list[str]:
-    return available_backends(
-        run_checks(SubprocessRunner(), HardwareDetector(SubprocessRunner()), http_ok)
-    )
-
-
 def _summary_payload(stack_id: str) -> dict:
     stack = load_stack(stack_id)
-    profile = HardwareDetector(SubprocessRunner()).full_report()
+    profile = _hardware_report()  # OPT-001 : mêmes sondes, mémoïsées
     nodes: list[str] = []
     try:
         nodes = [n["name"] for n in cluster_status(SubprocessRunner())]
diff --git a/tests/test_server_cache.py b/tests/test_server_cache.py
index dd918fa..7ec56fa 100644
--- a/tests/test_server_cache.py
+++ b/tests/test_server_cache.py
@@ -7,6 +7,16 @@ process, pas par requête). Preuve par identité : deux appels renvoient le MÊM
 RED avant correctif : chaque appel re-parse → objets distincts.
 """
 import forgeai.web.server as server
+import pytest
+
+
+@pytest.fixture(autouse=True)
+def _purge_cache_materiel():
+    """Le cache matériel est un état MODULE : le purger avant/après chaque test évite
+    qu'un faux détecteur monkeypatché fuite vers les autres tests (pollution)."""
+    server._hardware_cache_clear()
+    yield
+    server._hardware_cache_clear()
 
 
 def test_catalogue_entries_memoise():
@@ -33,3 +43,126 @@ def test_read_data_text_distingue_les_fichiers():
     a = server._read_data_text("moteurs-inference.json")
     b = server._read_data_text("modeles-locaux.json")
     assert a != b
+
+
+# ── OPT-001 (OBS-A060-1 / A061) — la DÉTECTION MATÉRIELLE est re-sondée à chaque requête ──
+# `hardware_json()` lance des SOUS-PROCESSUS (lscpu/lspci/nvidia-smi/df) à CHAQUE appel.
+# Mesuré sur machine rapide : /api/summary = 940→1583 ms (croissant), vs /api/stacks = 1 ms.
+# Sur runner CI chargé, le timeout client de 10 s est dépassé -> échecs CI systématiques.
+# Spécification : mémoïsation à TTL (le matériel ne change pas d'une requête à l'autre),
+# avec invalidation explicite possible. RED avant correctif : chaque appel re-sonde.
+import time as _time
+
+
+def test_hardware_json_memoise_avec_ttl(monkeypatch):
+    server._hardware_cache_clear()
+    appels = {"n": 0}
+
+    class _FauxProfil:
+        def to_json(self):
+            return '{"cpu_model":"faux"}'
+
+    class _FauxDetecteur:
+        def __init__(self, *a, **k):
+            appels["n"] += 1          # compte les SONDES réelles (construction+full_report)
+
+        def full_report(self):
+            return _FauxProfil()
+
+    monkeypatch.setattr(server, "HardwareDetector", _FauxDetecteur)
+    a = server.hardware_json()
+    b = server.hardware_json()
+    c = server.hardware_json()
+    assert a == b == c
+    assert appels["n"] == 1, f"détection relancée {appels['n']}x (aucun cache) — 1 attendu"
+
+
+def test_hardware_cache_expire_apres_ttl(monkeypatch):
+    server._hardware_cache_clear()
+    appels = {"n": 0}
+
+    class _FauxProfil:
+        def to_json(self):
+            return '{"cpu_model":"faux"}'
+
+    class _FauxDetecteur:
+        def __init__(self, *a, **k):
+            appels["n"] += 1
+
+        def full_report(self):
+            return _FauxProfil()
+
+    monkeypatch.setattr(server, "HardwareDetector", _FauxDetecteur)
+    faux_temps = {"t": 1000.0}
+    monkeypatch.setattr(server.time, "monotonic", lambda: faux_temps["t"])
+    server.hardware_json()
+    faux_temps["t"] += server._HARDWARE_TTL_S + 1      # au-delà du TTL
+    server.hardware_json()
+    assert appels["n"] == 2, "le cache n'expire jamais (matériel jamais re-sondé)"
+
+
+def test_hardware_cache_clear_force_une_nouvelle_sonde(monkeypatch):
+    server._hardware_cache_clear()
+    appels = {"n": 0}
+
+    class _FauxProfil:
+        def to_json(self):
+            return '{"cpu_model":"faux"}'
+
+    class _FauxDetecteur:
+        def __init__(self, *a, **k):
+            appels["n"] += 1
+
+        def full_report(self):
+            return _FauxProfil()
+
+    monkeypatch.setattr(server, "HardwareDetector", _FauxDetecteur)
+    server.hardware_json()
+    server._hardware_cache_clear()      # invalidation EXPLICITE
+    server.hardware_json()
+    assert appels["n"] == 2, "l'invalidation explicite ne force pas une nouvelle sonde"
+
+
+def test_available_backends_memoise(monkeypatch):
+    """OPT-001 (2e chemin chaud) : `_available_backends` sonde docker/k3s à CHAQUE appel
+    (mesuré 801 ms) et relance en plus une détection matérielle. Doit être mémoïsé au même TTL."""
+    server._hardware_cache_clear()
+    appels = {"n": 0}
+
+    def _faux_run_checks(*a, **k):
+        appels["n"] += 1
+        return {}
+
+    monkeypatch.setattr(server, "run_checks", _faux_run_checks)
+    monkeypatch.setattr(server, "available_backends", lambda checks: ["compose"])
+    a = server._available_backends()
+    b = server._available_backends()
+    assert a == b == ["compose"]
+    assert appels["n"] == 1, f"sondes backends relancées {appels['n']}x (aucun cache) — 1 attendu"
+
+
+def test_backends_et_hardware_sans_interblocage(monkeypatch):
+    """Garde anti-régression : `_available_backends` réutilise `_hardware_report()` alors qu'il
+    détient déjà le verrou du cache. Avec un `Lock` non réentrant -> INTERBLOCAGE (prouvé).
+    Le verrou doit être RÉENTRANT (RLock). Le test échoue par TIMEOUT si la régression revient."""
+    import threading as _th
+    server._hardware_cache_clear()
+    # Le faux run_checks DOIT appeler full_report() sur le détecteur : c'est CE chemin qui reprend
+    # le verrou (réentrance). Sans cet appel, le test réussirait même avec un Lock simple
+    # (faux positif — constaté en revue et corrigé ici).
+    def _faux_run_checks(runner, detector, http_ok):
+        detector.full_report()   # -> _hardware_report() alors que le verrou est DÉJÀ tenu
+        return {}
+
+    monkeypatch.setattr(server, "run_checks", _faux_run_checks)
+    monkeypatch.setattr(server, "available_backends", lambda checks: ["compose"])
+
+    fini = _th.Event()
+
+    def _appel():
+        server._available_backends()
+        fini.set()
+
+    t = _th.Thread(target=_appel, daemon=True)
+    t.start()
+    assert fini.wait(timeout=10), "INTERBLOCAGE : _available_backends bloqué sur le verrou du cache"
```
