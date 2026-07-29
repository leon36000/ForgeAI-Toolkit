# Revue DELTA 2 — D4 : correction des 12 issues SonarCloud (commit af5a821)

## Contexte
D4 a été scellée APPROVE 3/3, puis un premier delta (extraction de champAdopt) l'a été
aussi. Le quality gate SonarCloud refusait toujours la PR : « B Maintainability Rating
on New Code (required >= A) ». Une étape de diagnostic posée dans la CI a livré la liste
exacte des 12 issues. Ce diff les traite. Un sceau ne couvrant que le diff qu'il a lu,
ce delta doit être jugé à son tour.

## Ce que vous devez juger — et RIEN d'autre
Le diff ci-dessous seul. D4 et le delta 1 sont déjà jugés.

CA-1 : le comportement observable de l'application est INCHANGÉ. `var` -> `const` ne doit
       avoir modifié aucune sémantique (attention aux portées de bloc et au hoisting :
       `var` est à portée de fonction, `const` à portée de bloc — si l'une de ces
       variables était lue hors de son bloc, le changement CASSE le code).
CA-2 : `<div role="group">` -> `<fieldset>` ne casse ni la structure de la page, ni la
       sémantique d'accessibilité, ni aucun sélecteur existant.
CA-3 : la conversion des tests vers `node:test` n'a AFFAIBLI aucune assertion. Le nombre
       de cas (10 et 5) et les libellés sont conservés ; les assertions sont les mêmes.
CA-4 : chargerInventaire() ne lève toujours jamais (l'inventaire est une commodité, son
       indisponibilité ne doit jamais empêcher de déployer), mais n'avale plus l'erreur.

REJECT si l'un des quatre est faux. Cherchez le piège : un « nettoyage évidemment sûr »
qui change une sémantique. Regardez en particulier si une des variables passées en
`const` est réassignée ou utilisée hors de son bloc.

## Diff INTÉGRAL (src/ et tests/)
```diff
diff --git a/src/forgeai/web/assets/app.css b/src/forgeai/web/assets/app.css
index b97389f..9670e34 100644
--- a/src/forgeai/web/assets/app.css
+++ b/src/forgeai/web/assets/app.css
@@ -466,3 +466,12 @@ code {
   padding: 4px 16px 14px; background: var(--card-bg);
 }
 .cloud-block summary { cursor: pointer; padding: 10px 0; font-weight: 600; font-size: 14px; }
+
+/* Le groupe d'adoption est un <fieldset> pour porter la sémantique « groupe de cases »
+   sans attribut role. On neutralise la bordure et les marges que les navigateurs lui
+   donnent par défaut, pour que l'apparence soit celle du <div> qu'il remplace. */
+#inventaire {
+  border: 0;
+  padding: 0;
+  margin: 0;
+}
diff --git a/src/forgeai/web/assets/app.js b/src/forgeai/web/assets/app.js
index 11d881f..ad1d672 100644
--- a/src/forgeai/web/assets/app.js
+++ b/src/forgeai/web/assets/app.js
@@ -275,34 +275,36 @@
 
   async function chargerInventaire() {
     try {
-      var res = await fetch('/api/discover?node=local');
+      const res = await fetch('/api/discover?node=local');
       if (!res.ok) throw new Error('/api/discover -> ' + res.status);
       state.inventaire = await res.json();
     } catch (e) {
       // L'inventaire est une COMMODITÉ : son indisponibilité ne doit jamais empêcher de
-      // déployer. On retombe simplement sur « aucun service détecté ».
+      // déployer. On retombe simplement sur « aucun service détecté ». L'erreur est
+      // journalisée : un inventaire absent doit rester diagnosticable, pas silencieux.
+      console.warn('inventaire indisponible, déploiement sans adoption :', e);
       state.inventaire = null;
     }
     renderInventaire();
   }
 
   function renderInventaire() {
-    var container = document.getElementById('inventaire-content');
+    const container = document.getElementById('inventaire-content');
     if (!container) return;
-    var services = ForgeAIAdoption.servicesAdoptables(state.inventaire, briquesDuPlan());
+    const services = ForgeAIAdoption.servicesAdoptables(state.inventaire, briquesDuPlan());
     container.innerHTML = '';
     if (!services.length) {
       // Jamais de liste vide muette : l'utilisateur doit savoir que la recherche a eu lieu.
-      var p = document.createElement('p');
+      const p = document.createElement('p');
       p.className = 'muted';
       p.textContent = t('inventaire_vide');
       container.appendChild(p);
       return;
     }
     services.forEach(function(svc){
-      var label = document.createElement('label');
+      const label = document.createElement('label');
       label.className = 'inventaire-item';
-      var cb = document.createElement('input');
+      const cb = document.createElement('input');
       cb.type = 'checkbox';
       cb.id = 'adopt-' + svc.id;
       cb.checked = !!state.adoptChoisis[svc.id];
@@ -321,11 +323,11 @@
   // Extrait en fonction nommée plutôt qu'en expression inline : le quality gate refusait
   // l'IIFE dans le littéral (maintenabilité), et un nom rend l'intention lisible.
   function champAdopt() {
-    var choix = ForgeAIAdoption.servicesAdoptables(state.inventaire, briquesDuPlan())
+    const choix = ForgeAIAdoption.servicesAdoptables(state.inventaire, briquesDuPlan())
       .map(function (sv) {
         return { id: sv.id, endpoint: sv.endpoint, adopte: !!state.adoptChoisis[sv.id] };
       });
-    var dict = ForgeAIAdoption.construireAdopt(choix);
+    const dict = ForgeAIAdoption.construireAdopt(choix);
     return Object.keys(dict).length ? { adopt: dict } : {};
   }
 
diff --git a/src/forgeai/web/assets/index.html b/src/forgeai/web/assets/index.html
index 72b064c..a271ed7 100644
--- a/src/forgeai/web/assets/index.html
+++ b/src/forgeai/web/assets/index.html
@@ -157,11 +157,11 @@
       <section id="deploy" class="step-panel hidden" data-step-panel="7">
         <h2 data-i18n="deploy_title">Résumé &amp; Déploiement</h2>
         <p class="step-lede" data-i18n="deploy_subtitle">Vérifiez le résumé, puis tapez FORCER pour lancer le déploiement réel — chaque étape est prouvée en direct.</p>
-        <div id="inventaire" role="group" aria-labelledby="inventaire-titre">
+        <fieldset id="inventaire" aria-labelledby="inventaire-titre">
         <h3 id="inventaire-titre" data-i18n="inventaire_titre">Infrastructure déjà présente</h3>
         <p class="muted" data-i18n="inventaire_aide">Cochez un service pour l'ADOPTER : ForgeAI s'y branchera au lieu de le redéployer.</p>
         <div id="inventaire-content"></div>
-      </div>
+      </fieldset>
       <div id="deploy-summary" class="models-list" aria-live="polite"></div>
         <form id="deploy-form" class="model-form card" autocomplete="off">
           <div class="form-grid">
diff --git a/tests/js/adoption.test.cjs b/tests/js/adoption.test.cjs
index 97a7053..fda16fb 100644
--- a/tests/js/adoption.test.cjs
+++ b/tests/js/adoption.test.cjs
@@ -9,31 +9,17 @@
  * avec endpoint malformé, ou absent du plan, doit être écarté
  * silencieusement, sans exception et sans modification de l'entrée.
  *
- * Exécution : `node tests/js/adoption.test.cjs`
+ * Exécution : `node --test tests/js/adoption.test.cjs`
  * Sortie    : code 0 si toutes les assertions passent, non-nul sinon.
  */
 
 'use strict';
 
-const assert = require('node:assert');
+const test = require('node:test');
+const assert = require('node:assert/strict');
 
 const adoption = require('../../src/forgeai/web/assets/adoption.js');
 
-let passed = 0;
-let failed = 0;
-
-function check(label, fn) {
-  try {
-    fn();
-    passed += 1;
-    console.log('  ok  -', label);
-  } catch (err) {
-    failed += 1;
-    console.error('  FAIL -', label);
-    console.error('         ', err && err.message ? err.message : err);
-  }
-}
-
 // Copie profonde naïve : suffisante ici (chaînes, booléens, tableaux
 // et objets plats uniquement).
 function deepClone(x) {
@@ -42,7 +28,7 @@ function deepClone(x) {
 
 // ─────────────────────── servicesAdoptables ───────────────────────
 
-check('cas nominal : redis + qdrant détectés, valides, au plan -> 2 adoptables triés par id', () => {
+test('cas nominal : redis + qdrant détectés, valides, au plan -> 2 adoptables triés par id', () => {
   const inventaire = {
     services: [
       { id: 'redis',  detecte: true, endpoint: 'redis.local:6379', via: ['binaire'] },
@@ -66,7 +52,7 @@ check('cas nominal : redis + qdrant détectés, valides, au plan -> 2 adoptables
     'le champ `via` est préservé pour qdrant');
 });
 
-check('docker détecté (par binaire) mais endpoint null -> écarté', () => {
+test('docker détecté (par binaire) mais endpoint null -> écarté', () => {
   const inventaire = {
     services: [{ id: 'docker', detecte: true, endpoint: null, via: ['binaire'] }]
   };
@@ -75,7 +61,7 @@ check('docker détecté (par binaire) mais endpoint null -> écarté', () => {
     'endpoint null/absent signifie "non joignable" -> docker écarté');
 });
 
-check('postgres non détecté (detecte=false) -> écarté', () => {
+test('postgres non détecté (detecte=false) -> écarté', () => {
   const inventaire = {
     services: [{ id: 'postgres', detecte: false, endpoint: 'pg.local:5432', via: ['port'] }]
   };
@@ -84,7 +70,7 @@ check('postgres non détecté (detecte=false) -> écarté', () => {
     'un service non détecté ne peut pas être adopté, même avec un endpoint');
 });
 
-check('redis détecté et joignable mais absent du plan -> écarté', () => {
+test('redis détecté et joignable mais absent du plan -> écarté', () => {
   const inventaire = {
     services: [{ id: 'redis', detecte: true, endpoint: 'redis.local:6379', via: ['binaire'] }]
   };
@@ -94,7 +80,7 @@ check('redis détecté et joignable mais absent du plan -> écarté', () => {
     'on ne peut pas adopter ce qu\'on ne déploie pas -> redis écarté');
 });
 
-check('endpoints malformés (4 formes) -> tous écartés', () => {
+test('endpoints malformés (4 formes) -> tous écartés', () => {
   const inventaire = {
     services: [
       { id: 'a', detecte: true, endpoint: 'pasdeport' }, // pas de séparateur
@@ -119,7 +105,7 @@ check('endpoints malformés (4 formes) -> tous écartés', () => {
     'port vide (rien après le dernier ":") -> invalide');
 });
 
-check('inventaire null / undefined / {} / {services:[]} -> [] sans plantage', () => {
+test('inventaire null / undefined / {} / {services:[]} -> [] sans plantage', () => {
   const plan = ['redis', 'qdrant'];
   const cases = [
     ['null',          null],
@@ -138,7 +124,7 @@ check('inventaire null / undefined / {} / {services:[]} -> [] sans plantage', ()
 
 // ─────────────────────── construireAdopt ───────────────────────
 
-check('construireAdopt : 2 cochés sur 3 -> mapping {id:"hôte:port"} des 2 seuls', () => {
+test('construireAdopt : 2 cochés sur 3 -> mapping {id:"hôte:port"} des 2 seuls', () => {
   const choix = [
     { id: 'redis',  endpoint: 'redis.local:6379', adopte: true  },
     { id: 'qdrant', endpoint: 'q.local:6333',     adopte: true  },
@@ -156,7 +142,7 @@ check('construireAdopt : 2 cochés sur 3 -> mapping {id:"hôte:port"} des 2 seul
     'le mapping ne contient que les 2 entrées cochées (ni plus, ni moins)');
 });
 
-check('construireAdopt : aucun choix coché -> {} (objet vide)', () => {
+test('construireAdopt : aucun choix coché -> {} (objet vide)', () => {
   const choix = [
     { id: 'redis',  endpoint: 'redis.local:6379', adopte: false },
     { id: 'qdrant', endpoint: 'q.local:6333',     adopte: false }
@@ -168,7 +154,7 @@ check('construireAdopt : aucun choix coché -> {} (objet vide)', () => {
     'le mapping rendu est exactement {}');
 });
 
-check('construireAdopt : coché mais endpoint invalide -> ignoré', () => {
+test('construireAdopt : coché mais endpoint invalide -> ignoré', () => {
   const choix = [
     { id: 'redis',  endpoint: 'pasdeport',    adopte: true },
     { id: 'qdrant', endpoint: 'q.local:6333', adopte: true }
@@ -184,7 +170,7 @@ check('construireAdopt : coché mais endpoint invalide -> ignoré', () => {
 
 // ─────────────────────── non-mutation ───────────────────────
 
-check('aucune mutation : inventaire et tableau de choix inchangés après appel', () => {
+test('aucune mutation : inventaire et tableau de choix inchangés après appel', () => {
   const inventaire = {
     services: [
       { id: 'redis',  detecte: true,  endpoint: 'redis.local:6379', via: ['binaire'] },
@@ -210,9 +196,3 @@ check('aucune mutation : inventaire et tableau de choix inchangés après appel'
   assert.deepStrictEqual(choix, choixAvant,
     'construireAdopt ne doit pas muter le tableau de choix qui lui est passé');
 });
-
-// ─────────────────────── Résumé ───────────────────────
-
-console.log('');
-console.log(`adoption.test.cjs : ${passed} cas ok, ${failed} cas en échec, ${passed + failed} cas au total.`);
-process.exit(failed === 0 ? 0 : 1);
diff --git a/tests/js/chaine_adoption.test.cjs b/tests/js/chaine_adoption.test.cjs
index 2b1d28e..8ad5787 100644
--- a/tests/js/chaine_adoption.test.cjs
+++ b/tests/js/chaine_adoption.test.cjs
@@ -4,65 +4,78 @@
  * n'était pas dans index.html (ReferenceError au clic sur Déployer, pour TOUS les utilisateurs)
  * et où chargerInventaire() était définie sans être jamais appelée.
  * Compter les occurrences ne l'avait pas vu. Ce test exécute la chaîne.
- * Exécution : `node tests/js/chaine_adoption.test.cjs` (exit != 0 si une seule casse).
+ * Exécution : `node --test tests/js/chaine_adoption.test.cjs` (exit != 0 si une seule casse).
  */
-const assert = require('node:assert');
+const test = require('node:test');
+const assert = require('node:assert/strict');
 const fs = require('node:fs');
 const path = require('node:path');
 
 const RACINE = path.join(__dirname, '..', '..');
 const html = fs.readFileSync(path.join(RACINE, 'src/forgeai/web/assets/index.html'), 'utf8');
 const appjs = fs.readFileSync(path.join(RACINE, 'src/forgeai/web/assets/app.js'), 'utf8');
-let ok = 0;
 
 // 1. la page charge adoption.js, AVANT app.js qui référence son global
-const ordre = [...html.matchAll(/src="([a-z_]+\.js)"/g)].map((m) => m[1]);
-assert.ok(ordre.includes('adoption.js'),
-  'index.html doit charger adoption.js : sans lui, ForgeAIAdoption est undefined et le POST lève');
-assert.ok(ordre.indexOf('adoption.js') < ordre.indexOf('app.js'),
-  'adoption.js doit être chargé AVANT app.js qui utilise son global');
-ok++;
+test('la page charge adoption.js, AVANT app.js qui référence son global', () => {
+  const ordre = [...html.matchAll(/src="([a-z_]+\.js)"/g)].map((m) => m[1]);
+  assert.ok(ordre.includes('adoption.js'),
+    'index.html doit charger adoption.js : sans lui, ForgeAIAdoption est undefined et le POST lève');
+  assert.ok(ordre.indexOf('adoption.js') < ordre.indexOf('app.js'),
+    'adoption.js doit être chargé AVANT app.js qui utilise son global');
+});
 
 // 2. app.js appelle réellement ce qu'il définit (pas de code mort)
 // On compte sur les lignes NON COMMENTÉES : un appel mis en commentaire ne compte pas.
 // (Première version de ce test : comptage textuel brut — une ligne commentée le trompait,
 //  soit exactement le défaut « vérifier le texte au lieu du comportement » qu'il dénonce.)
-const lignesActives = appjs.split('\n').filter((l) => !l.trim().startsWith('//'));
-const appelsCharger = lignesActives.filter(
-  (l) => /chargerInventaire\(\)/.test(l) && !/function\s+chargerInventaire/.test(l)).length;
-const appelsRender = lignesActives.filter(
-  (l) => /renderInventaire\(\)/.test(l) && !/function\s+renderInventaire/.test(l)).length;
-assert.ok(appelsCharger >= 1,
-  `chargerInventaire() doit être APPELÉE hors commentaire (trouvé ${appelsCharger}) : sinon l'écran reste vide`);
-assert.ok(appelsRender >= 2,
-  `renderInventaire() doit être appelée au chargement ET après un changement de briques (trouvé ${appelsRender})`);
-ok++;
+test('app.js appelle réellement ce qu\'il définit (pas de code mort)', () => {
+  const lignesActives = appjs.split('\n').filter((l) => !l.trim().startsWith('//'));
+  const appelsCharger = lignesActives.filter(
+    (l) => /chargerInventaire\(\)/.test(l) && !/function\s+chargerInventaire/.test(l)).length;
+  const appelsRender = lignesActives.filter(
+    (l) => /renderInventaire\(\)/.test(l) && !/function\s+renderInventaire/.test(l)).length;
+  assert.ok(appelsCharger >= 1,
+    `chargerInventaire() doit être APPELÉE hors commentaire (trouvé ${appelsCharger}) : sinon l'écran reste vide`);
+  assert.ok(appelsRender >= 2,
+    `renderInventaire() doit être appelée au chargement ET après un changement de briques (trouvé ${appelsRender})`);
+});
 
 // 3. le global est bien exposé au chargement du module
-require(path.join(RACINE, 'src/forgeai/web/assets/adoption.js'));
-const A = globalThis.ForgeAIAdoption;
-assert.ok(A && typeof A.servicesAdoptables === 'function' && typeof A.construireAdopt === 'function',
-  'adoption.js doit exposer servicesAdoptables et construireAdopt sur le global');
-ok++;
+test('le global est bien exposé au chargement du module', () => {
+  require(path.join(RACINE, 'src/forgeai/web/assets/adoption.js'));
+  const A = globalThis.ForgeAIAdoption;
+  assert.ok(A && typeof A.servicesAdoptables === 'function' && typeof A.construireAdopt === 'function',
+    'adoption.js doit exposer servicesAdoptables et construireAdopt sur le global');
+});
 
 // 4. la chaîne produit le dictionnaire exact attendu par /api/deploy (contrat prouvé en D3)
-const inventaire = { services: [
-  { id: 'redis',  detecte: true, via: ['port'],      endpoint: '127.0.0.1:6379' },
-  { id: 'qdrant', detecte: true, via: ['conteneur'], endpoint: '127.0.0.1:6333' },
-  { id: 'docker', detecte: true, via: ['binaire'],   endpoint: null },
-]};
-const adoptables = A.servicesAdoptables(inventaire, ['redis', 'qdrant', 'litellm']);
-assert.deepStrictEqual(adoptables.map((s) => s.id), ['qdrant', 'redis'],
-  'docker (sans endpoint) est écarté ; redis et qdrant sont proposés, triés par id');
-const dict = A.construireAdopt(adoptables.map((s) => ({ ...s, adopte: s.id === 'redis' })));
-assert.deepStrictEqual(dict, { redis: '127.0.0.1:6379' },
-  'seul le service coché part dans le POST, au format {id: "hôte:port"} attendu par /api/deploy');
-ok++;
+test('la chaîne produit le dictionnaire exact attendu par /api/deploy (contrat prouvé en D3)', () => {
+  require(path.join(RACINE, 'src/forgeai/web/assets/adoption.js'));
+  const A = globalThis.ForgeAIAdoption;
+  const inventaire = { services: [
+    { id: 'redis',  detecte: true, via: ['port'],      endpoint: '127.0.0.1:6379' },
+    { id: 'qdrant', detecte: true, via: ['conteneur'], endpoint: '127.0.0.1:6333' },
+    { id: 'docker', detecte: true, via: ['binaire'],   endpoint: null },
+  ]};
+  const adoptables = A.servicesAdoptables(inventaire, ['redis', 'qdrant', 'litellm']);
+  assert.deepStrictEqual(adoptables.map((s) => s.id), ['qdrant', 'redis'],
+    'docker (sans endpoint) est écarté ; redis et qdrant sont proposés, triés par id');
+  const dict = A.construireAdopt(adoptables.map((s) => ({ ...s, adopte: s.id === 'redis' })));
+  assert.deepStrictEqual(dict, { redis: '127.0.0.1:6379' },
+    'seul le service coché part dans le POST, au format {id: "hôte:port"} attendu par /api/deploy');
+});
 
 // 5. rien de coché -> dict vide -> le POST n'ajoute pas la clé (équivalence stricte)
-const vide = A.construireAdopt(adoptables.map((s) => ({ ...s, adopte: false })));
-assert.strictEqual(Object.keys(vide).length, 0,
-  'aucune case cochée => dictionnaire vide => le corps du POST reste identique à avant D4');
-ok++;
-
-console.log(`chaine_adoption.test.cjs : ${ok} cas ok, 0 cas en échec, ${ok} cas au total.`);
+test('rien de coché -> dict vide -> le POST n\'ajoute pas la clé (équivalence stricte)', () => {
+  require(path.join(RACINE, 'src/forgeai/web/assets/adoption.js'));
+  const A = globalThis.ForgeAIAdoption;
+  const inventaire = { services: [
+    { id: 'redis',  detecte: true, via: ['port'],      endpoint: '127.0.0.1:6379' },
+    { id: 'qdrant', detecte: true, via: ['conteneur'], endpoint: '127.0.0.1:6333' },
+    { id: 'docker', detecte: true, via: ['binaire'],   endpoint: null },
+  ]};
+  const adoptables = A.servicesAdoptables(inventaire, ['redis', 'qdrant', 'litellm']);
+  const vide = A.construireAdopt(adoptables.map((s) => ({ ...s, adopte: false })));
+  assert.strictEqual(Object.keys(vide).length, 0,
+    'aucune case cochée => dictionnaire vide => le corps du POST reste identique à avant D4');
+});
```

## Preuve d'exécution CAPTURÉE, rejouée après le commit af5a821
```
$ node --check src/forgeai/web/assets/app.js
(exit 0)

$ node tests/js/adoption.test.cjs
ℹ tests 10
ℹ pass 10
ℹ fail 0
$ node tests/js/chaine_adoption.test.cjs
ℹ tests 5
ℹ pass 5
ℹ fail 0

# inventaire des assertions, avant (ancien lanceur) puis après (node:test)
adoption : 4 deepStrictEqual + 1 ok + 22 strictEqual = 27, identique avant/après
chaine   : 2 deepStrictEqual + 5 ok + 1 strictEqual = 8,  identique avant/après

# mutations injectees une a une -> la suite doit passer au ROUGE
  svc.detecte !== true          -> exit 1
  !endpointValide(svc.endpoint) -> exit 1
  !prevues[id]                  -> exit 1
  retrait de <script src=adoption.js> -> exit 1
  (substitution verifiee effective avant interpretation ; vert retrouve apres restauration)

$ grep -c '</section>' index.html : 7 avant, 7 apres
$ python3 -m pytest -q : exit=0
```
