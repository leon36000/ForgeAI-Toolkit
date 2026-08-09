# Pack de revue — CAND-001 (audit v7.1)

## Story
Constat CAND-001, P1_HIGH : aucun des 9 sites `urllib.request.urlopen()` du
produit ne validait le schéma de l'URL avant ouverture. `urlopen` accepte
`file://`, ce qui en faisait un lecteur de fichier local arbitraire pour
toute URL non fiable (catalogue, plugin communautaire, configuration
importée). Reproduit sur le chemin public réel (cli.py -> LocalModel.download_url
-> download_verified() -> Fetcher.fetch() -> urlopen), rejoué sur pc4
(second environnement, Python 3.14.4) durant l'audit v7.1.

## Critères de revue
1. La garde `valider_schema_url` refuse-t-elle bien tout schéma hors
   http/https, y compris l'absence de schéma ?
2. Chaque site `urlopen` est-il réellement couvert (9 sites, 10 appels) ?
3. La garde est-elle placée AVANT toute capture d'exception qui pourrait
   la ré-étiqueter (ValidationError hérite de ValueError) ?
4. Le comportement des 2 sondes booléennes (deploy/compose.py) est-il
   cohérent (retour False plutôt que levée, car ce sont des sondes de
   santé qui échouent déjà silencieusement sur toute autre erreur) ?
5. La preuve TDD est-elle réelle : tests rouges AVANT le fix, contre-preuve
   par mutation, suite complète sans régression ?

## Diff intégral
```diff
diff --git a/src/forgeai/audit/immudb.py b/src/forgeai/audit/immudb.py
index 9aa38dc..982f2bd 100644
--- a/src/forgeai/audit/immudb.py
+++ b/src/forgeai/audit/immudb.py
@@ -21,6 +21,7 @@ import json
 import urllib.error
 import urllib.request
 
+from forgeai.core.validation import valider_schema_url
 from forgeai.i18n import t
 
 _API = "/api/v2"
@@ -38,6 +39,8 @@ def _request(method: str, url: str, token: str | None, payload: dict | None,
         req.add_header("Content-Type", "application/json")
     if token:
         req.add_header("grpc-metadata-sessionid", token)
+    # HORS du try : ValidationError hérite de ValueError, capturé plus bas.
+    valider_schema_url(url)
     try:
         with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — URL locale/LAN du socle
             body = resp.read().decode("utf-8")
diff --git a/src/forgeai/core/validation.py b/src/forgeai/core/validation.py
index 2f619fd..9e90b11 100644
--- a/src/forgeai/core/validation.py
+++ b/src/forgeai/core/validation.py
@@ -1,10 +1,18 @@
 """Validateurs partagés (source unique — évite la duplication CLI ↔ web ↔ …)."""
 import os
 import re
+import urllib.parse
 from pathlib import Path
 
 from forgeai.i18n import t
 
+# CAND-001 (audit v7.1) : `urllib.request.urlopen` accepte `file://`, ce qui en
+# fait un lecteur de fichier local pour toute URL non validée. Source UNIQUE
+# réutilisée par les 9 modules qui appellent urlopen (models/local.py,
+# rag/client.py, rag/hardened.py, secrets/vault.py, secrets/openbao_init.py,
+# audit/immudb.py, deploy/compose.py, models/probe.py, observability/langfuse.py).
+SCHEMAS_URL_AUTORISES = frozenset({"http", "https"})
+
 # Nom de nœud / hôte : label RFC1123 en minuscules (a-z0-9, tirets/points internes, 1-63 car.).
 # Source UNIQUE réutilisée par cli.py et web/server.py (FAI-0016 : dé-duplication).
 NODE_NAME_RE = re.compile(r"^[a-z0-9]([a-z0-9.-]{0,62})\Z", re.ASCII)
@@ -66,3 +74,19 @@ def resolve_within(
         )
 
     return Path(cible_reelle)
+
+
+def valider_schema_url(url: str) -> None:
+    """Lève ValidationError si `url` n'a pas un schéma http(s) explicite.
+
+    Sans ce contrôle, `urllib.request.urlopen` accepte `file://` — et devient
+    un lecteur de fichier local pour toute URL non fiable (catalogue, plugin
+    communautaire, configuration importée). Le schéma DOIT être présent et
+    explicitement autorisé ; l'absence de schéma n'est jamais traitée comme
+    un cas par défaut sûr.
+    """
+    schema = urllib.parse.urlsplit(url).scheme.lower()
+    if schema not in SCHEMAS_URL_AUTORISES:
+        raise ValidationError(
+            t("core.validation.valider_schema_url.schema_refuse",
+              url=url, schema=schema or "(absent)"))
diff --git a/src/forgeai/data/locales/en.json b/src/forgeai/data/locales/en.json
index 131c030..8b0078a 100644
--- a/src/forgeai/data/locales/en.json
+++ b/src/forgeai/data/locales/en.json
@@ -202,6 +202,7 @@
   "core.registre_ancrage.checkpoint_de.registre_vide": "cannot create a checkpoint on an empty registry: anchoring nothing is forbidden",
   "core.validation.resolve_within.chemin_hors_racine": "path outside root: {cible!r} is not within {racine!r}",
   "core.validation.valider_nom_simple.nom_invalide": "invalid name: {name!r}",
+  "core.validation.valider_schema_url.schema_refuse": "URL scheme refused: {schema!r} for {url!r} — only http and https are allowed",
   "deploy.compose.compose_down.echec": "docker compose down failed:\n{detail}",
   "deploy.compose.compose_up.echec": "docker compose up failed:\n{detail}",
   "deploy.compose.wait_healthy.contrat_absent": "ERR_HEALTH_CONTRAT_ABSENT: service '{name}' requires health but has no exploitable probe contract (probe_type={probe_type!r}, healthcheck_url={healthcheck_url!r})",
diff --git a/src/forgeai/data/locales/fr.json b/src/forgeai/data/locales/fr.json
index 4a27d36..8ca251e 100644
--- a/src/forgeai/data/locales/fr.json
+++ b/src/forgeai/data/locales/fr.json
@@ -202,6 +202,7 @@
   "core.registre_ancrage.checkpoint_de.registre_vide": "impossible de creer un checkpoint sur un registre vide : un ancrage-de-rien est interdit",
   "core.validation.resolve_within.chemin_hors_racine": "chemin hors racine : {cible!r} n'est pas dans {racine!r}",
   "core.validation.valider_nom_simple.nom_invalide": "nom invalide : {name!r}",
+  "core.validation.valider_schema_url.schema_refuse": "schéma d'URL refusé : {schema!r} pour {url!r} — seuls http et https sont autorisés",
   "deploy.compose.compose_down.echec": "docker compose down a échoué :\n{detail}",
   "deploy.compose.compose_up.echec": "docker compose up a échoué :\n{detail}",
   "deploy.compose.wait_healthy.contrat_absent": "ERR_HEALTH_CONTRAT_ABSENT: service '{name}' exige la santé mais n'a pas de contrat de sonde exploitable (probe_type={probe_type!r}, healthcheck_url={healthcheck_url!r})",
diff --git a/src/forgeai/deploy/compose.py b/src/forgeai/deploy/compose.py
index ed84122..df372b6 100644
--- a/src/forgeai/deploy/compose.py
+++ b/src/forgeai/deploy/compose.py
@@ -13,6 +13,7 @@ import urllib.request
 from pathlib import Path
 
 from forgeai.core.models import HealthState, ProbeType, ServiceSpec
+from forgeai.core.validation import valider_schema_url
 from forgeai.core.redaction import redact_text
 from forgeai.i18n import t
 
@@ -48,6 +49,10 @@ def compose_down(compose_file: Path, volumes: bool = False) -> None:
 
 def http_ok(url: str, timeout_s: float = 3.0) -> bool:
     try:
+        # DANS le try : cette fonction est une sonde booléenne, un schéma
+        # invalide est déjà « pas sain » comme toute autre erreur ci-dessous
+        # (ValidationError hérite de ValueError, capturé par le même except).
+        valider_schema_url(url)
         with urllib.request.urlopen(url, timeout=timeout_s) as resp:
             return 200 <= resp.status < 300
     except (urllib.error.URLError, OSError, ValueError):
@@ -173,6 +178,7 @@ def wait_healthy(plan, timeout_s: float = 180.0, probe=None) -> dict:
 
     def _default_probe(url: str) -> bool:
         try:
+            valider_schema_url(url)
             urlopen(url, timeout=2)
             return True
         except Exception:
diff --git a/src/forgeai/models/local.py b/src/forgeai/models/local.py
index 0798324..339ddfe 100644
--- a/src/forgeai/models/local.py
+++ b/src/forgeai/models/local.py
@@ -16,6 +16,7 @@ from dataclasses import dataclass
 from pathlib import Path
 from typing import Callable, Protocol
 
+from forgeai.core.validation import valider_schema_url
 from forgeai.i18n import t
 
 from ..core.runner import CommandRunner
@@ -59,6 +60,7 @@ class UrllibFetcher:
         import urllib.request
         total = 0
         dest.parent.mkdir(parents=True, exist_ok=True)
+        valider_schema_url(url)
         with urllib.request.urlopen(url, timeout=timeout) as resp, dest.open("wb") as fh:
             while True:
                 buf = resp.read(self.chunk)
diff --git a/src/forgeai/models/probe.py b/src/forgeai/models/probe.py
index 3944096..6e618d1 100644
--- a/src/forgeai/models/probe.py
+++ b/src/forgeai/models/probe.py
@@ -27,7 +27,10 @@ class UrllibTransport:
              ) -> tuple[int, str]:
         import urllib.error
         import urllib.request
+
+        from forgeai.core.validation import valider_schema_url
         req = urllib.request.Request(url, data=body, headers=headers, method="POST")
+        valider_schema_url(url)
         try:
             with urllib.request.urlopen(req, timeout=timeout) as resp:
                 return resp.status, resp.read().decode("utf-8", "replace")
diff --git a/src/forgeai/observability/langfuse.py b/src/forgeai/observability/langfuse.py
index b8e6a4b..3c84ea9 100644
--- a/src/forgeai/observability/langfuse.py
+++ b/src/forgeai/observability/langfuse.py
@@ -15,6 +15,7 @@ import time
 import urllib.error
 import urllib.request
 
+from forgeai.core.validation import valider_schema_url
 from forgeai.i18n import t
 
 _TRACES = "/api/public/traces"
@@ -26,8 +27,11 @@ class ObservabilityError(RuntimeError):
 
 def _get(base_url: str, public_key: str, secret_key: str, path: str, timeout: float) -> dict:
     token = base64.b64encode(f"{public_key}:{secret_key}".encode()).decode()
-    req = urllib.request.Request(f"{base_url.rstrip('/')}{path}")
+    url = f"{base_url.rstrip('/')}{path}"
+    req = urllib.request.Request(url)
     req.add_header("Authorization", f"Basic {token}")
+    # HORS du try : ValidationError hérite de ValueError, capturé plus bas.
+    valider_schema_url(url)
     try:
         with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — URL locale/LAN
             return json.loads(resp.read().decode("utf-8"))
diff --git a/src/forgeai/rag/client.py b/src/forgeai/rag/client.py
index 8504c41..aad9460 100644
--- a/src/forgeai/rag/client.py
+++ b/src/forgeai/rag/client.py
@@ -11,6 +11,7 @@ import urllib.error
 import urllib.request
 from dataclasses import dataclass
 
+from forgeai.core.validation import valider_schema_url
 from forgeai.i18n import t
 
 
@@ -19,6 +20,7 @@ def _post(url: str, payload: dict, timeout_s: float = 300.0) -> dict:
         url, data=json.dumps(payload).encode("utf-8"),
         headers={"Content-Type": "application/json"}, method="POST",
     )
+    valider_schema_url(url)
     with urllib.request.urlopen(req, timeout=timeout_s) as resp:
         return json.loads(resp.read().decode("utf-8"))
 
@@ -28,6 +30,7 @@ def _put(url: str, payload: dict, timeout_s: float = 60.0) -> dict:
         url, data=json.dumps(payload).encode("utf-8"),
         headers={"Content-Type": "application/json"}, method="PUT",
     )
+    valider_schema_url(url)
     with urllib.request.urlopen(req, timeout=timeout_s) as resp:
         return json.loads(resp.read().decode("utf-8"))
 
diff --git a/src/forgeai/rag/hardened.py b/src/forgeai/rag/hardened.py
index afc91cf..de6ecc6 100644
--- a/src/forgeai/rag/hardened.py
+++ b/src/forgeai/rag/hardened.py
@@ -27,6 +27,7 @@ from forgeai.guardrails.io_guard import (
     scan_output,
     verify_grounding,
 )
+from forgeai.core.validation import valider_schema_url
 from forgeai.rag.client import RagClient, _post
 
 
@@ -41,6 +42,7 @@ def _post_bearer(url: str, payload: dict, bearer: str, timeout_s: float = 300.0)
         },
         method="POST",
     )
+    valider_schema_url(url)
     with urllib.request.urlopen(req, timeout=timeout_s) as resp:
         return json.loads(resp.read().decode("utf-8"))
 
diff --git a/src/forgeai/secrets/openbao_init.py b/src/forgeai/secrets/openbao_init.py
index 5f1e3f4..2124289 100644
--- a/src/forgeai/secrets/openbao_init.py
+++ b/src/forgeai/secrets/openbao_init.py
@@ -12,6 +12,7 @@ import urllib.request
 from collections.abc import Callable
 from typing import Any
 
+from forgeai.core.validation import valider_schema_url
 from forgeai.i18n import t
 
 # ---------------------------------------------------------------------------
@@ -64,6 +65,9 @@ def http_transport(base_url: str, timeout: float = 10.0):
             req.add_header("X-Vault-Token", token)
         if data_bytes is not None:
             req.add_header("Content-Type", "application/json")
+        # HORS du try : ValidationError hérite de ValueError, capturé plus
+        # bas pour « réponse illisible ».
+        valider_schema_url(url)
         try:
             with urllib.request.urlopen(req, timeout=timeout) as resp:
                 body = resp.read().decode("utf-8")
diff --git a/src/forgeai/secrets/vault.py b/src/forgeai/secrets/vault.py
index 90948fe..d7ca38c 100644
--- a/src/forgeai/secrets/vault.py
+++ b/src/forgeai/secrets/vault.py
@@ -14,6 +14,7 @@ import json
 import urllib.error
 import urllib.request
 
+from forgeai.core.validation import valider_schema_url
 from forgeai.i18n import t
 
 _KV_PREFIX = "/v1/secret/data/"
@@ -34,6 +35,10 @@ def _request(method: str, url: str, token: str, payload: dict | None, timeout: f
     req.add_header("X-Vault-Token", token)
     if data is not None:
         req.add_header("Content-Type", "application/json")
+    # HORS du try : ValidationError hérite de ValueError, et le bloc ci-dessous
+    # attrape ValueError pour « réponse non-JSON ». Dans le try, le refus de
+    # schéma serait ré-étiqueté à tort en erreur de parsing.
+    valider_schema_url(url)
     try:
         with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — URL locale/LAN du socle
             body = resp.read().decode("utf-8")
diff --git a/tests/test_core_validation.py b/tests/test_core_validation.py
index 9f71394..e21f4e6 100644
--- a/tests/test_core_validation.py
+++ b/tests/test_core_validation.py
@@ -153,3 +153,68 @@ def test_resolve_within_rejette_repertoire_frere_prefixe_commun(tmp_path):
     cible_ok.write_text("x")
     result = resolve_within(cible_ok, repo)
     assert result == Path(os.path.realpath(cible_ok))
+
+
+# --- valider_schema_url (CAND-001 : aucun controle de schema sur les 9 sites
+# urlopen du produit — file:// permettait de lire un fichier local arbitraire) ---
+
+
+def test_valider_schema_url_https_accepte():
+    from forgeai.core.validation import valider_schema_url
+    assert valider_schema_url("https://api.exemple.com/v1") is None
+
+
+def test_valider_schema_url_http_accepte():
+    from forgeai.core.validation import valider_schema_url
+    assert valider_schema_url("http://127.0.0.1:11434/api") is None
+
+
+def test_valider_schema_url_file_refuse():
+    from forgeai.core.validation import valider_schema_url
+    with pytest.raises(ValidationError):
+        valider_schema_url("file:///etc/passwd")
+
+
+def test_valider_schema_url_sans_schema_refuse():
+    from forgeai.core.validation import valider_schema_url
+    with pytest.raises(ValidationError):
+        valider_schema_url("etc/passwd")
+
+
+def test_valider_schema_url_ftp_refuse():
+    from forgeai.core.validation import valider_schema_url
+    with pytest.raises(ValidationError):
+        valider_schema_url("ftp://exemple.com/fichier")
+
+
+def test_valider_schema_url_data_refuse():
+    with pytest.raises(pytest.importorskip("forgeai.core.validation").ValidationError):
+        pytest.importorskip("forgeai.core.validation").valider_schema_url("data:text/plain;base64,eA==")
+
+
+def test_valider_schema_url_message_erreur_nomme_le_schema():
+    from forgeai.core.validation import valider_schema_url
+    with pytest.raises(ValidationError) as exc_info:
+        valider_schema_url("file:///secret.txt")
+    assert "file" in str(exc_info.value)
+
+
+def test_download_verified_refuse_file_scheme_sur_le_chemin_public(tmp_path):
+    """REPRODUCTION EXACTE de CAND-001 : download_verified() est le point
+    d'entree public reel (cli.py -> LocalModel.download_url -> ici). Avant
+    le fix, un `download_url="file:///secret"` lisait le fichier local et
+    l'ecrivait dans la destination — reproduit dans l'audit v7.1 sur pc4."""
+    import hashlib
+    from forgeai.models.local import LocalModel, UrllibFetcher, download_verified
+
+    fichier_prive = tmp_path / "hors-perimetre.txt"
+    fichier_prive.write_bytes(b"CONTENU QUI NE DOIT JAMAIS ETRE LU PAR UN TELECHARGEMENT\n")
+    empreinte = hashlib.sha256(fichier_prive.read_bytes()).hexdigest()
+    dest = tmp_path / "dest"; dest.mkdir()
+    modele = LocalModel(name="modele-piege", engine="llamacpp", model_ref="x",
+                        vram_required_mb=0, download_url="file://%s" % fichier_prive,
+                        sha256=empreinte)
+    with pytest.raises(ValidationError):
+        download_verified(modele, dest, UrllibFetcher())
+    assert not (dest / "modele-piege.bin").exists(), \
+        "le fichier local a ete lu et ecrit malgre le schema file://"
```

## Preuve d'exécution
- Baseline (code intact) : 1899 passed, 7 skipped, 0 failed
- Après fix : 1907 passed (1899 + 8 nouveaux), 7 skipped, 0 failed
- Contre-preuve (garde neutralisée par mutation minimale) : 6/8 tests rouges
  dont `test_download_verified_refuse_file_scheme_sur_le_chemin_public`
- `py_compile` sur tous les fichiers modifiés : succès

## Limite d'indépendance du panel (transparence, mesurée par l'audit v7.1)
Le panel de revue de cette story utilise les 3 points de confiance mesurés
en direct sur la passerelle : DeepSeek (route directe), un modèle Alibaba/Qwen
(route directe), et un modèle routé via OpenRouter (intermédiaire unique).
Voir Q-COURTIER-UNIQUE au registre de l'audit v7.1.

## Round 2 — réfutation mesurée de l'objection majeure (Kimi-K3, round 1)

**Objection round 1 (Kimi-K3, majeure)** : « Garde contournable par redirection :
l'opener par défaut suit les 301/302/303/307 sans revérifier le schéma de
l'URL cible ; une URL http(s) peut répondre 302 vers file:///etc/passwd et
urlopen lira le fichier local APRÈS passage de valider_schema_url. »

**Réfutation par la mesure** (script exécuté, sortie brute ci-dessous) :
un serveur HTTP local répond 302 avec `Location: file:///tmp/....txt` à une
requête `urlopen("http://127.0.0.1:PORT/")`. Résultat réel :

```
REFUSE : HTTPError HTTP Error 302: Found - Redirection to url 'file:///tmp/....txt' is not allowed
```

`urllib.request.HTTPRedirectHandler` de la stdlib CPython refuse déjà nativement
toute redirection dont le schéma cible n'est pas dans sa liste blanche
(`http`, `https`, `ftp` selon version) — `file://` en est exclu de longue date
(protection historique de la stdlib elle-même, pas ajoutée par ce diff).

**Portée de la réfutation** : elle couvre EXACTEMENT le cas décrit par
l'objection (redirection vers `file://`). Elle NE couvre PAS un scénario
distinct non soulevé par l'objection (redirection vers un service interne
http(s), type SSRF) — hors périmètre de CAND-001 tel que scellé, qui porte
spécifiquement sur le schéma `file://`.

Round 2 demandé au même trio scellé : l'objection majeure tient-elle compte
de cette preuve ? Les 5 objections mineures des 3 verdicts restent à traiter
séparément si le panel les maintient.
