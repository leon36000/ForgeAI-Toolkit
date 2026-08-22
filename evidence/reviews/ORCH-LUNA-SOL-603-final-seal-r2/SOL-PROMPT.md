Tu es reviewer de code Sol. Analyse uniquement l'ARTEFACT ci-dessous dans un contexte
frais et en lecture seule.
Ne consulte aucun autre verdict et ne suppose aucun résultat attendu.

STORY : stories/ORCH-LUNA-SOL-603.md
CRITÈRES D'ACCEPTATION :
- [x] La politique versionnée fixe GPT-5.6 Luna, exactement deux writer lanes,
  GPT-5.6 Sol, le mode frais/aveugle/read-only et les états terminaux.
- [x] Le dispatch de revue conserve le tally historique `multi_vendor` et
  exige un unique reviewer Sol pour `sol_blind`.
- [x] Le reçu Sol lie le diff Git, l’arbre, le prompt, les journaux exclus et
  les limites de fraîcheur sans dépendre de la configuration locale de Git.
- [x] La documentation, les registres, les vues et le test de non-régression du
  gate archive sont prêts. Le contrôle de l’archive de preuve est effectué par
  `reviews_gate.py`, séparément du diff canonique présenté au reviewer Sol.
- [ ] Le reçu Sol final est scellé dans
  `evidence/reviews/ORCH-LUNA-SOL-603-final-seal/RECU.json`, lié au manifeste
  actif, puis le gate PR et le gate archive sur `main` fusionné passent.
- [ ] La story passe à `DONE_WITH_EVIDENCE` uniquement après ces preuves;
  aucune réussite runtime, matérielle, réseau ou externe n’est revendiquée.

ARTEFACT — canonical-git-diff :
diff --git .github/workflows/gates.yml .github/workflows/gates.yml
index 86f7651a5687eff6aa9dd45efe62ba5230bbb37f..8907829a519b6f32ba71e62db1cc6c1fc78d9045 100644
--- .github/workflows/gates.yml
+++ .github/workflows/gates.yml
@@ -197,6 +197,10 @@ jobs:
       - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4
         with:
           persist-credentials: false
+          # Le test d'archive de la matrice vérifie que le commit Sol revu est
+          # ancêtre de l'arbre courant ; un checkout superficiel ne peut pas
+          # établir cette preuve sur le merge ref d'une PR.
+          fetch-depth: 0
       - uses: actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065 # v5
         with:
           python-version: ${{ matrix.python-version }}
diff --git Docs/reference/autonomy-luna-sol.md Docs/reference/autonomy-luna-sol.md
index f533b6811976610ef420fe8724bb700628ff7935..3251c301af9e46d39ed0951f50b3fa3cefa2f690 100644
--- Docs/reference/autonomy-luna-sol.md
+++ Docs/reference/autonomy-luna-sol.md
@@ -1,7 +1,7 @@
 # Référence exécutable — autonomie Luna/Sol
 
-Cette phase versionne le noyau du contrat de l’issue #603. La source de vérité
-est `governance/autonomy-policy.json`; la décision associée est
+Cette référence décrit l’implémentation finale et son protocole de scellement
+pour l’issue #603. La source de vérité est `governance/autonomy-policy.json`; la décision associée est
 `governance/decisions/D-2026-08-21-autonomie-luna-sol.md`.
 
 La règle d’absence d’écriture distante s’applique aux workflows du contrat
@@ -15,10 +15,14 @@ aveugle et strictement read-only. `multi_vendor` reste un mode historique
 d’archive et conserve son quorum 3/3.
 
 Le prompt Sol est reconstruit depuis le diff Git exact et les critères de la
-story `stories/ORCH-LUNA-SOL-603.md`. Le reçu lie les commits, arbres, digest
-du diff, prompt, template, journaux SDD et registre de mission; les digests
-neutralisent les configurations Git globales qui pourraient modifier ou
-ordonner la sortie. Le reviewer n’écrit jamais dans le dépôt.
+story `stories/ORCH-LUNA-SOL-603.md`. Après approbation de l’implémentation,
+le reçu final attendu sera
+`evidence/reviews/ORCH-LUNA-SOL-603-final-seal/RECU.json`; il liera les commits,
+arbres, digest du diff, prompt, template, journaux SDD et registre de mission.
+Le champ `candidate_diff_digest` reste le digest canonique des entrées Git brutes;
+`artifact_sha256` scelle séparément les octets exacts du diff texte présenté à Sol.
+Les digests neutralisent les configurations Git globales qui pourraient
+modifier ou ordonner la sortie. Le reviewer n’écrit jamais dans le dépôt.
 
 Le gate sans drapeau conserve le dépouillement historique, vérifie la forme/cohérence interne
 du reçu et le hash du prompt, mais ne recharge pas ses objets Git; cela reste compatible avec
@@ -42,9 +46,17 @@ Pour distinguer un reçu historique d’un reçu courant, le mode PR vérifie d
 intrinsèques et les futures, classe la liaison via Git, puis applique la fenêtre actuelle au
 reçu courant; l’historique est validé à l’heure de son scellement.
 
+Le mode archive exige en plus que chaque reçu encore présent dans
+`evidence/reviews/BINDING.txt` pointe vers un commit ancêtre de `main`. Les
+quatorze reçus historiques qui ne satisfaisaient plus cette preuve ont été
+retirés du manifeste actif, sans supprimer leurs dossiers; leurs identités et
+commits sont consignés dans `evidence/reviews/ARCHIVE-UNMERGED.txt`. Ils restent
+consultables mais ne sont pas réintroduits comme preuve liante sans nouvelle
+revue.
+
 Les limites T3 restent humaines : paiements, secrets de production,
 suppressions définitives et engagements externes. Les états terminaux sont
-`DONE_WITH_EVIDENCE` et `BLOCKED_WITH_REASON`; cette phase ne prétend aucun
+`DONE_WITH_EVIDENCE` et `BLOCKED_WITH_REASON`; cette livraison ne prétend aucun
 résultat runtime, matériel ou externe.
 
 Vérifications de la phase :
@@ -54,8 +66,11 @@ python3 scripts/governance/validate_authority.py
 python3 scripts/governance/state_current.py
 python3 scripts/governance/classify_paths.py
 python3 scripts/reviews_gate.py --exiger-recu-courant --base-ref origin/main --issue <pr>
+python3 scripts/reviews_gate.py --mode archive
 python3 -m pytest -q
 ```
 
-La preuve Sol et le dossier documentaire final sont ajoutés dans une phase
-bornée ultérieure, avec les fichiers qu’ils déclarent réellement.
+Le statut `DONE_WITH_EVIDENCE` de la story n’est recevable que lorsque ces
+commandes passent, que `BINDING.txt` contient le reçu final et que le mode
+archive réussit sur l’arbre fusionné. Une preuve non retrouvée reste
+`BLOCKED_WITH_REASON`; aucun transcript ou état runtime ne la remplace.
diff --git Docs/superpowers/plans/2026-08-22-autonomous-luna-sol.md Docs/superpowers/plans/2026-08-22-autonomous-luna-sol.md
new file mode 100644
index 0000000000000000000000000000000000000000..29185aa061bae3996849c5d291e37c10c15f1711
--- /dev/null
+++ Docs/superpowers/plans/2026-08-22-autonomous-luna-sol.md
@@ -0,0 +1,35 @@
+# Plan de livraison — autonomie Luna/Sol
+
+## État initial
+
+La phase compacte (#609) avait déjà livré la politique, le dispatch Sol, la
+validation de reçu et la preuve `ORCH-LUNA-SOL-603-phaseA-r5`. Après fusion,
+l’audit archive a révélé quatorze entrées historiques de `BINDING.txt` ne
+pointaient plus vers des ancêtres de `main`; l’état antérieur à #609 présentait
+le même défaut.
+
+## Exécution bornée
+
+1. Retirer uniquement ces entrées du manifeste actif, conserver les dossiers et
+   consigner chaque retrait dans `ARCHIVE-UNMERGED.txt`.
+2. Ajouter la preuve de non-régression du mode archive au test du manifeste réel.
+3. Mettre à jour la story et la référence exécutable, puis ajouter ce plan et
+   la spécification de conception.
+4. Ajouter l’événement de livraison au registre avec `scripts/registre.py
+   append`, régénérer les vues et vérifier l’autorité.
+5. Construire un prompt Sol frais et aveugle pour le diff final, obtenir son
+   APPROVE, sceller le reçu `ORCH-LUNA-SOL-603-final-seal`, l’ajouter à
+   `BINDING.txt`, puis exécuter les gates PR locaux et CI avant le merge. La
+   story reste `IN_PROGRESS` pendant cette étape.
+6. Après le merge, rejouer le mode archive sur `main` fusionné. Si ce contrôle
+   passe, créer la transaction de clôture post-merge qui passe la story à
+   `DONE_WITH_EVIDENCE` et ajoute l’événement terminal au registre; sinon
+   conserver `BLOCKED_WITH_REASON` avec la sortie du gate.
+7. Vérifier les vues régénérées et l’état terminal après cette clôture; aucune
+   transition terminale n’est faite avant le contrôle archive post-merge.
+
+## Critère d’arrêt
+
+Le travail n’est terminé que si le gate archive, le gate PR, les tests complets,
+les registres et les vues générées passent, et si la preuve Sol finale est
+liée au diff exact. Sinon la story reste bloquée avec une raison vérifiable.
diff --git Docs/superpowers/specs/2026-08-22-autonomous-luna-sol-design.md Docs/superpowers/specs/2026-08-22-autonomous-luna-sol-design.md
new file mode 100644
index 0000000000000000000000000000000000000000..10d87911f67dc949efdc0528ab9a2806e3332cc9
--- /dev/null
+++ Docs/superpowers/specs/2026-08-22-autonomous-luna-sol-design.md
@@ -0,0 +1,40 @@
+# Design — contrat autonome Luna/Sol
+
+## Décision
+
+Luna est l’unique writer actif (`luna_writer`) et Sol est le reviewer actif
+(`sol`). La politique autorise exactement deux writer lanes, mais cette limite
+ne crée pas de permission d’écriture distante. Le mode de revue actif est
+`sol_blind`: contexte frais, aveugle et strictement read-only. Le quorum
+historique `multi_vendor` reste disponible uniquement pour les anciennes
+preuves.
+
+## Preuve et frontières
+
+Une revue Sol est une revendication vérifiable, pas une autorisation implicite.
+Le reçu doit lier le commit de base, le commit et l’arbre examinés, le digest
+du diff Git, le prompt et son template, ainsi que les digests séparés des
+journaux SDD et du registre de mission. Le dossier de revue, l’identité
+canonique `GPT-5.6-Sol`, les marqueurs fresh/blind/read-only et les dates sont
+contrôlés avant toute résolution Git. Le digest du diff ne contient jamais les
+artefacts de preuve de la revue elle-même.
+
+Le gate possède trois usages distincts :
+
+1. sans drapeau, dépouillement déterministe et contrôle de cohérence interne;
+2. en mode PR, liaison de la preuve au diff courant et contrôle de fraîcheur;
+3. en mode archive, vérification que chaque preuve encore liante est réellement
+   ancêtre de `main`.
+
+Les reçus historiques dont le commit n’est plus ancêtre ne sont pas effacés.
+Ils sont retirés de `BINDING.txt`, consignés dans
+`evidence/reviews/ARCHIVE-UNMERGED.txt` et nécessitent une nouvelle preuve pour
+redevenir liants.
+
+## Terminalité
+
+La story ne peut atteindre `DONE_WITH_EVIDENCE` qu’après les tests, les vues
+générées, les registres vérifiés, la revue Sol scellée et le gate archive sur
+`main`. Les limites T3 — paiements, secrets de production, suppressions
+définitives et engagements externes — restent humaines. Aucun workflow du
+contrat ne reçoit `contents: write`, ne force-push ou ne s’auto-écrit.
diff --git governance/STATE-CURRENT.json governance/STATE-CURRENT.json
index 1390efd903c0c5f5f2010b37507ed3c6ba01bcaa..d5c14de2bfb06c00a82709709b2e2353bec8fb07 100644
--- governance/STATE-CURRENT.json
+++ governance/STATE-CURRENT.json
@@ -772,7 +772,7 @@
       },
       {
         "path": "tests/test_reviews_gate.py",
-        "sha256": "7cb06c0393ef774f86bcb511949523bc6b494c88e59fbe3a37293b37f7962e90"
+        "sha256": "7d96815c823a245171dcdedd6b25407e4a1eb53ffd5142db2026404fdb740242"
       },
       {
         "path": "tests/test_revue.py",
@@ -1001,7 +1001,7 @@
     "tests": {
       "js_files": 3,
       "python_files": 209,
-      "python_functions_declared": 2692
+      "python_functions_declared": 2695
     }
   },
   "observations": [
diff --git governance/STATE-CURRENT.md governance/STATE-CURRENT.md
index 321493d0d8c77f400d315d75f36575f71fca0141..7cf1628ea689afad645e7355f4603d81617592af 100644
--- governance/STATE-CURRENT.md
+++ governance/STATE-CURRENT.md
@@ -778,7 +778,7 @@
     },
     {
       "path": "tests/test_reviews_gate.py",
-      "sha256": "7cb06c0393ef774f86bcb511949523bc6b494c88e59fbe3a37293b37f7962e90"
+      "sha256": "7d96815c823a245171dcdedd6b25407e4a1eb53ffd5142db2026404fdb740242"
     },
     {
       "path": "tests/test_revue.py",
@@ -1007,7 +1007,7 @@
   "tests": {
     "js_files": 3,
     "python_files": 209,
-    "python_functions_declared": 2692
+    "python_functions_declared": 2695
   }
 }
 ```
diff --git scripts/revue.py scripts/revue.py
index 29705791135378119c751599d69f01580efd8f39..a5cbc83fd1059781d0199e8ceeafcdacabd41388 100644
--- scripts/revue.py
+++ scripts/revue.py
@@ -69,6 +69,17 @@ _SOL_CANONICAL_T3_LIMITS = (
     "permanent_deletions",
     "external_commitments",
 )
+# The Phase-A receipt predates the displayed-artifact seal.  Its exemption is deliberately
+# exact rather than dossier-name based: any new/current Sol receipt must carry artifact_sha256.
+_SOL_LEGACY_ARTIFACT_EXEMPTION = {
+    "dossier": "ORCH-LUNA-SOL-603-phaseA-r5",
+    "base_commit": "d4d46ef36fcac3cdeb92a00577f78c8e698c17c0",
+    "head_commit": "c6a26100033512106be8aaf056bf9ee906108379",
+    "reviewed_head_commit": "c6a26100033512106be8aaf056bf9ee906108379",
+    "candidate_diff_digest": "ec404cfd230c26599c20beed847b0b9542e0a623067cef765805c1a6e6c0127b",
+    "prompt_sha256": "aa8d7621249e1b3326d627ef9319a77fe74d3ba020b7ecf0662643c9f774a769",
+    "template_sha256": "a5bebc60556f4fc38d6ca96a3d0372577550f23157377af4d852e6144e25f137",
+}
 # Freeze every Git setting that can change the textual patch or make the diff
 # plumbing fail under a caller's global configuration. The order file is a
 # tracked empty repository file, so this remains portable across Git hosts.
@@ -109,6 +120,14 @@ _BLOCKING = {"critique", "eleve", "majeure"}
 GitRunner = Callable[[list[str]], str]
 
 
+def _sol_legacy_artifact_exemption(recu: object) -> bool:
+    """Return true only for the one immutable Phase-A receipt without artifact_sha256."""
+    return isinstance(recu, dict) and all(
+        recu.get(field) == value
+        for field, value in _SOL_LEGACY_ARTIFACT_EXEMPTION.items()
+    )
+
+
 def _normalize(value: str) -> str:
     """Réduit un identifiant à ses seuls alphanumériques minuscules — "Qwen3.7-Max",
     "qwen 3.7 max" et "qwen37max" doivent tous résoudre au même vendor, quelle que soit la
@@ -404,6 +423,10 @@ def _sol_expected_from_receipt_shape(
         "mission_diff_digest", "template_sha256",
     ):
         _validate_digest(recu[field], field)
+    if "artifact_sha256" not in recu and not _sol_legacy_artifact_exemption(recu):
+        raise ValueError("artifact_sha256 requis pour tout reçu Sol courant")
+    if "artifact_sha256" in recu:
+        _validate_digest(recu["artifact_sha256"], "artifact_sha256")
     if recu["diff_digest"] != recu["candidate_diff_digest"]:
         raise ValueError("diff_digest différent de candidate_diff_digest")
     if _aware_timestamp(recu["date_heure"]) is None:
@@ -446,6 +469,8 @@ def _sol_expected_from_receipt_shape(
     ):
         if verdict.get(field) != recu[field]:
             raise ValueError(f"{field} du verdict différent du reçu Sol")
+    if "artifact_sha256" in recu and verdict.get("artifact_sha256") != recu["artifact_sha256"]:
+        raise ValueError("artifact_sha256 du verdict différent du reçu Sol")
     reviewers = recu["reviewers_attendus"]
     if not isinstance(reviewers, list) or len(reviewers) != 1:
         raise ValueError("nombre incorrect de reviewers Sol")
@@ -467,6 +492,8 @@ def _sol_expected_from_receipt_shape(
     ):
         if recu[field] != metadata[field]:
             raise ValueError(f"{field} différent des métadonnées du prompt Sol")
+    if "artifact_sha256" in recu and recu["artifact_sha256"] != metadata.get("artifact_sha256"):
+        raise ValueError("artifact_sha256 différent des métadonnées du prompt Sol")
     response_marker = "conforme à ce\nschéma :\n"
     response_tail = prompt_text.split(response_marker, 1)
     if len(response_tail) != 2:
@@ -496,13 +523,15 @@ def _sol_expected_from_receipt_shape(
         "blocking_findings": [],
         "reviewed_at": "timestamp ISO-8601 avec fuseau",
     }
+    if "artifact_sha256" in metadata:
+        response_expectations["artifact_sha256"] = metadata["artifact_sha256"]
     for field, expected_value in response_expectations.items():
         if response_schema.get(field) != expected_value:
             raise ValueError(f"{field} différent des métadonnées du schéma Sol")
     story_marker = f"STORY : {recu['story']}\n"
     if story_marker not in prompt_text:
         raise ValueError("story absente du prompt Sol")
-    return {
+    result = {
         "candidate_diff_digest": recu["candidate_diff_digest"],
         "diff_digest": recu["diff_digest"],
         "base_commit": recu["base_commit"],
@@ -514,6 +543,9 @@ def _sol_expected_from_receipt_shape(
         "template_sha256": recu["template_sha256"],
         "reviewed_at": recu["reviewed_at"],
     }
+    if "artifact_sha256" in recu:
+        result["artifact_sha256"] = recu["artifact_sha256"]
+    return result
 
 
 def _diff_artifact_canonique(
@@ -789,7 +821,8 @@ def build_prompt(story_id: str, criteres: str, artefact_path: str, artefact: str
                  template_path: Path = TEMPLATE, *, mode: str = "multi_vendor",
                  expected: dict | None = None, base_ref: str | None = None,
                  head_ref: str | None = None, runner: GitRunner | None = None,
-                 template_content: str | None = None) -> tuple[str, str]:
+                 template_content: str | None = None,
+                 include_artifact_sha256: bool = True) -> tuple[str, str]:
     """Render one exact, versioned prompt section and return its SHA-256."""
     if template_content is None:
         tpl = template_path.read_text(encoding="utf-8")
@@ -823,6 +856,10 @@ def build_prompt(story_id: str, criteres: str, artefact_path: str, artefact: str
             "mission_diff_digest": git_state["mission_diff_digest"],
             "template_sha256": template_sha256,
         }
+        if include_artifact_sha256:
+            metadata["artifact_sha256"] = hashlib.sha256(
+                canonical_artifact.encode("utf-8")
+            ).hexdigest()
         if expected is not None:
             for field, value in metadata.items():
                 expected_value = expected.get(field)
@@ -912,6 +949,7 @@ def _canonical_sol_prompt(
     reviewed_head_commit: str,
     *,
     runner: GitRunner | None = None,
+    include_artifact_sha256: bool = True,
 ) -> tuple[bytes, str]:
     """Rebuild the exact Sol prompt from frozen Git objects and versioned inputs."""
     execute = _default_runner if runner is None else runner
@@ -930,6 +968,7 @@ def _canonical_sol_prompt(
         head_ref=frozen_head,
         runner=execute,
         template_content=template_content,
+        include_artifact_sha256=include_artifact_sha256,
     )
     return prompt.encode("utf-8"), prompt_sha
 
@@ -971,6 +1010,8 @@ def _sol_prompt_metadata(prompt: bytes) -> dict:
                 if field not in metadata:
                     raise ValueError(f"métadonnée Git absente du prompt Sol : {field}")
                 _validate_digest(metadata[field], field)
+            if "artifact_sha256" in metadata:
+                _validate_digest(metadata["artifact_sha256"], "artifact_sha256")
         except (TypeError, ValueError):
             continue
         candidates.append(metadata)
@@ -1249,6 +1290,10 @@ def _sol_expected_from_git(
         "prompt_sha256"
     ):
         _validate_digest(recu[field], field)
+    if "artifact_sha256" not in recu and not _sol_legacy_artifact_exemption(recu):
+        raise ValueError("artifact_sha256 requis pour tout reçu Sol courant")
+    if "artifact_sha256" in recu:
+        _validate_digest(recu["artifact_sha256"], "artifact_sha256")
     execute = _default_runner if runner is None else runner
     base_commit = _resolve_commit(execute, recu["base_commit"])
     head_commit = _resolve_commit(execute, recu["head_commit"])
@@ -1259,6 +1304,12 @@ def _sol_expected_from_git(
         raise ValueError("head_tree différent de l'arbre Git du head_commit")
     if recu["reviewed_head_tree"] != reviewed_head_tree:
         raise ValueError("reviewed_head_tree différent de l'arbre Git examiné")
+    canonical_artifact = _diff_artifact_canonique(
+        base_commit, reviewed_head_commit, runner=execute
+    )
+    canonical_artifact_sha256 = hashlib.sha256(canonical_artifact.encode("utf-8")).hexdigest()
+    if "artifact_sha256" in recu and recu["artifact_sha256"] != canonical_artifact_sha256:
+        raise ValueError("artifact_sha256 différent du diff texte Git examiné")
     canonical_digest = _diff_canonique(base_commit, reviewed_head_commit, runner=execute)
     _validate_digest(canonical_digest, "candidate_diff_digest Git")
     if recu["candidate_diff_digest"] != canonical_digest:
@@ -1282,6 +1333,7 @@ def _sol_expected_from_git(
         base_commit,
         reviewed_head_commit,
         runner=execute,
+        include_artifact_sha256=not _sol_legacy_artifact_exemption(recu),
     )
     template_content = _git_blob(execute, reviewed_head_commit, _SOL_TEMPLATE_PATH)
     template_sha = hashlib.sha256(template_content.encode("utf-8")).hexdigest()
@@ -1297,6 +1349,8 @@ def _sol_expected_from_git(
     ):
         if prompt_metadata[field] != recu[field]:
             raise ValueError(f"{field} différent des métadonnées du prompt Sol")
+    if "artifact_sha256" in recu and prompt_metadata.get("artifact_sha256") != recu["artifact_sha256"]:
+        raise ValueError("artifact_sha256 différent des métadonnées du prompt Sol")
     if stored_prompt != canonical_prompt:
         raise ValueError(
             f"{_SOL_PROMPT_FILENAME} différent du prompt Sol canonique généré depuis Git"
@@ -1341,7 +1395,7 @@ def _sol_expected_from_git(
         _require_commit_ancestor(
             execute, reviewed_head_commit, current_head, "reviewed_head_commit"
         )
-    return {
+    result = {
         "candidate_diff_digest": canonical_digest,
         "diff_digest": canonical_digest,
         "base_commit": base_commit,
@@ -1356,6 +1410,9 @@ def _sol_expected_from_git(
         "reviewed_at": reviewed_at,
         "_covers_current": covers_current,
     }
+    if "artifact_sha256" in recu:
+        result["artifact_sha256"] = recu["artifact_sha256"]
+    return result
 
 
 def _sol_receipt_binding_matches_current(recu: object, etat_git: object) -> bool:
@@ -1485,6 +1542,8 @@ def tally_sol_blind(
             "template_sha256",
         ):
             _validate_digest(expected[field], field)
+        if "artifact_sha256" in expected:
+            _validate_digest(expected["artifact_sha256"], "artifact_sha256")
     except ValueError as error:
         return {"result": "INVALIDE", "reason": str(error)}
     if expected["candidate_diff_digest"] != expected["diff_digest"]:
@@ -1508,6 +1567,8 @@ def tally_sol_blind(
     ):
         if verdict.get(field) != expected[field]:
             return {"result": "INVALIDE", "reason": f"{field} différent des métadonnées attendues"}
+    if "artifact_sha256" in expected and verdict.get("artifact_sha256") != expected["artifact_sha256"]:
+        return {"result": "INVALIDE", "reason": "artifact_sha256 différent des métadonnées attendues"}
     if verdict.get("reviewed_at") != expected["reviewed_at"]:
         return {"result": "INVALIDE", "reason": "reviewed_at différent ou non frais"}
     if _aware_timestamp(verdict.get("reviewed_at")) is None:
@@ -1729,6 +1790,8 @@ def _verifier_recu_sol_blind(
         _validate_digest(recu["sdd_diff_digest"], "sdd_diff_digest")
         _validate_digest(recu["mission_diff_digest"], "mission_diff_digest")
         _validate_digest(recu["template_sha256"], "template_sha256")
+        if "artifact_sha256" in recu:
+            _validate_digest(recu["artifact_sha256"], "artifact_sha256")
     except ValueError as error:
         return {"result": "INVALIDE", "reason": str(error)}
     try:
@@ -1860,6 +1923,8 @@ def _validate_sol_archive_receipt(
         ):
             if recu[field] != verdict.get(field):
                 raise ValueError(f"{field} du reçu Sol archive contradictoire")
+        if "artifact_sha256" in recu and recu["artifact_sha256"] != verdict.get("artifact_sha256"):
+            raise ValueError("artifact_sha256 du reçu Sol archive contradictoire")
         if review_dir is None:
             raise ValueError("dossier de revue Sol archive requis")
         expected = _sol_expected_from_git(
@@ -1888,6 +1953,8 @@ def _validate_sol_archive_receipt(
         "template_sha256",
     ):
         _validate_digest(recu[field], field)
+    if "artifact_sha256" in recu:
+        _validate_digest(recu["artifact_sha256"], "artifact_sha256")
     for commit_field, tree_field in (
         ("head_commit", "head_tree"),
         ("reviewed_head_commit", "reviewed_head_tree"),
@@ -1998,6 +2065,7 @@ def _cmd_recu(args) -> int:
         template_sha256 = None
         sdd_diff_digest = None
         mission_diff_digest = None
+        artifact_sha256 = None
         story = getattr(args, "story", None)
         if not isinstance(story, str) or not story.strip():
             raise ValueError("--story est obligatoire avec --mode sol_blind")
@@ -2022,6 +2090,7 @@ def _cmd_recu(args) -> int:
             template_sha256 = prompt_metadata["template_sha256"]
             sdd_diff_digest = prompt_metadata["sdd_diff_digest"]
             mission_diff_digest = prompt_metadata["mission_diff_digest"]
+            artifact_sha256 = prompt_metadata.get("artifact_sha256")
             expected = {
                 **etat,
                 "candidate_diff_digest": etat["diff_digest"],
@@ -2033,6 +2102,8 @@ def _cmd_recu(args) -> int:
                 "template_sha256": template_sha256,
                 "reviewed_at": verdicts[0].get("reviewed_at"),
             }
+            if artifact_sha256 is not None:
+                expected["artifact_sha256"] = artifact_sha256
             result = tally_sol_blind(verdicts, expected=expected, codeurs=args.codeur)
         reviewer = verdicts[0] if len(verdicts) == 1 else {}
         recu = {
@@ -2057,6 +2128,7 @@ def _cmd_recu(args) -> int:
             "template_sha256": template_sha256,
             "sdd_diff_digest": sdd_diff_digest,
             "mission_diff_digest": mission_diff_digest,
+            "artifact_sha256": artifact_sha256,
             "blocking_findings": reviewer.get("blocking_findings", []),
             "date_heure": datetime.now().astimezone().isoformat(),
             "fenetre_heures": args.fenetre_heures,
diff --git stories/ORCH-LUNA-SOL-603.md stories/ORCH-LUNA-SOL-603.md
index bcdc5fa151263a5dd02bc595e03993eff4981210..35f0e763cc07497075ae8ce2d761bea63525efd7 100644
--- stories/ORCH-LUNA-SOL-603.md
+++ stories/ORCH-LUNA-SOL-603.md
@@ -1,7 +1,7 @@
 # Story ORCH-LUNA-SOL-603 — contrat autonome Luna/Sol
 
-Status: IN_PROGRESS — phase compacte du contrat versionné; la preuve finale et
-la livraison documentaire complète restent dans une phase bornée ultérieure.
+Status: IN_PROGRESS — implémentation finale prête; scellement de la preuve Sol
+et passage à l’état terminal après la revue aveugle.
 
 ## Contexte et périmètre
 
@@ -18,8 +18,14 @@ les archives uniquement.
   exige un unique reviewer Sol pour `sol_blind`.
 - [x] Le reçu Sol lie le diff Git, l’arbre, le prompt, les journaux exclus et
   les limites de fraîcheur sans dépendre de la configuration locale de Git.
-- [ ] La documentation, les registres, les vues finales et la preuve Sol
-  finale sont scellés dans la phase de livraison bornée.
+- [x] La documentation, les registres, les vues et le test de non-régression du
+  gate archive sont prêts. Le contrôle de l’archive de preuve est effectué par
+  `reviews_gate.py`, séparément du diff canonique présenté au reviewer Sol.
+- [ ] Le reçu Sol final est scellé dans
+  `evidence/reviews/ORCH-LUNA-SOL-603-final-seal/RECU.json`, lié au manifeste
+  actif, puis le gate PR et le gate archive sur `main` fusionné passent.
+- [ ] La story passe à `DONE_WITH_EVIDENCE` uniquement après ces preuves;
+  aucune réussite runtime, matérielle, réseau ou externe n’est revendiquée.
 
 ## Limites
 
diff --git tests/test_reviews_gate.py tests/test_reviews_gate.py
index f47f5c7ce4c00f1490ac0c7f21320061d7b9ef0a..69c037689fd7ee10c27d870b7ae0b7c88e6cb6d8 100644
--- tests/test_reviews_gate.py
+++ tests/test_reviews_gate.py
@@ -92,6 +92,7 @@ SOL_TEMPLATE_SHA = hashlib.sha256(
 ).hexdigest()
 SOL_SDD_DIGEST = hashlib.sha256(b"").hexdigest()
 SOL_MISSION_DIGEST = hashlib.sha256(b"").hexdigest()
+SOL_ARTIFACT_SHA = hashlib.sha256(b"").hexdigest()
 
 
 def _receipt():
@@ -133,6 +134,7 @@ def _make_sol_blind_gate_review(
                 "reviewer_read_only": True,
                 "reviewer_model": "GPT-5.6-Sol",
                 "candidate_diff_digest": hashlib.sha256(b"").hexdigest(),
+                "artifact_sha256": SOL_ARTIFACT_SHA,
                 "diff_digest": hashlib.sha256(b"").hexdigest(),
                 "sdd_diff_digest": SOL_SDD_DIGEST,
                 "mission_diff_digest": SOL_MISSION_DIGEST,
@@ -153,6 +155,7 @@ def _make_sol_blind_gate_review(
         "mode": "sol_blind",
         "story": gate._load_revue()._SOL_CANONICAL_STORY_ID,
         "candidate_diff_digest": hashlib.sha256(b"").hexdigest(),
+        "artifact_sha256": SOL_ARTIFACT_SHA,
         "diff_digest": hashlib.sha256(b"").hexdigest(),
         "sdd_diff_digest": SOL_SDD_DIGEST,
         "mission_diff_digest": SOL_MISSION_DIGEST,
@@ -183,6 +186,16 @@ def _make_sol_blind_gate_review(
     return directory
 
 
+def test_sol_prompt_expose_lempreinte_du_diff_texte_affiche():
+    revue = gate._load_revue()
+    artifact = revue._diff_artifact_canonique("b" * 40, "c" * 40, runner=_runner)
+    metadata = revue._sol_prompt_metadata(SOL_PROMPT_BYTES)
+
+    assert artifact == ""
+    assert metadata["artifact_sha256"] == hashlib.sha256(artifact.encode("utf-8")).hexdigest()
+    assert metadata["artifact_sha256"] == SOL_ARTIFACT_SHA
+
+
 def test_gate_ok_si_toutes_approve(tmp_path):
     # RC1-010 (#440) lot 5d : reviews/ est intégralement migré vers evidence/reviews/ — le
     # repli bi-racine posé au lot 5a (une entrée liante pouvait vivre sous l'une OU l'autre
@@ -469,6 +482,7 @@ def test_mode_pr_historical_invalid_sol_binding_is_informational(tmp_path):
                 "reviewed_head_commit": "3" * 40,
                 "reviewed_head_tree": "d" * 40,
                 "prompt_sha256": historical_prompt_sha,
+                "artifact_sha256": SOL_ARTIFACT_SHA,
                 "template_sha256": SOL_TEMPLATE_SHA,
                 "verdict": "APPROVE",
                 "blocking_findings": [],
@@ -494,6 +508,7 @@ def test_mode_pr_historical_invalid_sol_binding_is_informational(tmp_path):
                 "reviewed_head_commit": "3" * 40,
                 "reviewed_head_tree": "d" * 40,
                 "prompt_sha256": historical_prompt_sha,
+                "artifact_sha256": SOL_ARTIFACT_SHA,
                 "template_sha256": SOL_TEMPLATE_SHA,
                 "issue": 603,
                 "round": 1,
@@ -527,6 +542,7 @@ def test_mode_pr_historical_invalid_sol_binding_is_informational(tmp_path):
                 "reviewed_head_commit": "c" * 40,
                 "reviewed_head_tree": "d" * 40,
                 "prompt_sha256": SOL_SHA,
+                "artifact_sha256": SOL_ARTIFACT_SHA,
                 "sdd_diff_digest": SOL_SDD_DIGEST,
                 "mission_diff_digest": SOL_MISSION_DIGEST,
                 "template_sha256": SOL_TEMPLATE_SHA,
@@ -546,8 +562,9 @@ def test_mode_pr_historical_invalid_sol_binding_is_informational(tmp_path):
                     "story": gate._load_revue()._SOL_CANONICAL_STORY_ID,
                     "dossier": "S-courante-sol",
                     "issue": 603,
-                "prompt_sha256": SOL_SHA,
-                "candidate_diff_digest": hashlib.sha256(b"").hexdigest(),
+                    "prompt_sha256": SOL_SHA,
+                    "artifact_sha256": SOL_ARTIFACT_SHA,
+                    "candidate_diff_digest": hashlib.sha256(b"").hexdigest(),
                 "reviewed_head_commit": "c" * 40,
                 "reviewed_head_tree": "d" * 40,
                 "reviewed_at": "2026-08-22T12:00:00+00:00",
@@ -712,6 +729,27 @@ def test_gate_sol_blind_defaut_rejette_recu_incomplet(tmp_path):
     assert any("schema" in line for line in report)
 
 
+def test_gate_sol_blind_pr_exige_lempreinte_du_diff_affiche(tmp_path):
+    root = tmp_path / "reviews"
+    directory = _make_sol_blind_gate_review(root)
+    receipt_path = directory / "RECU.json"
+    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
+    receipt.pop("artifact_sha256")
+    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
+
+    ok, report = gate.check(
+        _manifest(tmp_path, [directory.name]),
+        root,
+        exiger_recu_courant=True,
+        base_ref="origin/main",
+        runner=_runner,
+        now=SOL_NOW,
+    )
+
+    assert ok is False
+    assert any("artifact_sha256" in line for line in report)
+
+
 def test_gate_sol_blind_mode_pr_rejette_preuve_perimee(tmp_path):
     root = tmp_path / "reviews"
     directory = _make_sol_blind_gate_review(root)
@@ -1129,3 +1167,18 @@ def test_manifeste_reel_du_depot_est_approve():
         REPO / "evidence" / "reviews" / "BINDING.txt", REPO / "evidence" / "reviews"
     )
     assert ok is True, report
+
+
+def test_manifeste_reel_du_depot_est_archiveable_sur_l_arbre_courant():
+    """L'archive vérifie les ancêtres du checkout courant, avant ou après merge.
+
+    Le reçu final est généré sur le commit déjà revu, puis ajouté dans un commit
+    de preuve enfant : ce commit revu reste donc un ancêtre du checkout de la
+    branche PR comme de l'arbre main après fusion.
+    """
+    ok, report = gate.check(
+        REPO / "evidence" / "reviews" / "BINDING.txt",
+        REPO / "evidence" / "reviews",
+        mode="archive",
+    )
+    assert ok is True, report


MODE DE REVUE : sol_blind
MÉTADONNÉES GIT EXACTES (à recopier sans modification) :
{"artifact_sha256": "4881601c9484518a171d0ce4c3cf25d8d6f4a17347dad2fabdd2297ca568bbb9", "base_commit": "5e25de16bd38f8a6ffc16e120919beff128f95aa", "candidate_diff_digest": "2b2879e34b9117c0408dc9f4c397fd0e53185ca3961ae38609fb0e05353c4610", "mission_diff_digest": "b5ff599c26285b5df69f5a2487fe885870c89467c2fc357b321fcea3445ad1b1", "reviewed_head_commit": "231ec02a065deeae44235c7b15897c782cf22f20", "reviewed_head_tree": "af4b1a6dc0b5e65ca544a921efa5d16dff0b65a4", "sdd_diff_digest": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", "template_sha256": "a5bebc60556f4fc38d6ca96a3d0372577550f23157377af4d852e6144e25f137"}

Réponds STRICTEMENT avec un objet JSON valide, rien avant, rien après, conforme à ce
schéma :
{"artifact_sha256": "4881601c9484518a171d0ce4c3cf25d8d6f4a17347dad2fabdd2297ca568bbb9", "base_commit": "5e25de16bd38f8a6ffc16e120919beff128f95aa", "blind": true, "blocking_findings": [], "candidate_diff_digest": "2b2879e34b9117c0408dc9f4c397fd0e53185ca3961ae38609fb0e05353c4610", "fresh_context": true, "mission_diff_digest": "b5ff599c26285b5df69f5a2487fe885870c89467c2fc357b321fcea3445ad1b1", "prompt_sha256": "sha256 du prompt reçu", "reviewed_at": "timestamp ISO-8601 avec fuseau", "reviewed_head_commit": "231ec02a065deeae44235c7b15897c782cf22f20", "reviewed_head_tree": "af4b1a6dc0b5e65ca544a921efa5d16dff0b65a4", "reviewer_model": "GPT-5.6-Sol", "reviewer_read_only": true, "sdd_diff_digest": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", "template_sha256": "a5bebc60556f4fc38d6ca96a3d0372577550f23157377af4d852e6144e25f137", "verdict": "APPROVE ou REJECT"}