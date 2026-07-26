Tu es reviewer de code. Analyse l'ARTEFACT ci-dessous pour sa correction et sa sécurité.

Sortie STRICTE — réponds UNIQUEMENT un objet JSON valide, rien avant, rien après :
{"verdict":"APPROVE ou REJECT","objections":[{"severity":"critique|eleve|moyen|faible","file":"chemin","line":entier ou null,"desc":"défaut réel et vérifiable"}]}

Règles :
- N'indique aucune préférence de verdict. Ne suppose rien.
- Ne liste que des défauts RÉELS et vérifiables (correction, sécurité, fuite de secret,
  régression, réutilisation cryptographique, timing). Liste vide si aucun.
- `verdict` = "APPROVE" si et seulement si tu n'identifies aucun défaut de sévérité
  critique ou élevé ; sinon "REJECT".

STORY : DATA-003
CRITÈRES D'ACCEPTATION :
# [DATA-003] Créer un writer sécurisé commun et atomique pour les secrets OpenBao

## Identité immuable

- **Dépôt:** `https://github.com/leon36000/ForgeAI-Toolkit`
- **Owner/repo attendu:** `leon36000/ForgeAI-Toolkit`
- **Branche cible:** `main`
- **Branche de travail exacte:** `security/DATA-003-secure-atomic-secret-writer`
- **Exécuteur autorisé dans ce paquet:** `CODEX`
- **Lane exclusive:** `openbao-files`
- **Statut:** `READY_AFTER`
- **Priorité:** `P1_CRITICAL`
- **Sévérité:** `S1_HIGH`
- **Milestone:** `M1-CRITICAL`

## Règle de statut

Le package reste bloqué jusqu’à fusion de toutes ses dépendances et création du claim canonique.

## Objectif unique

Généraliser os.open avec mode final dès création, tempfile même répertoire, fsync, os.replace et fsync du dossier; supprimer toute fenêtre write-then-chmod.

## Findings sources

- `FAI-U-003`
- `FAI-U-035`

Le baseline de l’audit est `251f0682bf9d0ffde9f7fd7ab6c7c9f5bad1cd3e` (`tree 587de9c293183c776417ea9d5afdfc1ba5501d2c`), mais **la branche doit partir du dernier `origin/main` après fusion des dépendances**. Avant de modifier, vérifier si le défaut existe encore. S’il est déjà corrigé, produire un rapport `ALREADY_FIXED` avec preuves et ne pas créer de patch artificiel.

## Dépendances

- `ORCH-001` — propriétaire `COPILOT` — doit être **fusionné dans `main`** avant création de cette branche.

## Périmètre autorisé

- `src/forgeai/deploy/openbao_flow.py`
- `src/forgeai/bootstrap/secrets.py`
- `src/forgeai/models/vault.py`
- `tests/test_openbao_flow.py`
- `tests/test_assemble_and_secrets.py`
- `tests/test_vault.py`
- `stories/DATA-003.md`
- `reviews/DATA-003/**`
- `Registres/PATCH-DATA-003.jsonl`

## Périmètre interdit

- `build/**`
- `dist/**`
- `**/__pycache__/**`
- `src/forgeai/data/catalogue.json`

Tout fichier nécessaire hors périmètre provoque un **STOP** et une demande de changement de scope au cockpit. Ne jamais élargir silencieusement.

## Procédure obligatoire

1. Lire `00-LIRE-MOI-EN-PREMIER.md`, le contrat commun et ce document.
2. Exécuter `python3 SCRIPTS/verify_repo.py --repo <chemin>` depuis le paquet ou vérifier manuellement l’origin.
3. Vérifier que les dépendances sont fusionnées dans `origin/main`.
4. Vérifier l’absence de claim concurrent et de collision de lane/fichiers.
5. Créer la branche exacte depuis le dernier `origin/main` dans un worktree isolé.
6. Lire intégralement les fichiers autorisés et leurs tests actuels.
7. Reproduire le défaut par le chemin réel; archiver la preuve rouge.
8. Écrire le test rouge minimal.
9. Appliquer le changement minimal qui corrige la cause racine.
10. Exécuter tests ciblés, négatifs, sécurité, performance et gates complets applicables.
11. Exécuter le rollback lorsque requis.
12. Vérifier le scope avant chaque commit et avant la PR.
13. Produire les trois validations indépendantes détaillées.
14. Soumettre à la merge queue; ne jamais merger directement.

## Commandes/tests spécifiques

- `pytest -q tests/test_openbao_flow.py tests/test_assemble_and_secrets.py tests/test_vault.py`

## Critères d’acceptation

- [ ] Aucun lecteur concurrent ne voit une valeur vide ou partielle.
- [ ] Les modes sont corrects dès la création, indépendamment de umask.
- [ ] Les fichiers temporaires sont supprimés après erreur.
- [ ] Le writer refuse les symlinks et préserve les permissions attendues.

## Tests négatifs

- [ ] Panne après fsync fichier avant replace.
- [ ] Chemin cible symlink.
- [ ] Répertoire non-inscriptible.
- [ ] Lecteurs concurrents pendant 1000 remplacements.

## Tests de sécurité

- [ ] Aucune valeur de secret dans logs, assertions ou exceptions.

## Tests de performance

- [ ] Non applicable ou aucune régression mesurable; documenter la décision.

## Preuves obligatoires

- [ ] A failing regression test or direct reproduction on the audited baseline.
- [ ] Focused tests passing after the minimal change.
- [ ] Full project gates plus SonarQube, GitGuardian and CodeRabbit/Bugbot results.
- [ ] Diff-based blind-review pack, three detailed independent verdicts and deterministic tally.
- [ ] Issue-specific registry entry and rollback evidence.

## Rollback

1. Revert the PR commit(s) on main.
2. Restore changed state or schema from the pre-change fixture or backup.
3. Re-run focused tests and all repository quality gates.

## Notes

- Aucune note supplémentaire.

## Définition stricte de DONE

`DONE` est permis seulement lorsque:

- le défaut a été reproduit avant le patch ou classé `ALREADY_FIXED` avec preuve;
- le test rouge puis vert est archivé;
- tous les critères ci-dessus sont cochés;
- le scope est valide;
- aucun secret n’est présent;
- les trois validations détaillées sont disponibles;
- le rollback requis est prouvé;
- la PR est fusionnée par merge queue;
- le SHA fusionné est présent dans `origin/main` et les smoke tests post-merge passent.

## Rapport final obligatoire

```text
PACKAGE: DATA-003
REPOSITORY: https://github.com/leon36000/ForgeAI-Toolkit
BRANCH: security/DATA-003-secure-atomic-secret-writer
BASE_COMMIT:
MERGE_SHA:
FILES_CHANGED:
ROOT_CAUSE:
REPRODUCTION_BEFORE:
IMPLEMENTATION:
FOCUSED_TESTS:
NEGATIVE_TESTS:
FULL_GATES:
SECURITY_SCANS:
EVIDENCE_PATH:
ROLLBACK_RESULT:
LIMITATIONS:
OPEN_RISKS:
READY_FOR_PR: YES|NO
```

ARTEFACT — .superpowers/sdd/DATA-003/review-2ed262e..7061a79.diff :
# Review package: 2ed262e2c31a311134ff63c1336e50ddb23d0555..7061a793eb558161a136f93c2742704c1dd4362a

## Commits
7061a79 [DATA-003] Sérialiser le bootstrap des secrets
16ece65 [DATA-003] Rompre sûrement les hardlinks de secrets
641186e [DATA-003] Neutraliser les assertions de secrets
9acba25 [DATA-003] Documenter l'ouverture sécurisée du secret
606ae76 [DATA-003] Durcir la correction du mode des secrets
1970c46 [DATA-003] Sécuriser les écritures atomiques de secrets

## Files changed
 src/forgeai/bootstrap/secrets.py   |  73 ++++---
 src/forgeai/deploy/openbao_flow.py |   5 +-
 src/forgeai/models/vault.py        |  45 ++++-
 tests/test_assemble_and_secrets.py | 377 ++++++++++++++++++++++++++++++++++++-
 tests/test_openbao_flow.py         | 188 +++++++++++++++++-
 tests/test_vault.py                |  25 ++-
 6 files changed, 672 insertions(+), 41 deletions(-)

## Diff
diff --git a/src/forgeai/bootstrap/secrets.py b/src/forgeai/bootstrap/secrets.py
index 75f371b..434568d 100644
--- a/src/forgeai/bootstrap/secrets.py
+++ b/src/forgeai/bootstrap/secrets.py
@@ -4,54 +4,75 @@ Génère les secrets d'exécution (jetons aléatoires 256 bits) dans <out>/.env
 <out>/secrets/, permissions 0600, répertoire 0700. Idempotent : ne régénère pas
 un secret existant sauf --regen. Aucun secret n'apparaît jamais dans les
 manifestes rendus — ils sont référencés par env_file (vérifié par test).
 """
 from __future__ import annotations
 
 import os
 import secrets as pysecrets
 from pathlib import Path
 
+from forgeai.models._locking import file_lock
+from forgeai.models.vault import (
+    atomic_write_secret_text,
+    republish_existing_secret_file,
+)
+
 # Secrets ajoutés EN FIN (ligne 0 = FORGEAI_API_TOKEN préservée, cf. test permissions) :
 # - FORGEAI_LITELLM_KEY : master key de la passerelle LiteLLM du profil RAG durci (E2c).
 # - FORGEAI_PG_PASSWORD, FORGEAI_LANGFUSE_* : socle observabilité langfuse (E5) — postgres +
 #   clés d'ingestion (pk-lf-/sk-lf-), NextAuth/SALT/ENCRYPTION_KEY (64 hex requis par langfuse).
 # Tous interpolés dans le compose (${…}), jamais en clair dans un manifeste rendu.
 # NB (FAI-0005 S5) : PLUS de FORGEAI_BAO_TOKEN. En mode PRODUCTION le coffre openbao n'a pas de
 # dev-root-token pré-partagé — le token applicatif est créé au déploiement par ensure_openbao_ready
 # (secrets/openbao_init.py) et persisté RUNTIME (FileSecretStore / Secret k8s), jamais dans .env.
 ENV_KEYS = ("FORGEAI_API_TOKEN", "QDRANT_SERVICE_KEY", "FORGEAI_LITELLM_KEY",
             "FORGEAI_PG_PASSWORD", "FORGEAI_LANGFUSE_NEXTAUTH_SECRET", "FORGEAI_LANGFUSE_SALT",
             "FORGEAI_LANGFUSE_ENCRYPTION_KEY", "FORGEAI_LANGFUSE_PK", "FORGEAI_LANGFUSE_SK",
             "FORGEAI_LANGFUSE_UI_PASSWORD")
 
 # Préfixes de format exigés par langfuse pour ses clés d'API (le reste = 256 bits hex).
 _KEY_PREFIX = {"FORGEAI_LANGFUSE_PK": "pk-lf-", "FORGEAI_LANGFUSE_SK": "sk-lf-"}
 
+# `file_lock` ajoute le suffixe `.lock`. L'ancre reste volontairement dans
+# `out_dir`, à côté de `secrets/`, afin que l'artefact persistant de coordination
+# n'entre jamais dans le répertoire monté qui ne contient que les secrets.
+_BOOTSTRAP_LOCK_ANCHOR = ".bootstrap-secrets"
+
 
 def bootstrap_secrets(out_dir: Path, regen: bool = False) -> dict[str, Path]:
-    out_dir.mkdir(parents=True, exist_ok=True)
-    secrets_dir = out_dir / "secrets"
-    secrets_dir.mkdir(exist_ok=True)
-    os.chmod(secrets_dir, 0o700)
-
-    env_path = out_dir / ".env"
-    existing: dict[str, str] = {}
-    if env_path.exists() and not regen:
-        for line in env_path.read_text(encoding="utf-8").splitlines():
-            if "=" in line:
-                key, value = line.split("=", 1)
-                existing[key] = value
-
-    lines = []
-    for key in ENV_KEYS:
-        value = existing.get(key) or (_KEY_PREFIX.get(key, "") + pysecrets.token_hex(32))
-        lines.append(f"{key}={value}")
-    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
-    os.chmod(env_path, 0o600)
-
-    key_path = secrets_dir / "forgeai_token.key"
-    if not key_path.exists() or regen:
-        key_path.write_text(pysecrets.token_hex(32) + "\n", encoding="utf-8")
-    os.chmod(key_path, 0o600)
-
-    return {"env": env_path, "token_key": key_path}
+    with file_lock(out_dir / _BOOTSTRAP_LOCK_ANCHOR):
+        out_dir.mkdir(parents=True, exist_ok=True)
+        secrets_dir = out_dir / "secrets"
+        secrets_dir.mkdir(exist_ok=True)
+        os.chmod(secrets_dir, 0o700)
+
+        env_path = out_dir / ".env"
+        existing: dict[str, str] = {}
+        if env_path.exists() and not regen:
+            for line in env_path.read_text(encoding="utf-8").splitlines():
+                if "=" in line:
+                    key, value = line.split("=", 1)
+                    existing[key] = value
+
+        lines = []
+        for key in ENV_KEYS:
+            value = existing.get(key) or (
+                _KEY_PREFIX.get(key, "") + pysecrets.token_hex(32)
+            )
+            lines.append(f"{key}={value}")
+        atomic_write_secret_text(env_path, "\n".join(lines) + "\n", mode=0o600)
+
+        key_path = secrets_dir / "forgeai_token.key"
+        if regen:
+            atomic_write_secret_text(
+                key_path, pysecrets.token_hex(32) + "\n", mode=0o600
+            )
+        else:
+            try:
+                republish_existing_secret_file(key_path, mode=0o600)
+            except FileNotFoundError:
+                atomic_write_secret_text(
+                    key_path, pysecrets.token_hex(32) + "\n", mode=0o600
+                )
+
+        return {"env": env_path, "token_key": key_path}
diff --git a/src/forgeai/deploy/openbao_flow.py b/src/forgeai/deploy/openbao_flow.py
index ea8faa7..6f4ae95 100644
--- a/src/forgeai/deploy/openbao_flow.py
+++ b/src/forgeai/deploy/openbao_flow.py
@@ -8,20 +8,21 @@ root_token ne doit donc JAMAIS résider dans ce répertoire : FileKeyStore écri
 from __future__ import annotations
 
 import base64
 import json
 import os
 import subprocess
 import time
 from collections.abc import Callable
 from pathlib import Path
 
+from forgeai.models.vault import atomic_write_secret_text
 from forgeai.secrets.openbao_init import ensure_openbao_ready, http_transport
 
 
 class OpenBaoFlowError(RuntimeError):
     """Échec d'amorçage openbao au déploiement. Ne contient jamais de token/clé."""
 
 
 class FileKeyStore:
     """key_store fichier pour ensure_openbao_ready. `unseal_key` -> keys_dir/unseal_key (monté RO à
     l'unsealer) ; `root_token` -> root_path (SÉPARÉ, jamais monté). read() renvoie None si non initialisé."""
@@ -66,22 +67,22 @@ class FileSecretStore:
         return json.loads(text) if text else None
 
     def write(self, data: dict) -> None:
         self._path.parent.mkdir(parents=True, exist_ok=True)
         _write_file(self._path, json.dumps(dict(data)), 0o600)  # token opérateur, owner seul
 
 
 def _write_file(path: Path, content: str, mode: int) -> None:
     """Écrit `content` avec le mode donné (0600 pour les secrets owner-seul ; 0644 pour l'unseal_key
     que le conteneur unsealer non-root doit lire)."""
-    path.write_text(content if content.endswith("\n") else content + "\n", encoding="utf-8")
-    os.chmod(path, mode)
+    payload = content if content.endswith("\n") else content + "\n"
+    atomic_write_secret_text(path, payload, mode=mode)
 
 
 def prepare_key_store(keys_dir: Path) -> Path:
     """Pré-crée le répertoire des clés AVANT le démarrage d'openbao (le bind-mount hôte doit exister et
     appartenir à l'opérateur ; sinon docker le crée root et le flux Python ne peut plus écrire). Mode
     0o711 : le conteneur openbao-unsealer (UID NON-root de l'image ≠ opérateur) doit TRAVERSER le
     répertoire pour lire /keys/unseal_key par son nom (un 0700 le lui interdirait, prouvé e2e S6) SANS
     pouvoir le LISTER (pas de bit read pour les autres). Le répertoire ne contient QUE l'unseal_key (le
     root est ailleurs, 0600). Idempotent (create-if-absent). Renvoie le chemin."""
     d = Path(keys_dir)
diff --git a/src/forgeai/models/vault.py b/src/forgeai/models/vault.py
index 54da090..71c3935 100644
--- a/src/forgeai/models/vault.py
+++ b/src/forgeai/models/vault.py
@@ -18,20 +18,21 @@ maison) :
   blob = MAGIC | salt(16) | nonce(16) | tag(32) | ct
 Unicité (salt, nonce) aléatoires par scellement → pas de réutilisation de flux.
 Vérification du tag en temps constant (hmac.compare_digest) avant tout déchiffrement.
 """
 from __future__ import annotations
 
 import hashlib
 import hmac
 import os
 import secrets
+import stat
 from pathlib import Path
 
 from forgeai.models._locking import (
     MODELS_TRANSACTION_JOURNAL,
     MODELS_TRANSACTION_LOCK,
     _paths_identify_same_file,
     atomic_write_text,
     file_lock,
     recover_models_transaction_locked,
 )
@@ -42,20 +43,62 @@ _NONCE = 16
 _TAG = 32
 # Revue aveugle 3 vendors (DeepSeek/Grok/Gemini) : N=2^14 jugé bas pour une attaque
 # hors-ligne sur blob volé (cible « au repos ») → relevé à 2^16 (~67 Mo, <1 s, portable).
 _SCRYPT = dict(n=2 ** 16, r=8, p=1, dklen=64, maxmem=128 * 1024 * 1024)
 
 
 class VaultError(Exception):
     """Tag invalide : passphrase erronée ou données altérées."""
 
 
+def atomic_write_secret_text(
+    path: Path, payload: str, *, mode: int = 0o600
+) -> None:
+    """Remplace un fichier secret atomiquement sans suivre une cible symlink."""
+    path = Path(path)
+    try:
+        target = path.lstat()
+    except FileNotFoundError:
+        target = None
+    if target is not None and stat.S_ISLNK(target.st_mode):
+        raise OSError("refus d'écrire un secret via un lien symbolique")
+    atomic_write_text(path, payload, mode=mode)
+
+
+def republish_existing_secret_file(path: Path, *, mode: int = 0o600) -> None:
+    """Relit un secret régulier sans suivre de lien, puis le republie atomiquement."""
+    no_follow = getattr(os, "O_NOFOLLOW", None)
+    if no_follow is None:
+        raise OSError("ouverture sans suivi de lien indisponible")
+    flags = os.O_RDONLY | no_follow
+    flags |= getattr(os, "O_CLOEXEC", 0)
+    flags |= getattr(os, "O_NONBLOCK", 0)
+    # S2083 est un faux positif : cible locale de bootstrap choisie par
+    # l'opérateur, ouverte O_NOFOLLOW puis validée comme fichier régulier avant
+    # lecture; la publication passe ensuite par le writer atomique.
+    descriptor = os.open(Path(path), flags)  # NOSONAR S2083
+    try:
+        target = os.fstat(descriptor)
+        if not stat.S_ISREG(target.st_mode):
+            raise OSError("refus de republier un secret non régulier")
+        content = bytearray()
+        while chunk := os.read(descriptor, 8_192):
+            content.extend(chunk)
+    finally:
+        os.close(descriptor)
+    try:
+        payload = bytes(content).decode("utf-8")
+    except UnicodeDecodeError:
+        raise OSError("secret existant non UTF-8") from None
+    atomic_write_secret_text(path, payload, mode=mode)
+
+
 def _keystream(enc_key: bytes, nonce: bytes, length: int) -> bytes:
     out = bytearray()
     counter = 0
     while len(out) < length:
         block = hmac.new(enc_key, nonce + counter.to_bytes(8, "big"), hashlib.sha256).digest()
         out.extend(block)
         counter += 1
     return bytes(out[:length])
 
 
@@ -107,21 +150,21 @@ class Vault:
         import json
         if not self.path.exists():
             return {}
         return json.loads(self.path.read_text(encoding="utf-8"))
 
     def _save(self, data: dict[str, str]) -> None:
         import json
         self.path.parent.mkdir(parents=True, exist_ok=True)
         os.chmod(self.path.parent, 0o700)
         payload = json.dumps(data, ensure_ascii=False, indent=1)
-        atomic_write_text(self.path, payload, mode=0o600)
+        atomic_write_secret_text(self.path, payload, mode=0o600)
 
     def _with_secret(
         self, name: str, secret: str, passphrase: str
     ) -> tuple[dict[str, str], str]:
         """Prépare une nouvelle image du coffre sans l'écrire."""
         import base64
 
         data = self._load()
         blob = seal(secret.encode("utf-8"), passphrase)
         data[name] = base64.b64encode(blob).decode("ascii")
diff --git a/tests/test_assemble_and_secrets.py b/tests/test_assemble_and_secrets.py
index 71b2352..111b50d 100644
--- a/tests/test_assemble_and_secrets.py
+++ b/tests/test_assemble_and_secrets.py
@@ -1,21 +1,30 @@
 """Tests S04 (assemblage) et S05 (bootstrap secrets)."""
+import os
 import stat
 import sys
+import threading
+from contextlib import contextmanager
+from hashlib import sha256
 from pathlib import Path
+from queue import Queue
+from secrets import token_hex
+
+import pytest
 
 sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
 
+from forgeai.bootstrap import secrets as bootstrap_secrets_module
 from forgeai.bootstrap.secrets import bootstrap_secrets
 from forgeai.core.models import RenderTarget
+from forgeai.models import vault as vault_module
 from forgeai.planner.assemble import assemble_plan, find_free_port
-
 from forgeai.resources import deploy_overlay_path
 
 DEPLOY = deploy_overlay_path()
 
 
 def test_plan_minimal_assemble_deux_services():
     plan = assemble_plan("minimal-gpu-cuda", DEPLOY, is_free=lambda p: True)
     assert {s.name for s in plan.services} == {"ollama", "vector-store"}
     assert plan.model == "qwen2.5:0.5b"
     assert plan.target is RenderTarget.COMPOSE
@@ -35,31 +44,387 @@ def test_gpu_seulement_si_profil_cuda_et_service_capable():
     assert next(s for s in cuda.services if s.name == "vector-store").gpu is False
     assert all(not s.gpu for s in cpu.services)
 
 
 def test_find_free_port_epuise_leve():
     import pytest
     with pytest.raises(RuntimeError):
         find_free_port(30000, is_free=lambda p: False)
 
 
+def _assert_generated_env_contract(content: str) -> None:
+    if "FORGEAI_API_TOKEN=" not in content:
+        raise AssertionError("generated env is missing API token")
+    token = content.splitlines()[0].split("=", 1)[1]
+    if len(token) != 64:  # 256 bits hex
+        raise AssertionError("generated API token length is invalid")
+
+
 def test_secrets_generes_permissions_0600(tmp_path):
     paths = bootstrap_secrets(tmp_path)
     for p in (paths["env"], paths["token_key"]):
         assert p.exists()
         assert stat.S_IMODE(p.stat().st_mode) == 0o600
     content = paths["env"].read_text(encoding="utf-8")
-    assert "FORGEAI_API_TOKEN=" in content
-    token = content.splitlines()[0].split("=", 1)[1]
-    assert len(token) == 64  # 256 bits hex
+    _assert_generated_env_contract(content)
+
+
+def test_generated_env_contract_failures_never_disclose_content():
+    sentinel = token_hex(20)
+    cases = (
+        (
+            f"UNRELATED={sentinel}\n",
+            "generated env is missing API token",
+        ),
+        (
+            f"FORGEAI_API_TOKEN={sentinel}\n",
+            "generated API token length is invalid",
+        ),
+    )
+    for content, expected_message in cases:
+        with pytest.raises(AssertionError) as caught:
+            _assert_generated_env_contract(content)
+        if sentinel in str(caught.value):
+            raise AssertionError("env contract failure disclosed secret content")
+        if str(caught.value) != expected_message:
+            raise AssertionError("env contract failure was not neutral")
 
 
 def test_bootstrap_idempotent_sans_regen(tmp_path):
     first = bootstrap_secrets(tmp_path)["env"].read_text(encoding="utf-8")
     second = bootstrap_secrets(tmp_path)["env"].read_text(encoding="utf-8")
-    assert first == second
+    if first != second:
+        raise AssertionError("bootstrap changed existing secrets without regen")
 
 
 def test_regen_change_les_secrets(tmp_path):
     first = bootstrap_secrets(tmp_path)["env"].read_text(encoding="utf-8")
     regen = bootstrap_secrets(tmp_path, regen=True)["env"].read_text(encoding="utf-8")
-    assert first != regen
+    if first == regen:
+        raise AssertionError("bootstrap regen did not replace existing secrets")
+
+
+def test_bootstrap_refuses_env_symlink_without_touching_referent(tmp_path):
+    referent = tmp_path / "external-env"
+    referent.write_text("EXTERNAL=unchanged\n", encoding="utf-8")
+    target = tmp_path / ".env"
+    target.symlink_to(referent)
+    original_link = os.readlink(target)
+
+    with pytest.raises(OSError):
+        bootstrap_secrets(tmp_path, regen=True)
+
+    assert target.is_symlink()
+    assert os.readlink(target) == original_link
+    assert referent.read_text(encoding="utf-8") == "EXTERNAL=unchanged\n"
+
+
+def test_existing_token_key_symlink_swap_cannot_touch_external_inode(
+    tmp_path, monkeypatch
+):
+    out_dir = tmp_path / "out"
+    secrets_dir = out_dir / "secrets"
+    secrets_dir.mkdir(parents=True)
+    key_path = secrets_dir / "forgeai_token.key"
+    saved_key = secrets_dir / "original-token.key"
+    key_path.write_text(token_hex(32) + "\n", encoding="utf-8")
+    os.chmod(key_path, 0o640)
+    key_digest = sha256(key_path.read_bytes()).digest()
+
+    external = tmp_path / "external-token.key"
+    external.write_text(token_hex(32) + "\n", encoding="utf-8")
+    os.chmod(external, 0o640)
+    external_digest = sha256(external.read_bytes()).digest()
+    external_mode = stat.S_IMODE(external.stat().st_mode)
+
+    real_open = os.open
+    real_chmod = os.chmod
+    swapped = False
+
+    def swap_target_once() -> None:
+        nonlocal swapped
+        if swapped:
+            return
+        key_path.rename(saved_key)
+        key_path.symlink_to(external)
+        swapped = True
+
+    def open_after_swap(path, flags, *args, **kwargs):
+        if Path(path) == key_path:
+            swap_target_once()
+        return real_open(path, flags, *args, **kwargs)
+
+    def chmod_after_swap(path, mode, *args, **kwargs):
+        if Path(path) == key_path:
+            swap_target_once()
+        return real_chmod(path, mode, *args, **kwargs)
+
+    monkeypatch.setattr(bootstrap_secrets_module.os, "open", open_after_swap)
+    monkeypatch.setattr(bootstrap_secrets_module.os, "chmod", chmod_after_swap)
+
+    with pytest.raises(OSError):
+        bootstrap_secrets(out_dir)
+
+    assert swapped, "test did not inject the target swap"
+    assert key_path.is_symlink(), "swapped target is no longer a symlink"
+    assert stat.S_IMODE(external.stat().st_mode) == external_mode
+    if sha256(external.read_bytes()).digest() != external_digest:
+        raise AssertionError("writer changed external symlink referent content")
+    if sha256(saved_key.read_bytes()).digest() != key_digest:
+        raise AssertionError("writer changed the displaced original key content")
+
+
+def test_existing_token_key_hardlink_is_safely_broken_without_touching_external_inode(
+    tmp_path,
+):
+    out_dir = tmp_path / "out"
+    secrets_dir = out_dir / "secrets"
+    secrets_dir.mkdir(parents=True)
+    external = tmp_path / "external-token.key"
+    external.write_text(token_hex(32) + "\n", encoding="utf-8")
+    os.chmod(external, 0o640)
+    external_digest = sha256(external.read_bytes()).digest()
+    external_mode = stat.S_IMODE(external.stat().st_mode)
+    key_path = secrets_dir / "forgeai_token.key"
+    os.link(external, key_path)
+
+    paths = bootstrap_secrets(out_dir)
+
+    assert paths["token_key"] == key_path
+    assert key_path.stat().st_ino != external.stat().st_ino
+    assert stat.S_IMODE(key_path.stat().st_mode) == 0o600
+    assert stat.S_IMODE(external.stat().st_mode) == external_mode
+    if sha256(external.read_bytes()).digest() != external_digest:
+        raise AssertionError("writer changed external hardlink content")
+    if sha256(key_path.read_bytes()).digest() != external_digest:
+        raise AssertionError("writer did not preserve hardlinked key content")
+
+
+def test_existing_token_key_unlinked_after_open_republishes_without_mutating_alias(
+    tmp_path, monkeypatch
+):
+    out_dir = tmp_path / "out"
+    secrets_dir = out_dir / "secrets"
+    secrets_dir.mkdir(parents=True)
+    external = tmp_path / "external-token.key"
+    external.write_text(token_hex(32) + "\n", encoding="utf-8")
+    os.chmod(external, 0o640)
+    external_digest = sha256(external.read_bytes()).digest()
+    external_mode = stat.S_IMODE(external.stat().st_mode)
+    key_path = secrets_dir / "forgeai_token.key"
+    os.link(external, key_path)
+
+    descriptor_opened = threading.Event()
+    resume_writer = threading.Event()
+    writer_errors: list[str] = []
+    real_open = os.open
+
+    def open_then_pause(path, flags, *args, **kwargs):
+        descriptor = real_open(path, flags, *args, **kwargs)
+        if Path(path) == key_path:
+            descriptor_opened.set()
+            if not resume_writer.wait(timeout=5):
+                os.close(descriptor)
+                raise RuntimeError("writer did not resume after descriptor open")
+        return descriptor
+
+    monkeypatch.setattr(bootstrap_secrets_module.os, "open", open_then_pause)
+
+    def run_bootstrap() -> None:
+        try:
+            bootstrap_secrets(out_dir)
+        except (OSError, RuntimeError) as exc:
+            writer_errors.append(type(exc).__name__)
+
+    writer = threading.Thread(target=run_bootstrap, daemon=True)
+    writer.start()
+    assert descriptor_opened.wait(timeout=5), "key descriptor was not opened"
+    key_path.unlink()
+    resume_writer.set()
+    writer.join(timeout=5)
+
+    assert not writer.is_alive(), "bootstrap writer did not stop"
+    assert not writer_errors, f"bootstrap writer errors: {writer_errors}"
+    assert stat.S_IMODE(external.stat().st_mode) == external_mode
+    if sha256(external.read_bytes()).digest() != external_digest:
+        raise AssertionError("writer changed the remaining external alias content")
+    assert key_path.exists(), "bootstrap did not republish the key path"
+    assert key_path.stat().st_ino != external.stat().st_ino
+    assert stat.S_IMODE(key_path.stat().st_mode) == 0o600
+    if sha256(key_path.read_bytes()).digest() != external_digest:
+        raise AssertionError("writer did not preserve the republished key content")
+
+
+def test_non_regen_snapshot_cannot_overwrite_concurrent_regen_rotation(
+    tmp_path, monkeypatch
+):
+    out_dir = tmp_path / "out"
+    key_path = bootstrap_secrets(out_dir)["token_key"]
+    initial_digest = sha256(key_path.read_bytes()).digest()
+
+    snapshot_captured = threading.Event()
+    resume_non_regen = threading.Event()
+    start_regen = threading.Barrier(2)
+    serialization_state: Queue[str] = Queue()
+    rotated_digests: list[bytes] = []
+    worker_errors: list[str] = []
+    real_read = vault_module.os.read
+    real_atomic_write = bootstrap_secrets_module.atomic_write_secret_text
+    real_file_lock = vault_module.file_lock
+    non_regen_thread: threading.Thread | None = None
+    regen_thread: threading.Thread | None = None
+
+    def read_then_pause(descriptor: int, size: int) -> bytes:
+        chunk = real_read(descriptor, size)
+        if (
+            threading.current_thread() is non_regen_thread
+            and not chunk
+            and not snapshot_captured.is_set()
+        ):
+            snapshot_captured.set()
+            if not resume_non_regen.wait(timeout=5):
+                raise RuntimeError("non-regen bootstrap did not resume after snapshot")
+        return chunk
+
+    @contextmanager
+    def observed_file_lock(path):
+        if threading.current_thread() is regen_thread:
+            serialization_state.put("lock-attempted")
+        with real_file_lock(path):
+            yield
+
+    def observed_atomic_write(path, payload, *, mode=0o600):
+        real_atomic_write(path, payload, mode=mode)
+        if threading.current_thread() is regen_thread and Path(path) == key_path:
+            rotated_digests.append(sha256(payload.encode("utf-8")).digest())
+            serialization_state.put("published")
+
+    monkeypatch.setattr(vault_module.os, "read", read_then_pause)
+    monkeypatch.setattr(
+        bootstrap_secrets_module, "file_lock", observed_file_lock, raising=False
+    )
+    monkeypatch.setattr(
+        bootstrap_secrets_module, "atomic_write_secret_text", observed_atomic_write
+    )
+
+    def run_non_regen() -> None:
+        try:
+            bootstrap_secrets(out_dir)
+        except (OSError, RuntimeError) as exc:
+            worker_errors.append(type(exc).__name__)
+
+    def run_regen() -> None:
+        try:
+            start_regen.wait(timeout=5)
+            bootstrap_secrets(out_dir, regen=True)
+        except (OSError, RuntimeError) as exc:
+            worker_errors.append(type(exc).__name__)
+
+    non_regen_thread = threading.Thread(target=run_non_regen, daemon=True)
+    regen_thread = threading.Thread(target=run_regen, daemon=True)
+    non_regen_thread.start()
+    assert snapshot_captured.wait(timeout=5), "non-regen descriptor snapshot was not captured"
+    regen_thread.start()
+    start_regen.wait(timeout=5)
+
+    state = serialization_state.get(timeout=5)
+    try:
+        if state == "published":
+            if not rotated_digests or rotated_digests[0] == initial_digest:
+                raise AssertionError("regen did not publish a genuinely new token key")
+        elif state != "lock-attempted":
+            raise AssertionError("unexpected bootstrap serialization state")
+    finally:
+        resume_non_regen.set()
+
+    non_regen_thread.join(timeout=5)
+    regen_thread.join(timeout=5)
+    assert not non_regen_thread.is_alive(), "non-regen bootstrap did not stop"
+    assert not regen_thread.is_alive(), "regen bootstrap did not stop"
+    assert not worker_errors, f"bootstrap worker errors: {worker_errors}"
+    if not rotated_digests or rotated_digests[0] == initial_digest:
+        raise AssertionError("regen did not publish a genuinely new token key")
+    if sha256(key_path.read_bytes()).digest() != rotated_digests[0]:
+        raise AssertionError("stale non-regen snapshot replaced the rotated token key")
+
+
+def test_regen_then_non_regen_serialization_preserves_latest_rotation(
+    tmp_path, monkeypatch
+):
+    out_dir = tmp_path / "out"
+    key_path = bootstrap_secrets(out_dir)["token_key"]
+    initial_digest = sha256(key_path.read_bytes()).digest()
+
+    ordering: Queue[str] = Queue()
+    start_non_regen = threading.Barrier(2)
+    non_regen_lock_attempted = threading.Event()
+    resume_regen = threading.Event()
+    rotated_digests: list[bytes] = []
+    worker_errors: list[str] = []
+    real_atomic_write = bootstrap_secrets_module.atomic_write_secret_text
+    real_file_lock = vault_module.file_lock
+    regen_thread: threading.Thread | None = None
+    non_regen_thread: threading.Thread | None = None
+
+    @contextmanager
+    def ordered_file_lock(path):
+        if threading.current_thread() is non_regen_thread:
+            non_regen_lock_attempted.set()
+        with real_file_lock(path):
+            if threading.current_thread() is regen_thread:
+                ordering.put("locked")
+                if not resume_regen.wait(timeout=5):
+                    raise RuntimeError("regen bootstrap did not resume while holding lock")
+            yield
+
+    def observed_atomic_write(path, payload, *, mode=0o600):
+        real_atomic_write(path, payload, mode=mode)
+        if threading.current_thread() is regen_thread and Path(path) == key_path:
+            rotated_digests.append(sha256(payload.encode("utf-8")).digest())
+            ordering.put("key-published")
+
+    monkeypatch.setattr(
+        bootstrap_secrets_module, "file_lock", ordered_file_lock, raising=False
+    )
+    monkeypatch.setattr(
+        bootstrap_secrets_module, "atomic_write_secret_text", observed_atomic_write
+    )
+
+    def run_regen() -> None:
+        try:
+            bootstrap_secrets(out_dir, regen=True)
+        except (OSError, RuntimeError) as exc:
+            worker_errors.append(type(exc).__name__)
+
+    def run_non_regen() -> None:
+        try:
+            start_non_regen.wait(timeout=5)
+            bootstrap_secrets(out_dir)
+        except (OSError, RuntimeError) as exc:
+            worker_errors.append(type(exc).__name__)
+
+    regen_thread = threading.Thread(target=run_regen, daemon=True)
+    non_regen_thread = threading.Thread(target=run_non_regen, daemon=True)
+    regen_thread.start()
+    first_state = ordering.get(timeout=5)
+    if first_state != "locked":
+        regen_thread.join(timeout=5)
+        raise AssertionError("regen bootstrap did not acquire the serialization lock")
+
+    non_regen_thread.start()
+    start_non_regen.wait(timeout=5)
+    assert non_regen_lock_attempted.wait(timeout=5), "non-regen did not attempt the lock"
+    resume_regen.set()
+    regen_thread.join(timeout=5)
+    non_regen_thread.join(timeout=5)
+
+    assert not regen_thread.is_alive(), "regen bootstrap did not stop"
+    assert not non_regen_thread.is_alive(), "non-regen bootstrap did not stop"
+    assert not worker_errors, f"bootstrap worker errors: {worker_errors}"
+    if not rotated_digests or rotated_digests[0] == initial_digest:
+        raise AssertionError("regen did not publish a genuinely new token key")
+    if sha256(key_path.read_bytes()).digest() != rotated_digests[0]:
+        raise AssertionError("last serialized bootstrap did not preserve the rotated token key")
+    if {entry.name for entry in (out_dir / "secrets").iterdir()} != {
+        "forgeai_token.key"
+    }:
+        raise AssertionError("bootstrap lock artifact entered the secret directory")
diff --git a/tests/test_openbao_flow.py b/tests/test_openbao_flow.py
index a079737..5b129d6 100644
--- a/tests/test_openbao_flow.py
+++ b/tests/test_openbao_flow.py
@@ -1,44 +1,46 @@
 """S5 (#146) — stores fichier + amorçage du flux openbao, et renew_self de vault.py.
 
 Prouve (déterministe, sans cluster) : (1) FileKeyStore isole le root_token HORS du répertoire des clés
 monté à l'unsealer ; (2) FileSecretStore persiste le token applicatif en 0600 ; (3) bout-en-bout avec le
 VRAI `ensure_openbao_ready` (S2) sur un faux transport -> token applicatif rendu, stores peuplés, root jamais
 dans keys_dir ; (4) renew_self appelle POST renew-self et ne fuit jamais le token.
 """
 from __future__ import annotations
 
+import base64
 import os
 import stat
+import subprocess
 import sys
+import threading
+from hashlib import sha256
 from pathlib import Path
+from secrets import token_hex
 
 import pytest
 
 sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
 
-import base64
-import subprocess
-
+from forgeai.deploy import openbao_flow
 from forgeai.deploy.openbao_flow import (
     FileKeyStore,
     FileSecretStore,
     KubectlKeyStore,
     OpenBaoFlowError,
     initialize_openbao,
     prepare_key_store,
     wait_reachable,
 )
 from forgeai.secrets.openbao_init import ensure_openbao_ready
 from forgeai.secrets.vault import VaultError, renew_self
 
-
 # --- 1. prepare_key_store ---------------------------------------------------
 
 def test_prepare_key_store_creates_and_chmod(tmp_path) -> None:
     d = tmp_path / "keys"
     assert prepare_key_store(d) == d
     assert d.is_dir()
     assert oct(d.stat().st_mode & 0o777) == "0o711"
 
 
 def test_prepare_key_store_idempotent(tmp_path) -> None:
@@ -68,38 +70,216 @@ def test_file_key_store_write_read_and_root_isolation(tmp_path) -> None:
     assert [e.name for e in entries] == ["unseal_key"]
     unseal = (keys_dir / "unseal_key").read_text(encoding="utf-8").strip()
     assert unseal == "UNSEAL" and "ROOT" not in unseal
     assert root_path.read_text(encoding="utf-8").strip() == "ROOT"
 
     # unseal_key 0644 (lisible par le conteneur unsealer non-root) ; root_token 0600 (owner seul, isolé)
     assert stat.S_IMODE((keys_dir / "unseal_key").stat().st_mode) == 0o644
     assert stat.S_IMODE(root_path.stat().st_mode) == 0o600
 
 
+def test_file_key_store_modes_are_independent_of_permissive_umask(tmp_path) -> None:
+    keys_dir = tmp_path / "keys"
+    root_path = tmp_path / "secrets" / "root_token"
+    previous_umask = os.umask(0)
+    try:
+        FileKeyStore(keys_dir, root_path).write(
+            {"unseal_key": "UNSEAL", "root_token": "ROOT"}
+        )
+    finally:
+        os.umask(previous_umask)
+
+    assert stat.S_IMODE((keys_dir / "unseal_key").stat().st_mode) == 0o644
+    assert stat.S_IMODE(root_path.stat().st_mode) == 0o600
+
+
 # --- 3. FileSecretStore -----------------------------------------------------
 
 def test_file_secret_store_roundtrip_and_mode(tmp_path) -> None:
     p = tmp_path / "app_token.json"
     store = FileSecretStore(p)
     assert store.read() is None
     store.write({"token": "APPTOKEN"})
     assert store.read() == {"token": "APPTOKEN"}
     assert stat.S_IMODE(p.stat().st_mode) == 0o600
 
 
 def test_file_secret_store_overwrite(tmp_path) -> None:
     store = FileSecretStore(tmp_path / "t.json")
     store.write({"token": "OLD"})
     store.write({"token": "NEW"})
     assert store.read() == {"token": "NEW"}
 
 
+@pytest.mark.parametrize("requested_mode", [0o600, 0o644])
+def test_write_file_failure_before_replace_preserves_old_target_and_cleans_temp(
+    tmp_path, monkeypatch, requested_mode
+) -> None:
+    target = tmp_path / "secret"
+    target.write_text("old-value\n", encoding="utf-8")
+    sentinel = token_hex(32)
+    file_fsynced = False
+    replacement_mode = None
+    real_fsync = os.fsync
+
+    def record_real_fsync(descriptor: int) -> None:
+        nonlocal file_fsynced
+        real_fsync(descriptor)
+        if stat.S_ISREG(os.fstat(descriptor).st_mode):
+            file_fsynced = True
+
+    def fail_before_replace(source, destination) -> None:
+        nonlocal replacement_mode
+        if not file_fsynced:
+            raise AssertionError("replacement attempted before the temporary file was fsynced")
+        replacement_mode = stat.S_IMODE(Path(source).stat().st_mode)
+        raise OSError("injected failure after file fsync")
+
+    monkeypatch.setattr(openbao_flow.os, "fsync", record_real_fsync)
+    monkeypatch.setattr(openbao_flow.os, "replace", fail_before_replace)
+    previous_umask = os.umask(0)
+    try:
+        with pytest.raises(OSError) as caught:
+            openbao_flow._write_file(target, sentinel, requested_mode)
+    finally:
+        os.umask(previous_umask)
+
+    if sentinel in str(caught.value):
+        raise AssertionError("writer exception disclosed the secret payload")
+    assert replacement_mode == requested_mode
+    assert target.read_text(encoding="utf-8") == "old-value\n"
+    assert [entry.name for entry in tmp_path.iterdir()] == ["secret"]
+
+
+def test_write_file_fsyncs_file_then_parent_directory(tmp_path, monkeypatch) -> None:
+    fsync_targets: list[str] = []
+    real_fsync = os.fsync
+
+    def record_real_fsync(descriptor: int) -> None:
+        target_mode = os.fstat(descriptor).st_mode
+        real_fsync(descriptor)
+        fsync_targets.append("directory" if stat.S_ISDIR(target_mode) else "file")
+
+    monkeypatch.setattr(openbao_flow.os, "fsync", record_real_fsync)
+    openbao_flow._write_file(tmp_path / "secret", "non-secret-test-value", 0o600)
+
+    assert fsync_targets == ["file", "directory"]
+
+
+def test_file_secret_store_refuses_target_symlink_without_touching_referent(
+    tmp_path,
+) -> None:
+    referent = tmp_path / "external"
+    referent.write_text("external-old\n", encoding="utf-8")
+    target = tmp_path / "app-token.json"
+    target.symlink_to(referent)
+    original_link = os.readlink(target)
+    sentinel = token_hex(32)
+
+    with pytest.raises(OSError) as caught:
+        FileSecretStore(target).write({"token": sentinel})
+
+    if sentinel in str(caught.value):
+        raise AssertionError("writer exception disclosed the secret payload")
+    assert target.is_symlink()
+    assert os.readlink(target) == original_link
+    assert referent.read_text(encoding="utf-8") == "external-old\n"
+
+
+def test_file_secret_store_replacements_never_expose_partial_content(tmp_path) -> None:
+    target = tmp_path / "app-token.json"
+    store = FileSecretStore(target)
+    token_a = "A" * 65_536
+    token_b = "B" * 65_536
+    complete_a = '{"token": "' + token_a + '"}\n'
+    complete_b = '{"token": "' + token_b + '"}\n'
+    allowed_digests = {
+        sha256(complete_a.encode("utf-8")).digest(),
+        sha256(complete_b.encode("utf-8")).digest(),
+    }
+    store.write({"token": token_a})
+
+    start = threading.Barrier(3)
+    readers_started = [threading.Event(), threading.Event()]
+    stop = threading.Event()
+    observed_digests: set[bytes] = set()
+    read_errors: list[str] = []
+    observation_lock = threading.Lock()
+
+    def reader(started: threading.Event) -> None:
+        try:
+            start.wait()
+            first = sha256(target.read_bytes()).digest()
+            with observation_lock:
+                observed_digests.add(first)
+            started.set()
+            while not stop.is_set():
+                digest = sha256(target.read_bytes()).digest()
+                with observation_lock:
+                    observed_digests.add(digest)
+        except (OSError, RuntimeError) as exc:
+            with observation_lock:
+                read_errors.append(type(exc).__name__)
+            started.set()
+
+    readers = [
+        threading.Thread(target=reader, args=(started,), daemon=True)
+        for started in readers_started
+    ]
+    for thread in readers:
+        thread.start()
+    start.wait()
+    for started in readers_started:
+        assert started.wait(timeout=5), "reader did not reach the synchronized start"
+
+    try:
+        for index in range(1_000):
+            store.write({"token": token_a if index % 2 == 0 else token_b})
+    finally:
+        stop.set()
+        for thread in readers:
+            thread.join(timeout=5)
+
+    assert all(not thread.is_alive() for thread in readers), "reader did not stop"
+    assert not read_errors, f"reader errors: {read_errors}"
+    assert observed_digests
+    unexpected_digests = observed_digests - allowed_digests
+    assert not unexpected_digests, (
+        f"readers observed {len(unexpected_digests)} incomplete content digest(s)"
+    )
+
+
+def test_file_secret_store_unwritable_directory_fails_without_secret_leak(
+    tmp_path,
+) -> None:
+    directory = tmp_path / "locked"
+    directory.mkdir()
+    target = directory / "app-token.json"
+    sentinel = token_hex(32)
+    os.chmod(directory, 0o500)
+    try:
+        try:
+            FileSecretStore(target).write({"token": sentinel})
+        except OSError as exc:
+            if sentinel in str(exc):
+                raise AssertionError("writer exception disclosed the secret payload")
+            assert not target.exists()
+        else:
+            target.unlink(missing_ok=True)
+            effective_uid = getattr(os, "geteuid", lambda: -1)()
+            assert effective_uid == 0, (
+                "non-root process unexpectedly bypassed directory permissions"
+            )
+    finally:
+        os.chmod(directory, 0o700)
+
+
 # --- 4. Bout-en-bout avec le VRAI ensure_openbao_ready (S2) ------------------
 
 def _fake_transport():
     """request(method, path, *, token=None, payload=None) -> (status, body) simulant openbao."""
     state = {"mounts": False, "policy": False}
 
     def request(method, path, *, token=None, payload=None):
         if path == "/v1/sys/seal-status":
             return (200, {"initialized": False, "sealed": True})
         if path == "/v1/sys/init":
diff --git a/tests/test_vault.py b/tests/test_vault.py
index 11cbef5..04adc33 100644
--- a/tests/test_vault.py
+++ b/tests/test_vault.py
@@ -1,27 +1,30 @@
 """Story E3b — client coffre openbao (KV v2), stdlib pur.
 
 Spec exécutable (TDAD, AVANT le code). Un faux serveur openbao KV v2 (http.server) valide le
 contrat HTTP réel : écriture `POST /v1/secret/data/<path>` + lecture `GET …` authentifiées par
 en-tête `X-Vault-Token`. Le comportement contre un openbao RÉEL est prouvé par l'e2e journalisé
 au registre. Invariant secrets : ni le token ni la valeur ne doivent apparaître dans une exception.
 """
 import json
+import os
 import sys
 import threading
 from http.server import BaseHTTPRequestHandler, HTTPServer
 from pathlib import Path
+from secrets import token_hex
 
 import pytest
 
 sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
 
+from forgeai.models.vault import Vault as FileVault
 from forgeai.secrets.vault import VaultError, read, store
 
 TOKEN = "root-token-e3b"
 
 
 class _KVHandler(BaseHTTPRequestHandler):
     """openbao KV v2 minimal : exige le bon X-Vault-Token, stocke/rend sous data.data."""
 
     store: dict = {}
 
@@ -97,12 +100,30 @@ def test_mauvais_token_leve_vaulterror(bao):
 
 
 def test_exception_ne_fuit_ni_token_ni_valeur(bao):
     # openbao injoignable : le message d'erreur ne doit contenir ni le token ni la valeur secrète.
     secret_value = "sk-ne-doit-pas-fuiter"  # proof:allow — valeur de test
     try:
         store("http://127.0.0.1:1", "TOKEN-CONFIDENTIEL", "forgeai/x", {"k": secret_value})
         raise AssertionError("aurait dû lever VaultError")
     except VaultError as exc:
         msg = str(exc)
-        assert "TOKEN-CONFIDENTIEL" not in msg
-        assert secret_value not in msg
+        if "TOKEN-CONFIDENTIEL" in msg or secret_value in msg:
+            raise AssertionError("VaultError disclosed a secret input")
+
+
+def test_model_vault_refuses_target_symlink_without_touching_referent(tmp_path):
+    referent = tmp_path / "external-vault.json"
+    referent.write_text('{"external": "unchanged"}', encoding="utf-8")
+    target = tmp_path / "vault.json"
+    target.symlink_to(referent)
+    original_link = os.readlink(target)
+    sentinel = token_hex(32)
+
+    with pytest.raises(OSError) as caught:
+        FileVault(target).put("cloud-key", sentinel, "test-passphrase")
+
+    if sentinel in str(caught.value):
+        raise AssertionError("vault exception disclosed the secret payload")
+    assert target.is_symlink()
+    assert os.readlink(target) == original_link
+    assert referent.read_text(encoding="utf-8") == '{"external": "unchanged"}'

