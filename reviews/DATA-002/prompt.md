Tu es reviewer de code. Analyse l'ARTEFACT ci-dessous pour sa correction et sa sécurité.

Sortie STRICTE — réponds UNIQUEMENT un objet JSON valide, rien avant, rien après :
{"verdict":"APPROVE ou REJECT","objections":[{"severity":"critique|eleve|moyen|faible","file":"chemin","line":entier ou null,"desc":"défaut réel et vérifiable"}]}

Règles :
- N'indique aucune préférence de verdict. Ne suppose rien.
- Ne liste que des défauts RÉELS et vérifiables (correction, sécurité, fuite de secret,
  régression, réutilisation cryptographique, timing). Liste vide si aucun.
- `verdict` = "APPROVE" si et seulement si tu n'identifies aucun défaut de sévérité
  critique ou élevé ; sinon "REJECT".

STORY : DATA-002
CRITÈRES D'ACCEPTATION :
# [DATA-002] Rendre RouteStore transactionnel, verrouillé et atomique

## Identité immuable

- **Dépôt:** `https://github.com/leon36000/ForgeAI-Toolkit`
- **Owner/repo attendu:** `leon36000/ForgeAI-Toolkit`
- **Branche cible:** `main`
- **Branche de travail exacte:** `fix/DATA-002-routestore-atomic-transaction`
- **Exécuteur autorisé dans ce paquet:** `CODEX`
- **Lane exclusive:** `routes-store`
- **Statut:** `READY_AFTER`
- **Priorité:** `P1_CRITICAL`
- **Sévérité:** `S1_HIGH`
- **Milestone:** `M1-CRITICAL`

## Règle de statut

Le package reste bloqué jusqu’à fusion de toutes ses dépendances et création du claim canonique.

## Objectif unique

Éliminer lost updates, lectures tronquées et clés orphelines par une transaction locale couvrant routes.json et le coffre avec verrou unique, écriture temporaire, fsync et os.replace.

## Findings sources

- `FAI-U-002`

Le baseline de l’audit est `251f0682bf9d0ffde9f7fd7ab6c7c9f5bad1cd3e` (`tree 587de9c293183c776417ea9d5afdfc1ba5501d2c`), mais **la branche doit partir du dernier `origin/main` après fusion des dépendances**. Avant de modifier, vérifier si le défaut existe encore. S’il est déjà corrigé, produire un rapport `ALREADY_FIXED` avec preuves et ne pas créer de patch artificiel.

## Dépendances

- `ORCH-001` — propriétaire `COPILOT` — doit être **fusionné dans `main`** avant création de cette branche.

## Périmètre autorisé

- `src/forgeai/models/routes.py`
- `src/forgeai/models/_locking.py`
- `src/forgeai/models/vault.py`
- `tests/test_routestore_concurrence.py`
- `tests/test_models_cloud.py`
- `tests/test_models_cli.py`
- `stories/DATA-002.md`
- `reviews/DATA-002/**`
- `Registres/PATCH-DATA-002.jsonl`

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

- `pytest -q tests/test_routestore_concurrence.py tests/test_models_cloud.py tests/test_models_cli.py`

## Critères d’acceptation

- [ ] 100 répétitions concurrentes ne perdent aucune mise à jour et ne produisent aucun JSON invalide.
- [ ] Une collision add/configure donne un résultat déterministe ou une erreur métier claire.
- [ ] Une panne avant replace conserve l’ancien fichier complet.
- [ ] Aucune clé de coffre n’est laissée orpheline si la route ne peut être commitée.

## Tests négatifs

- [ ] SIGKILL entre write et replace.
- [ ] Deux configure_cache sur la même route.
- [ ] add_cloud et configure_cache concurrents.

## Tests de sécurité

- [ ] Exécuter au minimum GitGuardian/Gitleaks et les contrôles de sécurité pertinents.

## Tests de performance

- [ ] Le verrou ne couvre pas le probe réseau distant; contention mesurée.

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
PACKAGE: DATA-002
REPOSITORY: https://github.com/leon36000/ForgeAI-Toolkit
BRANCH: fix/DATA-002-routestore-atomic-transaction
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

ARTEFACT — /Users/nathanst-louis/Documents/Codex/2026-07-25/e/work/DATA-002-review-final.diff :
diff --git a/src/forgeai/models/_locking.py b/src/forgeai/models/_locking.py
index 473d2fd0c66b08591d9cd358be388f98fdd53ae3..152e6ebcfc40b1b5c8d8aab8b35511c5d3c1c16e 100644
--- a/src/forgeai/models/_locking.py
+++ b/src/forgeai/models/_locking.py
@@ -1,20 +1,173 @@
-"""Verrouillage fichier inter-process et inter-thread."""
+"""Verrouillage et remplacement atomique de fichiers locaux."""

 import fcntl
+import json
+import os
+import stat
+import tempfile
 from contextlib import contextmanager
 from pathlib import Path

+MODELS_TRANSACTION_LOCK = ".models-transaction"
+MODELS_TRANSACTION_JOURNAL = ".models-transaction.json"
+

 @contextmanager
 def file_lock(path: Path):
     """Context manager de verrou exclusif sur un fichier .lock associé à `path`."""
     path = Path(path)
     path.parent.mkdir(parents=True, exist_ok=True)
-    lock_path = str(path) + ".lock"
-    fd = open(lock_path, "w")
+    lock_path = Path(str(path) + ".lock")
+    try:
+        existing = lock_path.lstat()
+    except FileNotFoundError:
+        existing = None
+    if existing is not None and not stat.S_ISREG(existing.st_mode):
+        raise OSError(f"le verrou n'est pas un fichier régulier: {lock_path}")
+
+    flags = os.O_RDWR | os.O_CREAT
+    flags |= getattr(os, "O_CLOEXEC", 0)
+    flags |= getattr(os, "O_NOFOLLOW", 0)
+    descriptor = os.open(lock_path, flags, 0o600)
+    locked = False
     try:
-        fcntl.flock(fd.fileno(), fcntl.LOCK_EX)
+        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
+            raise OSError(f"le verrou n'est pas un fichier régulier: {lock_path}")
+        fcntl.flock(descriptor, fcntl.LOCK_EX)
+        locked = True
         yield
     finally:
-        fcntl.flock(fd.fileno(), fcntl.LOCK_UN)
-        fd.close()
+        try:
+            if locked:
+                fcntl.flock(descriptor, fcntl.LOCK_UN)
+        finally:
+            os.close(descriptor)
+
+
+def _fsync_directory(path: Path) -> None:
+    """Persiste les changements de nom du répertoire contenant un fichier."""
+    directory_fd = os.open(path, os.O_RDONLY)
+    try:
+        os.fsync(directory_fd)
+    finally:
+        os.close(directory_fd)
+
+
+def atomic_write_text(path: Path, payload: str, *, mode: int = 0o600) -> None:
+    """Écrit, fsync puis remplace `path`; l'ancien fichier reste intact avant replace."""
+    path = Path(path)
+    path.parent.mkdir(parents=True, exist_ok=True)
+    fd, temporary_name = tempfile.mkstemp(
+        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
+    )
+    temporary = Path(temporary_name)
+    descriptor_open = True
+    try:
+        os.fchmod(fd, mode)
+        with os.fdopen(fd, "w", encoding="utf-8") as stream:
+            descriptor_open = False
+            stream.write(payload)
+            stream.flush()
+            os.fsync(stream.fileno())
+        os.replace(temporary, path)
+        _fsync_directory(path.parent)
+    except BaseException:
+        if descriptor_open:
+            os.close(fd)
+        temporary.unlink(missing_ok=True)
+        raise
+
+
+def atomic_unlink(path: Path) -> None:
+    """Supprime un fichier puis persiste le changement de répertoire."""
+    path = Path(path)
+    try:
+        path.unlink()
+    except FileNotFoundError:
+        return
+    _fsync_directory(path.parent)
+
+
+def _journal_vault_path(home: Path, snapshot: dict) -> Path:
+    """Retourne le nom canonique lexical sans suivre un éventuel symlink injecté."""
+    vault_name = snapshot.get("vault_name", "vault.json")
+    if vault_name != "vault.json":
+        raise ValueError("identité de coffre invalide dans le journal")
+    return Path(os.path.abspath(Path(home) / vault_name))
+
+
+def _paths_identify_same_file(left: Path, right: Path) -> bool:
+    """Compare deux chemins en tenant compte des symlinks, hardlinks et de la casse."""
+    try:
+        return Path(left).samefile(right)
+    except OSError:
+        return Path(left).resolve(strict=False) == Path(right).resolve(strict=False)
+
+
+def _restore_vault_image(path: Path, snapshot: dict) -> None:
+    if snapshot["vault_existed"]:
+        atomic_write_text(
+            path,
+            json.dumps(snapshot["vault"], ensure_ascii=False, indent=1),
+            mode=0o600,
+        )
+    else:
+        atomic_unlink(path)
+
+
+def restore_models_transaction_locked(
+    home: Path, vault_path: Path, snapshot: dict
+) -> None:
+    """Restaure les deux fichiers; conserve le journal si une restauration échoue."""
+    home = Path(home)
+    requested_vault_path = Path(os.path.abspath(vault_path))
+    canonical_vault_path = _journal_vault_path(home, snapshot)
+    if not _paths_identify_same_file(
+        requested_vault_path, canonical_vault_path
+    ):
+        raise ValueError("le coffre demandé ne correspond pas au journal")
+    routes_path = home / "routes.json"
+    journal_path = home / MODELS_TRANSACTION_JOURNAL
+    rollback_error: Exception | None = None
+
+    try:
+        _restore_vault_image(canonical_vault_path, snapshot)
+        if (
+            requested_vault_path != canonical_vault_path
+            and not requested_vault_path.is_symlink()
+        ):
+            _restore_vault_image(requested_vault_path, snapshot)
+    except (OSError, TypeError, ValueError, KeyError) as exc:
+        rollback_error = exc
+
+    try:
+        if snapshot["routes_existed"]:
+            atomic_write_text(
+                routes_path,
+                json.dumps(snapshot["routes"], ensure_ascii=False, indent=1),
+                mode=0o600,
+            )
+        else:
+            atomic_unlink(routes_path)
+    except (OSError, TypeError, ValueError, KeyError) as exc:
+        if rollback_error is None:
+            rollback_error = exc
+
+    if rollback_error is not None:
+        raise rollback_error
+    atomic_unlink(journal_path)
+
+
+def recover_models_transaction_locked(home: Path, vault_path: Path) -> bool:
+    """Récupère le write-ahead journal sous le verrou modèles déjà détenu."""
+    home = Path(home)
+    journal_path = home / MODELS_TRANSACTION_JOURNAL
+    if not journal_path.exists():
+        return False
+    snapshot = json.loads(journal_path.read_text(encoding="utf-8"))
+    if not _paths_identify_same_file(
+        Path(vault_path), _journal_vault_path(home, snapshot)
+    ):
+        return False
+    restore_models_transaction_locked(home, vault_path, snapshot)
+    return True
diff --git a/src/forgeai/models/routes.py b/src/forgeai/models/routes.py
index 78f49a30e283cb47cc706987ce0dc0715e00deb1..b468505cbad2f7d53a8d988a31e1e6e2c0ad8192 100644
--- a/src/forgeai/models/routes.py
+++ b/src/forgeai/models/routes.py
@@ -14,7 +14,16 @@ from dataclasses import asdict, dataclass, replace
 from datetime import date
 from pathlib import Path

-from forgeai.models._locking import file_lock
+from forgeai.models._locking import (
+    MODELS_TRANSACTION_JOURNAL,
+    MODELS_TRANSACTION_LOCK,
+    atomic_unlink,
+    atomic_write_text,
+    file_lock,
+    recover_models_transaction_locked,
+    restore_models_transaction_locked,
+)
+
 from .probe import ProbeResult, Transport, UrllibTransport, probe_route
 from .vault import Vault

@@ -57,6 +66,9 @@ class RouteStore:
         self.home = Path(home)
         self.routes_path = self.home / "routes.json"
         self.vault = Vault(self.home / "vault.json")
+        self.transaction_lock_path = self.home / MODELS_TRANSACTION_LOCK
+        self.transaction_journal_path = self.home / MODELS_TRANSACTION_JOURNAL
+        self._recover_pending_transaction()

     def _load(self) -> list[dict]:
         if not self.routes_path.exists():
@@ -65,8 +77,42 @@ class RouteStore:

     def _save(self, routes: list[dict]) -> None:
         self.home.mkdir(parents=True, exist_ok=True)
-        self.routes_path.write_text(
-            json.dumps(routes, ensure_ascii=False, indent=1), encoding="utf-8")
+        atomic_write_text(
+            self.routes_path,
+            json.dumps(routes, ensure_ascii=False, indent=1),
+            mode=0o600,
+        )
+
+    def _transaction_snapshot(
+        self, routes: list[dict], vault: dict[str, str]
+    ) -> dict:
+        return {
+            "routes_existed": self.routes_path.exists(),
+            "routes": routes,
+            "vault_name": self.vault.path.name,
+            "vault_existed": self.vault.path.exists(),
+            "vault": vault,
+        }
+
+    def _write_transaction_journal(self, snapshot: dict) -> None:
+        atomic_write_text(
+            self.transaction_journal_path,
+            json.dumps(snapshot, ensure_ascii=False, sort_keys=True),
+            mode=0o600,
+        )
+
+    def _rollback_transaction(self, snapshot: dict) -> None:
+        restore_models_transaction_locked(self.home, self.vault.path, snapshot)
+
+    def _recover_pending_transaction(self) -> None:
+        if not self.transaction_journal_path.exists():
+            return
+        with file_lock(self.transaction_lock_path):
+            self._recover_pending_transaction_locked()
+
+    def _recover_pending_transaction_locked(self) -> None:
+        """Récupère un write-ahead journal alors que le verrou commun est détenu."""
+        recover_models_transaction_locked(self.home, self.vault.path)

     def _route_from_dict(self, r: dict) -> CloudRoute:
         known = {f.name for f in CloudRoute.__dataclass_fields__.values()}
@@ -88,45 +134,68 @@ class RouteStore:
                   passphrase: str, *, base_url: str | None = None,
                   transport: Transport | None = None) -> tuple[CloudRoute, ProbeResult]:
         """Ajoute une route APRÈS test réel. En cas d'échec : RouteError, rien n'est écrit."""
-        if any(r["name"] == name for r in self._load()):
-            raise RouteError(f"route '{name}' existe déjà")
+        with file_lock(self.transaction_lock_path):
+            self._recover_pending_transaction_locked()
+            if any(r["name"] == name for r in self._load()):
+                raise RouteError(f"route '{name}' existe déjà")
         resolved = self.resolve_base_url(provenance, base_url)
         result = probe_route(resolved, model_id, api_key, transport or UrllibTransport())
         if not result.ok:
             # Aucune route cassée n'est ajoutée ; la clé n'a jamais touché le disque.
             raise RouteError(f"test de connexion {result.light} : {result.detail}")
-        fp = self.vault.put(name, api_key, passphrase)  # clé scellée (chiffrée)
-        route = CloudRoute(name=name, provenance=provenance, base_url=resolved,
-                           model_id=model_id, key_fingerprint=fp,
-                           created_at=date.today().isoformat())
-        with file_lock(self.routes_path):
+        with file_lock(self.transaction_lock_path):
+            self._recover_pending_transaction_locked()
             routes = self._load()
             if any(r["name"] == name for r in routes):
                 raise RouteError(f"route '{name}' existe déjà")
-            routes.append(route.public_dict())
-            self._save(routes)
+            previous_vault = self.vault._load()
+            next_vault, fp = self.vault._with_secret(name, api_key, passphrase)
+            route = CloudRoute(
+                name=name,
+                provenance=provenance,
+                base_url=resolved,
+                model_id=model_id,
+                key_fingerprint=fp,
+                created_at=date.today().isoformat(),
+            )
+            snapshot = self._transaction_snapshot(routes, previous_vault)
+            next_routes = [*routes, route.public_dict()]
+            self._write_transaction_journal(snapshot)
+            try:
+                self.vault._save(next_vault)
+                self._save(next_routes)
+            except BaseException:
+                self._rollback_transaction(snapshot)
+                raise
+            atomic_unlink(self.transaction_journal_path)
         return route, result

     def list(self) -> list[CloudRoute]:
-        return [self._route_from_dict(r) for r in self._load()]
+        with file_lock(self.transaction_lock_path):
+            self._recover_pending_transaction_locked()
+            return [self._route_from_dict(r) for r in self._load()]

     def get(self, name: str) -> CloudRoute:
-        for r in self._load():
-            if r["name"] == name:
-                return self._route_from_dict(r)
+        with file_lock(self.transaction_lock_path):
+            self._recover_pending_transaction_locked()
+            for r in self._load():
+                if r["name"] == name:
+                    return self._route_from_dict(r)
         raise RouteError(f"route '{name}' introuvable")

     def configure_cache(self, name: str, enabled: bool, ttl_s: int | None = None,
                         prefix: str | None = None) -> CloudRoute:
         if ttl_s is not None and ttl_s < 0:
             raise RouteError("ttl_s doit être positif ou nul")
-        routes = self._load()
-        index = next((i for i, r in enumerate(routes) if r["name"] == name), None)
-        if index is None:
-            raise RouteError(f"route '{name}' introuvable")
-        old_route = self._route_from_dict(routes[index])
-        new_route = replace(old_route, cache=enabled, cache_ttl_s=ttl_s,
-                            cache_prefix=prefix)
-        routes[index] = new_route.public_dict()
-        self._save(routes)
+        with file_lock(self.transaction_lock_path):
+            self._recover_pending_transaction_locked()
+            routes = self._load()
+            index = next((i for i, r in enumerate(routes) if r["name"] == name), None)
+            if index is None:
+                raise RouteError(f"route '{name}' introuvable")
+            old_route = self._route_from_dict(routes[index])
+            new_route = replace(old_route, cache=enabled, cache_ttl_s=ttl_s,
+                                cache_prefix=prefix)
+            routes[index] = new_route.public_dict()
+            self._save(routes)
         return new_route
diff --git a/src/forgeai/models/vault.py b/src/forgeai/models/vault.py
index 4c90fd3ecae32ad8a537e48932de6879204529ba..54da090d25c1817125618e6f9cc854b8f1146d3d 100644
--- a/src/forgeai/models/vault.py
+++ b/src/forgeai/models/vault.py
@@ -27,7 +27,14 @@ import os
 import secrets
 from pathlib import Path

-from forgeai.models._locking import file_lock
+from forgeai.models._locking import (
+    MODELS_TRANSACTION_JOURNAL,
+    MODELS_TRANSACTION_LOCK,
+    _paths_identify_same_file,
+    atomic_write_text,
+    file_lock,
+    recover_models_transaction_locked,
+)

 MAGIC = b"FGV1"
 _SALT = 16
@@ -93,6 +100,8 @@ class Vault:

     def __init__(self, path: Path) -> None:
         self.path = Path(path)
+        self.transaction_lock_path = self.path.parent / MODELS_TRANSACTION_LOCK
+        self.transaction_journal_path = self.path.parent / MODELS_TRANSACTION_JOURNAL

     def _load(self) -> dict[str, str]:
         import json
@@ -105,27 +114,52 @@ class Vault:
         self.path.parent.mkdir(parents=True, exist_ok=True)
         os.chmod(self.path.parent, 0o700)
         payload = json.dumps(data, ensure_ascii=False, indent=1)
-        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
-        with os.fdopen(fd, "w", encoding="utf-8") as f:
-            f.write(payload)
-        os.chmod(self.path, 0o600)
+        atomic_write_text(self.path, payload, mode=0o600)
+
+    def _with_secret(
+        self, name: str, secret: str, passphrase: str
+    ) -> tuple[dict[str, str], str]:
+        """Prépare une nouvelle image du coffre sans l'écrire."""
+        import base64
+
+        data = self._load()
+        blob = seal(secret.encode("utf-8"), passphrase)
+        data[name] = base64.b64encode(blob).decode("ascii")
+        return data, fingerprint(secret)
+
+    def _recover_pending_transaction_locked(self) -> None:
+        canonical_vault_path = self.path.parent / "vault.json"
+        path_is_canonical_alias = _paths_identify_same_file(
+            self.path, canonical_vault_path
+        )
+        recovery_path = (
+            self.path if path_is_canonical_alias else canonical_vault_path
+        )
+        recovered = recover_models_transaction_locked(
+            self.path.parent, recovery_path
+        )
+        if recovered and path_is_canonical_alias:
+            self.path = canonical_vault_path

     def put(self, name: str, secret: str, passphrase: str) -> str:
         """Scelle `secret` sous `name`. Retourne l'empreinte (jamais le secret)."""
-        import base64
-        with file_lock(self.path):
-            data = self._load()
-            blob = seal(secret.encode("utf-8"), passphrase)
-            data[name] = base64.b64encode(blob).decode("ascii")
+        with file_lock(self.transaction_lock_path):
+            self._recover_pending_transaction_locked()
+            data, secret_fingerprint = self._with_secret(name, secret, passphrase)
             self._save(data)
-        return fingerprint(secret)
+        return secret_fingerprint

     def get(self, name: str, passphrase: str) -> str:
         import base64
-        data = self._load()
+
+        with file_lock(self.transaction_lock_path):
+            self._recover_pending_transaction_locked()
+            data = self._load()
         if name not in data:
             raise KeyError(name)
         return unseal(base64.b64decode(data[name]), passphrase).decode("utf-8")

     def names(self) -> list[str]:
-        return sorted(self._load())
+        with file_lock(self.transaction_lock_path):
+            self._recover_pending_transaction_locked()
+            return sorted(self._load())
diff --git a/src/forgeai/portability.py b/src/forgeai/portability.py
index f5cb6cd13c6782ca3511c7665ba9240363e65e05..e6b64a99999b88f199df7df894013b82f5cd1c95 100644
--- a/src/forgeai/portability.py
+++ b/src/forgeai/portability.py
@@ -16,12 +16,21 @@ Round-trip prouvé : un export suivi d'un import dans un répertoire vierge
 restaure exactement le même état (hors secrets).
 """

-import json
 import hashlib
-from pathlib import Path
+import json
 from datetime import date
+from pathlib import Path
 from typing import List

+from forgeai.models._locking import (
+    MODELS_TRANSACTION_JOURNAL,
+    MODELS_TRANSACTION_LOCK,
+    _paths_identify_same_file,
+    atomic_write_text,
+    file_lock,
+    recover_models_transaction_locked,
+)
+
 BUNDLE_VERSION = 1
 SETUP_FILES = ("routes.json", "gateway.json", "wirings.json", "strategy.json", "budgets.json")
 EXCLUDED_FILES = frozenset({"vault.json"})
@@ -66,6 +75,36 @@ def _validate_route(route: dict) -> None:
         raise PortabilityError(f"Champs non autorisés dans une route : {extra}")


+def _validate_export_destination(home: Path, out_path: Path | None) -> None:
+    """Interdit qu'un bundle remplace un fichier vivant du setup ou de sa transaction."""
+    if out_path is None:
+        return
+    protected_names = set(SETUP_FILES) | EXCLUDED_FILES | {
+        MODELS_TRANSACTION_JOURNAL,
+        f"{MODELS_TRANSACTION_LOCK}.lock",
+    }
+    protected_paths = [
+        (home / name).resolve(strict=False) for name in protected_names
+    ]
+    resolved_out = out_path.resolve(strict=False)
+    lexical_parent = out_path.parent.resolve(strict=False)
+    same_directory_case_alias = (
+        _paths_identify_same_file(lexical_parent, home.resolve(strict=False))
+        and out_path.name.casefold()
+        in {name.casefold() for name in protected_names}
+    )
+    if (
+        same_directory_case_alias
+        or any(
+            _paths_identify_same_file(resolved_out, protected)
+            for protected in protected_paths
+        )
+    ):
+        raise PortabilityError(
+            "La destination d'export chevauche un fichier protégé du setup"
+        )
+
+
 def export_setup(home, out_path=None) -> dict:
     """Exporte tous les fichiers de setup (sans secrets) vers un dict bundle.

@@ -79,34 +118,43 @@ def export_setup(home, out_path=None) -> dict:
     ou si une route contient un secret en clair.
     """
     home = Path(home)
+    out_path = Path(out_path) if out_path is not None else None
+    _validate_export_destination(home, out_path)
     files = {}

-    for fname in SETUP_FILES:
-        file_path = home / fname
-        if not file_path.exists():
-            continue
-
-        # Lecture
-        try:
-            with open(file_path, "r", encoding="utf-8") as fh:
-                content = json.load(fh)
-        except Exception as exc:
-            raise PortabilityError(f"Erreur lors du chargement de {fname} : {exc}") from exc
-
-        # Validation stricte pour routes.json
-        if fname == "routes.json":
-            if not isinstance(content, list):
-                raise PortabilityError("routes.json doit être une liste de routes")
-            for route in content:
-                if not isinstance(route, dict):
-                    raise PortabilityError("Chaque élément de routes.json doit être un dict")
-                _validate_route(route)
-
-        # Garde‑fou supplémentaire
-        if fname in EXCLUDED_FILES:
-            raise PortabilityError(f"Le fichier exclu {fname} ne doit jamais être exporté")
-
-        files[fname] = content
+    with file_lock(home / MODELS_TRANSACTION_LOCK):
+        # Un export ne peut observer une route encore révocable par un WAL.
+        recover_models_transaction_locked(home, home / "vault.json")
+
+        for fname in SETUP_FILES:
+            file_path = home / fname
+            if not file_path.exists():
+                continue
+
+            try:
+                with open(file_path, "r", encoding="utf-8") as fh:
+                    content = json.load(fh)
+            except Exception as exc:
+                raise PortabilityError(
+                    f"Erreur lors du chargement de {fname} : {exc}"
+                ) from exc
+
+            if fname == "routes.json":
+                if not isinstance(content, list):
+                    raise PortabilityError("routes.json doit être une liste de routes")
+                for route in content:
+                    if not isinstance(route, dict):
+                        raise PortabilityError(
+                            "Chaque élément de routes.json doit être un dict"
+                        )
+                    _validate_route(route)
+
+            if fname in EXCLUDED_FILES:
+                raise PortabilityError(
+                    f"Le fichier exclu {fname} ne doit jamais être exporté"
+                )
+
+            files[fname] = content

     created_at = date.today().isoformat()
     sha = bundle_sha256(files, created_at)
@@ -118,9 +166,16 @@ def export_setup(home, out_path=None) -> dict:
     }

     if out_path is not None:
-        out_path = Path(out_path)
-        with open(out_path, "w", encoding="utf-8") as fh:
-            json.dump(bundle, fh, indent=1, ensure_ascii=False)
+        try:
+            atomic_write_text(
+                out_path,
+                json.dumps(bundle, indent=1, ensure_ascii=False),
+                mode=0o600,
+            )
+        except OSError as exc:
+            raise PortabilityError(
+                f"Erreur lors de l'écriture du bundle : {exc}"
+            ) from exc

     return bundle

@@ -183,28 +238,36 @@ def import_setup(bundle_path, home, *, force=False) -> dict:
     home = Path(home)
     home.mkdir(parents=True, exist_ok=True)

-    # Vérification préalable (si force=False) – aucune écriture avant cette étape
-    if not force:
-        conflicts = []
-        for fname in files:
-            dest = home / fname
-            if dest.exists():
-                conflicts.append(fname)
-        if conflicts:
-            raise PortabilityError(
-                f"Fichiers déjà présents dans {home} : {', '.join(conflicts)}. Utilisez force=True pour écraser."
-            )
-
-    # Écriture effective
     restored = []
-    for fname, content in files.items():
-        # Défense en profondeur : ne jamais écrire un nom hors whitelist (vault.json, '..', absolu)
-        if not _safe_name(fname):
-            continue
-        dest = home / fname
-        with open(dest, "w", encoding="utf-8") as fh:
-            json.dump(content, fh, indent=1, ensure_ascii=False)
-        restored.append(fname)
+    with file_lock(home / MODELS_TRANSACTION_LOCK):
+        # Un import doit d'abord terminer toute transaction RouteStore/Vault
+        # interrompue, puis partager le même verrou avec leurs lecteurs/writers.
+        recover_models_transaction_locked(home, home / "vault.json")
+
+        # Vérification préalable (si force=False) – aucune écriture avant cette étape
+        if not force:
+            conflicts = []
+            for fname in files:
+                dest = home / fname
+                if dest.exists():
+                    conflicts.append(fname)
+            if conflicts:
+                raise PortabilityError(
+                    f"Fichiers déjà présents dans {home} : {', '.join(conflicts)}. "
+                    "Utilisez force=True pour écraser."
+                )
+
+        # Chaque remplacement est atomique; routes.json reste sérialisé avec RouteStore.
+        for fname, content in files.items():
+            # Défense en profondeur : jamais de nom hors whitelist.
+            if not _safe_name(fname):
+                continue
+            atomic_write_text(
+                home / fname,
+                json.dumps(content, indent=1, ensure_ascii=False),
+                mode=0o600,
+            )
+            restored.append(fname)

     secrets = secrets_to_reprovision(bundle)
     return {
diff --git a/stories/DATA-002.md b/stories/DATA-002.md
new file mode 100644
index 0000000000000000000000000000000000000000..2022c957d8fc3a3f4c5d0542653647e0efbb5fdf
--- /dev/null
+++ b/stories/DATA-002.md
@@ -0,0 +1,179 @@
+# DATA-002 — Transaction locale RouteStore/Vault
+
+## Calibration
+
+- Profil : `PROOF-Team`
+- Risque : `T2`
+- Branche : `fix/DATA-002-routestore-atomic-transaction`
+- Base initiale : `c14430057823cdc9eb6f0d5ae22ed84dd8a4b8d1`
+- Base finale après synchronisation : `7a1fbf1478e3dd89c5fbd0b4fa5e9da25726ac25`
+- Issue : `#164`
+- Claim Codex : tracé dans le ledger PROOF externe
+
+## Cause racine vérifiée
+
+Le correctif historique `FAI-0010` protège séparément les read-modify-write de
+`routes.json` et `vault.json`. Il ne crée pas de transaction commune :
+
+1. `configure_cache` charge puis réécrit `routes.json` sans verrou ;
+2. `RouteStore._save` et `Vault._save` tronquent directement le fichier cible ;
+3. `add_cloud` persiste la clé au coffre avant le commit de la route, sans
+   compensation si ce commit échoue ;
+4. les locks distincts de `routes.json` et `vault.json` ne sérialisent pas une
+   opération qui touche les deux ressources ;
+5. `forgeai import` et `forgeai export` accèdent à `routes.json` hors du verrou
+   commun et peuvent respectivement écraser une mutation ou publier un état
+   encore révocable par le journal ;
+6. la récupération acceptait le chemin de n’importe quelle instance `Vault`,
+   ce qui permettait à un coffre voisin de consommer le WAL canonique ;
+7. la destination `export --out` pouvait chevaucher les routes, le coffre ou le
+   WAL, et les alias de fichiers pouvaient contourner l’identité canonique ;
+8. l’ouverture du verrou en mode `w` suivait un symlink injecté et tronquait sa
+   cible avant même l’acquisition du verrou ;
+9. la résolution du dernier composant de `export --out` effaçait le nom lexical
+   fourni et permettait à un symlink portant une variante de casse protégée de
+   contourner le contrôle sur un volume sensible à la casse.
+
+La baseline ciblée existante passe 24 tests en environnement autorisant le
+loopback, mais elle ne couvre pas ces interleavings ni les pannes avant rename.
+
+## Hypothèse testée
+
+Un verrou de transaction unique pour le répertoire modèles, combiné à des
+écritures temporaires `fsync` puis `os.replace`, doit rendre chaque fichier
+atomique et sérialiser `add_cloud`, `configure_cache` et `Vault.put`. Si le
+commit de route échoue après l’écriture du coffre, un journal durable contenant
+l’état antérieur doit permettre de restaurer les deux fichiers sous le même
+verrou, y compris après l’arrêt brutal du processus.
+
+## Preuves RED attendues
+
+- 100 `configure_cache` concurrents perdent des mises à jour ou lisent un JSON
+  tronqué avec l’implémentation actuelle ;
+- un `add_cloud` suspendu pendant son commit écrase une configuration
+  concurrente ;
+- une panne injectée dans `os.replace` ne touche pas l’ancien fichier ;
+- un échec du commit de route ne laisse aucune clé orpheline.
+- un `SIGKILL` entre le remplacement du coffre et celui des routes est récupéré
+  automatiquement à la prochaine ouverture du `RouteStore` ;
+- un import suspendu à son commit écrase un `add_cloud` et un
+  `configure_cache` concurrents ;
+- un `Vault(home/"autre.json")` consomme le WAL de `RouteStore` et laisse la
+  clé canonique orpheline ;
+- un export effectué avant la suppression du WAL publie une route non commitée.
+
+## Implémentation
+
+- verrou commun `.models-transaction.lock` pour les mutations et lectures
+  `RouteStore`/`Vault`, ouvert sans troncature ni suivi du dernier symlink et
+  validé comme fichier régulier avant `flock` ;
+- écriture temporaire dans le même répertoire, permissions `0600`, `fsync` du
+  fichier, `os.replace`, puis `fsync` du répertoire ;
+- write-ahead journal `.models-transaction.json` contenant l’état antérieur
+  chiffré du coffre, les anciennes routes et l’identité canonique `vault.json` ;
+- rollback idempotent après exception ou reprise à la première opération d’une
+  instance neuve ou déjà existante ;
+- probe réseau exécuté hors verrou, entre le précontrôle atomique et le commit ;
+- import et export sérialisés avec la transaction RouteStore, récupération du
+  WAL avant lecture/écriture et remplacements atomiques `0600` à l’import ;
+- refus de restaurer un WAL vers tout coffre autre que le `vault.json` auquel
+  le journal est explicitement lié ;
+- comparaison d’identité par inode (`samefile`) pour les alias casse/symlink/
+  hardlink, restauration du canon et de l’alias avant suppression du WAL ;
+- conservation du chemin canonique lexical lors du rollback afin qu’un symlink
+  injecté sur `vault.json` soit remplacé/supprimé sans jamais suivre sa cible ;
+- rejet de toute destination d’export chevauchant un fichier vivant du setup,
+  y compris alias inode, variantes de casse et combinaison variante de casse +
+  symlink du nom lexical fourni, puis écriture atomique `fsync`/`os.replace` du
+  bundle.
+
+## Extension de périmètre tracée
+
+Trois revues OpenAI indépendantes ont découvert que le writer CLI de production
+`src/forgeai/portability.py` contournait le verrou DATA-002. Ce fichier n’était
+pas dans l’allowlist initiale. L’extension n’a pas été silencieuse : elle a été
+annoncée comme STOP au cockpit, puis couverte par l’autorisation explicite de
+Nathan d’effectuer toutes les corrections nécessaires jusqu’à complétion. Le
+delta hors allowlist est limité à ce fichier et au chemin réel du défaut.
+
+## Résultats vérifiés
+
+- 67 tests ciblés : PASS ;
+- 19 tests de concurrence et de panne, avec dix arrêts `SIGKILL` réels
+  répartis sur les fenêtres de commit : PASS ;
+- 100 configurations concurrentes, lecteur JSON brut actif et probe hors
+  verrou : PASS en `0,31 s` ;
+- suite complète locale du delta final : tous les tests DATA-002 et UI passent ;
+  l’unique échec restant est le faux serveur `tests/test_immudb.py`, qui
+  réinitialise la connexion indépendamment de ce diff ; couverture globale
+  `89,74 %` (seuil `85 %`) ;
+- `forgeai/core/registre.py` : `98 %` (seuil `95 %`) ;
+- no-stub, registres, catalogue et gate des revues existantes : PASS ;
+- Gitleaks `8.30.1`, scan du worktree complet : aucune fuite.
+
+Le premier passage complet a exposé une instabilité préexistante du faux serveur
+`tests/test_immudb.py` (socket réinitialisée parce que le handler ne consomme pas
+le corps de la requête d’audit). Le second passage complet est vert. Ce fichier
+est hors périmètre DATA-002 et n’a pas été modifié.
+
+La revue de code Codex interne a d’abord rejeté le patch pour deux fenêtres de
+course supplémentaires : une opération `Vault` après crash pouvait être
+acquittée puis annulée, et le premier contrôle de doublon n’était pas atomique
+avec la récupération. Les deux constats ont été reproduits en rouge, corrigés,
+puis re-revus sans constat critique ou important.
+
+Trois autres revues OpenAI indépendantes ont ensuite rejeté le candidat
+`f1b1a825` pour le writer import/export hors transaction, le détournement du WAL
+par un coffre voisin et le pack de revue périmé. Chaque défaut fonctionnel a été
+reproduit en rouge puis corrigé. Ces revues ne sont pas présentées comme trois
+fournisseurs distincts et ne satisfont donc pas artificiellement une exigence
+multi-vendeurs.
+
+Le premier tour final sur le pack `23ec2b…` a encore découvert deux défauts
+importants : collision de `export --out` avec l’état vivant et alias du coffre
+sur volume insensible à la casse. Les reproductions CLI, case-insensitive/
+hardlink et les corrections sont incluses dans le nouveau candidat; le pack
+`23ec2b…` est donc superseded et doit être régénéré.
+
+Le tour suivant sur `b3bf0e…` a détecté le suivi dangereux d’un symlink
+canonique pendant un rollback et les variantes `Routes.json`/`Vault.json` sur
+un volume insensible à la casse. Un test SIGKILL prouve désormais qu’une cible
+externe reste byte-identique et quatre tests CLI couvrent ces alias; le pack
+`b3bf0e…` est superseded à son tour.
+
+Le tour sur `f65636…` a approuvé la concurrence, puis rejeté deux chemins de
+sécurité encore réels : troncature d’une cible externe par symlink du verrou et
+perte du nom lexical d’un alias casse+symlink à l’export. Les cinq régressions
+ont été exécutées en RED/GREEN; l’ouverture du verrou est désormais fail-closed
+et le contrôle de destination conserve le nom fourni. Le pack `f65636…` est
+superseded et une nouvelle revue exacte est obligatoire.
+
+## Rollback
+
+Le rollback de données est couvert par :
+
+- échec injecté avant `os.replace` pour `routes.json` et `vault.json` ;
+- échec du commit route après écriture du coffre ;
+- `SIGKILL` entre le remplacement du coffre et celui des routes, avec état vide
+  puis état préexistant ;
+- récupération depuis une instance `RouteStore` créée avant le crash.
+
+Le rollback Git du candidat fonctionnel final
+`6fa26714a8bd7fa6bdd60db87b7fce561fe7b53c`
+a été rejoué dans un worktree éphémère isolé : tous les commits de
+`origin/main..HEAD` ont été inversés sans commit, puis `git diff --exit-code
+origin/main` a confirmé une identité exacte. Les 24 tests ciblés de la base
+passent (`sha256:03b0266c7ace109634ff7cf710bf4d3fd9c177be220281a8ef1a4fe375d276d6`) ;
+le worktree de preuve a ensuite été supprimé.
+
+## Limite plateforme
+
+Le verrou repose sur `fcntl`, et les tests de crash utilisent `fork`/`SIGKILL` :
+la transaction reste donc explicitement POSIX. Cette contrainte existait avant
+DATA-002 ; aucun support Windows non prouvé n’est revendiqué.
+
+## Gates encore externes
+
+Le nouveau SHA doit encore repasser SonarQube, GitGuardian, CodeRabbit et la CI.
+La merge queue n’est pas configurée sur le dépôt ; Nathan a autorisé une fusion
+directe tracée. Aucun verdict multi-vendeur n’est préfabriqué localement.
diff --git a/tests/test_models_cli.py b/tests/test_models_cli.py
index 3043a391f761ccef75ed9ca1584a1d5d7c7598a7..7840084871bfb1e4bdb9edc7d253670325d931a8 100644
--- a/tests/test_models_cli.py
+++ b/tests/test_models_cli.py
@@ -92,3 +92,88 @@ def test_cli_add_cloud_echec_reseau_rien_ajoute(tmp_path, monkeypatch, capsys):
     assert not (home / "routes.json").exists()
     err = capsys.readouterr().err
     assert "ECHEC ROUTE" in err and SECRET not in err
+
+
+@pytest.mark.parametrize(
+    "protected_name",
+    [
+        "routes.json",
+        "vault.json",
+        "gateway.json",
+        ".models-transaction.json",
+        ".models-transaction.lock",
+        "Routes.json",
+        "Vault.json",
+        ".Models-Transaction.json",
+        ".Models-Transaction.lock",
+    ],
+)
+def test_cli_export_refuse_ecraser_un_fichier_protege(
+    tmp_path, protected_name, capsys
+):
+    """--out ne peut jamais viser l'état vivant du répertoire exporté."""
+    home = tmp_path / "models"
+    home.mkdir()
+    (home / "routes.json").write_text("[]", encoding="utf-8")
+    (home / "vault.json").write_text('{"sentinelle":"coffre"}', encoding="utf-8")
+    (home / "gateway.json").write_text('{"sentinelle":"gateway"}', encoding="utf-8")
+    protected = home / protected_name
+    before = protected.read_bytes() if protected.exists() else None
+
+    rc = main(
+        [
+            "export",
+            "--home",
+            str(home),
+            "--out",
+            str(protected),
+            "--registre",
+            str(tmp_path / "registre.jsonl"),
+        ]
+    )
+
+    assert rc == 11
+    assert "ECHEC EXPORT" in capsys.readouterr().err
+    if before is None:
+        assert not protected.exists() or protected.read_bytes() == b""
+    else:
+        assert protected.read_bytes() == before
+
+
+@pytest.mark.parametrize(
+    "protected_name",
+    [
+        "Routes.json",
+        "Vault.json",
+        ".Models-Transaction.json",
+        ".Models-Transaction.lock",
+    ],
+)
+def test_cli_export_refuse_alias_casse_protege_meme_si_symlink(
+    tmp_path, protected_name, capsys
+):
+    """Le nom lexical protégé reste interdit quand le dernier composant est un lien."""
+    home = tmp_path / "models"
+    home.mkdir()
+    external = tmp_path / f"externe-{protected_name.replace('/', '-')}"
+    external_payload = b'{"externe":true}'
+    external.write_bytes(external_payload)
+    protected_alias = home / protected_name
+    protected_alias.symlink_to(external)
+
+    rc = main(
+        [
+            "export",
+            "--home",
+            str(home),
+            "--out",
+            str(protected_alias),
+            "--registre",
+            str(tmp_path / "registre.jsonl"),
+        ]
+    )
+
+    assert rc == 11
+    assert "ECHEC EXPORT" in capsys.readouterr().err
+    assert protected_alias.is_symlink()
+    assert external.read_bytes() == external_payload
diff --git a/tests/test_models_cloud.py b/tests/test_models_cloud.py
index 14e8926294f83c4cdb2a7439ffebb75385c498ec..d0bcb0d938b93eeb71eaf1020c64e62e336b9428 100644
--- a/tests/test_models_cloud.py
+++ b/tests/test_models_cloud.py
@@ -228,6 +228,119 @@ def test_configure_cache_route_inconnue(tmp_path):
         RouteStore(tmp_path).configure_cache("absente", True)


+def test_configure_cache_replace_echoue_conserve_ancien_fichier(
+    tmp_path, monkeypatch
+):
+    route_dict = {
+        "name": "r",
+        "provenance": "openrouter",
+        "base_url": "https://openrouter.ai/api/v1",
+        "model_id": "m",
+        "key_fingerprint": "sha256:abcd",
+        "created_at": "2026-07-16",
+    }
+    path = tmp_path / "routes.json"
+    path.write_text(json.dumps([route_dict]), encoding="utf-8")
+    before = path.read_bytes()
+    real_replace = os.replace
+
+    def fail_route_replace(src, dst):
+        if os.fspath(dst) == os.fspath(path):
+            raise OSError("panne injectee avant replace routes")
+        return real_replace(src, dst)
+
+    monkeypatch.setattr(os, "replace", fail_route_replace)
+    store = RouteStore(tmp_path)
+    with pytest.raises(OSError, match="avant replace routes"):
+        store.configure_cache("r", True, 60, "cache")
+
+    assert path.read_bytes() == before
+    assert RouteStore(tmp_path).get("r").cache is False
+
+
+def test_vault_replace_echoue_conserve_ancien_fichier(tmp_path, monkeypatch):
+    vault = Vault(tmp_path / "vault.json")
+    vault.put("existante", "secret-existant", "pp")
+    before = vault.path.read_bytes()
+    real_replace = os.replace
+
+    def fail_vault_replace(src, dst):
+        if os.fspath(dst) == os.fspath(vault.path):
+            raise OSError("panne injectee avant replace vault")
+        return real_replace(src, dst)
+
+    monkeypatch.setattr(os, "replace", fail_vault_replace)
+    with pytest.raises(OSError, match="avant replace vault"):
+        vault.put("nouvelle", "secret-nouveau", "pp")
+
+    assert vault.path.read_bytes() == before
+    assert vault.names() == ["existante"]
+    assert vault.get("existante", "pp") == "secret-existant"
+
+
+def test_add_cloud_echec_commit_route_compense_la_cle_vault(
+    tmp_path, monkeypatch
+):
+    store = RouteStore(tmp_path)
+
+    def fail_route_commit(routes):
+        raise OSError("commit routes impossible")
+
+    monkeypatch.setattr(store, "_save", fail_route_commit)
+    with pytest.raises(OSError, match="commit routes impossible"):
+        store.add_cloud(
+            "orpheline",
+            "openrouter",
+            "m",
+            SECRET,
+            "pp",
+            transport=GREEN,
+        )
+
+    assert "orpheline" not in store.vault.names()
+    assert store.list() == []
+
+
+def test_add_cloud_rollback_restaure_vault_meme_si_routes_reste_indisponible(
+    tmp_path, monkeypatch
+):
+    store = RouteStore(tmp_path)
+    store.add_cloud(
+        "existante",
+        "openrouter",
+        "m",
+        "secret-existant",
+        "pp",
+        transport=GREEN,
+    )
+    real_replace = os.replace
+
+    def fail_every_route_replace(src, dst):
+        if os.fspath(dst) == os.fspath(store.routes_path):
+            raise OSError("routes indisponible")
+        return real_replace(src, dst)
+
+    monkeypatch.setattr(os, "replace", fail_every_route_replace)
+    with pytest.raises(OSError, match="routes indisponible"):
+        store.add_cloud(
+            "orpheline",
+            "openrouter",
+            "m",
+            "secret-orphelin",
+            "pp",
+            transport=GREEN,
+        )
+
+    assert sorted(store.vault._load()) == ["existante"]
+    assert store.transaction_journal_path.exists()
+
+    monkeypatch.undo()
+    recovered = RouteStore(tmp_path)
+    assert [route.name for route in recovered.list()] == ["existante"]
+    assert recovered.vault.names() == ["existante"]
+    assert not recovered.transaction_journal_path.exists()
+
+
 def test_cli_route_configure(tmp_path):
     import json
     from forgeai.cli import main
diff --git a/tests/test_routestore_concurrence.py b/tests/test_routestore_concurrence.py
index b50267fb75b3efc806be3fc05662d88207cca910..dee8b916eadbbc5444b6e01e52035701c933db1f 100644
--- a/tests/test_routestore_concurrence.py
+++ b/tests/test_routestore_concurrence.py
@@ -5,13 +5,20 @@ puis la dernière écriture écrase l'autre : des routes ET des clés API scell
 Spécification : N ajouts concurrents de routes distinctes ⇒ les N routes sont persistées, et les N
 clés sont retrouvables au coffre. RED avant correctif : lost-update (moins de N).
 """
+import builtins
 import json
 import multiprocessing as mp
+import os
+import signal
 import threading
 from pathlib import Path

-from forgeai.models.routes import RouteStore
-from forgeai.models.vault import Vault
+import pytest
+
+from forgeai.models._locking import file_lock
+from forgeai.models.routes import RouteError, RouteStore
+from forgeai.models.vault import Vault, fingerprint
+from forgeai.portability import bundle_sha256, export_setup, import_setup

 FAKE_KEY = "sk-fake-DO-NOT-LEAK"

@@ -28,6 +35,140 @@ def _add_one(home_str: str, i: int, barrier) -> None:
                     transport=_GreenTransport())


+def _add_named(home_str: str, done) -> None:
+    RouteStore(Path(home_str)).add_cloud(
+        "ajoutee",
+        "openrouter",
+        "m",
+        FAKE_KEY,
+        "pp-coffre",
+        transport=_GreenTransport(),
+    )
+    done.set()
+
+
+def _configure_named(home_str: str, done) -> None:
+    RouteStore(Path(home_str)).configure_cache("existante", True, 60, "cache")
+    done.set()
+
+
+def _import_pause_before_routes_commit(
+    bundle_path: str, home_str: str, ready, release
+) -> None:
+    """Suspend l'import à sa primitive de commit, quel que soit le writer utilisé."""
+    target = Path(home_str) / "routes.json"
+    real_open = builtins.open
+    real_replace = os.replace
+
+    def paused_open(path, mode="r", *args, **kwargs):
+        if os.fspath(path) == os.fspath(target) and "w" in mode:
+            ready.set()
+            if not release.wait(timeout=10):
+                raise RuntimeError("import non libéré")
+        return real_open(path, mode, *args, **kwargs)
+
+    def paused_replace(src, dst):
+        if os.fspath(dst) == os.fspath(target):
+            ready.set()
+            if not release.wait(timeout=10):
+                raise RuntimeError("import non libéré")
+        return real_replace(src, dst)
+
+    builtins.open = paused_open
+    os.replace = paused_replace
+    import_setup(bundle_path, home_str, force=True)
+
+
+def _configure_pause_before_replace(home_str: str, ready) -> None:
+    """Processus victime : attend indéfiniment juste avant le rename atomique."""
+    target = Path(home_str) / "routes.json"
+    real_replace = os.replace
+
+    def paused_replace(src, dst):
+        if os.fspath(dst) == os.fspath(target):
+            ready.set()
+            threading.Event().wait()
+        return real_replace(src, dst)
+
+    os.replace = paused_replace
+    RouteStore(Path(home_str)).configure_cache("route", True, 60, "cache")
+
+
+def _add_cloud_pause_before_routes_replace(home_str: str, ready) -> None:
+    """Processus victime : coffre remplacé, puis attente avant le replace des routes."""
+    target = Path(home_str) / "routes.json"
+    real_replace = os.replace
+
+    def paused_replace(src, dst):
+        if os.fspath(dst) == os.fspath(target):
+            ready.set()
+            threading.Event().wait()
+        return real_replace(src, dst)
+
+    os.replace = paused_replace
+    RouteStore(Path(home_str)).add_cloud(
+        "orpheline",
+        "openrouter",
+        "m",
+        FAKE_KEY,
+        "pp-coffre",
+        transport=_GreenTransport(),
+    )
+
+
+def _add_cloud_pause_before_vault_replace(home_str: str, ready) -> None:
+    """Processus victime : WAL durable, attente avant le premier replace du coffre."""
+    target = Path(home_str) / "vault.json"
+    real_replace = os.replace
+
+    def paused_replace(src, dst):
+        if os.fspath(dst) == os.fspath(target):
+            ready.set()
+            threading.Event().wait()
+        return real_replace(src, dst)
+
+    os.replace = paused_replace
+    RouteStore(Path(home_str)).add_cloud(
+        "orpheline",
+        "openrouter",
+        "m",
+        FAKE_KEY,
+        "pp-coffre",
+        transport=_GreenTransport(),
+    )
+
+
+def _add_cloud_pause_before_journal_unlink(home_str: str, ready) -> None:
+    """Processus victime : les deux fichiers sont commités, le journal est encore présent."""
+    target = Path(home_str) / ".models-transaction.json"
+    real_unlink = os.unlink
+
+    def paused_unlink(path, *args, **kwargs):
+        if os.fspath(path) == os.fspath(target):
+            ready.set()
+            threading.Event().wait()
+        return real_unlink(path, *args, **kwargs)
+
+    os.unlink = paused_unlink
+    RouteStore(Path(home_str)).add_cloud(
+        "orpheline",
+        "openrouter",
+        "m",
+        FAKE_KEY,
+        "pp-coffre",
+        transport=_GreenTransport(),
+    )
+
+
+def _add_cloud_wait_then_pause_before_journal_unlink(
+    home_str: str, start, ready
+) -> None:
+    """Attend le signal parent; le processus est forké avant les threads du test."""
+    if not start.wait(timeout=10):
+        raise RuntimeError("signal de départ absent")
+    _add_cloud_pause_before_journal_unlink(home_str, ready)
+
+
 def test_add_cloud_concurrent_ne_perd_aucune_route(tmp_path):
     """N process ajoutent des routes distinctes en parallèle ⇒ les N sont persistées."""
     home = tmp_path / "models"
@@ -48,6 +189,71 @@ def test_add_cloud_concurrent_ne_perd_aucune_route(tmp_path):
         assert store.vault.get(f"route-{i}", "pp-coffre") == FAKE_KEY


+def test_import_add_et_configure_partagent_le_verrou_interprocessus(tmp_path):
+    """L'import ne peut écraser ni l'ajout ni la configuration concurrents."""
+    home = tmp_path / "models"
+    home.mkdir()
+    route = {
+        "name": "existante",
+        "provenance": "openrouter",
+        "base_url": "https://openrouter.ai/api/v1",
+        "model_id": "m",
+        "key_fingerprint": "sha256:0000000000000000",
+        "created_at": "2026-07-25",
+        "cache": False,
+        "cache_ttl_s": None,
+        "cache_prefix": None,
+    }
+    (home / "routes.json").write_text(json.dumps([route]), encoding="utf-8")
+    created_at = "2026-07-25"
+    files = {"routes.json": [route]}
+    bundle = {
+        "version": 1,
+        "created_at": created_at,
+        "files": files,
+        "sha256": bundle_sha256(files, created_at),
+    }
+    bundle_path = tmp_path / "bundle.json"
+    bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
+
+    ctx = mp.get_context("fork")
+    import_ready = ctx.Event()
+    release_import = ctx.Event()
+    add_done = ctx.Event()
+    configure_done = ctx.Event()
+    importer = ctx.Process(
+        target=_import_pause_before_routes_commit,
+        args=(str(bundle_path), str(home), import_ready, release_import),
+    )
+    importer.start()
+    assert import_ready.wait(timeout=5), "l'import n'a pas atteint son commit"
+
+    adder = ctx.Process(target=_add_named, args=(str(home), add_done))
+    configurator = ctx.Process(
+        target=_configure_named, args=(str(home), configure_done)
+    )
+    adder.start()
+    configurator.start()
+
+    # Sans verrou commun, les deux RMW finissent avant l'import puis sont écrasés.
+    add_done.wait(timeout=2)
+    configure_done.wait(timeout=2)
+    release_import.set()
+
+    for process in (importer, adder, configurator):
+        process.join(timeout=10)
+        assert not process.is_alive()
+        assert process.exitcode == 0
+
+    persisted = {item.name: item for item in RouteStore(home).list()}
+    assert sorted(persisted) == ["ajoutee", "existante"]
+    assert (
+        persisted["existante"].cache,
+        persisted["existante"].cache_ttl_s,
+        persisted["existante"].cache_prefix,
+    ) == (True, 60, "cache")
+
+
 def test_vault_put_concurrent_ne_perd_aucune_cle(tmp_path):
     """T threads scellent des secrets distincts en parallèle ⇒ tous retrouvables."""
     vault = Vault(tmp_path / "vault.json")
@@ -66,3 +272,645 @@ def test_vault_put_concurrent_ne_perd_aucune_cle(tmp_path):

     for i in range(T):
         assert vault.get(f"k-{i}", "pp") == f"secret-{i}"
+
+
+def test_configure_cache_100_ecritures_concurrentes_sont_toutes_persistees(tmp_path):
+    """100 RMW concurrents sur des routes distinctes ne perdent aucune configuration."""
+    home = tmp_path / "models"
+    home.mkdir()
+    route_count = 100
+    routes = [
+        {
+            "name": f"route-{i}",
+            "provenance": "openrouter",
+            "base_url": "https://openrouter.ai/api/v1",
+            "model_id": "m",
+            "key_fingerprint": f"sha256:{i:016x}",
+            "created_at": "2026-07-25",
+        }
+        for i in range(route_count)
+    ]
+    (home / "routes.json").write_text(json.dumps(routes), encoding="utf-8")
+    barrier = threading.Barrier(route_count)
+    errors: list[Exception] = []
+    errors_lock = threading.Lock()
+    reader_stop = threading.Event()
+    reader_started = threading.Event()
+
+    def reader() -> None:
+        reader_started.set()
+        while not reader_stop.is_set():
+            try:
+                persisted = json.loads((home / "routes.json").read_text())
+            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
+                with errors_lock:
+                    errors.append(exc)
+                return
+            if not isinstance(persisted, list):
+                with errors_lock:
+                    errors.append(TypeError("routes.json doit contenir une liste"))
+                return
+
+    reader_thread = threading.Thread(target=reader)
+    reader_thread.start()
+    assert reader_started.wait(timeout=2)
+
+    def worker(i: int) -> None:
+        barrier.wait()
+        try:
+            RouteStore(home).configure_cache(
+                f"route-{i}", True, ttl_s=i, prefix=f"prefix-{i}"
+            )
+        except Exception as exc:  # la liste rend les erreurs de thread observables
+            with errors_lock:
+                errors.append(exc)
+
+    threads = [threading.Thread(target=worker, args=(i,)) for i in range(route_count)]
+    for thread in threads:
+        thread.start()
+    for thread in threads:
+        thread.join(timeout=10)
+        assert not thread.is_alive(), "configure_cache est resté bloqué"
+    reader_stop.set()
+    reader_thread.join(timeout=5)
+
+    assert errors == []
+    persisted = {route.name: route for route in RouteStore(home).list()}
+    assert len(persisted) == route_count
+    for i in range(route_count):
+        route = persisted[f"route-{i}"]
+        assert (route.cache, route.cache_ttl_s, route.cache_prefix) == (
+            True,
+            i,
+            f"prefix-{i}",
+        )
+
+
+def test_add_cloud_et_configure_cache_partagent_la_meme_transaction(
+    tmp_path, monkeypatch
+):
+    """Un add bloqué ne peut pas écraser une configuration concurrente déjà persistée."""
+    home = tmp_path / "models"
+    home.mkdir()
+    (home / "routes.json").write_text(
+        json.dumps(
+            [
+                {
+                    "name": "existante",
+                    "provenance": "openrouter",
+                    "base_url": "https://openrouter.ai/api/v1",
+                    "model_id": "m",
+                    "key_fingerprint": "sha256:0000000000000000",
+                    "created_at": "2026-07-25",
+                }
+            ]
+        ),
+        encoding="utf-8",
+    )
+    add_store = RouteStore(home)
+    config_store = RouteStore(home)
+    add_save_entered = threading.Event()
+    release_add_save = threading.Event()
+    config_save_entered = threading.Event()
+    errors: list[Exception] = []
+    errors_lock = threading.Lock()
+    original_add_save = add_store._save
+    original_config_save = config_store._save
+
+    def blocked_add_save(routes: list[dict]) -> None:
+        add_save_entered.set()
+        if not release_add_save.wait(timeout=5):
+            raise RuntimeError("timeout de synchronisation add_cloud")
+        original_add_save(routes)
+
+    def observed_config_save(routes: list[dict]) -> None:
+        config_save_entered.set()
+        original_config_save(routes)
+
+    monkeypatch.setattr(add_store, "_save", blocked_add_save)
+    monkeypatch.setattr(config_store, "_save", observed_config_save)
+
+    def add_worker() -> None:
+        try:
+            add_store.add_cloud(
+                "nouvelle",
+                "openrouter",
+                "m",
+                FAKE_KEY,
+                "pp-coffre",
+                transport=_GreenTransport(),
+            )
+        except Exception as exc:
+            with errors_lock:
+                errors.append(exc)
+
+    def configure_worker() -> None:
+        try:
+            config_store.configure_cache("existante", True, 60, "cache")
+        except Exception as exc:
+            with errors_lock:
+                errors.append(exc)
+
+    add_thread = threading.Thread(target=add_worker)
+    add_thread.start()
+    assert add_save_entered.wait(timeout=5), "add_cloud n'a pas atteint son commit"
+    config_thread = threading.Thread(target=configure_worker)
+    config_thread.start()
+    config_save_entered.wait(timeout=0.5)
+    release_add_save.set()
+    add_thread.join(timeout=10)
+    config_thread.join(timeout=10)
+
+    assert not add_thread.is_alive()
+    assert not config_thread.is_alive()
+    assert errors == []
+    persisted = {route.name: route for route in RouteStore(home).list()}
+    assert sorted(persisted) == ["existante", "nouvelle"]
+    assert (
+        persisted["existante"].cache,
+        persisted["existante"].cache_ttl_s,
+        persisted["existante"].cache_prefix,
+    ) == (True, 60, "cache")
+
+
+def test_sigkill_avant_replace_conserve_ancien_routes_json(tmp_path):
+    """Un kill après fsync du tmp mais avant replace laisse l'ancien JSON complet."""
+    home = tmp_path / "models"
+    home.mkdir()
+    path = home / "routes.json"
+    path.write_text(
+        json.dumps(
+            [
+                {
+                    "name": "route",
+                    "provenance": "openrouter",
+                    "base_url": "https://openrouter.ai/api/v1",
+                    "model_id": "m",
+                    "key_fingerprint": "sha256:0000000000000000",
+                    "created_at": "2026-07-25",
+                }
+            ]
+        ),
+        encoding="utf-8",
+    )
+    before = path.read_bytes()
+    ctx = mp.get_context("fork")
+    ready = ctx.Event()
+    process = ctx.Process(
+        target=_configure_pause_before_replace, args=(str(home), ready)
+    )
+    process.start()
+    assert ready.wait(timeout=5), "le processus n'a pas atteint os.replace"
+
+    os.kill(process.pid, signal.SIGKILL)
+    process.join(timeout=5)
+
+    assert process.exitcode == -signal.SIGKILL
+    assert path.read_bytes() == before
+    assert RouteStore(home).get("route").cache is False
+
+
+def test_sigkill_entre_vault_et_routes_recupere_sans_cle_orpheline(tmp_path):
+    """Une nouvelle session rollback la transaction interrompue entre les deux fichiers."""
+    home = tmp_path / "models"
+    ctx = mp.get_context("fork")
+    ready = ctx.Event()
+    process = ctx.Process(
+        target=_add_cloud_pause_before_routes_replace, args=(str(home), ready)
+    )
+    process.start()
+    assert ready.wait(timeout=10), "le processus n'a pas atteint le replace routes"
+
+    os.kill(process.pid, signal.SIGKILL)
+    process.join(timeout=5)
+
+    assert process.exitcode == -signal.SIGKILL
+    recovered = RouteStore(home)
+    assert recovered.list() == []
+    assert recovered.vault.names() == []
+
+
+def test_sigkill_add_cloud_restaure_exactement_etat_preexistant(tmp_path):
+    """Le journal ne doit pas être contaminé par la mutation du nouvel état."""
+    home = tmp_path / "models"
+    home.mkdir()
+    existing_secret = "secret-existant"
+    Vault(home / "vault.json").put("existante", existing_secret, "pp")
+    (home / "routes.json").write_text(
+        json.dumps(
+            [
+                {
+                    "name": "existante",
+                    "provenance": "openrouter",
+                    "base_url": "https://openrouter.ai/api/v1",
+                    "model_id": "m",
+                    "key_fingerprint": fingerprint(existing_secret),
+                    "created_at": "2026-07-25",
+                }
+            ]
+        ),
+        encoding="utf-8",
+    )
+    observer = RouteStore(home)
+    ctx = mp.get_context("fork")
+    ready = ctx.Event()
+    process = ctx.Process(
+        target=_add_cloud_pause_before_routes_replace, args=(str(home), ready)
+    )
+    process.start()
+    assert ready.wait(timeout=10), "le processus n'a pas atteint le replace routes"
+
+    os.kill(process.pid, signal.SIGKILL)
+    process.join(timeout=5)
+
+    assert process.exitcode == -signal.SIGKILL
+    assert [route.name for route in observer.list()] == ["existante"]
+    assert observer.vault.names() == ["existante"]
+    assert observer.vault.get("existante", "pp") == existing_secret
+
+
+def test_vault_put_apres_crash_recupere_avant_nouvelle_ecriture(tmp_path):
+    """Une écriture Vault acquittée après crash ne doit jamais être effacée ensuite."""
+    home = tmp_path / "models"
+    ctx = mp.get_context("fork")
+    ready = ctx.Event()
+    process = ctx.Process(
+        target=_add_cloud_pause_before_routes_replace, args=(str(home), ready)
+    )
+    process.start()
+    assert ready.wait(timeout=10), "le processus n'a pas atteint le replace routes"
+
+    os.kill(process.pid, signal.SIGKILL)
+    process.join(timeout=5)
+
+    assert process.exitcode == -signal.SIGKILL
+    vault = Vault(home / "vault.json")
+    vault.put("apres-crash", "secret-durable", "pp")
+    assert vault.names() == ["apres-crash"]
+
+    recovered = RouteStore(home)
+    assert recovered.list() == []
+    assert recovered.vault.names() == ["apres-crash"]
+    assert recovered.vault.get("apres-crash", "pp") == "secret-durable"
+
+
+def test_vault_voisin_ne_detourne_pas_la_recuperation_route_store(tmp_path):
+    """Un coffre voisin récupère le WAL canonique sans recevoir son snapshot."""
+    home = tmp_path / "models"
+    ctx = mp.get_context("fork")
+    ready = ctx.Event()
+    process = ctx.Process(
+        target=_add_cloud_pause_before_routes_replace, args=(str(home), ready)
+    )
+    process.start()
+    assert ready.wait(timeout=10), "le processus n'a pas atteint le replace routes"
+
+    os.kill(process.pid, signal.SIGKILL)
+    process.join(timeout=5)
+
+    assert process.exitcode == -signal.SIGKILL
+    voisin = Vault(home / "autre.json")
+    voisin.put("voisine", "secret-voisin", "pp")
+    assert voisin.get("voisine", "pp") == "secret-voisin"
+    assert not (home / ".models-transaction.json").exists()
+
+    recovered = RouteStore(home)
+    assert recovered.list() == []
+    assert recovered.vault.names() == []
+    assert voisin.names() == ["voisine"]
+
+
+def test_alias_hardlink_du_coffre_est_restaure_avant_put(tmp_path):
+    """Un alias du coffre ne conserve ni état révocable ni écriture hors recovery."""
+    home = tmp_path / "models"
+    ctx = mp.get_context("fork")
+    ready = ctx.Event()
+    process = ctx.Process(
+        target=_add_cloud_pause_before_routes_replace, args=(str(home), ready)
+    )
+    process.start()
+    assert ready.wait(timeout=10), "le processus n'a pas atteint le replace routes"
+
+    os.kill(process.pid, signal.SIGKILL)
+    process.join(timeout=5)
+
+    assert process.exitcode == -signal.SIGKILL
+    alias_path = home / "Vault.json"
+    if not alias_path.exists():
+        os.link(home / "vault.json", alias_path)
+    alias = Vault(alias_path)
+    alias.put("acquittee", "secret-durable", "pp")
+
+    assert not (home / ".models-transaction.json").exists()
+    assert alias.names() == ["acquittee"]
+    assert alias.get("acquittee", "pp") == "secret-durable"
+    recovered = RouteStore(home)
+    assert recovered.list() == []
+    assert recovered.vault.names() == ["acquittee"]
+    assert recovered.vault.get("acquittee", "pp") == "secret-durable"
+
+
+def test_recovery_ne_suit_jamais_un_symlink_vault_externe(tmp_path):
+    """Le rollback supprime le lien canonique injecté, jamais sa cible externe."""
+    home = tmp_path / "models"
+    victim = tmp_path / "victime.json"
+    victim_payload = '{"ne_pas_toucher":true}'
+    victim.write_text(victim_payload, encoding="utf-8")
+    ctx = mp.get_context("fork")
+    ready = ctx.Event()
+    process = ctx.Process(
+        target=_add_cloud_pause_before_vault_replace, args=(str(home), ready)
+    )
+    process.start()
+    assert ready.wait(timeout=10), "le processus n'a pas atteint le replace coffre"
+
+    (home / "vault.json").symlink_to(victim)
+    os.kill(process.pid, signal.SIGKILL)
+    process.join(timeout=5)
+
+    assert process.exitcode == -signal.SIGKILL
+    recovered = RouteStore(home)
+    assert recovered.list() == []
+    assert recovered.vault.names() == []
+    assert victim.read_text(encoding="utf-8") == victim_payload
+    assert not (home / "vault.json").is_symlink()
+    assert not (home / ".models-transaction.json").exists()
+
+
+def test_verrou_transaction_refuse_symlink_sans_alterer_la_cible(tmp_path):
+    """L'acquisition du verrou échoue fermée sans suivre ni tronquer un symlink."""
+    home = tmp_path / "models"
+    home.mkdir()
+    victim = tmp_path / "victime-lock.txt"
+    victim_payload = b"contenu-externe-intact"
+    victim.write_bytes(victim_payload)
+    lock_path = home / ".models-transaction.lock"
+    lock_path.symlink_to(victim)
+
+    store = RouteStore(home)
+    with pytest.raises(OSError):
+        store.list()
+
+    assert lock_path.is_symlink()
+    assert victim.read_bytes() == victim_payload
+
+
+def test_export_recupere_le_wal_avant_de_lire_routes(tmp_path):
+    """Un export ne doit jamais publier une route encore révocable par le WAL."""
+    home = tmp_path / "models"
+    ctx = mp.get_context("fork")
+    ready = ctx.Event()
+    process = ctx.Process(
+        target=_add_cloud_pause_before_journal_unlink, args=(str(home), ready)
+    )
+    process.start()
+    assert ready.wait(timeout=10), "le processus n'a pas atteint l'unlink du journal"
+
+    os.kill(process.pid, signal.SIGKILL)
+    process.join(timeout=5)
+
+    assert process.exitcode == -signal.SIGKILL
+    assert json.loads((home / "routes.json").read_text())[0]["name"] == "orpheline"
+    assert (home / ".models-transaction.json").exists()
+
+    bundle = export_setup(home)
+    assert "routes.json" not in bundle["files"]
+    assert not (home / ".models-transaction.json").exists()
+
+
+def test_sigkill_apres_routes_replace_est_recupere_avant_precheck_add(tmp_path):
+    """Le precheck d'une instance existante récupère avant de juger un doublon."""
+    home = tmp_path / "models"
+    observer = RouteStore(home)
+    ctx = mp.get_context("fork")
+    ready = ctx.Event()
+    process = ctx.Process(
+        target=_add_cloud_pause_before_journal_unlink, args=(str(home), ready)
+    )
+    process.start()
+    assert ready.wait(timeout=10), "le processus n'a pas atteint l'unlink du journal"
+
+    os.kill(process.pid, signal.SIGKILL)
+    process.join(timeout=5)
+
+    assert process.exitcode == -signal.SIGKILL
+    route, result = observer.add_cloud(
+        "orpheline",
+        "openrouter",
+        "m",
+        "nouveau-secret",
+        "pp",
+        transport=_GreenTransport(),
+    )
+    assert result.ok
+    assert route.key_fingerprint == fingerprint("nouveau-secret")
+    assert observer.vault.get("orpheline", "pp") == "nouveau-secret"
+
+
+def test_precheck_add_est_atomique_avec_la_recuperation(tmp_path, monkeypatch):
+    """Aucun writer ne peut commiter entre recovery et lecture du precheck."""
+    home = tmp_path / "models"
+    observer = RouteStore(home)
+    load_entered = threading.Event()
+    release_load = threading.Event()
+    observer_done = threading.Event()
+    results = []
+    errors: list[Exception] = []
+    real_load = observer._load
+    first_load = True
+
+    def blocked_first_load():
+        nonlocal first_load
+        if first_load:
+            first_load = False
+            load_entered.set()
+            if not release_load.wait(timeout=10):
+                raise RuntimeError("precheck non libéré")
+        return real_load()
+
+    monkeypatch.setattr(observer, "_load", blocked_first_load)
+    ctx = mp.get_context("fork")
+    writer_start = ctx.Event()
+    writer_ready = ctx.Event()
+    writer = ctx.Process(
+        target=_add_cloud_wait_then_pause_before_journal_unlink,
+        args=(str(home), writer_start, writer_ready),
+    )
+    writer.start()
+
+    def observer_worker() -> None:
+        try:
+            results.append(
+                observer.add_cloud(
+                    "collision",
+                    "openrouter",
+                    "m",
+                    "secret-observer",
+                    "pp",
+                    transport=_GreenTransport(),
+                )
+            )
+        except Exception as exc:
+            errors.append(exc)
+        finally:
+            observer_done.set()
+
+    observer_thread = threading.Thread(target=observer_worker)
+    observer_thread.start()
+    assert load_entered.wait(timeout=5), "le precheck observer n'a pas commencé"
+
+    writer_start.set()
+    writer_interleaved_during_precheck = writer_ready.wait(timeout=0.5)
+    release_load.set()
+
+    writer_reached_commit = (
+        writer_interleaved_during_precheck or writer_ready.wait(timeout=5)
+    )
+    if writer_reached_commit:
+        os.kill(writer.pid, signal.SIGKILL)
+    writer.join(timeout=5)
+    observer_thread.join(timeout=10)
+
+    assert not writer_interleaved_during_precheck, (
+        "un writer a commité pendant le precheck"
+    )
+    assert observer_done.is_set()
+    assert errors == []
+    assert len(results) == 1
+
+
+def test_deux_configure_cache_meme_route_restent_linearisables(tmp_path):
+    """Deux configurations concurrentes donnent un état final complet de l'une des deux."""
+    home = tmp_path / "models"
+    home.mkdir()
+    (home / "routes.json").write_text(
+        json.dumps(
+            [
+                {
+                    "name": "route",
+                    "provenance": "openrouter",
+                    "base_url": "https://openrouter.ai/api/v1",
+                    "model_id": "m",
+                    "key_fingerprint": "sha256:0000000000000000",
+                    "created_at": "2026-07-25",
+                }
+            ]
+        ),
+        encoding="utf-8",
+    )
+    barrier = threading.Barrier(2)
+    results: list[tuple[int | None, str | None]] = []
+    errors: list[Exception] = []
+    result_lock = threading.Lock()
+
+    def worker(ttl: int, prefix: str) -> None:
+        barrier.wait()
+        try:
+            route = RouteStore(home).configure_cache(
+                "route", True, ttl_s=ttl, prefix=prefix
+            )
+            with result_lock:
+                results.append((route.cache_ttl_s, route.cache_prefix))
+        except Exception as exc:
+            with result_lock:
+                errors.append(exc)
+
+    threads = [
+        threading.Thread(target=worker, args=(10, "a")),
+        threading.Thread(target=worker, args=(20, "b")),
+    ]
+    for thread in threads:
+        thread.start()
+    for thread in threads:
+        thread.join(timeout=5)
+
+    assert errors == []
+    assert sorted(results) == [(10, "a"), (20, "b")]
+    final = RouteStore(home).get("route")
+    assert (final.cache_ttl_s, final.cache_prefix) in {(10, "a"), (20, "b")}
+
+
+def test_deux_add_cloud_meme_nom_refusent_le_perdant_sans_desaligner_vault(
+    tmp_path,
+):
+    """Le perdant reçoit RouteError; la clé du coffre correspond à la route gagnante."""
+    home = tmp_path / "models"
+    barrier = threading.Barrier(2)
+    successes: list[tuple[str, str]] = []
+    errors: list[Exception] = []
+    result_lock = threading.Lock()
+
+    class BarrierTransport(_GreenTransport):
+        def post(self, url, headers, body, timeout):
+            barrier.wait()
+            return super().post(url, headers, body, timeout)
+
+    def worker(secret: str) -> None:
+        try:
+            route, _ = RouteStore(home).add_cloud(
+                "collision",
+                "openrouter",
+                "m",
+                secret,
+                "pp",
+                transport=BarrierTransport(),
+            )
+            with result_lock:
+                successes.append((secret, route.key_fingerprint))
+        except Exception as exc:
+            with result_lock:
+                errors.append(exc)
+
+    threads = [
+        threading.Thread(target=worker, args=("secret-a",)),
+        threading.Thread(target=worker, args=("secret-b",)),
+    ]
+    for thread in threads:
+        thread.start()
+    for thread in threads:
+        thread.join(timeout=10)
+
+    assert len(successes) == 1
+    assert len(errors) == 1
+    assert isinstance(errors[0], RouteError)
+    assert "existe déjà" in str(errors[0])
+    persisted_route = RouteStore(home).get("collision")
+    persisted_secret = RouteStore(home).vault.get("collision", "pp")
+    assert persisted_route.key_fingerprint == fingerprint(persisted_secret)
+    assert successes == [(persisted_secret, persisted_route.key_fingerprint)]
+
+
+def test_probe_reseau_reste_hors_verrou_transaction(tmp_path):
+    """Un contender acquiert le lock pendant le probe réseau lui-même."""
+    home = tmp_path / "models"
+    store = RouteStore(home)
+    probe_completed = threading.Event()
+    lock_acquired_during_probe = threading.Event()
+
+    class ObservedTransport(_GreenTransport):
+        def post(self, url, headers, body, timeout):
+            def contender() -> None:
+                with file_lock(store.transaction_lock_path):
+                    lock_acquired_during_probe.set()
+
+            contender_thread = threading.Thread(target=contender)
+            contender_thread.start()
+            assert lock_acquired_during_probe.wait(timeout=2), (
+                "le verrou transactionnel couvre le probe réseau"
+            )
+            contender_thread.join(timeout=2)
+            result = super().post(url, headers, body, timeout)
+            probe_completed.set()
+            return result
+
+    store.add_cloud(
+        "route",
+        "openrouter",
+        "m",
+        "secret",
+        "pp",
+        transport=ObservedTransport(),
+    )
+
+    assert probe_completed.is_set()
+    assert lock_acquired_during_probe.is_set()
