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
  `evidence/reviews/ORCH-LUNA-SOL-603-final-approval/RECU.json`, lié au manifeste
  actif, puis le gate PR et le gate archive sur `main` fusionné passent.
- [ ] La story passe à `DONE_WITH_EVIDENCE` uniquement après ces preuves;
  aucune réussite runtime, matérielle, réseau ou externe n’est revendiquée.

ARTEFACT — canonical-git-diff :
diff --git Docs/reference/autonomy-luna-sol.md Docs/reference/autonomy-luna-sol.md
index f533b6811976610ef420fe8724bb700628ff7935..a50a4bcb86d26f1a5ae060e152a170f9c7520b1a 100644
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
+`evidence/reviews/ORCH-LUNA-SOL-603-final-approval/RECU.json`; il liera les commits,
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
index 0000000000000000000000000000000000000000..7c222e752609a774b9af5bcb2691953a38bc8e50
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
+   APPROVE, sceller le reçu `ORCH-LUNA-SOL-603-final-approval`, l’ajouter à
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
index 1390efd903c0c5f5f2010b37507ed3c6ba01bcaa..6f81edd087e77b11134894b2857ffe2a59d25089 100644
--- governance/STATE-CURRENT.json
+++ governance/STATE-CURRENT.json
@@ -772,7 +772,7 @@
       },
       {
         "path": "tests/test_reviews_gate.py",
-        "sha256": "7cb06c0393ef774f86bcb511949523bc6b494c88e59fbe3a37293b37f7962e90"
+        "sha256": "ed8d6c8b129e814b84efeb5f23b1d2e353530d7e69c4f74a50ca47f4a8737f79"
       },
       {
         "path": "tests/test_revue.py",
@@ -1001,7 +1001,7 @@
     "tests": {
       "js_files": 3,
       "python_files": 209,
-      "python_functions_declared": 2692
+      "python_functions_declared": 2694
     }
   },
   "observations": [
diff --git governance/STATE-CURRENT.md governance/STATE-CURRENT.md
index 321493d0d8c77f400d315d75f36575f71fca0141..fcd4cd0c71107a081694911fcf221c4d6b3acd32 100644
--- governance/STATE-CURRENT.md
+++ governance/STATE-CURRENT.md
@@ -778,7 +778,7 @@
     },
     {
       "path": "tests/test_reviews_gate.py",
-      "sha256": "7cb06c0393ef774f86bcb511949523bc6b494c88e59fbe3a37293b37f7962e90"
+      "sha256": "ed8d6c8b129e814b84efeb5f23b1d2e353530d7e69c4f74a50ca47f4a8737f79"
     },
     {
       "path": "tests/test_revue.py",
@@ -1007,7 +1007,7 @@
   "tests": {
     "js_files": 3,
     "python_files": 209,
-    "python_functions_declared": 2692
+    "python_functions_declared": 2694
   }
 }
 ```
diff --git scripts/revue.py scripts/revue.py
index 29705791135378119c751599d69f01580efd8f39..9ab6c79e35c59f9e273ac7e649e60fa87ed7a3ae 100644
--- scripts/revue.py
+++ scripts/revue.py
@@ -404,6 +404,8 @@ def _sol_expected_from_receipt_shape(
         "mission_diff_digest", "template_sha256",
     ):
         _validate_digest(recu[field], field)
+    if "artifact_sha256" in recu:
+        _validate_digest(recu["artifact_sha256"], "artifact_sha256")
     if recu["diff_digest"] != recu["candidate_diff_digest"]:
         raise ValueError("diff_digest différent de candidate_diff_digest")
     if _aware_timestamp(recu["date_heure"]) is None:
@@ -446,6 +448,8 @@ def _sol_expected_from_receipt_shape(
     ):
         if verdict.get(field) != recu[field]:
             raise ValueError(f"{field} du verdict différent du reçu Sol")
+    if "artifact_sha256" in recu and verdict.get("artifact_sha256") != recu["artifact_sha256"]:
+        raise ValueError("artifact_sha256 du verdict différent du reçu Sol")
     reviewers = recu["reviewers_attendus"]
     if not isinstance(reviewers, list) or len(reviewers) != 1:
         raise ValueError("nombre incorrect de reviewers Sol")
@@ -467,6 +471,8 @@ def _sol_expected_from_receipt_shape(
     ):
         if recu[field] != metadata[field]:
             raise ValueError(f"{field} différent des métadonnées du prompt Sol")
+    if "artifact_sha256" in recu and recu["artifact_sha256"] != metadata.get("artifact_sha256"):
+        raise ValueError("artifact_sha256 différent des métadonnées du prompt Sol")
     response_marker = "conforme à ce\nschéma :\n"
     response_tail = prompt_text.split(response_marker, 1)
     if len(response_tail) != 2:
@@ -496,13 +502,15 @@ def _sol_expected_from_receipt_shape(
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
@@ -514,6 +522,9 @@ def _sol_expected_from_receipt_shape(
         "template_sha256": recu["template_sha256"],
         "reviewed_at": recu["reviewed_at"],
     }
+    if "artifact_sha256" in recu:
+        result["artifact_sha256"] = recu["artifact_sha256"]
+    return result
 
 
 def _diff_artifact_canonique(
@@ -789,7 +800,8 @@ def build_prompt(story_id: str, criteres: str, artefact_path: str, artefact: str
                  template_path: Path = TEMPLATE, *, mode: str = "multi_vendor",
                  expected: dict | None = None, base_ref: str | None = None,
                  head_ref: str | None = None, runner: GitRunner | None = None,
-                 template_content: str | None = None) -> tuple[str, str]:
+                 template_content: str | None = None,
+                 include_artifact_sha256: bool = True) -> tuple[str, str]:
     """Render one exact, versioned prompt section and return its SHA-256."""
     if template_content is None:
         tpl = template_path.read_text(encoding="utf-8")
@@ -823,6 +835,10 @@ def build_prompt(story_id: str, criteres: str, artefact_path: str, artefact: str
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
@@ -912,6 +928,7 @@ def _canonical_sol_prompt(
     reviewed_head_commit: str,
     *,
     runner: GitRunner | None = None,
+    include_artifact_sha256: bool = True,
 ) -> tuple[bytes, str]:
     """Rebuild the exact Sol prompt from frozen Git objects and versioned inputs."""
     execute = _default_runner if runner is None else runner
@@ -930,6 +947,7 @@ def _canonical_sol_prompt(
         head_ref=frozen_head,
         runner=execute,
         template_content=template_content,
+        include_artifact_sha256=include_artifact_sha256,
     )
     return prompt.encode("utf-8"), prompt_sha
 
@@ -971,6 +989,8 @@ def _sol_prompt_metadata(prompt: bytes) -> dict:
                 if field not in metadata:
                     raise ValueError(f"métadonnée Git absente du prompt Sol : {field}")
                 _validate_digest(metadata[field], field)
+            if "artifact_sha256" in metadata:
+                _validate_digest(metadata["artifact_sha256"], "artifact_sha256")
         except (TypeError, ValueError):
             continue
         candidates.append(metadata)
@@ -1249,6 +1269,8 @@ def _sol_expected_from_git(
         "prompt_sha256"
     ):
         _validate_digest(recu[field], field)
+    if "artifact_sha256" in recu:
+        _validate_digest(recu["artifact_sha256"], "artifact_sha256")
     execute = _default_runner if runner is None else runner
     base_commit = _resolve_commit(execute, recu["base_commit"])
     head_commit = _resolve_commit(execute, recu["head_commit"])
@@ -1259,6 +1281,12 @@ def _sol_expected_from_git(
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
@@ -1282,6 +1310,7 @@ def _sol_expected_from_git(
         base_commit,
         reviewed_head_commit,
         runner=execute,
+        include_artifact_sha256="artifact_sha256" in recu,
     )
     template_content = _git_blob(execute, reviewed_head_commit, _SOL_TEMPLATE_PATH)
     template_sha = hashlib.sha256(template_content.encode("utf-8")).hexdigest()
@@ -1297,6 +1326,8 @@ def _sol_expected_from_git(
     ):
         if prompt_metadata[field] != recu[field]:
             raise ValueError(f"{field} différent des métadonnées du prompt Sol")
+    if "artifact_sha256" in recu and prompt_metadata.get("artifact_sha256") != recu["artifact_sha256"]:
+        raise ValueError("artifact_sha256 différent des métadonnées du prompt Sol")
     if stored_prompt != canonical_prompt:
         raise ValueError(
             f"{_SOL_PROMPT_FILENAME} différent du prompt Sol canonique généré depuis Git"
@@ -1341,7 +1372,7 @@ def _sol_expected_from_git(
         _require_commit_ancestor(
             execute, reviewed_head_commit, current_head, "reviewed_head_commit"
         )
-    return {
+    result = {
         "candidate_diff_digest": canonical_digest,
         "diff_digest": canonical_digest,
         "base_commit": base_commit,
@@ -1356,6 +1387,9 @@ def _sol_expected_from_git(
         "reviewed_at": reviewed_at,
         "_covers_current": covers_current,
     }
+    if "artifact_sha256" in recu:
+        result["artifact_sha256"] = recu["artifact_sha256"]
+    return result
 
 
 def _sol_receipt_binding_matches_current(recu: object, etat_git: object) -> bool:
@@ -1485,6 +1519,8 @@ def tally_sol_blind(
             "template_sha256",
         ):
             _validate_digest(expected[field], field)
+        if "artifact_sha256" in expected:
+            _validate_digest(expected["artifact_sha256"], "artifact_sha256")
     except ValueError as error:
         return {"result": "INVALIDE", "reason": str(error)}
     if expected["candidate_diff_digest"] != expected["diff_digest"]:
@@ -1508,6 +1544,8 @@ def tally_sol_blind(
     ):
         if verdict.get(field) != expected[field]:
             return {"result": "INVALIDE", "reason": f"{field} différent des métadonnées attendues"}
+    if "artifact_sha256" in expected and verdict.get("artifact_sha256") != expected["artifact_sha256"]:
+        return {"result": "INVALIDE", "reason": "artifact_sha256 différent des métadonnées attendues"}
     if verdict.get("reviewed_at") != expected["reviewed_at"]:
         return {"result": "INVALIDE", "reason": "reviewed_at différent ou non frais"}
     if _aware_timestamp(verdict.get("reviewed_at")) is None:
@@ -1729,6 +1767,8 @@ def _verifier_recu_sol_blind(
         _validate_digest(recu["sdd_diff_digest"], "sdd_diff_digest")
         _validate_digest(recu["mission_diff_digest"], "mission_diff_digest")
         _validate_digest(recu["template_sha256"], "template_sha256")
+        if "artifact_sha256" in recu:
+            _validate_digest(recu["artifact_sha256"], "artifact_sha256")
     except ValueError as error:
         return {"result": "INVALIDE", "reason": str(error)}
     try:
@@ -1860,6 +1900,8 @@ def _validate_sol_archive_receipt(
         ):
             if recu[field] != verdict.get(field):
                 raise ValueError(f"{field} du reçu Sol archive contradictoire")
+        if "artifact_sha256" in recu and recu["artifact_sha256"] != verdict.get("artifact_sha256"):
+            raise ValueError("artifact_sha256 du reçu Sol archive contradictoire")
         if review_dir is None:
             raise ValueError("dossier de revue Sol archive requis")
         expected = _sol_expected_from_git(
@@ -1888,6 +1930,8 @@ def _validate_sol_archive_receipt(
         "template_sha256",
     ):
         _validate_digest(recu[field], field)
+    if "artifact_sha256" in recu:
+        _validate_digest(recu["artifact_sha256"], "artifact_sha256")
     for commit_field, tree_field in (
         ("head_commit", "head_tree"),
         ("reviewed_head_commit", "reviewed_head_tree"),
@@ -1998,6 +2042,7 @@ def _cmd_recu(args) -> int:
         template_sha256 = None
         sdd_diff_digest = None
         mission_diff_digest = None
+        artifact_sha256 = None
         story = getattr(args, "story", None)
         if not isinstance(story, str) or not story.strip():
             raise ValueError("--story est obligatoire avec --mode sol_blind")
@@ -2022,6 +2067,7 @@ def _cmd_recu(args) -> int:
             template_sha256 = prompt_metadata["template_sha256"]
             sdd_diff_digest = prompt_metadata["sdd_diff_digest"]
             mission_diff_digest = prompt_metadata["mission_diff_digest"]
+            artifact_sha256 = prompt_metadata.get("artifact_sha256")
             expected = {
                 **etat,
                 "candidate_diff_digest": etat["diff_digest"],
@@ -2033,6 +2079,8 @@ def _cmd_recu(args) -> int:
                 "template_sha256": template_sha256,
                 "reviewed_at": verdicts[0].get("reviewed_at"),
             }
+            if artifact_sha256 is not None:
+                expected["artifact_sha256"] = artifact_sha256
             result = tally_sol_blind(verdicts, expected=expected, codeurs=args.codeur)
         reviewer = verdicts[0] if len(verdicts) == 1 else {}
         recu = {
@@ -2057,6 +2105,7 @@ def _cmd_recu(args) -> int:
             "template_sha256": template_sha256,
             "sdd_diff_digest": sdd_diff_digest,
             "mission_diff_digest": mission_diff_digest,
+            "artifact_sha256": artifact_sha256,
             "blocking_findings": reviewer.get("blocking_findings", []),
             "date_heure": datetime.now().astimezone().isoformat(),
             "fenetre_heures": args.fenetre_heures,
diff --git stories/ORCH-LUNA-SOL-603.md stories/ORCH-LUNA-SOL-603.md
index bcdc5fa151263a5dd02bc595e03993eff4981210..67b389a09d7ad13ccae8f26fb5de655376b20888 100644
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
+  `evidence/reviews/ORCH-LUNA-SOL-603-final-approval/RECU.json`, lié au manifeste
+  actif, puis le gate PR et le gate archive sur `main` fusionné passent.
+- [ ] La story passe à `DONE_WITH_EVIDENCE` uniquement après ces preuves;
+  aucune réussite runtime, matérielle, réseau ou externe n’est revendiquée.
 
 ## Limites
 
diff --git tests/test_reviews_gate.py tests/test_reviews_gate.py
index f47f5c7ce4c00f1490ac0c7f21320061d7b9ef0a..9aca6111e5689a64e9340a37aa75c18ec15eef3e 100644
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
@@ -447,7 +460,14 @@ def test_mode_pr_ignore_recu_historique_non_couvrant(tmp_path):
 
 def test_mode_pr_historical_invalid_sol_binding_is_informational(tmp_path):
     root = tmp_path / "reviews"
-    historical_prompt = SOL_PROMPT_BYTES.replace(b"b" * 40, b"a" * 40).replace(
+    legacy_prompt, _ = gate._load_revue()._canonical_sol_prompt(
+        gate._load_revue()._SOL_CANONICAL_STORY_ID,
+        "b" * 40,
+        "c" * 40,
+        runner=_runner,
+        include_artifact_sha256=False,
+    )
+    historical_prompt = legacy_prompt.replace(b"b" * 40, b"a" * 40).replace(
         b"c" * 40, b"3" * 40
     )
     historical_prompt_sha = hashlib.sha256(historical_prompt).hexdigest()
@@ -527,6 +547,7 @@ def test_mode_pr_historical_invalid_sol_binding_is_informational(tmp_path):
                 "reviewed_head_commit": "c" * 40,
                 "reviewed_head_tree": "d" * 40,
                 "prompt_sha256": SOL_SHA,
+                "artifact_sha256": SOL_ARTIFACT_SHA,
                 "sdd_diff_digest": SOL_SDD_DIGEST,
                 "mission_diff_digest": SOL_MISSION_DIGEST,
                 "template_sha256": SOL_TEMPLATE_SHA,
@@ -546,8 +567,9 @@ def test_mode_pr_historical_invalid_sol_binding_is_informational(tmp_path):
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
@@ -1129,3 +1151,18 @@ def test_manifeste_reel_du_depot_est_approve():
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
{"artifact_sha256": "b19c9e436b2b80cd05310e14e76244acf2846d32ae0be2b5c2399c1e11581ead", "base_commit": "5e25de16bd38f8a6ffc16e120919beff128f95aa", "candidate_diff_digest": "9cff0ecec2d1f6253521a3f5a7b7817e7da668569f5b96fd7166869c2c3a9571", "mission_diff_digest": "f1000e979d1c67813da9a5be098a089d9d2ebb986c6bc420ef9eba2b349c1f9a", "reviewed_head_commit": "167c6219a86e20df84e6f0a61360c83f434d2719", "reviewed_head_tree": "9a40a1b68bfafe4f12f966e42a247eea588b2639", "sdd_diff_digest": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", "template_sha256": "a5bebc60556f4fc38d6ca96a3d0372577550f23157377af4d852e6144e25f137"}

Réponds STRICTEMENT avec un objet JSON valide, rien avant, rien après, conforme à ce
schéma :
{"artifact_sha256": "b19c9e436b2b80cd05310e14e76244acf2846d32ae0be2b5c2399c1e11581ead", "base_commit": "5e25de16bd38f8a6ffc16e120919beff128f95aa", "blind": true, "blocking_findings": [], "candidate_diff_digest": "9cff0ecec2d1f6253521a3f5a7b7817e7da668569f5b96fd7166869c2c3a9571", "fresh_context": true, "mission_diff_digest": "f1000e979d1c67813da9a5be098a089d9d2ebb986c6bc420ef9eba2b349c1f9a", "prompt_sha256": "sha256 du prompt reçu", "reviewed_at": "timestamp ISO-8601 avec fuseau", "reviewed_head_commit": "167c6219a86e20df84e6f0a61360c83f434d2719", "reviewed_head_tree": "9a40a1b68bfafe4f12f966e42a247eea588b2639", "reviewer_model": "GPT-5.6-Sol", "reviewer_read_only": true, "sdd_diff_digest": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", "template_sha256": "a5bebc60556f4fc38d6ca96a3d0372577550f23157377af4d852e6144e25f137", "verdict": "APPROVE ou REJECT"}