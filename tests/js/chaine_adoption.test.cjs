'use strict';
/* D4 — preuve de CHAÎNE : les fonctions pures ne suffisent pas, encore faut-il que la page
 * les CHARGE et que app.js les APPELLE. La revue scellée a rejeté une version où adoption.js
 * n'était pas dans index.html (ReferenceError au clic sur Déployer, pour TOUS les utilisateurs)
 * et où chargerInventaire() était définie sans être jamais appelée.
 * Compter les occurrences ne l'avait pas vu. Ce test exécute la chaîne.
 * Exécution : `node tests/js/chaine_adoption.test.cjs` (exit != 0 si une seule casse).
 */
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');

const RACINE = path.join(__dirname, '..', '..');
const html = fs.readFileSync(path.join(RACINE, 'src/forgeai/web/assets/index.html'), 'utf8');
const appjs = fs.readFileSync(path.join(RACINE, 'src/forgeai/web/assets/app.js'), 'utf8');
let ok = 0;

// 1. la page charge adoption.js, AVANT app.js qui référence son global
const ordre = [...html.matchAll(/src="([a-z_]+\.js)"/g)].map((m) => m[1]);
assert.ok(ordre.includes('adoption.js'),
  'index.html doit charger adoption.js : sans lui, ForgeAIAdoption est undefined et le POST lève');
assert.ok(ordre.indexOf('adoption.js') < ordre.indexOf('app.js'),
  'adoption.js doit être chargé AVANT app.js qui utilise son global');
ok++;

// 2. app.js appelle réellement ce qu'il définit (pas de code mort)
// On compte sur les lignes NON COMMENTÉES : un appel mis en commentaire ne compte pas.
// (Première version de ce test : comptage textuel brut — une ligne commentée le trompait,
//  soit exactement le défaut « vérifier le texte au lieu du comportement » qu'il dénonce.)
const lignesActives = appjs.split('\n').filter((l) => !l.trim().startsWith('//'));
const appelsCharger = lignesActives.filter(
  (l) => /chargerInventaire\(\)/.test(l) && !/function\s+chargerInventaire/.test(l)).length;
const appelsRender = lignesActives.filter(
  (l) => /renderInventaire\(\)/.test(l) && !/function\s+renderInventaire/.test(l)).length;
assert.ok(appelsCharger >= 1,
  `chargerInventaire() doit être APPELÉE hors commentaire (trouvé ${appelsCharger}) : sinon l'écran reste vide`);
assert.ok(appelsRender >= 2,
  `renderInventaire() doit être appelée au chargement ET après un changement de briques (trouvé ${appelsRender})`);
ok++;

// 3. le global est bien exposé au chargement du module
require(path.join(RACINE, 'src/forgeai/web/assets/adoption.js'));
const A = globalThis.ForgeAIAdoption;
assert.ok(A && typeof A.servicesAdoptables === 'function' && typeof A.construireAdopt === 'function',
  'adoption.js doit exposer servicesAdoptables et construireAdopt sur le global');
ok++;

// 4. la chaîne produit le dictionnaire exact attendu par /api/deploy (contrat prouvé en D3)
const inventaire = { services: [
  { id: 'redis',  detecte: true, via: ['port'],      endpoint: '127.0.0.1:6379' },
  { id: 'qdrant', detecte: true, via: ['conteneur'], endpoint: '127.0.0.1:6333' },
  { id: 'docker', detecte: true, via: ['binaire'],   endpoint: null },
]};
const adoptables = A.servicesAdoptables(inventaire, ['redis', 'qdrant', 'litellm']);
assert.deepStrictEqual(adoptables.map((s) => s.id), ['qdrant', 'redis'],
  'docker (sans endpoint) est écarté ; redis et qdrant sont proposés, triés par id');
const dict = A.construireAdopt(adoptables.map((s) => ({ ...s, adopte: s.id === 'redis' })));
assert.deepStrictEqual(dict, { redis: '127.0.0.1:6379' },
  'seul le service coché part dans le POST, au format {id: "hôte:port"} attendu par /api/deploy');
ok++;

// 5. rien de coché -> dict vide -> le POST n'ajoute pas la clé (équivalence stricte)
const vide = A.construireAdopt(adoptables.map((s) => ({ ...s, adopte: false })));
assert.strictEqual(Object.keys(vide).length, 0,
  'aucune case cochée => dictionnaire vide => le corps du POST reste identique à avant D4');
ok++;

console.log(`chaine_adoption.test.cjs : ${ok} cas ok, 0 cas en échec, ${ok} cas au total.`);
