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
- [x] La documentation, les registres, les vues et le nettoyage contrôlé de
  l’archive sont prêts; les anciens reçus non ancêtres restent conservés et
  sont listés dans `evidence/reviews/ARCHIVE-UNMERGED.txt`.
- [ ] Le reçu Sol final est scellé dans
  `evidence/reviews/ORCH-LUNA-SOL-603-final-r2/RECU.json`, lié au manifeste
  actif, puis le gate PR et le gate archive sur `main` fusionné passent.
- [ ] La story passe à `DONE_WITH_EVIDENCE` uniquement après ces preuves;
  aucune réussite runtime, matérielle, réseau ou externe n’est revendiquée.

ARTEFACT — canonical-git-diff :
diff --git Docs/reference/autonomy-luna-sol.md Docs/reference/autonomy-luna-sol.md
index f533b6811976610ef420fe8724bb700628ff7935..739fbcfacf226e581c327e4866ef9da73da68bd6 100644
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
@@ -15,10 +15,12 @@ aveugle et strictement read-only. `multi_vendor` reste un mode historique
 d’archive et conserve son quorum 3/3.
 
 Le prompt Sol est reconstruit depuis le diff Git exact et les critères de la
-story `stories/ORCH-LUNA-SOL-603.md`. Le reçu lie les commits, arbres, digest
-du diff, prompt, template, journaux SDD et registre de mission; les digests
-neutralisent les configurations Git globales qui pourraient modifier ou
-ordonner la sortie. Le reviewer n’écrit jamais dans le dépôt.
+story `stories/ORCH-LUNA-SOL-603.md`. Après approbation de l’implémentation,
+le reçu final attendu sera
+`evidence/reviews/ORCH-LUNA-SOL-603-final-r2/RECU.json`; il liera les commits,
+arbres, digest du diff, prompt, template, journaux SDD et registre de mission.
+Les digests neutralisent les configurations Git globales qui pourraient
+modifier ou ordonner la sortie. Le reviewer n’écrit jamais dans le dépôt.
 
 Le gate sans drapeau conserve le dépouillement historique, vérifie la forme/cohérence interne
 du reçu et le hash du prompt, mais ne recharge pas ses objets Git; cela reste compatible avec
@@ -42,9 +44,17 @@ Pour distinguer un reçu historique d’un reçu courant, le mode PR vérifie d
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
@@ -54,8 +64,11 @@ python3 scripts/governance/validate_authority.py
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
index 0000000000000000000000000000000000000000..5b8510d233f71d092cdd45dbaf505c0df013a04f
--- /dev/null
+++ Docs/superpowers/plans/2026-08-22-autonomous-luna-sol.md
@@ -0,0 +1,38 @@
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
+   APPROVE, puis sceller le reçu `ORCH-LUNA-SOL-603-final-r2`, l’ajouter à
+   `BINDING.txt`, passer la story à `DONE_WITH_EVIDENCE` et exécuter les gates
+   locaux et CI avant merge.
+6. Rejouer le mode archive sur `main` fusionné et vérifier que la story est
+   terminale.
+
+## Critère d’arrêt
+
+Le travail n’est terminé que si le gate archive, le gate PR, les tests complets,
+les registres et les vues générées passent, et si la preuve Sol finale est
+liée au diff exact. Sinon la story reste bloquée avec une raison vérifiable.
+
+## Itération de revue
+
+Le premier prompt final a été rejeté parce que le statut terminal précédait le
+scellement visible de la preuve. Ce rejet est conservé hors liaison dans
+`ORCH-LUNA-SOL-603-final-r1`; la story a été remise explicitement en
+`IN_PROGRESS` avant le round final.
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
index 1390efd903c0c5f5f2010b37507ed3c6ba01bcaa..26a7c7819ecc367d3d73f93bb44071c2e6b60d98 100644
--- governance/STATE-CURRENT.json
+++ governance/STATE-CURRENT.json
@@ -772,7 +772,7 @@
       },
       {
         "path": "tests/test_reviews_gate.py",
-        "sha256": "7cb06c0393ef774f86bcb511949523bc6b494c88e59fbe3a37293b37f7962e90"
+        "sha256": "60b2a4c0ac50fca960dcdfcebbbda0b2abdef7099cb502204eaf82b9b475ea3e"
       },
       {
         "path": "tests/test_revue.py",
@@ -1001,7 +1001,7 @@
     "tests": {
       "js_files": 3,
       "python_files": 209,
-      "python_functions_declared": 2692
+      "python_functions_declared": 2693
     }
   },
   "observations": [
diff --git governance/STATE-CURRENT.md governance/STATE-CURRENT.md
index 321493d0d8c77f400d315d75f36575f71fca0141..0c43a6c5ca53756a7bc21279238feeaadec2f9b0 100644
--- governance/STATE-CURRENT.md
+++ governance/STATE-CURRENT.md
@@ -778,7 +778,7 @@
     },
     {
       "path": "tests/test_reviews_gate.py",
-      "sha256": "7cb06c0393ef774f86bcb511949523bc6b494c88e59fbe3a37293b37f7962e90"
+      "sha256": "60b2a4c0ac50fca960dcdfcebbbda0b2abdef7099cb502204eaf82b9b475ea3e"
     },
     {
       "path": "tests/test_revue.py",
@@ -1007,7 +1007,7 @@
   "tests": {
     "js_files": 3,
     "python_files": 209,
-    "python_functions_declared": 2692
+    "python_functions_declared": 2693
   }
 }
 ```
diff --git stories/ORCH-LUNA-SOL-603.md stories/ORCH-LUNA-SOL-603.md
index bcdc5fa151263a5dd02bc595e03993eff4981210..16d85408f67b10929b7da630fed56dd09b0f1063 100644
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
+- [x] La documentation, les registres, les vues et le nettoyage contrôlé de
+  l’archive sont prêts; les anciens reçus non ancêtres restent conservés et
+  sont listés dans `evidence/reviews/ARCHIVE-UNMERGED.txt`.
+- [ ] Le reçu Sol final est scellé dans
+  `evidence/reviews/ORCH-LUNA-SOL-603-final-r2/RECU.json`, lié au manifeste
+  actif, puis le gate PR et le gate archive sur `main` fusionné passent.
+- [ ] La story passe à `DONE_WITH_EVIDENCE` uniquement après ces preuves;
+  aucune réussite runtime, matérielle, réseau ou externe n’est revendiquée.
 
 ## Limites
 
diff --git tests/test_reviews_gate.py tests/test_reviews_gate.py
index f47f5c7ce4c00f1490ac0c7f21320061d7b9ef0a..3d4b745f86f5103214ecfebdf8c336d119414ada 100644
--- tests/test_reviews_gate.py
+++ tests/test_reviews_gate.py
@@ -1129,3 +1129,12 @@ def test_manifeste_reel_du_depot_est_approve():
         REPO / "evidence" / "reviews" / "BINDING.txt", REPO / "evidence" / "reviews"
     )
     assert ok is True, report
+
+
+def test_manifeste_reel_du_depot_est_archiveable():
+    ok, report = gate.check(
+        REPO / "evidence" / "reviews" / "BINDING.txt",
+        REPO / "evidence" / "reviews",
+        mode="archive",
+    )
+    assert ok is True, report


MODE DE REVUE : sol_blind
MÉTADONNÉES GIT EXACTES (à recopier sans modification) :
{"base_commit": "5e25de16bd38f8a6ffc16e120919beff128f95aa", "candidate_diff_digest": "746a143a2581e67e7887c06d439eebde24198704aa09e4a8598334073337366e", "mission_diff_digest": "bb236de1c446ee9b127ea57f25e68d98aeb235136c32f9eca16072c13ca3614a", "reviewed_head_commit": "5037809e6de8a73802ce33a7274da3a4dee75034", "reviewed_head_tree": "6d6191083b76c7a34102f7ddad7c352d26211256", "sdd_diff_digest": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", "template_sha256": "a5bebc60556f4fc38d6ca96a3d0372577550f23157377af4d852e6144e25f137"}

Réponds STRICTEMENT avec un objet JSON valide, rien avant, rien après, conforme à ce
schéma :
{"base_commit": "5e25de16bd38f8a6ffc16e120919beff128f95aa", "blind": true, "blocking_findings": [], "candidate_diff_digest": "746a143a2581e67e7887c06d439eebde24198704aa09e4a8598334073337366e", "fresh_context": true, "mission_diff_digest": "bb236de1c446ee9b127ea57f25e68d98aeb235136c32f9eca16072c13ca3614a", "prompt_sha256": "sha256 du prompt reçu", "reviewed_at": "timestamp ISO-8601 avec fuseau", "reviewed_head_commit": "5037809e6de8a73802ce33a7274da3a4dee75034", "reviewed_head_tree": "6d6191083b76c7a34102f7ddad7c352d26211256", "reviewer_model": "GPT-5.6-Sol", "reviewer_read_only": true, "sdd_diff_digest": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", "template_sha256": "a5bebc60556f4fc38d6ca96a3d0372577550f23157377af4d852e6144e25f137", "verdict": "APPROVE ou REJECT"}