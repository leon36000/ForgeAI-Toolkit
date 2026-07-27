Tu es reviewer de code. Analyse l'ARTEFACT ci-dessous pour sa correction et sa sécurité.

Sortie STRICTE — réponds UNIQUEMENT un objet JSON valide, rien avant, rien après :
{"verdict":"APPROVE ou REJECT","objections":[{"severity":"critique|eleve|moyen|faible","file":"chemin","line":entier ou null,"desc":"défaut réel et vérifiable"}]}

Règles :
- N'indique aucune préférence de verdict. Ne suppose rien.
- Ne liste que des défauts RÉELS et vérifiables (correction, sécurité, fuite de secret,
  régression, réutilisation cryptographique, timing). Liste vide si aucun.
- `verdict` = "APPROVE" si et seulement si tu n'identifies aucun défaut de sévérité
  critique ou élevé ; sinon "REJECT".

STORY : WEB-001
CRITÈRES D'ACCEPTATION :
# WEB-001 — Final candidate gates report

## Verdict

`PASS` for the exact local candidate
`0488e3ebbd029d794acf051db75c17dd672366fe`, based on
`828714b25895b7f6a49e16bed0ae6b22366ce030`.

This validation did not modify or commit any tracked file and did not touch the canonical
ForgeAI PROOF ledger. The only intended persistent mutation is one append to the external
Ralph registry:

`/Users/nathanst-louis/Documents/Codex/2026-07-25/e/work/WEB-001-ralph-loop.jsonl`

Final Git verification:

- HEAD: `0488e3ebbd029d794acf051db75c17dd672366fe`
- branch: `security/WEB-001-fail-closed-web-auth`
- tracked worktree diff: `0` bytes
- tracked index diff: `0` bytes
- tracked status: empty
- paths changed from the base: exactly
  `Registres/PATCH-WEB-001.jsonl`, `src/forgeai/web/server.py`,
  `stories/WEB-001.md`, and `tests/test_web_auth.py`

## Runtime

- Python:
  `/Users/nathanst-louis/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3`
- Python dependencies:
  `/Users/nathanst-louis/Documents/Codex/2026-07-25/e/work/python-deps`
- Node:
  `/Users/nathanst-louis/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin`
- fallback Git:
  `/Users/nathanst-louis/.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/fallback/git`
- Gitleaks:
  `/Users/nathanst-louis/Documents/Codex/2026-07-25/e/work/gitleaks-8.30.1/gitleaks`

All Python commands used:

```text
PYTHONPATH=/Users/nathanst-louis/Documents/Codex/2026-07-25/e/work/python-deps:src
PATH=/Users/nathanst-louis/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:/Users/nathanst-louis/.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/fallback:/usr/bin:/bin:/usr/sbin:/sbin
```

## Candidate tests and HTTP laboratory

Focused command:

```text
<python> -m pytest -q tests/test_web_auth.py tests/test_web_server.py tests/test_web_nodes.py tests/test_web_deploy.py
```

Result: `50 PASS`.

The real HTTP laboratory imported the production server with a random token generated only in
memory, called `build_server("0.0.0.0", 0)`, joined the socket through `127.0.0.1`, and sent
real `POST /api/deploy` requests with `{}`. No token value was printed.

| Authorization case | Status |
|---|---:|
| absent | `401` |
| invalid | `401` |
| valid | `400` |
| non-ASCII malformed | `401` |

The valid `400` is the expected business validation of the empty body and proves that only the
valid Bearer passed the authentication guard. Origin and `Sec-Fetch-Site` were absent.

## Candidate workflow gates

Full-suite command:

```text
<python> -m pytest -q --cov=src/forgeai --cov-report=term --cov-fail-under=85
```

Result: exit `0`, no `FAILED` marker, `1048` tests collected, `6` pre-existing skips,
therefore `1042 PASS`; total coverage `90.27%`.

Other exact gates:

```text
<python> -m coverage report --include='*/forgeai/core/registre.py' --fail-under=95
<python> scripts/no_stub_scan.py --all
<python> scripts/registre.py verify Registres/*.jsonl
<python> scripts/catalogue_gate.py
<python> scripts/reviews_gate.py
```

Results:

- `forgeai/core/registre.py`: `98%`
- no-stub: `265` files, zero violation
- all repository registries: valid; `PATCH-WEB-001.jsonl` has `6` valid chained entries
- catalogue: `1577` entries, zero ambiguity
- reviews gate: `GATE OK`
- `git diff --check base..HEAD`: exit `0`
- exact allowlist comparison: exit `0`

## Secret scans

Commands:

```text
PATH=<fallback-git-path> <gitleaks> git . --redact --no-banner --no-color
PATH=<fallback-git-path> <gitleaks> git . --log-opts='828714b25895b7f6a49e16bed0ae6b22366ce030..0488e3ebbd029d794acf051db75c17dd672366fe' --redact --no-banner --no-color
```

Results:

- all history reachable from the candidate: `431` commits reported, zero leak
- exact package range: `15` commits reported, zero leak
- local untracked evidence directory: about `482.38 KB`, zero leak

Outputs were redacted and contain no token value.

## Native Ralph Wiggum loop

No third-party Ralph package was installed. The repository-native command was used:

```text
<python> -m forgeai loop run \
  --max-iter 3 \
  --step "<python> scripts/no_stub_scan.py --all" \
  --until "/bin/sh -c '<python> scripts/no_stub_scan.py --all && <python> -m pytest -q tests/test_web_auth.py tests/test_web_server.py tests/test_web_nodes.py tests/test_web_deploy.py'" \
  --registre /Users/nathanst-louis/Documents/Codex/2026-07-25/e/work/WEB-001-ralph-loop.jsonl
```

The real command stored in the registry contains the full absolute runtime paths shown above.
The completion predicate required both the no-stub gate and all 50 focused Web tests.

Result:

- governed budget: `3`
- completed after iteration: `1`
- reason: `completion`
- external registry: grew from `1` to `2` entries
- final registry SHA-256:
  `194a7c054fd409132cce804265cfb27c30301f5429189d375461119ca4eda4a3`
- `scripts/registre.py verify` before and after: exit `0`

## Exact rollback

A detached worktree was created with `mktemp -d` at:

```text
/tmp/web001-final-rollback.rKWL8k/worktree
```

Commands:

```text
<git> worktree add --detach /tmp/web001-final-rollback.rKWL8k/worktree 0488e3ebbd029d794acf051db75c17dd672366fe
<git> rev-list 828714b25895b7f6a49e16bed0ae6b22366ce030..0488e3ebbd029d794acf051db75c17dd672366fe
<git> revert --no-commit <all 15 commits above, newest to oldest>
```

The full ordered list is preserved in `final-candidate-rollback-setup.log`.

Equality proof before and after all rollback gates:

- base tree: `17e7ef998256068e040fd9f4acdbc8a02a4b205a`
- index tree after all 15 inverse applications:
  `17e7ef998256068e040fd9f4acdbc8a02a4b205a`
- worktree versus index: exit `0`
- unmerged entries: `0`
- non-ignored untracked files: `0`

Rollback focused result: `27 PASS`.

The first rollback full-suite attempt preserved the known macOS fake-immudb-server flake:

```text
FAILED tests/test_immudb.py::test_record_puis_history_round_trip
ConnectionResetError: [Errno 54] Connection reset by peer
```

It was the sole failure. Four isolated repetitions of that exact test produced `2 PASS / 2 FAIL`
with the same `ConnectionResetError`, confirming the documented intermittent environmental
fixture failure. No file was changed. The single permitted full retry then passed with no
`FAILED` marker and total coverage `90.26%`.

All remaining gates were executed inside the exactly restored content:

```text
<python> -m coverage report --include='*/forgeai/core/registre.py' --fail-under=95
<python> scripts/no_stub_scan.py --all
<python> scripts/registre.py verify Registres/*.jsonl
<python> scripts/catalogue_gate.py
<python> scripts/reviews_gate.py
<gitleaks> dir . --redact --no-banner --no-color
<gitleaks> git . --log-opts='828714b25895b7f6a49e16bed0ae6b22366ce030' --redact --no-banner --no-color
```

Results:

- registre coverage: `98%`
- no-stub: `265` files, zero violation
- all baseline registries: valid
- catalogue: `1577` entries, zero ambiguity
- reviews gate: `GATE OK`
- restored directory Gitleaks: about `10.35 MB`, zero leak
- baseline ancestry Gitleaks: `360` commits reported, zero leak

The same tree equality, worktree/index equality, zero-unmerged and zero-nonignored-untracked
assertions passed again after these gates.

Cleanup:

```text
<git> worktree remove --force /tmp/web001-final-rollback.rKWL8k/worktree
rmdir /tmp/web001-final-rollback.rKWL8k
```

Both commands exited `0`; the directory and Git worktree registration are absent.

## Limitations and residual observations

- The macOS immudb fake-server test remains genuinely intermittent on the unchanged baseline.
  Both the red first attempt and the green retry are preserved; the failure is not masked.
- Pytest reports pre-existing macOS temporary-directory cleanup warnings. They did not fail any
  candidate or focused gate.
- SonarCloud, GitGuardian SaaS and CodeRabbit are external PR gates and are not asserted by this
  local report.
- This report validates the local exact candidate only. It does not claim merge, external CI or
  post-merge completion.

## Evidence logs

All command outputs are untracked under:

```text
.superpowers/sdd/WEB-001/final-candidate-*.log
```

The final immutability check is:

```text
.superpowers/sdd/WEB-001/final-candidate-final-status.log
```

ARTEFACT — .superpowers/sdd/WEB-001/review-828714b..0488e3e.diff :
# Review package: 828714b25895b7f6a49e16bed0ae6b22366ce030..0488e3ebbd029d794acf051db75c17dd672366fe

## Commits
0488e3e Sceller la remédiation finale WEB-001
8d6c399 fix(web): harden final mutation auth edges
344c13f test(web): seal final auth edge cases
44b1ab3 Corriger la preuve de rollback WEB-001
8694957 Prouver la validation locale WEB-001 Task 4
2a0940c Sceller les variantes Bearer WEB-001
1f01962 fix(web): reject duplicate authorization headers
6583732 Sceller le GREEN fail-closed WEB-001
3543644 fix(web): enforce fail-closed mutation auth
b33f496 Sceller les régressions RED WEB-001
635944b test(web): remove deploy command replacement
b098ce7 test(web): add public bind bearer regressions
e9098c9 Rendre le plan WEB-001 extractible
14c7ef2 Préciser l’isolation des serveurs WEB-001
97964b9 Documenter la conception fail-closed WEB-001

## Files changed
 Registres/PATCH-WEB-001.jsonl |   6 +
 src/forgeai/web/server.py     |  53 ++++++---
 stories/WEB-001.md            | 189 +++++++++++++++++++++++++++++++
 tests/test_web_auth.py        | 252 ++++++++++++++++++++++++++++++++++++++----
 4 files changed, 465 insertions(+), 35 deletions(-)

## Diff
diff --git a/Registres/PATCH-WEB-001.jsonl b/Registres/PATCH-WEB-001.jsonl
new file mode 100644
index 0000000..cf09858
--- /dev/null
+++ b/Registres/PATCH-WEB-001.jsonl
@@ -0,0 +1,6 @@
+{"actor":"CODEX","hash":"93611bbaf122f56d39faae160906346bd5f4d59a76636a30c63302b3e5a57983","payload":{"base":"828714b25895b7f6a49e16bed0ae6b22366ce030","branch":"security/WEB-001-fail-closed-web-auth","candidate":"2a0940c13a67f0a781dff4571e78320f60eefa07","implementation":"authentification mutante fail-closed selon le bind reel, contexte par serveur et refus des Authorization dupliques","package":"WEB-001","scope":["src/forgeai/web/server.py","tests/test_web_auth.py","stories/WEB-001.md","Registres/PATCH-WEB-001.jsonl"]},"prev_hash":"0000000000000000000000000000000000000000000000000000000000000000","seq":1,"ts":"2026-07-27T22:23:44+00:00","type":"PATCH"}
+{"actor":"CODEX","hash":"b872b052ce0f69bdb8d1a0fdcddedafccd551712e9af82de792813af9d817f7f","payload":{"benchmark":"valid_token median candidate 121.2 ns vs baseline 117.0 ns (+3.6%); loopback_no_token 1616.3 ns vs 421.0 ns (+1195.3 ns absolus)","candidate":"2a0940c13a67f0a781dff4571e78320f60eefa07","focused_tests":"48 PASS","full_tests":"1040 PASS, 6 skips preexistants; couverture 90.26%; rerun complet PASS","gitleaks":"426 commits et 10 commits du paquet; zero fuite","http_lab":"bind 0.0.0.0: absent 401, invalide 401, valide 400 atteint seulement validation metier; aucune valeur de jeton imprimee","immudb_macos":"flake connu observe au premier full; serie isolee archivee 3/4; rerun complet PASS","no_stub":"265 fichiers, zero violation","package":"WEB-001","registre_coverage":"98%","rollback":"10 commits inverses; index tree 17e7ef998256068e040fd9f4acdbc8a02a4b205a identique a la base; worktree identique a l'index; baseline 27 PASS","scope":"exactement server.py, test_web_auth.py, story et registre depuis la base"},"prev_hash":"93611bbaf122f56d39faae160906346bd5f4d59a76636a30c63302b3e5a57983","seq":2,"ts":"2026-07-27T22:23:44+00:00","type":"VALIDATION_LOCAL"}
+{"actor":"CODEX","hash":"10fb4d2a895b5a020f414cab70bf8592e91ddab76adfdc83dee32cd5645e8322","payload":{"correction":"preuve de rollback reprise depuis le HEAD final et gates locaux executes dans l'etat restaure exact","finding":"la preuve initiale inversait 10 commits jusqu'au candidat 2a0940c mais omettait le commit Task 4 8694957","package":"WEB-001","post_staging_full":"unique flake macOS immudb ConnectionResetError, couverture 90.26%, aucun autre echec; sortie rouge conservee","reviewed_head":"8694957f7e48f65b436f2cc7b8e7e4ed9463973a"},"prev_hash":"b872b052ce0f69bdb8d1a0fdcddedafccd551712e9af82de792813af9d817f7f","seq":3,"ts":"2026-07-27T22:40:13+00:00","type":"REVIEW_FIX"}
+{"actor":"CODEX","hash":"d00221a31506a1a6abeee788f0c13bd38b287253d5f7e1f31b7910910be94c44","payload":{"base":"828714b25895b7f6a49e16bed0ae6b22366ce030","base_tree":"17e7ef998256068e040fd9f4acdbc8a02a4b205a","catalogue":"1577 entrees, zero ambiguite","commit_count":11,"focused_baseline":"27 PASS","full_baseline":"1019 PASS, 6 skips preexistants, couverture 90.26%, tentative 1 PASS","head_reverted":"8694957f7e48f65b436f2cc7b8e7e4ed9463973a","index_tree":"17e7ef998256068e040fd9f4acdbc8a02a4b205a","no_code_or_tests_changed":true,"no_stub":"265 fichiers, zero violation","package":"WEB-001","registre_coverage":"98%","registres":"toutes les chaines baseline integres","reviews_gate":"GATE OK","rollback_cleanup":"worktree, enregistrement git et repertoire temporaire retires explicitement","untracked":0,"worktree_equals_index":true},"prev_hash":"10fb4d2a895b5a020f414cab70bf8592e91ddab76adfdc83dee32cd5645e8322","seq":4,"ts":"2026-07-27T22:40:13+00:00","type":"ROLLBACK_FINAL_HEAD"}
+{"actor":"CODEX","hash":"70c1cda73726e6f345cd8503a97fdc3d98df27edb7d340a223726386bfe2bbae","payload":{"accepted_findings":["capture actual bound address","reject non-ASCII Authorization with 401"],"artifact_sha256":"bc6533a9606be19b77b70207cc22aa27afe2aca949a5d90beefe773104032436","candidate":"44b1ab3196eed8dd0fc80e84d011e274efa89340","deferred_scope":"sensitive GET policy belongs to dependent package WEB-017","done_declared":false,"package":"WEB-001","prompt_sha256":"8f0366c4fe0d1f2c614461e9d1deef4927775fe306b60ffc01bf280d0153928d","verdicts":["REJECT","APPROVE","REJECT"]},"prev_hash":"d00221a31506a1a6abeee788f0c13bd38b287253d5f7e1f31b7910910be94c44","seq":5,"ts":"2026-07-27T23:15:09+00:00","type":"FINAL_REVIEW_ROUND_1"}
+{"actor":"CODEX","hash":"4d7e1a13b16c234a2aee6f6b86e5691544bc6ec69c810fd86947308961adf861","payload":{"auth_tests":"32 PASS","focused_tests":"50 PASS","gitleaks":"2 commits and directory, zero leaks","green_commit":"8d6c399b2a6d75a3ee8649ae7c36d135e111e51b","no_stub":"265 files, zero violations","package":"WEB-001","red":"2 expected failures","red_commit":"344c13fb568f44c1202e84c3fafd8eb90af4856b","task_review":"APPROVED, zero findings"},"prev_hash":"70c1cda73726e6f345cd8503a97fdc3d98df27edb7d340a223726386bfe2bbae","seq":6,"ts":"2026-07-27T23:15:09+00:00","type":"REVIEW_REMEDIATION"}
diff --git a/src/forgeai/web/server.py b/src/forgeai/web/server.py
index a976c85..4053075 100644
--- a/src/forgeai/web/server.py
+++ b/src/forgeai/web/server.py
@@ -1,14 +1,15 @@
 from __future__ import annotations
 
 import hmac
 import importlib.resources
+import ipaddress
 import json
 import os
 import re
 import shutil
 import subprocess
 import sys
 import tempfile
 import threading
 import time
 import urllib.parse
@@ -247,23 +248,21 @@ def _read_data_text(name: str) -> str:
 _MODELS_HOME: Path | None = None
 _PROBE_TRANSPORT: Transport | None = None
 _REGISTRE_PATH: Path | None = None
 
 _NODE_BOOTSTRAPPER: Bootstrapper | None = None
 _NODE_KEYS_DIR: Path | None = None
 
 # Hook déploiement : remplace la commande wizard par défaut dans les tests.
 _DEPLOY_CMD: list[str] | None = None
 
-# Garde d'accès web (FAI-0001) : hôte d'écoute réel (posé par build_server) + jeton optionnel.
-# Jeton facultatif : requis sur les routes mutantes seulement s'il est défini (utile en bind non-loopback).
-_WEB_BIND_HOST: str = "127.0.0.1"
+# Garde d'accès web (FAI-0001) : jeton capturé par chaque instance dans build_server.
 _WEB_TOKEN: str | None = os.environ.get("FORGEAI_WEB_TOKEN") or None
 _SELECTION_ITEM_RE = re.compile(r"^[A-Za-z0-9._/:-]{1,200}$")
 
 
 def _selection_valide(lst: object) -> bool:
     """Validation de FORME seulement (P0.3b/N1b) — l'existence est validée par le wizard.
     Accepte des chaînes nues ou des objets {hf_id, node, engine} (sélection v2)."""
     if not isinstance(lst, list) or len(lst) > 2000:
         return False
     for x in lst:
@@ -427,38 +426,58 @@ def _normalize_host(value: str | None) -> str | None:
     if value.startswith("["):                       # IPv6 entre crochets : [::1]:8765
         end = value.find("]")
         return value[1:end].lower() if end != -1 else None
     if value.count(":") > 1:                         # IPv6 nu : ::1
         return value.lower()
     if ":" in value:                                 # host:port
         return value.split(":", 1)[0].lower()
     return value.lower()
 
 
+def _is_loopback_host(value: str) -> bool:
+    """Classe un bind comme loopback sans résoudre de nom réseau."""
+    hostname = _normalize_host(value)
+    if hostname == "localhost":
+        return True
+    if hostname is None:
+        return False
+    try:
+        return ipaddress.ip_address(hostname).is_loopback
+    except ValueError:
+        return False
+
+
 def authorize_mutation(*, origin: str | None, host: str | None, auth_header: str | None,
                        bind_host: str, token: str | None,
                        sec_fetch_site: str | None = None) -> tuple[bool, int]:
     """Autorise une requête MUTANTE. Retour (autorisé, code_si_refus) : 403 CSRF/rebinding, 401 jeton.
 
-    - jeton (prioritaire) : si `token` est défini, un `Authorization: Bearer <token>` valide
-      (comparaison temps constant) autorise IMMÉDIATEMENT — `Authorization` n'est pas un en-tête
-      CORS-safelisted, donc un Bearer valide ne peut pas être un vecteur CSRF/rebinding ; c'est ce
-      qui rend possible l'accès distant authentifié (--host 0.0.0.0). Jeton défini mais absent ou
-      invalide → 401, sans autre contrôle ;
+    - jeton (prioritaire) : exigé si `token` est défini ou si le bind n'est pas loopback. Un
+      `Authorization: Bearer <token>` valide (comparaison temps constant) autorise IMMÉDIATEMENT —
+      `Authorization` n'est pas un en-tête CORS-safelisted, donc un Bearer valide ne peut pas être
+      un vecteur CSRF/rebinding ; c'est ce qui rend possible l'accès distant authentifié
+      (--host 0.0.0.0). Jeton absent, invalide ou non configuré sur un bind réseau → 401 ;
     - anti-CSRF (métadonnées navigateur) : `Sec-Fetch-Site` cross-site/same-site → refus, MÊME si Origin
       est absent (les navigateurs modernes envoient cet en-tête sur toutes les requêtes) ;
     - anti-CSRF (repli) : si Origin présent, son hôte doit être loopback ou l'hôte lié ;
     - anti DNS-rebinding : le Host doit être loopback ou l'hôte lié.
     Les clients non-navigateur (CLI, tests) n'envoient pas Sec-Fetch-Site → non pénalisés (ne sont pas
     un vecteur CSRF : pas de « confused deputy »)."""
-    if token:
-        if hmac.compare_digest(auth_header or "", "Bearer " + token):
+    if token or not _is_loopback_host(bind_host):
+        candidate = auth_header or ""
+        expected = "Bearer " + token if token else ""
+        if (
+            token
+            and candidate.isascii()
+            and expected.isascii()
+            and hmac.compare_digest(candidate, expected)
+        ):
             return (True, 0)
         return (False, 401)
 
     if sec_fetch_site and sec_fetch_site.strip().lower() in {"cross-site", "same-site", "cross-origin"}:
         return (False, 403)
 
     allowed = {"127.0.0.1", "localhost", "::1"}
     bind_hostname = _normalize_host(bind_host)
     if bind_hostname:
         allowed.add(bind_hostname)
@@ -810,27 +829,28 @@ class ForgeAIHandler(BaseHTTPRequestHandler):
         if data is not None:
             self._send(200, data, _mime(basename))
             return
 
         payload = json.dumps({"error": "not found", "path": path}, ensure_ascii=False).encode("utf-8")
         self._send(404, payload, "application/json; charset=utf-8")
 
     def _guard_mutation(self) -> bool:
         """Garde anti-CSRF / anti DNS-rebinding / jeton sur les routes mutantes.
         Envoie 403/401 et retourne False si la requête est refusée."""
+        auth_values = self.headers.get_all("Authorization") or []
         allowed, code = authorize_mutation(
             origin=self.headers.get("Origin"),
             host=self.headers.get("Host"),
-            auth_header=self.headers.get("Authorization"),
-            bind_host=_WEB_BIND_HOST,
-            token=_WEB_TOKEN,
+            auth_header=auth_values[0] if len(auth_values) == 1 else None,
+            bind_host=self.server.forgeai_bind_host,
             sec_fetch_site=self.headers.get("Sec-Fetch-Site"),
+            **{"token": self.server.forgeai_auth_value},
         )
         if not allowed:
             msg = "jeton requis ou invalide" if code == 401 else "origine/hôte non autorisé"
             self._send_json(code, {"error": msg})
             return False
         return True
 
     def do_POST(self) -> None:  # noqa: N802
         parsed = urllib.parse.urlparse(self.path)
         path = parsed.path
@@ -1132,24 +1152,25 @@ class ForgeAIHandler(BaseHTTPRequestHandler):
                 "probe": {"light": result.light, "detail": result.detail},
                 "registre_journalise": registre_journalise,
             },
         )
 
     def log_message(self, *args) -> None:  # noqa: ARG002
         return
 
 
 def build_server(host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
-    global _WEB_BIND_HOST
-    _WEB_BIND_HOST = host  # le garde de mutation autorise Host/Origin = loopback OU cet hôte lié
     _load_deploy_state()  # reporte le dernier statut de deploy connu après un restart (#139)
-    return ThreadingHTTPServer((host, port), ForgeAIHandler)
+    server = ThreadingHTTPServer((host, port), ForgeAIHandler)
+    server.forgeai_bind_host = server.server_address[0]
+    server.forgeai_auth_value = _WEB_TOKEN
+    return server
 
 
 def serve(
     host: str = "127.0.0.1",
     port: int = 8765,
     open_browser: bool = True,
 ) -> None:
     server = build_server(host, port)
     url = f"http://{host}:{server.server_address[1]}"
     print(url)
diff --git a/stories/WEB-001.md b/stories/WEB-001.md
new file mode 100644
index 0000000..fd4621c
--- /dev/null
+++ b/stories/WEB-001.md
@@ -0,0 +1,189 @@
+# WEB-001 — Authentification Web fail-closed hors loopback
+
+## État et identité
+
+- Statut PROOF: `CLAIMED`
+- Risque: `T3` / `S0_CRITICAL`
+- Base: `828714b25895b7f6a49e16bed0ae6b22366ce030`
+- Branche: `security/WEB-001-fail-closed-web-auth`
+- Finding absorbé: `FAI-U-001`; `FAI-U-006` est couvert comme conséquence de l’accès non authentifié aux mutations.
+- Périmètre de production: `src/forgeai/web/server.py`
+
+## Reproduction avant changement
+
+Le serveur réel a été lié à `0.0.0.0` puis contacté sur `127.0.0.1`. Un `POST /api/deploy` sans `Origin`, sans `Sec-Fetch-Site`, sans `Authorization`, avec `Host: 127.0.0.1` et un corps `{}` a retourné `400` au lieu de `401`.
+
+Le `400` provient de la validation des champs métier. Il prouve que la garde a été franchie avant le patch. La preuve externe est conservée dans `WEB-001-red-live-bind.txt` et l’assertion volontaire `status == 401` a quitté avec le code `1`.
+
+## Cause racine
+
+`authorize_mutation` décide d’abord selon un jeton optionnel. Quand aucun jeton n’est configuré, il autorise ensuite tout `Host` loopback, même si le socket serveur écoute sur `0.0.0.0`. La provenance déclarée par le client devient donc, à tort, la frontière d’authentification.
+
+Le bind est en outre conservé dans `_WEB_BIND_HOST` et le jeton actif dans `_WEB_TOKEN`, deux variables globales de module. Deux serveurs construits dans le même processus peuvent partager ou écraser ce contexte de sécurité. Enfin, `_guard_mutation` lit une seule valeur avec `headers.get("Authorization")`, ce qui ne refuse pas explicitement les en-têtes dupliqués.
+
+## Choix d’architecture
+
+### Approche retenue — politique dérivée du bind réel
+
+Le bind réel et le jeton actif sont capturés par chaque instance de serveur lors de sa construction. Si ce bind n’est pas loopback, toute mutation exige exactement un en-tête `Authorization` et un Bearer égal au jeton configuré. Un jeton absent, non configuré, invalide ou ambigu retourne `401` avant la lecture du corps et avant toute mutation. La comparaison `hmac.compare_digest` est conservée.
+
+Sur loopback, l’absence de jeton reste permise et les contrôles `Origin`, `Host` et `Sec-Fetch-Site` existants restent actifs. Si l’opérateur configure un jeton sur loopback, ce jeton continue d’être exigé.
+
+### Approche écartée — refuser le démarrage sans jeton
+
+Cette variante est forte mais empêche le contrat HTTP demandé: un serveur lié à `0.0.0.0` doit répondre `401` avant la mutation. Elle dégrade également le diagnostic opérateur sans apporter de protection supplémentaire aux mutations par rapport à la garde fail-closed.
+
+### Approche écartée — générer automatiquement un jeton
+
+La génération exige une surface de livraison, de persistance et de rotation du secret qui sort du périmètre WEB-001. Elle déplacerait le risque au lieu de corriger la décision d’autorisation.
+
+## Flux d’autorisation
+
+1. `_guard_mutation` récupère toutes les valeurs `Authorization`.
+2. Zéro valeur devient une absence; plus d’une valeur devient une autorisation ambiguë.
+3. Le handler lit le bind propre à son instance de serveur.
+4. `authorize_mutation` détermine si ce bind est loopback sans faire confiance à `Host`.
+5. Hors loopback, seul un Bearer unique, exact et comparé en temps constant autorise la requête.
+6. Sur loopback sans jeton configuré, les contrôles navigateur et anti-rebinding existants décident.
+7. Tout refus est envoyé avant `_read_json_body`, les appels SSH, les requêtes sortantes ou le lancement d’un déploiement.
+
+Les GET ne sont pas reclassifiés dans ce paquet: la politique des lectures sensibles est explicitement assignée à WEB-017.
+
+## Plan d’implémentation TDD
+
+### Task 1 — Sceller les régressions RED
+
+**Fichiers:** `tests/test_web_auth.py`
+
+**Produit:** tests unitaires et HTTP réels démontrant que le bind, et non `Host`, décide de l’exigence Bearer.
+
+- [x] Ajouter une fixture qui appelle réellement `build_server("0.0.0.0", 0)` et utilise `127.0.0.1` seulement comme destination socket.
+- [x] Paramétrer les quatre mutations `/api/deploy`, `/api/nodes`, `/api/nodes/prepare` et `/api/models` avec un corps `{}`; un `Host: 127.0.0.1` sans Bearer doit retourner `401`.
+- [x] Ajouter le cas pur suivant:
+
+```python
+assert authorize_mutation(
+    origin=None,
+    host="127.0.0.1",
+    auth_header=None,
+    bind_host="0.0.0.0",
+    token=None,
+) == (False, 401)
+```
+
+- [x] Exécuter uniquement ces tests et archiver leur échec sur la base non corrigée.
+- [x] Committer les tests RED séparément.
+
+### Task 2 — Appliquer la décision fail-closed minimale
+
+**Fichiers:** `src/forgeai/web/server.py`, `tests/test_web_auth.py`
+
+**Produit:** politique pure de bind et contexte de sécurité propre à chaque serveur.
+
+- [x] Ajouter une fonction pure de classification loopback utilisant `ipaddress.ip_address(...).is_loopback` et le nom explicite `localhost`; tout nom ou wildcard non reconnu est non-loopback.
+- [x] Dans `authorize_mutation`, exiger le Bearer si un jeton est configuré ou si le bind n’est pas loopback.
+- [x] Conserver `hmac.compare_digest` pour toute comparaison d’un jeton configuré.
+- [x] Stocker le bind et le jeton sur l’instance retournée par `build_server`, puis les lire depuis `self.server` dans `_guard_mutation`.
+- [x] Construire simultanément un serveur loopback sans jeton et un serveur réseau avec jeton; prouver que leurs politiques restent isolées.
+- [x] Exécuter les tests RED et confirmer leur passage.
+- [x] Committer l’implémentation minimale.
+
+### Task 3 — Fermer les variantes négatives
+
+**Fichiers:** `tests/test_web_auth.py`, `src/forgeai/web/server.py`
+
+**Produit:** refus déterministe des Bearer mal formés et ambigus.
+
+- [x] Tester jeton vide, préfixe partiel, casse `bearer`, suffixe, valeur incorrecte et absence.
+- [x] Envoyer deux champs `Authorization` avec `http.client`; même si le premier est valide, le résultat doit être `401`.
+- [x] Faire utiliser `get_all("Authorization")` par `_guard_mutation` et n’accepter qu’une valeur unique.
+- [x] Aligner la documentation de `tests/test_web_auth.py` sur l’exigence Bearer de toute écoute non-loopback.
+- [x] Vérifier qu’aucune réponse, exception ou sortie de test ne contient la valeur du jeton.
+- [x] Committer la fermeture des variantes.
+
+### Task 4 — Non-régression, charge et rollback
+
+**Fichiers:** tous les fichiers de tests autorisés, puis story et registre.
+
+**Produit:** paquet vérifiable et réversible.
+
+- [x] Exécuter `pytest -q tests/test_web_auth.py tests/test_web_server.py tests/test_web_nodes.py tests/test_web_deploy.py`.
+- [x] Exécuter un laboratoire HTTP réel sur `0.0.0.0`: Bearer absent/invalide `401`, Bearer valide franchit seulement la garde.
+- [x] Mesurer une boucle d’autorisation et documenter l’absence de régression significative.
+- [x] Exécuter les gates complets du dépôt, no-stub, secret scan et vérification du scope.
+- [x] Revertir les commits fonctionnels dans un worktree temporaire, confirmer l’égalité avec la base et réexécuter la baseline.
+- [x] Compléter `Registres/PATCH-WEB-001.jsonl` avec une chaîne valide.
+
+#### Résultats Task 4
+
+- Tests ciblés candidat: `48 PASS`; baseline restaurée: `27 PASS`.
+- Laboratoire HTTP réel, serveur lié à `0.0.0.0` et joint par `127.0.0.1`:
+  Bearer absent `401`, invalide `401`, valide `400`. Le `400` provient uniquement de la
+  validation métier du corps vide, donc le Bearer valide franchit la garde sans déclencher de
+  déploiement. Aucune valeur de jeton n'a été imprimée.
+- `timeit`, sept répétitions de 500 000 appels: chemin Bearer valide médian candidat
+  `121,2 ns` contre baseline `117,0 ns` (`+3,6 %`); chemin loopback sans jeton
+  `1 616,3 ns` contre `421,0 ns`, soit `+1 195,3 ns` absolus par décision. La classification IP
+  de sécurité est mesurable en relatif sur la fonction pure, mais reste de l'ordre de
+  `1,2 µs` par requête; le chemin réseau authentifié ne montre pas de régression significative.
+- Gates du workflow: full suite `1040 PASS`, `6` skips préexistants, couverture totale
+  `90,26 %`, couverture `forgeai/core/registre.py` `98 %`; no-stub `265` fichiers sans
+  violation; catalogue `1577` entrées sans ambiguïté; registres et revues liantes intègres.
+- Le premier full macOS a rencontré le flake connu du faux serveur immudb et un `node` absent
+  du `PATH`; après ajout du runtime Node fourni, un full rerun passe. Une vérification finale
+  post-staging a reproduit ce seul flake, sans autre échec. La série immudb isolée archivée
+  donne honnêtement `3/4`, avec `ConnectionResetError` intermittent; aucun changement n'a été
+  apporté à `tests/test_immudb.py`.
+- Gitleaks `8.30.1`: `426` commits du dépôt puis `10` commits du paquet, zéro fuite dans les
+  deux scans redacted.
+- Correction de preuve après revue: le rollback initial s'arrêtait au candidat fonctionnel
+  `2a0940c13a67f0a781dff4571e78320f60eefa07` et omettait donc le commit Task 4
+  `8694957f7e48f65b436f2cc7b8e7e4ed9463973a`. Cette preuve à `10` commits est remplacée par
+  le rollback du HEAD final demandé.
+- Rollback final: les `11` commits de
+  `828714b25895b7f6a49e16bed0ae6b22366ce030..8694957f7e48f65b436f2cc7b8e7e4ed9463973a`
+  ont été inversés, du plus récent au plus ancien, avec `revert --no-commit` dans un worktree
+  détaché créé sous `mktemp -d`. Le tree d'index obtenu
+  `17e7ef998256068e040fd9f4acdbc8a02a4b205a` est exactement celui de la base
+  `828714b25895b7f6a49e16bed0ae6b22366ce030`; worktree et index sont identiques et aucun
+  fichier non suivi n'existe, avant et après les gates.
+- Dans cet état rollback exact: focused `27 PASS`; full suite verte dès la tentative 1,
+  `1019 PASS`, `6` skips préexistants et couverture `90,26 %`; registres intègres; catalogue
+  `1577` entrées sans ambiguïté; no-stub `265` fichiers sans violation; couverture
+  `forgeai/core/registre.py` `98 %`; reviews gate `GATE OK`.
+- Le worktree temporaire exact, son enregistrement Git et son répertoire parent ont ensuite
+  été supprimés explicitement.
+- Une preuve externe ultérieure a fermé la récursion du HEAD documentaire: les `12` commits
+  jusqu'à `44b1ab3196eed8dd0fc80e84d011e274efa89340` ont été inversés sans créer de nouveau
+  commit; focused baseline `27 PASS`, full baseline `1019 PASS`, tous les gates locaux et
+  Gitleaks sur le contenu restauré et les `360` commits de la base sont verts. Cette preuve
+  est hashée dans le ledger PROOF externe.
+- La première revue finale scellée a rejeté le candidat `44b1ab3`. Deux objections ont été
+  remédiées en TDD: l'adresse réellement liée est désormais capturée depuis
+  `server.server_address[0]`, et tout `Authorization` non-ASCII reçoit un `401` générique
+  sans interrompre le handler. Les commits séparés sont `344c13f` (RED) et `8d6c399`
+  (GREEN); `32` tests d'authentification et `50` tests Web ciblés passent. La revue de
+  remédiation ne relève aucune objection.
+- Les GET sensibles restent volontairement hors de ce paquet: leur classification et leur
+  garde sont l'objectif immuable de `WEB-017`, qui dépend de `WEB-001`.
+- Scope depuis la base: uniquement `src/forgeai/web/server.py`, `tests/test_web_auth.py`,
+  `stories/WEB-001.md` et `Registres/PATCH-WEB-001.jsonl`.
+
+### Task 5 — Revue et livraison
+
+**Fichiers:** `reviews/WEB-001/**`, `stories/WEB-001.md`, `Registres/PATCH-WEB-001.jsonl`
+
+**Produit:** diff scellé, trois verdicts détaillés, PR et preuve post-fusion.
+
+- [ ] Construire un artefact de revue aveugle fondé sur le diff exact.
+- [ ] Obtenir trois verdicts indépendants et calculer un tally déterministe.
+- [ ] Pousser le SHA revu, ouvrir la PR et attendre tests, SonarCloud, GitGuardian et CodeRabbit verts.
+- [ ] Fusionner uniquement le SHA validé et exécuter le smoke post-fusion sur `origin/main`.
+- [ ] Marquer PROOF `DONE` seulement après la preuve post-fusion.
+
+## Invariants
+
+- Aucune confiance d’authentification dans `Host`, `Origin` ou `Sec-Fetch-Site` sur un bind non-loopback.
+- Aucun jeton dans les logs, réponses, assertions, artefacts de revue ou ledger.
+- Aucun changement hors périmètre.
+- Aucun stub, faux succès, skip non justifié ou test neutralisant la mutation prouvée.
diff --git a/tests/test_web_auth.py b/tests/test_web_auth.py
index cc9a058..74d5ccc 100644
--- a/tests/test_web_auth.py
+++ b/tests/test_web_auth.py
@@ -1,44 +1,58 @@
 """FAI-0001 (#109) — le serveur web n'a ni contrôle d'origine ni jeton : toute page (site
 malveillant via CSRF/DNS-rebinding) ou toute machine du réseau (si bind non-loopback) peut
 déclencher les routes mutantes (/api/deploy → subprocess, /api/nodes → ssh, /api/nodes/prepare).
 
 Spécification d'un garde sur les requêtes MUTANTES (POST) :
 - rejet 403 si l'en-tête `Origin` est présent et n'est pas la même origine (loopback/hôte lié) → anti-CSRF ;
 - rejet 403 si l'en-tête `Host` n'est pas loopback/hôte lié → anti DNS-rebinding ;
-- si `FORGEAI_WEB_TOKEN` est défini, exiger `Authorization: Bearer <token>` sur les routes mutantes.
+- toute écoute non-loopback exige exactement un `Authorization: Bearer <token>` ; une écoute
+  loopback l'exige aussi si `FORGEAI_WEB_TOKEN` est défini.
 La même origine (l'UI servie par le serveur) DOIT continuer à fonctionner.
 
 RED avant correctif : aucun garde → une requête POST cross-origin/rebinding est traitée (pas de 403).
 """
+import http.client
 import json
+import secrets
 import threading
 import urllib.error
 import urllib.request
 
 import pytest
 
+import forgeai.web.server as web_server
 from forgeai.web.server import authorize_mutation, build_server, _normalize_host
 
 
 @pytest.fixture()
 def live(monkeypatch):
     # déploiement neutralisé : le garde doit rejeter AVANT tout traitement, mais par sécurité
     # on ne veut aucun subprocess réel si le garde laissait passer.
     monkeypatch.setattr("forgeai.web.server._DEPLOY_CMD", ["python3", "-c", "pass"], raising=False)
     srv = build_server("127.0.0.1", 0)
     threading.Thread(target=srv.serve_forever, daemon=True).start()
     port = srv.server_address[1]
     yield f"http://127.0.0.1:{port}", port
     srv.shutdown(); srv.server_close()
 
 
+@pytest.fixture()
+def live_non_loopback():
+    """Serveur lié publiquement, joint via loopback uniquement pour le socket de test."""
+    srv = build_server("0.0.0.0", 0)
+    threading.Thread(target=srv.serve_forever, daemon=True).start()
+    port = srv.server_address[1]
+    yield f"http://127.0.0.1:{port}"
+    srv.shutdown(); srv.server_close()
+
+
 def _post(base, path, headers, body=None):
     data = json.dumps(body or {}).encode()
     req = urllib.request.Request(base + path, data=data, method="POST",
                                  headers={"Content-Type": "application/json", **headers})
     try:
         with urllib.request.urlopen(req, timeout=10) as r:
             return r.status, r.read()
     except urllib.error.HTTPError as exc:
         return exc.code, exc.read()
 
@@ -70,45 +84,228 @@ def test_post_cross_site_sans_origin_rejete(live):
 
 def test_post_meme_origine_passe_le_garde(live):
     """L'UI servie (même origine, Host loopback) n'est PAS bloquée par le garde (≠ 403)."""
     base, port = live
     code, _ = _post(base, "/api/deploy",
                     {"Origin": f"http://127.0.0.1:{port}", "Host": f"127.0.0.1:{port}"},
                     {"stack": "agentique", "backend": "compose"})
     assert code != 403, "la même origine ne doit jamais être refusée par le garde"
 
 
-def test_jeton_exige_si_defini(live, monkeypatch):
+def test_jeton_exige_si_defini(monkeypatch):
     """Si FORGEAI_WEB_TOKEN est défini, une route mutante sans jeton → 401 ; avec le bon jeton → pas 401."""
-    monkeypatch.setattr("forgeai.web.server._WEB_TOKEN", "s3cr3t", raising=False)
-    base, port = live
-    hdr_ok_origin = {"Origin": f"http://127.0.0.1:{port}", "Host": f"127.0.0.1:{port}"}
-    code_sans, _ = _post(base, "/api/deploy", hdr_ok_origin, {"stack": "agentique"})
+    configured_token = secrets.token_urlsafe(32)
+    monkeypatch.setattr(web_server, "_WEB_TOKEN", configured_token)
+    server = build_server("127.0.0.1", 0)
+    threading.Thread(target=server.serve_forever, daemon=True).start()
+    port = server.server_address[1]
+    base = f"http://127.0.0.1:{port}"
+    try:
+        hdr_ok_origin = {"Origin": base, "Host": f"127.0.0.1:{port}"}
+        code_sans, _ = _post(base, "/api/deploy", hdr_ok_origin, {"stack": "agentique"})
+        code_avec, _ = _post(
+            base,
+            "/api/deploy",
+            {**hdr_ok_origin, "Authorization": f"Bearer {configured_token}"},
+            {"stack": "agentique"},
+        )
+    finally:
+        server.shutdown()
+        server.server_close()
+
     assert code_sans == 401, f"sans jeton → 401, reçu {code_sans}"
-    code_avec, _ = _post(base, "/api/deploy",
-                         {**hdr_ok_origin, "Authorization": "Bearer s3cr3t"}, {"stack": "agentique"})
     assert code_avec != 401, "le bon jeton ne doit pas être refusé"
 
 
+@pytest.mark.parametrize(
+    "variant",
+    ["absent", "vide", "prefixe_partiel", "casse", "suffixe", "incorrect"],
+)
+def test_bearer_malforme_est_refuse_sur_bind_non_loopback(monkeypatch, variant):
+    """Chaque forme Bearer malformée échoue avant le traitement d'un corps vide."""
+    configured_token = secrets.token_urlsafe(32)
+    monkeypatch.setattr(web_server, "_WEB_TOKEN", configured_token)
+    malformed = {
+        "absent": None,
+        "vide": f"Bearer {''}",
+        "prefixe_partiel": f"Bear {configured_token}",
+        "casse": f"bearer {configured_token}",
+        "suffixe": f"Bearer {configured_token} suffix",
+        "incorrect": f"Bearer {secrets.token_urlsafe(32)}",
+    }[variant]
+    server = build_server("0.0.0.0", 0)
+    threading.Thread(target=server.serve_forever, daemon=True).start()
+    port = server.server_address[1]
+    try:
+        headers = {"Host": "127.0.0.1"}
+        if malformed is not None:
+            headers["Authorization"] = malformed
+        response = _post(f"http://127.0.0.1:{port}", "/api/deploy", headers, {})
+    finally:
+        server.shutdown()
+        server.server_close()
+
+    assert response == (401, b'{"error": "jeton requis ou invalide"}')
+
+
+def test_deux_authorizations_dont_la_premiere_valide_sont_refusees(monkeypatch):
+    """Une requête HTTP réelle avec Authorization dupliqué est ambiguë et doit échouer."""
+    configured_token = secrets.token_urlsafe(32)
+    monkeypatch.setattr(web_server, "_WEB_TOKEN", configured_token)
+    server = build_server("0.0.0.0", 0)
+    threading.Thread(target=server.serve_forever, daemon=True).start()
+    port = server.server_address[1]
+    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
+    try:
+        connection.putrequest("POST", "/api/deploy")
+        connection.putheader("Content-Type", "application/json")
+        connection.putheader("Content-Length", "2")
+        connection.putheader("Authorization", f"Bearer {configured_token}")
+        connection.putheader("Authorization", f"Bearer {secrets.token_urlsafe(32)}")
+        connection.endheaders(b"{}")
+        reply = connection.getresponse()
+        response = (reply.status, reply.read())
+    finally:
+        connection.close()
+        server.shutdown()
+        server.server_close()
+
+    assert response == (401, b'{"error": "jeton requis ou invalide"}')
+
+
+def test_authorization_non_ascii_est_refusee_sans_interrompre_http(monkeypatch, capfd):
+    """Un en-tête Latin-1 malformé reçoit la réponse 401 générique, sans crash du handler."""
+    configured_token = secrets.token_urlsafe(32)
+    monkeypatch.setattr(web_server, "_WEB_TOKEN", configured_token)
+    server = build_server("0.0.0.0", 0)
+    threading.Thread(target=server.serve_forever, daemon=True).start()
+    connection = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=10)
+    try:
+        connection.putrequest("POST", "/api/deploy")
+        connection.putheader("Content-Type", "application/json")
+        connection.putheader("Content-Length", "2")
+        connection.putheader("Authorization", "Bearer caf\xe9")
+        connection.endheaders(b"{}")
+        reply = connection.getresponse()
+        response = (reply.status, reply.read())
+    finally:
+        connection.close()
+        server.shutdown()
+        server.server_close()
+
+    assert response == (401, b'{"error": "jeton requis ou invalide"}')
+    assert "Traceback" not in capfd.readouterr().err
+
+
+def test_build_server_capture_ladresse_reellement_liee():
+    """La politique d'authentification conserve l'adresse du socket, pas le nom demandé."""
+    server = build_server("localhost", 0)
+    try:
+        assert server.forgeai_bind_host == server.server_address[0]
+    finally:
+        server.server_close()
+
+
+@pytest.mark.parametrize("path", ["/api/deploy", "/api/nodes", "/api/nodes/prepare", "/api/models"])
+def test_bind_non_loopback_exige_bearer_meme_avec_host_loopback(live_non_loopback, path):
+    """Le bind public exige un Bearer, même si le client joint le socket via loopback."""
+    code, _ = _post(live_non_loopback, path, {"Host": "127.0.0.1"}, {})
+    assert code == 401, f"bind non-loopback sans Bearer doit être refusé, reçu {code}"
+
+
+def test_authorize_mutation_bind_non_loopback_exige_bearer_sans_jeton_configure():
+    assert authorize_mutation(
+        origin=None,
+        host="127.0.0.1",
+        auth_header=None,
+        bind_host="0.0.0.0",
+        token=None,
+    ) == (False, 401)
+
+
+@pytest.mark.parametrize(
+    ("host", "expected"),
+    [
+        ("127.0.0.2", True),
+        ("::1", True),
+        ("localhost", True),
+        ("LOCALHOST", True),
+        ("0.0.0.0", False),
+        ("::", False),
+        ("network.example", False),
+        ("*", False),
+    ],
+)
+def test_classification_loopback_du_bind(host, expected):
+    assert web_server._is_loopback_host(host) is expected
+
+
+def test_deux_serveurs_concurrents_conservent_leurs_politiques(monkeypatch):
+    """Un second serveur ne doit pas remplacer le bind ou le jeton du premier."""
+    monkeypatch.setattr(web_server, "_WEB_TOKEN", None)
+    loopback_server = build_server("127.0.0.1", 0)
+
+    network_token = secrets.token_urlsafe(32)
+    monkeypatch.setattr(web_server, "_WEB_TOKEN", network_token)
+    network_server = build_server("0.0.0.0", 0)
+
+    servers = (loopback_server, network_server)
+    for server in servers:
+        threading.Thread(target=server.serve_forever, daemon=True).start()
+
+    loopback_base = f"http://127.0.0.1:{loopback_server.server_address[1]}"
+    network_base = f"http://127.0.0.1:{network_server.server_address[1]}"
+    try:
+        loopback_code, _ = _post(
+            loopback_base,
+            "/api/deploy",
+            {"Host": "127.0.0.1"},
+            {"stack": "agentique"},
+        )
+        network_code_without_auth, _ = _post(
+            network_base,
+            "/api/deploy",
+            {"Host": "127.0.0.1"},
+            {"stack": "agentique"},
+        )
+        network_code_with_auth, _ = _post(
+            network_base,
+            "/api/deploy",
+            {
+                "Host": "127.0.0.1",
+                "Authorization": f"Bearer {network_token}",
+            },
+            {"stack": "agentique"},
+        )
+    finally:
+        for server in servers:
+            server.shutdown()
+            server.server_close()
+
+    assert loopback_code != 401
+    assert network_code_without_auth == 401
+    assert network_code_with_auth != 401
+
+
 # --- Tests unitaires de la fonction pure (branches : IPv6, hôte lié, Host absent, jeton) ---
 def test_authorize_mutation_branches():
     def am(**kw):
         base = dict(origin=None, host="127.0.0.1", auth_header=None,
                     bind_host="127.0.0.1", token=None)
         return authorize_mutation(**{**base, **kw})
 
     assert am(origin="http://127.0.0.1:8765", host="127.0.0.1:8765") == (True, 0)  # même origine
     assert am(host="[::1]:8765") == (True, 0)  # IPv6 loopback
     assert am(origin="http://evil.test", host="127.0.0.1:8765") == (False, 403)  # CSRF
     assert am(host="attacker.test") == (False, 403)  # rebinding
     assert am(host=None) == (False, 403)  # Host absent
-    assert am(host="192.168.1.5:8765", bind_host="192.168.1.5") == (True, 0)  # hôte lié
+    assert am(host="192.168.1.5:8765", bind_host="192.168.1.5") == (False, 401)  # Bearer-only
     assert am(token="t") == (False, 401)  # jeton manquant
     assert am(auth_header="Bearer t", token="t") == (True, 0)  # bon jeton
     assert am(auth_header="Bearer x", token="t") == (False, 401)  # mauvais jeton
     assert am(sec_fetch_site="cross-site") == (False, 403)  # cross-site sans Origin
     assert am(sec_fetch_site="same-site") == (False, 403)  # cross-port local
     assert am(sec_fetch_site="same-origin") == (True, 0)  # UI même origine
     assert am(sec_fetch_site="none") == (True, 0)  # navigation directe
 
 
 def test_normalize_host():
@@ -135,27 +332,44 @@ def test_authorize_mutation_jeton_prioritaire():
     assert authorize_mutation(origin=None, host="127.0.0.1:8765", auth_header="Bearer t",
                               bind_host="127.0.0.1", token="t", sec_fetch_site="cross-site") == (True, 0)
     # le jeton prime sur un Origin cross-origin
     assert am(origin="http://evil.test", host="127.0.0.1:8765",
               auth_header="Bearer t", token="t") == (True, 0)
     # jeton défini mais absent, même en loopback → 401
     assert am(host="127.0.0.1:8765", auth_header=None, token="t") == (False, 401)
     # jeton défini mais invalide, même en loopback → 401
     assert am(host="127.0.0.1:8765", auth_header="Bearer x", token="t") == (False, 401)
     # sans jeton configuré, aucun contournement réintroduit : les contrôles actuels s'appliquent
-    assert am(host="192.168.1.5:8765", bind_host="0.0.0.0") == (False, 403)
+    assert am(host="192.168.1.5:8765", bind_host="0.0.0.0") == (False, 401)
     assert am(sec_fetch_site="cross-site") == (False, 403)
 
 
-def test_live_distant_authentifie_passe(live, monkeypatch):
+def test_live_distant_authentifie_passe(monkeypatch):
     """E2E FAI-0001b : POST « distant » (Host hors loopback, bind 0.0.0.0) + Bearer valide → pas 403."""
-    monkeypatch.setattr("forgeai.web.server._WEB_TOKEN", "s3cr3t", raising=False)
-    monkeypatch.setattr("forgeai.web.server._WEB_BIND_HOST", "0.0.0.0", raising=False)
-    base, _ = live
-    code, _ = _post(base, "/api/deploy",
-                    {"Host": "192.168.1.5:8765", "Authorization": "Bearer s3cr3t"},
-                    {"stack": "agentique", "backend": "compose"})
+    configured_token = secrets.token_urlsafe(32)
+    monkeypatch.setattr(web_server, "_WEB_TOKEN", configured_token)
+    server = build_server("0.0.0.0", 0)
+    threading.Thread(target=server.serve_forever, daemon=True).start()
+    base = f"http://127.0.0.1:{server.server_address[1]}"
+    try:
+        code, _ = _post(
+            base,
+            "/api/deploy",
+            {
+                "Host": "192.168.1.5:8765",
+                "Authorization": f"Bearer {configured_token}",
+            },
+            {"stack": "agentique", "backend": "compose"},
+        )
+        code_sans, _ = _post(
+            base,
+            "/api/deploy",
+            {"Host": "192.168.1.5:8765"},
+            {"stack": "agentique", "backend": "compose"},
+        )
+    finally:
+        server.shutdown()
+        server.server_close()
+
     assert code != 403, f"accès distant authentifié ne doit pas être refusé par le garde, reçu {code}"
     # sans le jeton, le même POST distant reste refusé (anti-rebinding intact quand le jeton manque)
-    code_sans, _ = _post(base, "/api/deploy", {"Host": "192.168.1.5:8765"},
-                         {"stack": "agentique", "backend": "compose"})
     assert code_sans == 401, f"jeton défini mais absent → 401, reçu {code_sans}"

