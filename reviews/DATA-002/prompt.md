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

ARTEFACT — DATA-002-review-final.txt :
diff --git a/src/forgeai/models/_locking.py b/src/forgeai/models/_locking.py
index 473d2fd..7322c69 100644
--- a/src/forgeai/models/_locking.py
+++ b/src/forgeai/models/_locking.py
@@ -1,9 +1,15 @@
-"""Verrouillage fichier inter-process et inter-thread."""
+"""Verrouillage et remplacement atomique de fichiers locaux."""

 import fcntl
+import json
+import os
+import tempfile
 from contextlib import contextmanager
 from pathlib import Path

+MODELS_TRANSACTION_LOCK = ".models-transaction"
+MODELS_TRANSACTION_JOURNAL = ".models-transaction.json"
+

 @contextmanager
 def file_lock(path: Path):
@@ -18,3 +24,98 @@ def file_lock(path: Path):
     finally:
         fcntl.flock(fd.fileno(), fcntl.LOCK_UN)
         fd.close()
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
+def restore_models_transaction_locked(
+    home: Path, vault_path: Path, snapshot: dict
+) -> None:
+    """Restaure les deux fichiers; conserve le journal si une restauration échoue."""
+    home = Path(home)
+    vault_path = Path(vault_path)
+    routes_path = home / "routes.json"
+    journal_path = home / MODELS_TRANSACTION_JOURNAL
+    rollback_error: BaseException | None = None
+
+    try:
+        if snapshot["vault_existed"]:
+            atomic_write_text(
+                vault_path,
+                json.dumps(snapshot["vault"], ensure_ascii=False, indent=1),
+                mode=0o600,
+            )
+        else:
+            atomic_unlink(vault_path)
+    except BaseException as exc:
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
+    except BaseException as exc:
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
+    restore_models_transaction_locked(home, vault_path, snapshot)
+    return True
diff --git a/src/forgeai/models/routes.py b/src/forgeai/models/routes.py
index 78f49a3..ca17fa6 100644
--- a/src/forgeai/models/routes.py
+++ b/src/forgeai/models/routes.py
@@ -14,7 +14,15 @@ from dataclasses import asdict, dataclass, replace
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
 from .probe import ProbeResult, Transport, UrllibTransport, probe_route
 from .vault import Vault

@@ -57,6 +65,9 @@ class RouteStore:
         self.home = Path(home)
         self.routes_path = self.home / "routes.json"
         self.vault = Vault(self.home / "vault.json")
+        self.transaction_lock_path = self.home / MODELS_TRANSACTION_LOCK
+        self.transaction_journal_path = self.home / MODELS_TRANSACTION_JOURNAL
+        self._recover_pending_transaction()

     def _load(self) -> list[dict]:
         if not self.routes_path.exists():
@@ -65,8 +76,41 @@ class RouteStore:

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
@@ -88,45 +132,68 @@ class RouteStore:
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
index 4c90fd3..b5b8d86 100644
--- a/src/forgeai/models/vault.py
+++ b/src/forgeai/models/vault.py
@@ -27,7 +27,13 @@ import os
 import secrets
 from pathlib import Path

-from forgeai.models._locking import file_lock
+from forgeai.models._locking import (
+    MODELS_TRANSACTION_JOURNAL,
+    MODELS_TRANSACTION_LOCK,
+    atomic_write_text,
+    file_lock,
+    recover_models_transaction_locked,
+)

 MAGIC = b"FGV1"
 _SALT = 16
@@ -93,6 +99,8 @@ class Vault:

     def __init__(self, path: Path) -> None:
         self.path = Path(path)
+        self.transaction_lock_path = self.path.parent / MODELS_TRANSACTION_LOCK
+        self.transaction_journal_path = self.path.parent / MODELS_TRANSACTION_JOURNAL

     def _load(self) -> dict[str, str]:
         import json
@@ -105,27 +113,41 @@ class Vault:
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
+        recover_models_transaction_locked(self.path.parent, self.path)

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
diff --git a/stories/DATA-002.md b/stories/DATA-002.md
new file mode 100644
index 0000000..0a2e0ae
--- /dev/null
+++ b/stories/DATA-002.md
@@ -0,0 +1,100 @@
+# DATA-002 — Transaction locale RouteStore/Vault
+
+## Calibration
+
+- Profil : `PROOF-Team`
+- Risque : `T2`
+- Branche : `fix/DATA-002-routestore-atomic-transaction`
+- Base initiale : `c14430057823cdc9eb6f0d5ae22ed84dd8a4b8d1`
+- Base finale après synchronisation : `9ef84cc2bcf2ceacf3cd564ff8eb73a749bbfeeb`
+- Issue : `#164`
+- Claim Codex : actif dans le ledger PROOF externe
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
+   opération qui touche les deux ressources.
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
+  automatiquement à la prochaine ouverture du `RouteStore`.
+
+## Implémentation
+
+- verrou commun `.models-transaction.lock` pour les mutations et lectures
+  `RouteStore`/`Vault` ;
+- écriture temporaire dans le même répertoire, permissions `0600`, `fsync` du
+  fichier, `os.replace`, puis `fsync` du répertoire ;
+- write-ahead journal `.models-transaction.json` contenant l’état antérieur
+  chiffré du coffre et les anciennes routes ;
+- rollback idempotent après exception ou reprise à la première opération d’une
+  instance neuve ou déjà existante ;
+- probe réseau exécuté hors verrou, entre le précontrôle atomique et le commit.
+
+## Résultats vérifiés
+
+- 39 tests ciblés : PASS ;
+- 13 tests de concurrence et de panne, avec six arrêts `SIGKILL` réels
+  répartis sur les fenêtres de commit : PASS ;
+- 100 configurations concurrentes, lecteur JSON brut actif et probe hors
+  verrou : PASS en `0,31 s` ;
+- suite complète : PASS, couverture globale `89,70 %` (seuil `85 %`) ;
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
+puis re-revus sans constat critique ou important. Cette revue interne ne compte
+pas parmi les trois verdicts multi-vendeurs requis.
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
+Le rollback Git du commit sera rejoué dans un worktree éphémère après création
+du commit, puis les tests ciblés de la base seront exécutés.
+
+## Gates encore externes
+
+SonarQube, CodeRabbit/Bugbot, les trois verdicts indépendants et la merge queue
+nécessitent la PR. Aucun verdict n’est préfabriqué localement.
diff --git a/tests/test_models_cloud.py b/tests/test_models_cloud.py
index 14e8926..512da73 100644
--- a/tests/test_models_cloud.py
+++ b/tests/test_models_cloud.py
@@ -228,6 +228,118 @@ def test_configure_cache_route_inconnue(tmp_path):
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
+    with pytest.raises(OSError, match="avant replace routes"):
+        RouteStore(tmp_path).configure_cache("r", True, 60, "cache")
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
index b50267f..73ec79e 100644
--- a/tests/test_routestore_concurrence.py
+++ b/tests/test_routestore_concurrence.py
@@ -7,11 +7,14 @@ clés sont retrouvables au coffre. RED avant correctif : lost-update (moins de N
 """
 import json
 import multiprocessing as mp
+import os
+import signal
 import threading
 from pathlib import Path

-from forgeai.models.routes import RouteStore
-from forgeai.models.vault import Vault
+from forgeai.models._locking import file_lock
+from forgeai.models.routes import RouteError, RouteStore
+from forgeai.models.vault import Vault, fingerprint

 FAKE_KEY = "sk-fake-DO-NOT-LEAK"

@@ -28,6 +31,74 @@ def _add_one(home_str: str, i: int, barrier) -> None:
                     transport=_GreenTransport())


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
@@ -66,3 +137,518 @@ def test_vault_put_concurrent_ne_perd_aucune_cle(tmp_path):

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
+                assert isinstance(persisted, list)
+            except Exception as exc:
+                with errors_lock:
+                    errors.append(exc)
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
