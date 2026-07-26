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

ARTEFACT — .superpowers/sdd/DATA-003/review-0547cca..5da95e6.diff :
# Review package: 0547cca2417ba860851dce1f89a39073dca5b762..5da95e6f3c3d9fb75971a4113df4262ae50e6d27

## Commits
5da95e6 [DATA-003] Restaurer le mode exact du key store
4575017 [DATA-003] Sécuriser les parents des stores OpenBao
1aec2e5 [DATA-003] Durcir le coffre et les répertoires imbriqués
5b82397 [DATA-003] Expliciter les branches de sécurité
dad4e86 [DATA-003] Supporter les umasks restrictifs
9cd8c33 [DATA-003] Durcir les chemins du bootstrap secret
67564ce [DATA-003] Sérialiser le bootstrap des secrets
d20fccb [DATA-003] Rompre sûrement les hardlinks de secrets
6be8a68 [DATA-003] Neutraliser les assertions de secrets
aa08909 [DATA-003] Documenter l'ouverture sécurisée du secret
2c5c13d [DATA-003] Durcir la correction du mode des secrets
745e04b [DATA-003] Sécuriser les écritures atomiques de secrets

## Files changed
 src/forgeai/bootstrap/secrets.py   |  87 ++--
 src/forgeai/deploy/openbao_flow.py |  42 +-
 src/forgeai/models/vault.py        | 246 +++++++++++-
 tests/test_assemble_and_secrets.py | 787 ++++++++++++++++++++++++++++++++++++-
 tests/test_openbao_flow.py         | 574 ++++++++++++++++++++++++++-
 tests/test_vault.py                | 169 +++++++-
 6 files changed, 1848 insertions(+), 57 deletions(-)

## Diff
diff --git a/src/forgeai/bootstrap/secrets.py b/src/forgeai/bootstrap/secrets.py
index 75f371b..4de1c20 100644
--- a/src/forgeai/bootstrap/secrets.py
+++ b/src/forgeai/bootstrap/secrets.py
@@ -1,57 +1,90 @@
 """Story P1-S05 — bootstrap sécurisé local (codeur : fable).
 
 Génère les secrets d'exécution (jetons aléatoires 256 bits) dans <out>/.env et
 <out>/secrets/, permissions 0600, répertoire 0700. Idempotent : ne régénère pas
 un secret existant sauf --regen. Aucun secret n'apparaît jamais dans les
 manifestes rendus — ils sont référencés par env_file (vérifié par test).
 """
 from __future__ import annotations
 
-import os
 import secrets as pysecrets
 from pathlib import Path
 
+from forgeai.models._locking import file_lock
+from forgeai.models.vault import (
+    atomic_write_secret_text,
+    prepare_lock_file,
+    prepare_secure_directory,
+    read_secret_text,
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
+    # Limite du modèle de menace : `out_dir` et ses ancêtres sont contrôlés par
+    # l'opérateur et non inscriptibles par un attaquant. O_NOFOLLOW protège les
+    # composants finaux; une prévalidation user-space ne peut pas neutraliser
+    # le renommage concurrent d'un composant parent contrôlé par un tiers.
+    prepare_secure_directory(out_dir, preserve_existing_final=True)
+    prepare_lock_file(out_dir / _BOOTSTRAP_LOCK_ANCHOR)
+    with file_lock(out_dir / _BOOTSTRAP_LOCK_ANCHOR):
+        secrets_dir = out_dir / "secrets"
+        prepare_secure_directory(secrets_dir)
+        env_path = out_dir / ".env"
+        existing: dict[str, str] = {}
+        if not regen:
+            try:
+                existing_payload = read_secret_text(env_path)
+            except FileNotFoundError:
+                existing_payload = ""
+            for line in existing_payload.splitlines():
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
+        atomic_write_secret_text(
+            env_path, "\n".join(lines) + "\n", mode=0o600
+        )
+
+        prepare_secure_directory(secrets_dir)
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
index ea8faa7..9fc06bd 100644
--- a/src/forgeai/deploy/openbao_flow.py
+++ b/src/forgeai/deploy/openbao_flow.py
@@ -2,101 +2,117 @@
 
 Le sidecar/service openbao-unsealer monte RO le répertoire des clés et n'en lit que `unseal_key`. Le
 root_token ne doit donc JAMAIS résider dans ce répertoire : FileKeyStore écrit `unseal_key` dans `keys_dir`
 (monté RO à l'unsealer) et `root_token` dans un fichier SÉPARÉ `root_path` (jamais monté). Aucune dépendance
 (stdlib pure). Aucun secret n'apparaît dans un message d'erreur.
 """
 from __future__ import annotations
 
 import base64
 import json
-import os
+import stat
 import subprocess
 import time
 from collections.abc import Callable
 from pathlib import Path
 
+from forgeai.models.vault import (
+    atomic_write_secret_text,
+    prepare_secure_directory,
+    read_secret_text,
+)
 from forgeai.secrets.openbao_init import ensure_openbao_ready, http_transport
 
 
 class OpenBaoFlowError(RuntimeError):
     """Échec d'amorçage openbao au déploiement. Ne contient jamais de token/clé."""
 
 
 class FileKeyStore:
     """key_store fichier pour ensure_openbao_ready. `unseal_key` -> keys_dir/unseal_key (monté RO à
     l'unsealer) ; `root_token` -> root_path (SÉPARÉ, jamais monté). read() renvoie None si non initialisé."""
 
     def __init__(self, keys_dir: Path, root_path: Path) -> None:
         self._unseal_path = Path(keys_dir) / "unseal_key"
         self._root_path = Path(root_path)
 
     def read(self) -> dict | None:
-        if not self._unseal_path.exists() or not self._root_path.exists():
+        try:
+            unseal = read_secret_text(self._unseal_path).strip()
+            root = read_secret_text(self._root_path).strip()
+        except FileNotFoundError:
             return None
-        unseal = self._unseal_path.read_text(encoding="utf-8").strip()
-        root = self._root_path.read_text(encoding="utf-8").strip()
         if not unseal or not root:
             return None
         return {"unseal_key": unseal, "root_token": root}
 
     def write(self, data: dict) -> None:
+        prepare_secure_directory(self._root_path.parent, final_mode=0o700)
+        prepare_secure_directory(self._unseal_path.parent, final_mode=0o711)
         # root_token -> 0600, ISOLÉ dans un fichier séparé jamais monté à l'unsealer (owner seul).
-        self._root_path.parent.mkdir(parents=True, exist_ok=True)
         _write_file(self._root_path, data["root_token"], 0o600)
         # unseal_key -> 0644 : le conteneur openbao-unsealer tourne sous l'UID NON-root de l'image
         # (≠ UID de l'opérateur qui écrit), via un bind-mount hôte -> il ne pourrait PAS lire un 0600
         # possédé par l'opérateur (prouvé e2e S6 : re-unseal muet après restart). La clé d'unseal est
         # co-localisée avec le STORAGE scellé sur le même hôte (MÊME frontière de confiance : qui lit
         # l'hôte a déjà les deux) -> 0644 n'élargit pas la surface au-delà du contrôle d'accès au nœud
         # (documenté). Le ROOT reste 0600 et isolé (l'unsealer ne le voit jamais).
-        self._unseal_path.parent.mkdir(parents=True, exist_ok=True)
         _write_file(self._unseal_path, data["unseal_key"], 0o644)
 
 
 class FileSecretStore:
     """secret_store fichier pour ensure_openbao_ready : {"token": <app_token>} en JSON, 0600."""
 
     def __init__(self, path: Path) -> None:
         self._path = Path(path)
 
     def read(self) -> dict | None:
-        if not self._path.exists():
+        try:
+            text = read_secret_text(self._path).strip()
+        except FileNotFoundError:
             return None
-        text = self._path.read_text(encoding="utf-8").strip()
         return json.loads(text) if text else None
 
     def write(self, data: dict) -> None:
-        self._path.parent.mkdir(parents=True, exist_ok=True)
+        try:
+            parent_state = self._path.parent.lstat()
+        except FileNotFoundError:
+            parent_state = None
+        if (
+            parent_state is not None
+            and stat.S_ISDIR(parent_state.st_mode)
+            and stat.S_IMODE(parent_state.st_mode) & 0o200 == 0
+        ):
+            raise OSError("le répertoire du secret n'est pas inscriptible")
+        prepare_secure_directory(self._path.parent, final_mode=0o700)
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
-    d.mkdir(parents=True, exist_ok=True)
     # 0o711 : traversable par l'UID non-root du conteneur unsealer (pour lire /keys/unseal_key par son
     # nom) MAIS non LISTABLE par les autres (pas de bit read). Risque accepté et documenté (S2612) : la
     # clé d'unseal est co-localisée avec le storage scellé sur le même hôte (même frontière de confiance).
-    os.chmod(d, 0o711)  # nosec B103
+    prepare_secure_directory(d, final_mode=0o711)
     return d
 
 
 # --------------------------------------------------------------------------
 # key_store k3s : Secret Kubernetes (le sidecar S3 ne monte QUE l'item unseal_key -> le root est
 # dans le Secret mais jamais dans le volume du sidecar). Les secrets transitent par STDIN (manifeste
 # `kubectl apply -f -`) et par la sortie de `kubectl get`, JAMAIS par argv (invariant : pas de secret
 # en ligne de commande, visible via ps).
 # --------------------------------------------------------------------------
 
diff --git a/src/forgeai/models/vault.py b/src/forgeai/models/vault.py
index 54da090..3662dc3 100644
--- a/src/forgeai/models/vault.py
+++ b/src/forgeai/models/vault.py
@@ -18,44 +18,270 @@ maison) :
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
 
 MAGIC = b"FGV1"
 _SALT = 16
 _NONCE = 16
 _TAG = 32
+_MAX_SECRET_TEXT_BYTES = 1024 * 1024
 # Revue aveugle 3 vendors (DeepSeek/Grok/Gemini) : N=2^14 jugé bas pour une attaque
 # hors-ligne sur blob volé (cible « au repos ») → relevé à 2^16 (~67 Mo, <1 s, portable).
 _SCRYPT = dict(n=2 ** 16, r=8, p=1, dklen=64, maxmem=128 * 1024 * 1024)
 
 
 class VaultError(Exception):
     """Tag invalide : passphrase erronée ou données altérées."""
 
 
+def _same_inode(left: os.stat_result, right: os.stat_result) -> bool:
+    return (left.st_dev, left.st_ino) == (right.st_dev, right.st_ino)
+
+
+def _set_mode_without_following_preexisting_symlink(
+    path: Path, mode: int, expected_state: os.stat_result
+) -> os.stat_result:
+    current = path.lstat()
+    if (
+        stat.S_IFMT(current.st_mode) != stat.S_IFMT(expected_state.st_mode)
+        or not _same_inode(current, expected_state)
+    ):
+        raise OSError("le chemin sécurisé a changé")
+
+    if os.chmod in os.supports_follow_symlinks:
+        os.chmod(path, mode, follow_symlinks=False)
+    else:
+        # Limite POSIX : le fallback pathname repose sur un parent contrôlé par
+        # l'opérateur et non soumis à un renommage hostile entre les deux lstat.
+        os.chmod(path, mode)
+
+    updated = path.lstat()
+    if (
+        stat.S_IFMT(updated.st_mode) != stat.S_IFMT(expected_state.st_mode)
+        or not _same_inode(updated, expected_state)
+    ):
+        raise OSError("le chemin sécurisé a changé")
+    return updated
+
+
+def _open_directory_with_mode(
+    path: Path, path_state: os.stat_result, final_mode: int
+) -> int:
+    no_follow = getattr(os, "O_NOFOLLOW", None)
+    directory = getattr(os, "O_DIRECTORY", None)
+    if no_follow is None or directory is None:
+        raise OSError("validation de répertoire sans suivi indisponible")
+    if not stat.S_ISDIR(path_state.st_mode):
+        raise OSError("le chemin sécurisé n'est pas un répertoire")
+
+    if stat.S_IMODE(path_state.st_mode) & 0o500 != 0o500:
+        path_state = _set_mode_without_following_preexisting_symlink(
+            path, final_mode, path_state
+        )
+
+    flags = os.O_RDONLY | no_follow | directory
+    flags |= getattr(os, "O_CLOEXEC", 0)
+    descriptor = os.open(path, flags)
+    try:
+        descriptor_state = os.fstat(descriptor)
+        if (
+            not stat.S_ISDIR(descriptor_state.st_mode)
+            or not _same_inode(descriptor_state, path_state)
+        ):
+            raise OSError("le chemin sécurisé n'est pas un répertoire")
+        os.fchmod(descriptor, final_mode)
+        current = path.lstat()
+        if not stat.S_ISDIR(current.st_mode) or not _same_inode(
+            current, descriptor_state
+        ):
+            raise OSError("le répertoire sécurisé a changé")
+    except BaseException:
+        os.close(descriptor)
+        raise
+    return descriptor
+
+
+def prepare_secure_directory(
+    path: Path,
+    *,
+    final_mode: int = 0o700,
+    preserve_existing_final: bool = False,
+) -> None:
+    """Crée/valide une chaîne de répertoires sans symlink, umask-indépendante."""
+    path = Path(path)
+    creation_chain_started = False
+    for candidate in (*reversed(path.parents), path):
+        try:
+            current = candidate.lstat()
+        except FileNotFoundError:
+            creation_chain_started = True
+            try:
+                candidate.mkdir(mode=0o700)
+            except FileExistsError:
+                current = candidate.lstat()
+            else:
+                current = candidate.lstat()
+
+        if not stat.S_ISDIR(current.st_mode):
+            raise OSError("le chemin sécurisé n'est pas un répertoire")
+
+        permissions = stat.S_IMODE(current.st_mode)
+        is_final = candidate == path
+        if is_final and not preserve_existing_final:
+            desired_mode = final_mode
+        elif creation_chain_started:
+            desired_mode = final_mode if is_final else 0o700
+        elif permissions & 0o700 != 0o700:
+            desired_mode = permissions | 0o700
+        else:
+            continue
+
+        descriptor = _open_directory_with_mode(
+            candidate, current, desired_mode
+        )
+        os.close(descriptor)
+
+
+def _ensure_regular_path_matches(
+    path: Path, expected_state: os.stat_result
+) -> None:
+    current = path.lstat()
+    if (
+        not stat.S_ISREG(current.st_mode)
+        or current.st_nlink != 1
+        or not _same_inode(current, expected_state)
+    ):
+        raise OSError("le fichier de verrouillage a changé")
+
+
+def prepare_lock_file(path: Path) -> None:
+    """Établit le même inode de verrou 0600 avant file_lock."""
+    mode = 0o600
+    no_follow = getattr(os, "O_NOFOLLOW", None)
+    if no_follow is None:
+        raise OSError("ouverture sans suivi de lien indisponible")
+    flags = os.O_RDWR | no_follow
+    flags |= getattr(os, "O_CLOEXEC", 0)
+    lock_path = Path(str(path) + ".lock")
+
+    try:
+        descriptor = os.open(
+            lock_path, flags | os.O_CREAT | os.O_EXCL, mode
+        )
+        expected_state = None
+    except FileExistsError:
+        expected_state = lock_path.lstat()
+        if (
+            not stat.S_ISREG(expected_state.st_mode)
+            or expected_state.st_nlink != 1
+        ):
+            raise OSError("le verrou n'est pas un fichier régulier")
+        if stat.S_IMODE(expected_state.st_mode) & 0o600 != 0o600:
+            expected_state = _set_mode_without_following_preexisting_symlink(
+                lock_path, mode, expected_state
+            )
+        descriptor = os.open(lock_path, flags)
+
+    try:
+        descriptor_state = os.fstat(descriptor)
+        if (
+            not stat.S_ISREG(descriptor_state.st_mode)
+            or descriptor_state.st_nlink != 1
+        ):
+            raise OSError("le verrou n'est pas un fichier régulier")
+        if expected_state is not None and not _same_inode(
+            descriptor_state, expected_state
+        ):
+            raise OSError("le fichier de verrouillage a changé")
+        os.fchmod(descriptor, mode)
+        _ensure_regular_path_matches(lock_path, descriptor_state)
+    finally:
+        os.close(descriptor)
+
+
+def _reject_secret_target_symlink(path: Path) -> None:
+    try:
+        target = path.lstat()
+    except FileNotFoundError:
+        target = None
+    if target is not None and stat.S_ISLNK(target.st_mode):
+        raise OSError("refus d'utiliser un secret via un lien symbolique")
+
+
+def atomic_write_secret_text(
+    path: Path, payload: str, *, mode: int = 0o600
+) -> None:
+    """Remplace un fichier secret atomiquement sans suivre une cible symlink."""
+    path = Path(path)
+    _reject_secret_target_symlink(path)
+    atomic_write_text(path, payload, mode=mode)
+
+
+def read_secret_text(
+    path: Path, *, max_bytes: int = _MAX_SECRET_TEXT_BYTES
+) -> str:
+    """Lit un petit fichier secret régulier sans suivre son composant final."""
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
+            raise OSError("refus de lire un secret non régulier")
+        if target.st_size > max_bytes:
+            raise OSError("fichier secret trop volumineux")
+        content = bytearray()
+        while chunk := os.read(
+            descriptor, min(8_192, max_bytes + 1 - len(content))
+        ):
+            content.extend(chunk)
+            if len(content) > max_bytes:
+                raise OSError("fichier secret trop volumineux")
+    finally:
+        os.close(descriptor)
+    try:
+        return bytes(content).decode("utf-8")
+    except UnicodeDecodeError:
+        raise OSError("secret existant non UTF-8") from None
+
+
+def republish_existing_secret_file(path: Path, *, mode: int = 0o600) -> None:
+    """Relit un secret régulier sans suivre de lien, puis le republie atomiquement."""
+    payload = read_secret_text(path)
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
 
 
@@ -96,32 +322,39 @@ def fingerprint(secret: str) -> str:
 
 
 class Vault:
     """Coffre fichier (un blob par clé logique). Fichier 0600, répertoire 0700."""
 
     def __init__(self, path: Path) -> None:
         self.path = Path(path)
         self.transaction_lock_path = self.path.parent / MODELS_TRANSACTION_LOCK
         self.transaction_journal_path = self.path.parent / MODELS_TRANSACTION_JOURNAL
 
+    def _prepare_storage(self) -> None:
+        prepare_secure_directory(self.path.parent, final_mode=0o700)
+        _reject_secret_target_symlink(self.path)
+        prepare_lock_file(self.transaction_lock_path)
+
     def _load(self) -> dict[str, str]:
         import json
-        if not self.path.exists():
+
+        try:
+            payload = read_secret_text(self.path)
+        except FileNotFoundError:
             return {}
-        return json.loads(self.path.read_text(encoding="utf-8"))
+        return json.loads(payload)
 
     def _save(self, data: dict[str, str]) -> None:
         import json
-        self.path.parent.mkdir(parents=True, exist_ok=True)
-        os.chmod(self.path.parent, 0o700)
+
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
@@ -136,30 +369,33 @@ class Vault:
             self.path if path_is_canonical_alias else canonical_vault_path
         )
         recovered = recover_models_transaction_locked(
             self.path.parent, recovery_path
         )
         if recovered and path_is_canonical_alias:
             self.path = canonical_vault_path
 
     def put(self, name: str, secret: str, passphrase: str) -> str:
         """Scelle `secret` sous `name`. Retourne l'empreinte (jamais le secret)."""
+        self._prepare_storage()
         with file_lock(self.transaction_lock_path):
             self._recover_pending_transaction_locked()
             data, secret_fingerprint = self._with_secret(name, secret, passphrase)
             self._save(data)
         return secret_fingerprint
 
     def get(self, name: str, passphrase: str) -> str:
         import base64
 
+        self._prepare_storage()
         with file_lock(self.transaction_lock_path):
             self._recover_pending_transaction_locked()
             data = self._load()
         if name not in data:
             raise KeyError(name)
         return unseal(base64.b64decode(data[name]), passphrase).decode("utf-8")
 
     def names(self) -> list[str]:
+        self._prepare_storage()
         with file_lock(self.transaction_lock_path):
             self._recover_pending_transaction_locked()
             return sorted(self._load())
diff --git a/tests/test_assemble_and_secrets.py b/tests/test_assemble_and_secrets.py
index 71b2352..fc3627a 100644
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
@@ -35,31 +44,797 @@ def test_gpu_seulement_si_profil_cuda_et_service_capable():
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
+def test_secrets_directory_is_private_at_its_first_creation(
+    tmp_path, monkeypatch
+):
+    out_dir = tmp_path / "out"
+    secrets_dir = out_dir / "secrets"
+    observed_creation_modes: list[int] = []
+    real_mkdir = os.mkdir
+
+    def observe_real_mkdir(path, mode=0o777, *args, **kwargs):
+        result = real_mkdir(path, mode, *args, **kwargs)
+        if Path(path) == secrets_dir:
+            observed_creation_modes.append(
+                stat.S_IMODE(os.lstat(path).st_mode)
+            )
+        return result
+
+    monkeypatch.setattr(vault_module.os, "mkdir", observe_real_mkdir)
+    previous_umask = os.umask(0)
+    try:
+        bootstrap_secrets(out_dir)
+    finally:
+        os.umask(previous_umask)
+
+    if observed_creation_modes != [0o700]:
+        raise AssertionError("secret directory was not private at creation")
+
+
+def test_bootstrap_succeeds_under_restrictive_umask_without_relaxing_paths(
+    tmp_path, monkeypatch
+):
+    out_dir = tmp_path / "out"
+    out_dir.mkdir()
+    os.chmod(out_dir, 0o750)
+    original_out_mode = stat.S_IMODE(out_dir.stat().st_mode)
+    secrets_dir = out_dir / "secrets"
+    observed_creation_modes: list[int] = []
+    real_mkdir = os.mkdir
+
+    def observe_real_mkdir(path, mode=0o777, *args, **kwargs):
+        result = real_mkdir(path, mode, *args, **kwargs)
+        if Path(path) == secrets_dir:
+            observed_creation_modes.append(
+                stat.S_IMODE(os.lstat(path).st_mode)
+            )
+        return result
+
+    monkeypatch.setattr(vault_module.os, "mkdir", observe_real_mkdir)
+    previous_umask = os.umask(0o777)
+    try:
+        first_paths = bootstrap_secrets(out_dir)
+        second_paths = bootstrap_secrets(out_dir)
+    finally:
+        os.umask(previous_umask)
+
+    if not observed_creation_modes:
+        raise AssertionError("secret directory creation was not observed")
+    if any(mode & ~0o700 for mode in observed_creation_modes):
+        raise AssertionError("secret directory creation exposed excess permissions")
+    assert stat.S_IMODE(out_dir.stat().st_mode) == original_out_mode
+    assert stat.S_IMODE(secrets_dir.stat().st_mode) == 0o700
+    for secret_path in (*first_paths.values(), *second_paths.values()):
+        assert stat.S_IMODE(secret_path.stat().st_mode) == 0o600
+
+
+def test_bootstrap_creates_missing_out_dir_under_restrictive_umask(
+    tmp_path, monkeypatch
+):
+    out_dir = tmp_path / "out"
+    secrets_dir = out_dir / "secrets"
+    observed_creation_modes: dict[Path, list[int]] = {
+        out_dir: [],
+        secrets_dir: [],
+    }
+    real_mkdir = os.mkdir
+
+    def observe_real_mkdir(path, mode=0o777, *args, **kwargs):
+        result = real_mkdir(path, mode, *args, **kwargs)
+        candidate = Path(path)
+        if candidate in observed_creation_modes:
+            observed_creation_modes[candidate].append(
+                stat.S_IMODE(os.lstat(candidate).st_mode)
+            )
+        return result
+
+    monkeypatch.setattr(vault_module.os, "mkdir", observe_real_mkdir)
+    previous_umask = os.umask(0o777)
+    try:
+        first_paths = bootstrap_secrets(out_dir)
+        second_paths = bootstrap_secrets(out_dir)
+    finally:
+        os.umask(previous_umask)
+
+    for candidate, modes in observed_creation_modes.items():
+        if not modes:
+            raise AssertionError(f"directory creation was not observed: {candidate.name}")
+        if any(mode & ~0o700 for mode in modes):
+            raise AssertionError("directory creation exposed excess permissions")
+    assert stat.S_IMODE(out_dir.stat().st_mode) == 0o700
+    assert stat.S_IMODE(secrets_dir.stat().st_mode) == 0o700
+    for secret_path in (*first_paths.values(), *second_paths.values()):
+        assert stat.S_IMODE(secret_path.stat().st_mode) == 0o600
+
+
+def test_bootstrap_creates_nested_out_dir_under_restrictive_umask(
+    tmp_path, monkeypatch
+):
+    out_dir = tmp_path / "a" / "b" / "c"
+    secrets_dir = out_dir / "secrets"
+    created_directories = (
+        tmp_path / "a",
+        tmp_path / "a" / "b",
+        out_dir,
+        secrets_dir,
+    )
+    observed_creation_modes = {
+        candidate: [] for candidate in created_directories
+    }
+    original_tmp_mode = stat.S_IMODE(tmp_path.stat().st_mode)
+    real_mkdir = os.mkdir
+
+    def observe_real_mkdir(path, mode=0o777, *args, **kwargs):
+        result = real_mkdir(path, mode, *args, **kwargs)
+        candidate = Path(path)
+        if candidate in observed_creation_modes:
+            observed_creation_modes[candidate].append(
+                stat.S_IMODE(os.lstat(candidate).st_mode)
+            )
+        return result
+
+    monkeypatch.setattr(vault_module.os, "mkdir", observe_real_mkdir)
+    previous_umask = os.umask(0o777)
+    try:
+        first_paths = bootstrap_secrets(out_dir)
+        second_paths = bootstrap_secrets(out_dir)
+    finally:
+        os.umask(previous_umask)
+
+    assert stat.S_IMODE(tmp_path.stat().st_mode) == original_tmp_mode
+    for candidate, modes in observed_creation_modes.items():
+        if not modes:
+            raise AssertionError(f"directory creation was not observed: {candidate.name}")
+        if any(mode & ~0o700 for mode in modes):
+            raise AssertionError("directory creation exposed excess permissions")
+        assert stat.S_IMODE(candidate.stat().st_mode) == 0o700
+    for secret_path in (*first_paths.values(), *second_paths.values()):
+        assert stat.S_IMODE(secret_path.stat().st_mode) == 0o600
+
+
+def test_concurrent_first_bootstraps_share_one_lock_under_restrictive_umask(
+    tmp_path, monkeypatch
+):
+    out_dir = tmp_path / "out"
+    lock_path = out_dir / ".bootstrap-secrets.lock"
+    out_created = threading.Event()
+    release_creator = threading.Event()
+    contender_done = threading.Event()
+    observed_lock_inodes: list[int] = []
+    worker_errors: list[str] = []
+    result_digests: list[tuple[bytes, bytes]] = []
+    observation_lock = threading.Lock()
+    real_open = os.open
+    real_mkdir = os.mkdir
+    creator_thread: threading.Thread | None = None
+    contender_thread: threading.Thread | None = None
+
+    def observe_lock_open(path, flags, *args, **kwargs):
+        descriptor = real_open(path, flags, *args, **kwargs)
+        if Path(path) == lock_path:
+            inode = os.fstat(descriptor).st_ino
+            with observation_lock:
+                observed_lock_inodes.append(inode)
+        return descriptor
+
+    def pause_after_out_creation(path, mode=0o777, *args, **kwargs):
+        result = real_mkdir(path, mode, *args, **kwargs)
+        if Path(path) == out_dir and threading.current_thread() is creator_thread:
+            out_created.set()
+            if not release_creator.wait(timeout=5):
+                raise RuntimeError("creator did not resume after out creation")
+        return result
+
+    monkeypatch.setattr(vault_module.os, "open", observe_lock_open)
+    monkeypatch.setattr(vault_module.os, "mkdir", pause_after_out_creation)
+
+    def run_bootstrap() -> None:
+        try:
+            paths = bootstrap_secrets(out_dir)
+            digests = (
+                sha256(paths["env"].read_bytes()).digest(),
+                sha256(paths["token_key"].read_bytes()).digest(),
+            )
+            with observation_lock:
+                result_digests.append(digests)
+        except (OSError, RuntimeError) as exc:
+            with observation_lock:
+                worker_errors.append(type(exc).__name__)
+        finally:
+            if threading.current_thread() is contender_thread:
+                contender_done.set()
+
+    creator_thread = threading.Thread(target=run_bootstrap, daemon=True)
+    contender_thread = threading.Thread(target=run_bootstrap, daemon=True)
+    workers = [creator_thread, contender_thread]
+    previous_umask = os.umask(0o777)
+    try:
+        creator_thread.start()
+        assert out_created.wait(timeout=5), "creator did not create out directory"
+        contender_thread.start()
+        assert contender_done.wait(timeout=5), "contender did not finish"
+        release_creator.set()
+        for worker in workers:
+            worker.join(timeout=5)
+    finally:
+        release_creator.set()
+        os.umask(previous_umask)
+
+    assert all(not worker.is_alive() for worker in workers)
+    assert not worker_errors, f"concurrent bootstrap errors: {worker_errors}"
+    if len(result_digests) != 2 or result_digests[0] != result_digests[1]:
+        raise AssertionError("concurrent bootstrap results diverged")
+    if not observed_lock_inodes or len(set(observed_lock_inodes)) != 1:
+        raise AssertionError("concurrent bootstraps used different lock inodes")
+    assert stat.S_IMODE(lock_path.stat().st_mode) == 0o600
+
+
+def test_concurrent_nested_first_bootstraps_restore_restrictive_parent(
+    tmp_path, monkeypatch
+):
+    first_parent = tmp_path / "a"
+    out_dir = first_parent / "b" / "c"
+    lock_path = out_dir / ".bootstrap-secrets.lock"
+    parent_created = threading.Event()
+    release_creator = threading.Event()
+    contender_done = threading.Event()
+    observed_lock_inodes: list[int] = []
+    worker_errors: list[str] = []
+    result_digests: list[tuple[bytes, bytes]] = []
+    observation_lock = threading.Lock()
+    real_open = os.open
+    real_mkdir = os.mkdir
+    creator_thread: threading.Thread | None = None
+    contender_thread: threading.Thread | None = None
+
+    def observe_lock_open(path, flags, *args, **kwargs):
+        descriptor = real_open(path, flags, *args, **kwargs)
+        if Path(path) == lock_path:
+            with observation_lock:
+                observed_lock_inodes.append(os.fstat(descriptor).st_ino)
+        return descriptor
+
+    def pause_after_parent_creation(path, mode=0o777, *args, **kwargs):
+        result = real_mkdir(path, mode, *args, **kwargs)
+        if (
+            Path(path) == first_parent
+            and threading.current_thread() is creator_thread
+        ):
+            parent_created.set()
+            if not release_creator.wait(timeout=5):
+                raise RuntimeError("nested creator did not resume")
+        return result
+
+    monkeypatch.setattr(vault_module.os, "open", observe_lock_open)
+    monkeypatch.setattr(vault_module.os, "mkdir", pause_after_parent_creation)
+
+    def run_bootstrap() -> None:
+        try:
+            paths = bootstrap_secrets(out_dir)
+            digests = (
+                sha256(paths["env"].read_bytes()).digest(),
+                sha256(paths["token_key"].read_bytes()).digest(),
+            )
+            with observation_lock:
+                result_digests.append(digests)
+        except (OSError, RuntimeError) as exc:
+            with observation_lock:
+                worker_errors.append(type(exc).__name__)
+        finally:
+            if threading.current_thread() is contender_thread:
+                contender_done.set()
+
+    creator_thread = threading.Thread(target=run_bootstrap, daemon=True)
+    contender_thread = threading.Thread(target=run_bootstrap, daemon=True)
+    workers = [creator_thread, contender_thread]
+    previous_umask = os.umask(0o777)
+    try:
+        creator_thread.start()
+        assert parent_created.wait(timeout=5), "creator did not create nested parent"
+        contender_thread.start()
+        assert contender_done.wait(timeout=5), "nested contender did not finish"
+        release_creator.set()
+        for worker in workers:
+            worker.join(timeout=5)
+    finally:
+        release_creator.set()
+        os.umask(previous_umask)
+
+    assert all(not worker.is_alive() for worker in workers)
+    assert not worker_errors, f"nested bootstrap errors: {worker_errors}"
+    if len(result_digests) != 2 or result_digests[0] != result_digests[1]:
+        raise AssertionError("nested concurrent bootstrap results diverged")
+    if not observed_lock_inodes or len(set(observed_lock_inodes)) != 1:
+        raise AssertionError("nested bootstraps used different lock inodes")
+    assert stat.S_IMODE(lock_path.stat().st_mode) == 0o600
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
+def test_non_regen_refuses_env_symlink_before_reading_referent(
+    tmp_path, monkeypatch
+):
+    out_dir = tmp_path / "out"
+    out_dir.mkdir()
+    referent = tmp_path / "external-env"
+    referent.write_text(
+        f"FORGEAI_API_TOKEN={token_hex(32)}\n", encoding="utf-8"
+    )
+    referent_digest = sha256(referent.read_bytes()).digest()
+    env_path = out_dir / ".env"
+    env_path.symlink_to(referent)
+    referent_was_read = False
+    real_read_text = Path.read_text
+
+    def observe_completed_read(path, *args, **kwargs):
+        nonlocal referent_was_read
+        content = real_read_text(path, *args, **kwargs)
+        if Path(path) == env_path:
+            referent_was_read = True
+        return content
+
+    monkeypatch.setattr(Path, "read_text", observe_completed_read)
+
+    with pytest.raises(OSError):
+        bootstrap_secrets(out_dir)
+
+    if referent_was_read:
+        raise AssertionError("bootstrap read an env symlink referent")
+    if sha256(referent.read_bytes()).digest() != referent_digest:
+        raise AssertionError("bootstrap changed an env symlink referent")
+
+
+def test_non_regen_env_fifo_symlink_uses_nofollow_nonblocking_open(
+    tmp_path, monkeypatch
+):
+    out_dir = tmp_path / "out"
+    out_dir.mkdir()
+    fifo_referent = tmp_path / "external-env-fifo"
+    os.mkfifo(fifo_referent)
+    env_path = out_dir / ".env"
+    env_path.symlink_to(fifo_referent)
+    observed_flags: list[int] = []
+    path_read_attempted = False
+    real_open = os.open
+    real_read_text = Path.read_text
+
+    def observe_real_open(path, flags, *args, **kwargs):
+        if Path(path) == env_path:
+            observed_flags.append(flags)
+            required = os.O_NOFOLLOW | os.O_NONBLOCK
+            if flags & required != required:
+                raise OSError("unsafe env open flags")
+        return real_open(path, flags, *args, **kwargs)
+
+    def reject_blocking_path_read(path, *args, **kwargs):
+        nonlocal path_read_attempted
+        if Path(path) == env_path:
+            path_read_attempted = True
+            raise OSError("blocking env read refused by test")
+        return real_read_text(path, *args, **kwargs)
+
+    monkeypatch.setattr(vault_module.os, "open", observe_real_open)
+    monkeypatch.setattr(Path, "read_text", reject_blocking_path_read)
+
+    with pytest.raises(OSError):
+        bootstrap_secrets(out_dir)
+
+    if path_read_attempted:
+        raise AssertionError("bootstrap attempted a blocking FIFO read")
+    if len(observed_flags) != 1:
+        raise AssertionError("bootstrap did not perform one bounded env open")
+    assert env_path.is_symlink()
+    assert stat.S_ISFIFO(fifo_referent.stat().st_mode)
+
+
+def test_bootstrap_refuses_secrets_directory_symlink_before_any_write(tmp_path):
+    out_dir = tmp_path / "out"
+    out_dir.mkdir()
+    external_dir = tmp_path / "external-secrets"
+    external_dir.mkdir()
+    os.chmod(external_dir, 0o750)
+    external_mode = stat.S_IMODE(external_dir.stat().st_mode)
+    external_key = external_dir / "forgeai_token.key"
+    external_key.write_text(token_hex(32) + "\n", encoding="utf-8")
+    os.chmod(external_key, 0o640)
+    external_key_mode = stat.S_IMODE(external_key.stat().st_mode)
+    external_key_digest = sha256(external_key.read_bytes()).digest()
+    secrets_dir = out_dir / "secrets"
+    secrets_dir.symlink_to(external_dir, target_is_directory=True)
+    original_link = os.readlink(secrets_dir)
+
+    with pytest.raises(OSError):
+        bootstrap_secrets(out_dir)
+
+    assert secrets_dir.is_symlink()
+    assert os.readlink(secrets_dir) == original_link
+    assert stat.S_IMODE(external_dir.stat().st_mode) == external_mode
+    assert stat.S_IMODE(external_key.stat().st_mode) == external_key_mode
+    if sha256(external_key.read_bytes()).digest() != external_key_digest:
+        raise AssertionError("bootstrap changed a secret-directory referent")
+    if (out_dir / ".env").exists():
+        raise AssertionError("bootstrap wrote env before directory validation")
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
+    monkeypatch.setattr(vault_module.os, "open", open_after_swap)
+    monkeypatch.setattr(vault_module.os, "chmod", chmod_after_swap)
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
+    monkeypatch.setattr(vault_module.os, "open", open_then_pause)
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
index a079737..d2506fb 100644
--- a/tests/test_openbao_flow.py
+++ b/tests/test_openbao_flow.py
@@ -1,61 +1,136 @@
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
+from forgeai.models import vault as vault_module
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
     d = tmp_path / "keys"
     d.mkdir(parents=True)
     os.chmod(d, 0o700)  # trop restrictif au départ (l'unsealer non-root ne pourrait pas traverser)
     prepare_key_store(d)
     assert oct(d.stat().st_mode & 0o777) == "0o711"
 
 
+@pytest.mark.parametrize("initial_mode", [0, 0o500])
+def test_prepare_key_store_restores_exact_mode_from_restrictive_directory(
+    tmp_path, initial_mode
+) -> None:
+    keys_dir = tmp_path / "keys"
+    keys_dir.mkdir()
+    os.chmod(keys_dir, initial_mode)
+
+    prepare_key_store(keys_dir)
+
+    assert stat.S_IMODE(keys_dir.stat().st_mode) == 0o711
+
+
+def test_prepare_key_store_uses_nofollow_descriptor_not_pathname_chmod(
+    tmp_path, monkeypatch
+) -> None:
+    keys_dir = tmp_path / "keys"
+    observed_flags: list[int] = []
+    real_open = os.open
+    real_chmod = os.chmod
+
+    def observe_directory_open(path, flags, *args, **kwargs):
+        descriptor = real_open(path, flags, *args, **kwargs)
+        if Path(path) == keys_dir:
+            observed_flags.append(flags)
+        return descriptor
+
+    def reject_pathname_chmod(path, mode, *args, **kwargs):
+        if Path(path) == keys_dir:
+            raise AssertionError("prepare_key_store used pathname chmod")
+        return real_chmod(path, mode, *args, **kwargs)
+
+    monkeypatch.setattr(vault_module.os, "open", observe_directory_open)
+    monkeypatch.setattr(vault_module.os, "chmod", reject_pathname_chmod)
+    previous_umask = os.umask(0)
+    try:
+        assert prepare_key_store(keys_dir) == keys_dir
+    finally:
+        os.umask(previous_umask)
+
+    required = os.O_NOFOLLOW | os.O_DIRECTORY
+    if len(observed_flags) != 1 or observed_flags[0] & required != required:
+        raise AssertionError("prepare_key_store did not validate one directory descriptor")
+    assert stat.S_IMODE(keys_dir.stat().st_mode) == 0o711
+
+
+def test_prepare_key_store_refuses_symlink_without_changing_referent(
+    tmp_path,
+) -> None:
+    external = tmp_path / "external-keys"
+    external.mkdir()
+    os.chmod(external, 0o750)
+    external_mode = stat.S_IMODE(external.stat().st_mode)
+    marker = external / "marker"
+    marker.write_bytes(token_hex(32).encode("ascii"))
+    marker_digest = sha256(marker.read_bytes()).digest()
+    keys_dir = tmp_path / "keys"
+    keys_dir.symlink_to(external, target_is_directory=True)
+    original_link = os.readlink(keys_dir)
+
+    with pytest.raises(OSError):
+        prepare_key_store(keys_dir)
+
+    assert keys_dir.is_symlink()
+    assert os.readlink(keys_dir) == original_link
+    assert stat.S_IMODE(external.stat().st_mode) == external_mode
+    if {entry.name for entry in external.iterdir()} != {"marker"}:
+        raise AssertionError("prepare_key_store wrote through a symlink")
+    if sha256(marker.read_bytes()).digest() != marker_digest:
+        raise AssertionError("prepare_key_store changed symlink referent content")
+
+
 # --- 2. FileKeyStore (isolation du root) ------------------------------------
 
 def test_file_key_store_read_none_before_write(tmp_path) -> None:
     store = FileKeyStore(tmp_path / "keys", tmp_path / "secrets" / "root_token")
     assert store.read() is None
 
 
 def test_file_key_store_write_read_and_root_isolation(tmp_path) -> None:
     keys_dir = tmp_path / "keys"
     root_path = tmp_path / "secrets" / "root_token"
@@ -68,38 +143,529 @@ def test_file_key_store_write_read_and_root_isolation(tmp_path) -> None:
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
+@pytest.mark.parametrize("initial_mode", [0, 0o500])
+def test_file_key_store_restores_unsealer_access_on_restrictive_keys_directory(
+    tmp_path, initial_mode
+) -> None:
+    keys_dir = tmp_path / "keys"
+    keys_dir.mkdir()
+    os.chmod(keys_dir, initial_mode)
+    root_path = tmp_path / "root-secrets" / "root_token"
+
+    FileKeyStore(keys_dir, root_path).write(
+        {"unseal_key": "UNSEAL", "root_token": "ROOT"}
+    )
+
+    assert stat.S_IMODE(keys_dir.stat().st_mode) == 0o711
+    assert stat.S_IMODE((keys_dir / "unseal_key").stat().st_mode) == 0o644
+    assert stat.S_IMODE(root_path.parent.stat().st_mode) == 0o700
+    assert stat.S_IMODE(root_path.stat().st_mode) == 0o600
+
+
+@pytest.mark.parametrize("requested_umask", [0, 0o777])
+def test_file_key_store_parent_modes_are_secure_from_first_creation(
+    tmp_path, monkeypatch, requested_umask
+) -> None:
+    keys_dir = tmp_path / "keys"
+    root_parent = tmp_path / "root-secrets"
+    root_path = root_parent / "root_token"
+    observed_modes: dict[Path, list[int]] = {
+        keys_dir: [],
+        root_parent: [],
+    }
+    real_mkdir = os.mkdir
+
+    def observe_real_mkdir(path, mode=0o777, *args, **kwargs):
+        result = real_mkdir(path, mode, *args, **kwargs)
+        candidate = Path(path)
+        if candidate in observed_modes:
+            observed_modes[candidate].append(
+                stat.S_IMODE(os.lstat(candidate).st_mode)
+            )
+        return result
+
+    monkeypatch.setattr(vault_module.os, "mkdir", observe_real_mkdir)
+    previous_umask = os.umask(requested_umask)
+    try:
+        FileKeyStore(keys_dir, root_path).write(
+            {"unseal_key": "UNSEAL", "root_token": "ROOT"}
+        )
+    finally:
+        os.umask(previous_umask)
+
+    expected_modes = {keys_dir: 0o711, root_parent: 0o700}
+    for candidate, expected_mode in expected_modes.items():
+        modes = observed_modes[candidate]
+        if not modes or any(mode & ~expected_mode for mode in modes):
+            raise AssertionError(
+                f"file key store parent creation was unsafe: {candidate.name}"
+            )
+        assert stat.S_IMODE(candidate.stat().st_mode) == expected_mode
+    assert stat.S_IMODE((keys_dir / "unseal_key").stat().st_mode) == 0o644
+    assert stat.S_IMODE(root_path.stat().st_mode) == 0o600
+
+
+def test_file_key_store_refuses_root_parent_symlink_without_external_change(
+    tmp_path,
+) -> None:
+    external = tmp_path / "external-root"
+    external.mkdir()
+    os.chmod(external, 0o750)
+    external_mode = stat.S_IMODE(external.stat().st_mode)
+    marker = external / "marker"
+    marker.write_bytes(token_hex(32).encode("ascii"))
+    marker_digest = sha256(marker.read_bytes()).digest()
+    root_parent = tmp_path / "root-secrets"
+    root_parent.symlink_to(external, target_is_directory=True)
+
+    with pytest.raises(OSError):
+        FileKeyStore(tmp_path / "keys", root_parent / "root_token").write(
+            {"unseal_key": "UNSEAL", "root_token": "ROOT"}
+        )
+
+    assert stat.S_IMODE(external.stat().st_mode) == external_mode
+    if {entry.name for entry in external.iterdir()} != {"marker"}:
+        raise AssertionError("file key store wrote through root-parent symlink")
+    if sha256(marker.read_bytes()).digest() != marker_digest:
+        raise AssertionError("file key store changed root-parent referent")
+
+
+def test_file_key_store_refuses_keys_parent_symlink_before_secret_write(
+    tmp_path,
+) -> None:
+    external = tmp_path / "external-keys"
+    external.mkdir()
+    os.chmod(external, 0o750)
+    external_mode = stat.S_IMODE(external.stat().st_mode)
+    marker = external / "marker"
+    marker.write_bytes(token_hex(32).encode("ascii"))
+    marker_digest = sha256(marker.read_bytes()).digest()
+    keys_dir = tmp_path / "keys"
+    keys_dir.symlink_to(external, target_is_directory=True)
+    root_path = tmp_path / "root-secrets" / "root_token"
+
+    with pytest.raises(OSError):
+        FileKeyStore(keys_dir, root_path).write(
+            {"unseal_key": "UNSEAL", "root_token": "ROOT"}
+        )
+
+    assert not root_path.exists()
+    assert stat.S_IMODE(external.stat().st_mode) == external_mode
+    if {entry.name for entry in external.iterdir()} != {"marker"}:
+        raise AssertionError("file key store wrote through keys-parent symlink")
+    if sha256(marker.read_bytes()).digest() != marker_digest:
+        raise AssertionError("file key store changed keys-parent referent")
+
+
+def test_file_key_store_read_refuses_target_symlink_before_referent_read(
+    tmp_path, monkeypatch
+) -> None:
+    keys_dir = tmp_path / "keys"
+    keys_dir.mkdir()
+    external = tmp_path / "external-unseal"
+    external.write_text("UNSEAL\n", encoding="utf-8")
+    external_digest = sha256(external.read_bytes()).digest()
+    unseal_path = keys_dir / "unseal_key"
+    unseal_path.symlink_to(external)
+    root_path = tmp_path / "root-secrets" / "root_token"
+    root_path.parent.mkdir()
+    root_path.write_text("ROOT\n", encoding="utf-8")
+    referent_was_read = False
+    real_read_text = Path.read_text
+
+    def observe_completed_read(path, *args, **kwargs):
+        nonlocal referent_was_read
+        content = real_read_text(path, *args, **kwargs)
+        if Path(path) == unseal_path:
+            referent_was_read = True
+        return content
+
+    monkeypatch.setattr(Path, "read_text", observe_completed_read)
+
+    with pytest.raises(OSError):
+        FileKeyStore(keys_dir, root_path).read()
+
+    if referent_was_read:
+        raise AssertionError("file key store read a target-symlink referent")
+    if sha256(external.read_bytes()).digest() != external_digest:
+        raise AssertionError("file key store changed target-symlink referent")
+
+
+def test_file_key_store_read_refuses_fifo_without_blocking(
+    tmp_path, monkeypatch
+) -> None:
+    keys_dir = tmp_path / "keys"
+    keys_dir.mkdir()
+    unseal_path = keys_dir / "unseal_key"
+    unseal_path.write_text("UNSEAL\n", encoding="utf-8")
+    root_path = tmp_path / "root-secrets" / "root_token"
+    root_path.parent.mkdir()
+    os.mkfifo(root_path)
+    observed_flags: list[int] = []
+    path_read_attempted = False
+    real_open = os.open
+    real_read_text = Path.read_text
+
+    def observe_real_open(path, flags, *args, **kwargs):
+        if Path(path) == root_path:
+            observed_flags.append(flags)
+            required = os.O_NOFOLLOW | os.O_NONBLOCK
+            if flags & required != required:
+                raise OSError("unsafe root-token open flags")
+        return real_open(path, flags, *args, **kwargs)
+
+    def reject_blocking_path_read(path, *args, **kwargs):
+        nonlocal path_read_attempted
+        if Path(path) == root_path:
+            path_read_attempted = True
+            raise OSError("blocking root-token read refused by test")
+        return real_read_text(path, *args, **kwargs)
+
+    monkeypatch.setattr(vault_module.os, "open", observe_real_open)
+    monkeypatch.setattr(Path, "read_text", reject_blocking_path_read)
+
+    with pytest.raises(OSError):
+        FileKeyStore(keys_dir, root_path).read()
+
+    if path_read_attempted:
+        raise AssertionError("file key store attempted a blocking FIFO read")
+    if len(observed_flags) != 1:
+        raise AssertionError("file key store did not perform one bounded root open")
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
 
 
+@pytest.mark.parametrize("requested_umask", [0, 0o777])
+def test_file_secret_store_parent_is_secure_from_first_creation(
+    tmp_path, monkeypatch, requested_umask
+) -> None:
+    parent = tmp_path / "app-secrets"
+    target = parent / "app_token.json"
+    observed_creation_modes: list[int] = []
+    real_mkdir = os.mkdir
+
+    def observe_real_mkdir(path, mode=0o777, *args, **kwargs):
+        result = real_mkdir(path, mode, *args, **kwargs)
+        if Path(path) == parent:
+            observed_creation_modes.append(
+                stat.S_IMODE(os.lstat(parent).st_mode)
+            )
+        return result
+
+    monkeypatch.setattr(vault_module.os, "mkdir", observe_real_mkdir)
+    previous_umask = os.umask(requested_umask)
+    try:
+        FileSecretStore(target).write({"token": token_hex(32)})
+    finally:
+        os.umask(previous_umask)
+
+    if not observed_creation_modes or any(
+        mode & ~0o700 for mode in observed_creation_modes
+    ):
+        raise AssertionError("file secret store parent creation was unsafe")
+    assert stat.S_IMODE(parent.stat().st_mode) == 0o700
+    assert stat.S_IMODE(target.stat().st_mode) == 0o600
+
+
+def test_file_secret_store_refuses_parent_symlink_before_external_change(
+    tmp_path,
+) -> None:
+    external = tmp_path / "external-app-secrets"
+    external.mkdir()
+    os.chmod(external, 0o750)
+    external_mode = stat.S_IMODE(external.stat().st_mode)
+    marker = external / "marker"
+    marker.write_bytes(token_hex(32).encode("ascii"))
+    marker_digest = sha256(marker.read_bytes()).digest()
+    parent = tmp_path / "app-secrets"
+    parent.symlink_to(external, target_is_directory=True)
+
+    with pytest.raises(OSError):
+        FileSecretStore(parent / "app_token.json").write(
+            {"token": token_hex(32)}
+        )
+
+    assert stat.S_IMODE(external.stat().st_mode) == external_mode
+    if {entry.name for entry in external.iterdir()} != {"marker"}:
+        raise AssertionError("file secret store wrote through parent symlink")
+    if sha256(marker.read_bytes()).digest() != marker_digest:
+        raise AssertionError("file secret store changed parent-symlink referent")
+
+
+def test_file_secret_store_read_refuses_symlink_before_referent_read(
+    tmp_path, monkeypatch
+) -> None:
+    external = tmp_path / "external-app-token"
+    external.write_text('{"token":"external"}\n', encoding="utf-8")
+    external_digest = sha256(external.read_bytes()).digest()
+    target = tmp_path / "app_token.json"
+    target.symlink_to(external)
+    referent_was_read = False
+    real_read_text = Path.read_text
+
+    def observe_completed_read(path, *args, **kwargs):
+        nonlocal referent_was_read
+        content = real_read_text(path, *args, **kwargs)
+        if Path(path) == target:
+            referent_was_read = True
+        return content
+
+    monkeypatch.setattr(Path, "read_text", observe_completed_read)
+
+    with pytest.raises(OSError):
+        FileSecretStore(target).read()
+
+    if referent_was_read:
+        raise AssertionError("file secret store read a target-symlink referent")
+    if sha256(external.read_bytes()).digest() != external_digest:
+        raise AssertionError("file secret store changed target-symlink referent")
+
+
+def test_file_secret_store_read_refuses_fifo_without_blocking(
+    tmp_path, monkeypatch
+) -> None:
+    target = tmp_path / "app-token.fifo"
+    os.mkfifo(target)
+    observed_flags: list[int] = []
+    path_read_attempted = False
+    real_open = os.open
+    real_read_text = Path.read_text
+
+    def observe_real_open(path, flags, *args, **kwargs):
+        if Path(path) == target:
+            observed_flags.append(flags)
+            required = os.O_NOFOLLOW | os.O_NONBLOCK
+            if flags & required != required:
+                raise OSError("unsafe app-token open flags")
+        return real_open(path, flags, *args, **kwargs)
+
+    def reject_blocking_path_read(path, *args, **kwargs):
+        nonlocal path_read_attempted
+        if Path(path) == target:
+            path_read_attempted = True
+            raise OSError("blocking app-token read refused by test")
+        return real_read_text(path, *args, **kwargs)
+
+    monkeypatch.setattr(vault_module.os, "open", observe_real_open)
+    monkeypatch.setattr(Path, "read_text", reject_blocking_path_read)
+
+    with pytest.raises(OSError):
+        FileSecretStore(target).read()
+
+    if path_read_attempted:
+        raise AssertionError("file secret store attempted a blocking FIFO read")
+    if len(observed_flags) != 1:
+        raise AssertionError("file secret store did not perform one bounded target open")
+
+
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
+    monkeypatch.setattr(vault_module.os, "fsync", record_real_fsync)
+    monkeypatch.setattr(vault_module.os, "replace", fail_before_replace)
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
+    monkeypatch.setattr(vault_module.os, "fsync", record_real_fsync)
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
index 11cbef5..7213c22 100644
--- a/tests/test_vault.py
+++ b/tests/test_vault.py
@@ -1,27 +1,33 @@
 """Story E3b — client coffre openbao (KV v2), stdlib pur.
 
 Spec exécutable (TDAD, AVANT le code). Un faux serveur openbao KV v2 (http.server) valide le
 contrat HTTP réel : écriture `POST /v1/secret/data/<path>` + lecture `GET …` authentifiées par
 en-tête `X-Vault-Token`. Le comportement contre un openbao RÉEL est prouvé par l'e2e journalisé
 au registre. Invariant secrets : ni le token ni la valeur ne doivent apparaître dans une exception.
 """
 import json
+import os
+import stat
 import sys
 import threading
+from hashlib import sha256
 from http.server import BaseHTTPRequestHandler, HTTPServer
 from pathlib import Path
+from secrets import token_hex
 
 import pytest
 
 sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
 
+from forgeai.models import vault as file_vault_module
+from forgeai.models.vault import Vault as FileVault
 from forgeai.secrets.vault import VaultError, read, store
 
 TOKEN = "root-token-e3b"
 
 
 class _KVHandler(BaseHTTPRequestHandler):
     """openbao KV v2 minimal : exige le bon X-Vault-Token, stocke/rend sous data.data."""
 
     store: dict = {}
 
@@ -97,12 +103,171 @@ def test_mauvais_token_leve_vaulterror(bao):
 
 
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
+def test_model_vault_refuses_target_symlink_before_reading_referent(
+    tmp_path, monkeypatch
+):
+    referent = tmp_path / "external-vault.json"
+    referent.write_text('{"external": "unchanged"}', encoding="utf-8")
+    referent_digest = sha256(referent.read_bytes()).digest()
+    target = tmp_path / "vault.json"
+    target.symlink_to(referent)
+    original_link = os.readlink(target)
+    sentinel = token_hex(32)
+    referent_was_read = False
+    real_read_text = Path.read_text
+
+    def observe_completed_read(path, *args, **kwargs):
+        nonlocal referent_was_read
+        content = real_read_text(path, *args, **kwargs)
+        if Path(path) == target:
+            referent_was_read = True
+        return content
+
+    monkeypatch.setattr(Path, "read_text", observe_completed_read)
+
+    with pytest.raises(OSError) as caught:
+        FileVault(target).put("cloud-key", sentinel, "test-passphrase")
+
+    if sentinel in str(caught.value):
+        raise AssertionError("vault exception disclosed the secret payload")
+    if referent_was_read:
+        raise AssertionError("vault read a target-symlink referent")
+    assert target.is_symlink()
+    assert os.readlink(target) == original_link
+    if sha256(referent.read_bytes()).digest() != referent_digest:
+        raise AssertionError("vault changed a target-symlink referent")
+
+
+def test_model_vault_refuses_fifo_without_blocking_read(tmp_path, monkeypatch):
+    target = tmp_path / "vault-fifo"
+    os.mkfifo(target)
+    observed_flags: list[int] = []
+    path_read_attempted = False
+    real_open = os.open
+    real_read_text = Path.read_text
+
+    def observe_real_open(path, flags, *args, **kwargs):
+        if Path(path) == target:
+            observed_flags.append(flags)
+            required = os.O_NOFOLLOW | os.O_NONBLOCK
+            if flags & required != required:
+                raise OSError("unsafe vault open flags")
+        return real_open(path, flags, *args, **kwargs)
+
+    def reject_blocking_path_read(path, *args, **kwargs):
+        nonlocal path_read_attempted
+        if Path(path) == target:
+            path_read_attempted = True
+            raise OSError("blocking vault read refused by test")
+        return real_read_text(path, *args, **kwargs)
+
+    monkeypatch.setattr(file_vault_module.os, "open", observe_real_open)
+    monkeypatch.setattr(Path, "read_text", reject_blocking_path_read)
+
+    with pytest.raises(OSError):
+        FileVault(target).names()
+
+    if path_read_attempted:
+        raise AssertionError("vault attempted a blocking FIFO read")
+    if len(observed_flags) != 1:
+        raise AssertionError("vault did not perform one bounded target open")
+    assert stat.S_ISFIFO(target.stat().st_mode)
+
+
+def test_model_vault_refuses_parent_symlink_before_external_change(tmp_path):
+    external_dir = tmp_path / "external-vault-parent"
+    external_dir.mkdir()
+    os.chmod(external_dir, 0o750)
+    external_mode = stat.S_IMODE(external_dir.stat().st_mode)
+    external_file = external_dir / "existing"
+    external_file.write_bytes(token_hex(32).encode("ascii"))
+    external_digest = sha256(external_file.read_bytes()).digest()
+    parent_link = tmp_path / "vault-parent"
+    parent_link.symlink_to(external_dir, target_is_directory=True)
+    original_link = os.readlink(parent_link)
+
+    with pytest.raises(OSError):
+        FileVault(parent_link / "vault.json").put(
+            "cloud-key", token_hex(32), "test-passphrase"
+        )
+
+    assert parent_link.is_symlink()
+    assert os.readlink(parent_link) == original_link
+    assert stat.S_IMODE(external_dir.stat().st_mode) == external_mode
+    if {entry.name for entry in external_dir.iterdir()} != {"existing"}:
+        raise AssertionError("vault wrote through a parent symlink")
+    if sha256(external_file.read_bytes()).digest() != external_digest:
+        raise AssertionError("vault changed parent-symlink referent content")
+
+
+def test_model_vault_parent_is_private_at_first_creation(tmp_path, monkeypatch):
+    parent = tmp_path / "vault-parent"
+    target = parent / "vault.json"
+    observed_creation_modes: list[int] = []
+    real_mkdir = os.mkdir
+
+    def observe_real_mkdir(path, mode=0o777, *args, **kwargs):
+        result = real_mkdir(path, mode, *args, **kwargs)
+        if Path(path) == parent:
+            observed_creation_modes.append(stat.S_IMODE(os.lstat(path).st_mode))
+        return result
+
+    monkeypatch.setattr(file_vault_module.os, "mkdir", observe_real_mkdir)
+    previous_umask = os.umask(0)
+    try:
+        FileVault(target).put("cloud-key", token_hex(32), "test-passphrase")
+    finally:
+        os.umask(previous_umask)
+
+    if not observed_creation_modes or any(
+        mode & ~0o700 for mode in observed_creation_modes
+    ):
+        raise AssertionError("vault parent exposed excess creation permissions")
+    assert stat.S_IMODE(parent.stat().st_mode) == 0o700
+    assert stat.S_IMODE(target.stat().st_mode) == 0o600
+
+
+def test_model_vault_creates_nested_parent_under_restrictive_umask(
+    tmp_path, monkeypatch
+):
+    parents = (tmp_path / "a", tmp_path / "a" / "b")
+    target = parents[-1] / "vault.json"
+    observed_creation_modes = {candidate: [] for candidate in parents}
+    real_mkdir = os.mkdir
+
+    def observe_real_mkdir(path, mode=0o777, *args, **kwargs):
+        result = real_mkdir(path, mode, *args, **kwargs)
+        candidate = Path(path)
+        if candidate in observed_creation_modes:
+            observed_creation_modes[candidate].append(
+                stat.S_IMODE(os.lstat(candidate).st_mode)
+            )
+        return result
+
+    monkeypatch.setattr(file_vault_module.os, "mkdir", observe_real_mkdir)
+    previous_umask = os.umask(0o777)
+    try:
+        vault = FileVault(target)
+        vault.put("first-key", token_hex(32), "test-passphrase")
+        vault.put("second-key", token_hex(32), "test-passphrase")
+    finally:
+        os.umask(previous_umask)
+
+    for candidate, modes in observed_creation_modes.items():
+        if not modes or any(mode & ~0o700 for mode in modes):
+            raise AssertionError(
+                f"vault parent creation was not private: {candidate.name}"
+            )
+        assert stat.S_IMODE(candidate.stat().st_mode) == 0o700
+    assert stat.S_IMODE(target.stat().st_mode) == 0o600

