# PACK DE REVUE — TRUST-019B (FAI-U-019) : HMAC Tier 1 pour le registre
## Défaut prouvé : verify() SHA-256 nu -> réécriture INTÉGRALE cohérente NON détectée (renvoie None).
## Implémente l'ADR TRUST-019A §9 : key_id optionnel, rétro-compat Tier 0 stricte, clé 0600 par commande explicite,
## UNVERIFIED si racine absente. IMPORTANT : le test rouge a révélé une ATTAQUE PAR DÉCLASSEMENT dans la 1re
## implémentation (entrée sans key_id acceptée en SHA-256 nu malgré une clé fournie) -> corrigée par un refus explicite.
## Preuves d'exécution : (1) chaîne saine -> OK ; (2) réécriture intégrale -> INVALID 'déclassement refusé' ;
## (3) Tier1 sans clé -> UNVERIFIED ; (4) Tier0 historique -> None (rétro-compat). Suite complète verte, no-stub OK, gitleaks 0.
## Limite déclarée (ADR §3) : Tier 1 ne défend PAS contre root ni contre le même UID que l'écrivain.

```diff
diff --git a/src/forgeai/core/registre.py b/src/forgeai/core/registre.py
index 6ca9c56..a385112 100644
--- a/src/forgeai/core/registre.py
+++ b/src/forgeai/core/registre.py
@@ -1,19 +1,26 @@
 #!/usr/bin/env python3
 """Registre append-only hash-chaîné (JSONL) — module canonique du Toolkit.
 
-Chaque entrée : {seq, ts, type, actor, payload, prev_hash, hash} où
+Tier 0 : SHA-256 nu sur le JSON canonique de l'entrée sans son champ ``hash``.
+Tier 1 (TRUST-019B) : HMAC-SHA256 à clé locale par entrée, optionnel et
+rétro-compatible via le champ ``key_id``.
+
+Chaque entrée : {seq, ts, type, actor, payload, prev_hash, hash[, key_id]} où
 hash = sha256 du JSON canonique (clés triées) de l'entrée sans son champ "hash",
+ou HMAC-SHA256(clé, JSON canonique) lorsqu'un ``key_id`` est présent,
 et prev_hash = hash de l'entrée précédente (64 zéros pour la genèse).
 
 Usage :
-    registre.py append <fichier.jsonl> --type <t> --actor <a> [--payload-json '<json>']
-    registre.py verify <fichier.jsonl> [...]
+    registre.py append <fichier.jsonl> --type <t> --actor <a> [--payload-json '<json>'] [--key <clé.hex>]
+    registre.py verify <fichier.jsonl> [...] [--key <clé.hex>]
 """
 import argparse
 import fcntl
 import hashlib
+import hmac
 import json
 import os
+import secrets
 import sys
 from datetime import datetime, timezone
 from pathlib import Path
@@ -21,10 +28,27 @@ from pathlib import Path
 GENESIS = "0" * 64
 
 
-def _entry_hash(entry: dict) -> str:
+def _key_id(key: bytes) -> str:
+    """Empreinte publique d'une clé HMAC (16 premiers hex de sha256)."""
+    return hashlib.sha256(key).hexdigest()[:16]
+
+
+def _load_key(key_path: Path) -> bytes:
+    """Lit une clé stockée en hexadécimal."""
+    return bytes.fromhex(key_path.read_text(encoding="utf-8").strip())
+
+
+def _canonical_material(entry: dict) -> bytes:
     material = {k: v for k, v in entry.items() if k != "hash"}
-    blob = json.dumps(material, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
-    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
+    return json.dumps(material, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
+
+
+def _entry_hash(entry: dict) -> str:
+    return hashlib.sha256(_canonical_material(entry)).hexdigest()
+
+
+def _entry_hmac(key: bytes, entry: dict) -> str:
+    return hmac.new(key, _canonical_material(entry), hashlib.sha256).hexdigest()
 
 
 def _parse_entries_from_text(text: str, source: str = "") -> list[dict]:
@@ -49,7 +73,41 @@ def _read_entries(path: Path) -> list[dict]:
     return _parse_entries_from_text(path.read_text(encoding="utf-8"), source=str(path))  # NOSONAR
 
 
-def append(path: Path, type_: str, actor: str, payload: dict) -> dict:
+def init_key(path: Path) -> str:
+    """Crée une clé HMAC locale (32 octets, permissions 0600) et renvoie son key_id.
+
+    Idempotent : si le fichier existe déjà, renvoie le key_id de la clé existante.
+    """
+    path.parent.mkdir(parents=True, exist_ok=True)
+    try:
+        fd = os.open(path, os.O_CREAT | os.O_WRONLY | os.O_EXCL, 0o600)
+    except FileExistsError:
+        existing_hex = path.read_text(encoding="utf-8").strip()
+        return _key_id(bytes.fromhex(existing_hex))
+
+    try:
+        key = secrets.token_bytes(32)
+        with os.fdopen(fd, "w", encoding="utf-8") as fh:
+            fh.write(key.hex() + "\n")
+            fh.flush()
+            os.fsync(fh.fileno())
+        return _key_id(key)
+    except Exception:
+        try:
+            os.close(fd)
+        except OSError:
+            pass
+        raise
+
+
+def append(
+    path: Path,
+    type_: str,
+    actor: str,
+    payload: dict,
+    *,
+    key_path: Path | None = None,
+) -> dict:
     path.parent.mkdir(parents=True, exist_ok=True)  # ex. ~/.forgeai/Registres/ (P3)
     # `path` = registre app/opérateur (pas d'entrée HTTP) ; chemin non dérivé d'input.
     with path.open("a+", encoding="utf-8") as fh:  # NOSONAR
@@ -65,7 +123,12 @@ def append(path: Path, type_: str, actor: str, payload: dict) -> dict:
             "payload": payload,
             "prev_hash": prev_hash,
         }
-        entry["hash"] = _entry_hash(entry)
+        if key_path is not None:
+            key = _load_key(key_path)
+            entry["key_id"] = _key_id(key)
+            entry["hash"] = _entry_hmac(key, entry)
+        else:
+            entry["hash"] = _entry_hash(entry)
         line = json.dumps(entry, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
         fh.seek(0, os.SEEK_END)
         fh.write(line + "\n")
@@ -75,19 +138,77 @@ def append(path: Path, type_: str, actor: str, payload: dict) -> dict:
     return entry
 
 
-def verify(path: Path) -> str | None:
-    """Retourne None si la chaîne est intègre, sinon la description de la rupture."""
+def verify(path: Path, *, key_path: Path | None = None) -> str | None:
+    """Retourne None si la chaîne est intègre, sinon la description de la rupture.
+
+    - Entrée sans ``key_id`` : vérification SHA-256 nu (rétro-compatible Tier 0)
+      uniquement si aucune clé n'est fournie.
+    - Entrée avec ``key_id`` : vérification HMAC-SHA256 avec ``key_path``.
+      Si ``key_path`` est manquant ou ne correspond pas au ``key_id``,
+      une erreur explicite est retournée (jamais None silencieux).
+    - Si une clé est fournie mais qu'une entrée n'a pas de ``key_id``,
+      l'entrée est refusée (défense contre le déclassement Tier 1 -> Tier 0).
+    """
+    key: bytes | None = None
+    expected_key_id: str | None = None
+    if key_path is not None:
+        key = _load_key(key_path)
+        expected_key_id = _key_id(key)
+
     prev_hash = GENESIS
     for entry in _read_entries(path):
         seq = entry.get("seq")
         if entry.get("prev_hash") != prev_hash:
             return f"seq {seq}: prev_hash ne chaîne pas avec l'entrée précédente"
-        if _entry_hash(entry) != entry.get("hash"):
-            return f"seq {seq}: hash invalide (entrée altérée)"
+
+        entry_key_id = entry.get("key_id")
+        if key is not None:
+            if entry_key_id is None:
+                return (
+                    f"seq {seq}: entrée sans key_id alors qu'une clé est fournie "
+                    f"(déclassement Tier 1 -> Tier 0 refusé)"
+                )
+            if entry_key_id != expected_key_id:
+                return f"seq {seq}: key_id {entry_key_id} ne correspond pas à la clé fournie"
+            if not hmac.compare_digest(_entry_hmac(key, entry), entry.get("hash", "")):
+                return f"seq {seq}: hash HMAC invalide (entrée altérée)"
+        else:
+            if entry_key_id is not None:
+                return f"seq {seq}: key_id {entry_key_id} présent mais aucune clé fournie (UNVERIFIED)"
+            if not hmac.compare_digest(_entry_hash(entry), entry.get("hash", "")):
+                return f"seq {seq}: hash invalide (entrée altérée)"
+
         prev_hash = entry["hash"]
     return None
 
 
+def verify_status(path: Path, *, key_path: Path | None = None) -> str:
+    """Renvoie OK, UNVERIFIED ou INVALID selon l'état du registre.
+
+    - OK        : la chaîne est intègre.
+    - UNVERIFIED: au moins une entrée porte un key_id mais aucune clé n'est disponible.
+    - INVALID   : une erreur de chaînage, d'intégrité ou de déclassement est détectée.
+    """
+    entries = _read_entries(path)
+    has_keyed = any("key_id" in e for e in entries)
+
+    if has_keyed:
+        if key_path is None or not key_path.exists():
+            return "UNVERIFIED"
+        try:
+            _load_key(key_path)
+        except (OSError, ValueError):
+            return "UNVERIFIED"
+
+    if key_path is not None and entries and any("key_id" not in e for e in entries):
+        return "INVALID"
+
+    error = verify(path, key_path=key_path)
+    if error is not None:
+        return "INVALID"
+    return "OK"
+
+
 def main() -> None:
     parser = argparse.ArgumentParser(description=__doc__)
     sub = parser.add_subparsers(dest="cmd", required=True)
@@ -97,19 +218,27 @@ def main() -> None:
     p_append.add_argument("--type", required=True, dest="type_")
     p_append.add_argument("--actor", required=True)
     p_append.add_argument("--payload-json", default="{}")
+    p_append.add_argument("--key", type=Path, default=None, help="clé HMAC locale (hex)")
 
     p_verify = sub.add_parser("verify", help="vérifie l'intégrité de la chaîne")
     p_verify.add_argument("registres", type=Path, nargs="+")
+    p_verify.add_argument("--key", type=Path, default=None, help="clé HMAC locale (hex)")
 
     args = parser.parse_args()
     if args.cmd == "append":
-        entry = append(args.registre, args.type_, args.actor, json.loads(args.payload_json))
+        entry = append(
+            args.registre,
+            args.type_,
+            args.actor,
+            json.loads(args.payload_json),
+            key_path=args.key,
+        )
         print(json.dumps(entry, ensure_ascii=False))
         return
 
     failed = False
     for path in args.registres:
-        error = verify(path)
+        error = verify(path, key_path=args.key)
         if error:
             print(f"ECHEC {path}: {error}")
             failed = True
diff --git a/tests/test_registre.py b/tests/test_registre.py
index cce9f26..3459068 100644
--- a/tests/test_registre.py
+++ b/tests/test_registre.py
@@ -96,3 +96,63 @@ def test_ligne_json_invalide_rejetee(tmp_path):
     reg.write_text("{pas du json\n", encoding="utf-8")
     with pytest.raises(SystemExit, match="JSON invalide"):
         registre.verify(reg)
+
+
+# ── TRUST-019B (FAI-U-019) — Tier 1 : HMAC-SHA256 à clé locale ────────────────
+# ADR TRUST-019A §9 : key_id optionnel par entrée ; verify rétro-compatible avec les
+# entrées Tier 0 (sans key_id -> SHA-256 nu) ; clé générée par commande EXPLICITE en 0600 ;
+# sans racine disponible -> statut UNVERIFIED/échec explicite, jamais silencieusement OK.
+import os
+import stat as _stat
+
+from forgeai.core import registre as core_registre
+
+
+def test_init_key_cree_une_cle_locale_en_0600(tmp_path):
+    """`init_key` (commande explicite, jamais implicite) crée la clé HMAC en 0600."""
+    key_path = tmp_path / "hmac.key"
+    key_id = core_registre.init_key(key_path)
+    assert key_id and isinstance(key_id, str)
+    assert key_path.exists()
+    assert _stat.S_IMODE(os.stat(key_path).st_mode) == 0o600
+    # idempotence : ne régénère pas silencieusement une clé existante
+    assert core_registre.init_key(key_path) == key_id
+
+
+def test_reecriture_integrale_detectee_avec_hmac(tmp_path):
+    """Défaut FAI-U-019 : une réécriture TOTALE cohérente passait verify(). Avec une clé
+    HMAC (Tier 1), l'attaquant sans la clé ne peut pas reforger la chaîne -> DÉTECTÉE."""
+    key_path = tmp_path / "hmac.key"
+    core_registre.init_key(key_path)
+    reg = tmp_path / "r.jsonl"
+    for i in range(3):
+        core_registre.append(reg, "t", "auteur", {"i": i}, key_path=key_path)
+    assert core_registre.verify(reg, key_path=key_path) is None  # chaîne saine
+
+    # l'attaquant réécrit TOUT de façon cohérente, SANS la clé (Tier 0 seulement)
+    entries = [json.loads(l) for l in reg.read_text(encoding="utf-8").splitlines()]
+    reg.unlink()
+    for e in entries:
+        core_registre.append(reg, "t", "attaquant", {**e["payload"], "HOSTILE": True})
+    erreur = core_registre.verify(reg, key_path=key_path)
+    assert erreur, "réécriture intégrale NON détectée (régression FAI-U-019)"
+
+
+def test_sans_cle_les_entrees_hmac_sont_unverified(tmp_path):
+    """Racine indisponible : statut UNVERIFIED explicite, jamais un OK silencieux."""
+    key_path = tmp_path / "hmac.key"
+    core_registre.init_key(key_path)
+    reg = tmp_path / "r.jsonl"
+    core_registre.append(reg, "t", "auteur", {"i": 1}, key_path=key_path)
+    statut = core_registre.verify_status(reg, key_path=None)
+    assert statut == "UNVERIFIED", statut
+
+
+def test_retrocompat_entrees_tier0_sans_key_id(tmp_path):
+    """Entrées historiques (sans key_id) : vérification SHA-256 nue, aucune migration destructive."""
+    reg = tmp_path / "r.jsonl"
+    core_registre.append(reg, "t", "auteur", {"i": 1})          # Tier 0, pas de clé
+    core_registre.append(reg, "t", "auteur", {"i": 2})
+    assert core_registre.verify(reg) is None
+    entries = [json.loads(l) for l in reg.read_text(encoding="utf-8").splitlines()]
+    assert all("key_id" not in e for e in entries)
```
