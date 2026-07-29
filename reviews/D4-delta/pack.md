# Revue DELTA D4 — refactor post-scellé (commit cc11b12)

## Contexte
La story D4 (écran d'inventaire + adoption depuis l'UI web) a été scellée APPROVE 3/3.
APRÈS ce scellé, le quality gate SonarCloud a refusé la PR : « B Maintainability Rating
on New Code (required >= A) ». Un sceau ne couvre que le diff qu'il a lu : ce delta
doit donc être revu à son tour avant merge.

## Ce que vous devez juger (et RIEN d'autre)
Le diff ci-dessous, seul. La story D4 elle-même est déjà jugée — ne la re-jugez pas.

CA-DELTA-1 : le comportement observable est INCHANGÉ. En particulier, quand aucun
             service n'est coché, le corps du POST /api/deploy doit être strictement
             identique à celui d'avant D4 (aucune clé `adopt`).
CA-DELTA-2 : la lisibilité est réellement améliorée (c'est l'objet du changement).
CA-DELTA-3 : aucune régression de la chaîne inventaire -> cases cochées -> dict adopt.

REJECT si l'un des trois est faux. Cherchez activement le piège : un refactor
« évidemment sûr » qui change une sémantique (spread d'un objet vide, portée d'une
fonction déclarée après son usage, capture de variable, etc.).

## Diff INTÉGRAL du delta
```diff
diff --git a/src/forgeai/web/assets/app.js b/src/forgeai/web/assets/app.js
index be39bf4..11d881f 100644
--- a/src/forgeai/web/assets/app.js
+++ b/src/forgeai/web/assets/app.js
@@ -316,6 +316,19 @@
     });
   }
 
+  // Fragment `adopt` du corps POST /api/deploy. Rendu VIDE quand rien n'est coché : le corps
+  // est alors strictement identique à celui d'avant D4 (équivalence stricte, CA-4).
+  // Extrait en fonction nommée plutôt qu'en expression inline : le quality gate refusait
+  // l'IIFE dans le littéral (maintenabilité), et un nom rend l'intention lisible.
+  function champAdopt() {
+    var choix = ForgeAIAdoption.servicesAdoptables(state.inventaire, briquesDuPlan())
+      .map(function (sv) {
+        return { id: sv.id, endpoint: sv.endpoint, adopte: !!state.adoptChoisis[sv.id] };
+      });
+    var dict = ForgeAIAdoption.construireAdopt(choix);
+    return Object.keys(dict).length ? { adopt: dict } : {};
+  }
+
   function isChecked(brick) {
     if (brick.locked) return true;
     const ov = state.overrides[overrideKey()];
@@ -600,14 +613,7 @@
             bricks: briquesDuPlan(),
             rag_node: form.elements.rag_node.value,
             confirm: confirm,
-            ...(function(){
-              // `adopt` n'est ajouté QUE s'il est non vide : sans case cochée, le corps du
-              // POST est strictement identique au comportement d'avant cette story.
-              var choix = ForgeAIAdoption.servicesAdoptables(state.inventaire, briquesDuPlan())
-                .map(function(sv){ return {id: sv.id, endpoint: sv.endpoint, adopte: !!state.adoptChoisis[sv.id]}; });
-              var dict = ForgeAIAdoption.construireAdopt(choix);
-              return Object.keys(dict).length ? {adopt: dict} : {};
-            })()
+            ...champAdopt()
           })
         });
         const body = await res.json();
```

## Fichier app.js — la fonction extraite et son point d'appel (état final)
```javascript
  function champAdopt() {
    var choix = ForgeAIAdoption.servicesAdoptables(state.inventaire, briquesDuPlan())
      .map(function (sv) {
        return { id: sv.id, endpoint: sv.endpoint, adopte: !!state.adoptChoisis[sv.id] };
      });
    var dict = ForgeAIAdoption.construireAdopt(choix);
    return Object.keys(dict).length ? { adopt: dict } : {};
  }
...
323:  function champAdopt() {
616:            ...champAdopt()
```

## Preuve d'exécution CAPTURÉE (rejouée après le commit cc11b12)
```
$ node --check src/forgeai/web/assets/app.js
(exit 0)

$ node tests/js/adoption.test.cjs
  ok  - construireAdopt : coché mais endpoint invalide -> ignoré
  ok  - aucune mutation : inventaire et tableau de choix inchangés après appel

adoption.test.cjs : 10 cas ok, 0 cas en échec, 10 cas au total.

$ node tests/js/chaine_adoption.test.cjs
chaine_adoption.test.cjs : 5 cas ok, 0 cas en échec, 5 cas au total.
```
