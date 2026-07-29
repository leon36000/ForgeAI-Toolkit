/*
 * adoption.test.cjs — Tests Node du module d'adoption.
 *
 * Portée de la preuve : on vérifie les règles d'exclusion et de tri
 * de `servicesAdoptables`, la construction du mapping envoyé au
 * backend par `construireAdopt`, ainsi que l'absence de mutation
 * des arguments. Chaque cas ci-dessous correspond à une règle
 * d'acceptation de la story : un service non détecté, sans endpoint,
 * avec endpoint malformé, ou absent du plan, doit être écarté
 * silencieusement, sans exception et sans modification de l'entrée.
 *
 * Exécution : `node tests/js/adoption.test.cjs`
 * Sortie    : code 0 si toutes les assertions passent, non-nul sinon.
 */

'use strict';

const assert = require('node:assert');

const adoption = require('../../src/forgeai/web/assets/adoption.js');

let passed = 0;
let failed = 0;

function check(label, fn) {
  try {
    fn();
    passed += 1;
    console.log('  ok  -', label);
  } catch (err) {
    failed += 1;
    console.error('  FAIL -', label);
    console.error('         ', err && err.message ? err.message : err);
  }
}

// Copie profonde naïve : suffisante ici (chaînes, booléens, tableaux
// et objets plats uniquement).
function deepClone(x) {
  return JSON.parse(JSON.stringify(x));
}

// ─────────────────────── servicesAdoptables ───────────────────────

check('cas nominal : redis + qdrant détectés, valides, au plan -> 2 adoptables triés par id', () => {
  const inventaire = {
    services: [
      { id: 'redis',  detecte: true, endpoint: 'redis.local:6379', via: ['binaire'] },
      { id: 'qdrant', detecte: true, endpoint: 'q.local:6333',     via: ['binaire'] }
    ]
  };
  const plan = ['redis', 'qdrant'];
  const out = adoption.servicesAdoptables(inventaire, plan);

  assert.strictEqual(out.length, 2,
    'redis et qdrant sont tous deux détectés, joignables et au plan -> 2 adoptables');
  assert.strictEqual(out[0].id, 'qdrant',
    'tri par id : qdrant (q) précède redis (r)');
  assert.strictEqual(out[1].id, 'redis',
    'tri par id : redis (r) suit qdrant (q)');
  assert.strictEqual(out[0].endpoint, 'q.local:6333',
    'l\'endpoint de qdrant est propagé tel quel dans la sortie');
  assert.strictEqual(out[1].endpoint, 'redis.local:6379',
    'l\'endpoint de redis est propagé tel quel dans la sortie');
  assert.deepStrictEqual(out[0].via, ['binaire'],
    'le champ `via` est préservé pour qdrant');
});

check('docker détecté (par binaire) mais endpoint null -> écarté', () => {
  const inventaire = {
    services: [{ id: 'docker', detecte: true, endpoint: null, via: ['binaire'] }]
  };
  const out = adoption.servicesAdoptables(inventaire, ['docker']);
  assert.strictEqual(out.length, 0,
    'endpoint null/absent signifie "non joignable" -> docker écarté');
});

check('postgres non détecté (detecte=false) -> écarté', () => {
  const inventaire = {
    services: [{ id: 'postgres', detecte: false, endpoint: 'pg.local:5432', via: ['port'] }]
  };
  const out = adoption.servicesAdoptables(inventaire, ['postgres']);
  assert.strictEqual(out.length, 0,
    'un service non détecté ne peut pas être adopté, même avec un endpoint');
});

check('redis détecté et joignable mais absent du plan -> écarté', () => {
  const inventaire = {
    services: [{ id: 'redis', detecte: true, endpoint: 'redis.local:6379', via: ['binaire'] }]
  };
  const plan = ['postgres']; // redis n'est PAS prévu au déploiement
  const out = adoption.servicesAdoptables(inventaire, plan);
  assert.strictEqual(out.length, 0,
    'on ne peut pas adopter ce qu\'on ne déploie pas -> redis écarté');
});

check('endpoints malformés (4 formes) -> tous écartés', () => {
  const inventaire = {
    services: [
      { id: 'a', detecte: true, endpoint: 'pasdeport' }, // pas de séparateur
      { id: 'b', detecte: true, endpoint: 'h:abc' },     // port non numérique
      { id: 'c', detecte: true, endpoint: ':6379' },     // hôte vide
      { id: 'd', detecte: true, endpoint: 'h:' }         // port vide
    ]
  };
  const plan = ['a', 'b', 'c', 'd'];
  const out = adoption.servicesAdoptables(inventaire, plan);
  assert.strictEqual(out.length, 0,
    'les 4 endpoints malformés doivent tous être écartés par servicesAdoptables');

  // Vérification fine de chaque forme via la primitive endpointValide.
  assert.strictEqual(adoption.endpointValide('pasdeport'), false,
    '"pasdeport" n\'a pas de séparateur -> invalide');
  assert.strictEqual(adoption.endpointValide('h:abc'), false,
    'port "abc" non numérique -> invalide');
  assert.strictEqual(adoption.endpointValide(':6379'), false,
    'hôte vide (rien avant le dernier ":") -> invalide');
  assert.strictEqual(adoption.endpointValide('h:'), false,
    'port vide (rien après le dernier ":") -> invalide');
});

check('inventaire null / undefined / {} / {services:[]} -> [] sans plantage', () => {
  const plan = ['redis', 'qdrant'];
  const cases = [
    ['null',          null],
    ['undefined',     undefined],
    ['{}',            {}],
    ['{services:[]}', { services: [] }]
  ];
  for (const [label, inv] of cases) {
    const out = adoption.servicesAdoptables(inv, plan);
    assert.ok(Array.isArray(out),
      `[${label}] le résultat reste un tableau (aucune exception levée)`);
    assert.strictEqual(out.length, 0,
      `[${label}] aucun service ne peut être adopté depuis un inventaire absent`);
  }
});

// ─────────────────────── construireAdopt ───────────────────────

check('construireAdopt : 2 cochés sur 3 -> mapping {id:"hôte:port"} des 2 seuls', () => {
  const choix = [
    { id: 'redis',  endpoint: 'redis.local:6379', adopte: true  },
    { id: 'qdrant', endpoint: 'q.local:6333',     adopte: true  },
    { id: 'ollama', endpoint: 'o.local:11434',    adopte: false }
  ];
  const adopt = adoption.construireAdopt(choix);

  assert.strictEqual(adopt.redis, 'redis.local:6379',
    'redis coché + endpoint valide -> présent dans le mapping');
  assert.strictEqual(adopt.qdrant, 'q.local:6333',
    'qdrant coché + endpoint valide -> présent dans le mapping');
  assert.strictEqual('ollama' in adopt, false,
    'ollama non coché -> aucune clé correspondante dans le mapping');
  assert.strictEqual(Object.keys(adopt).length, 2,
    'le mapping ne contient que les 2 entrées cochées (ni plus, ni moins)');
});

check('construireAdopt : aucun choix coché -> {} (objet vide)', () => {
  const choix = [
    { id: 'redis',  endpoint: 'redis.local:6379', adopte: false },
    { id: 'qdrant', endpoint: 'q.local:6333',     adopte: false }
  ];
  const adopt = adoption.construireAdopt(choix);
  assert.strictEqual(Object.keys(adopt).length, 0,
    'mapping strictement vide si rien n\'est coché');
  assert.deepStrictEqual(adopt, {},
    'le mapping rendu est exactement {}');
});

check('construireAdopt : coché mais endpoint invalide -> ignoré', () => {
  const choix = [
    { id: 'redis',  endpoint: 'pasdeport',    adopte: true },
    { id: 'qdrant', endpoint: 'q.local:6333', adopte: true }
  ];
  const adopt = adoption.construireAdopt(choix);
  assert.strictEqual('redis' in adopt, false,
    'redis coché avec endpoint invalide -> clé absente du mapping');
  assert.strictEqual(adopt.qdrant, 'q.local:6333',
    'qdrant coché avec endpoint valide -> conservé');
  assert.strictEqual(Object.keys(adopt).length, 1,
    'seul qdrant est retenu : redis invalide a été ignoré');
});

// ─────────────────────── non-mutation ───────────────────────

check('aucune mutation : inventaire et tableau de choix inchangés après appel', () => {
  const inventaire = {
    services: [
      { id: 'redis',  detecte: true,  endpoint: 'redis.local:6379', via: ['binaire'] },
      { id: 'qdrant', detecte: true,  endpoint: 'q.local:6333',     via: ['binaire'] },
      { id: 'ollama', detecte: false, endpoint: null,               via: [] }
    ]
  };
  const choix = [
    { id: 'redis',  endpoint: 'redis.local:6379', adopte: true  },
    { id: 'qdrant', endpoint: 'q.local:6333',     adopte: false }
  ];
  const plan = ['redis', 'qdrant'];

  // Copies profondes réalisées AVANT tout appel.
  const invAvant   = deepClone(inventaire);
  const choixAvant = deepClone(choix);

  adoption.servicesAdoptables(inventaire, plan);
  adoption.construireAdopt(choix);

  assert.deepStrictEqual(inventaire, invAvant,
    'servicesAdoptables ne doit pas muter l\'inventaire qui lui est passé');
  assert.deepStrictEqual(choix, choixAvant,
    'construireAdopt ne doit pas muter le tableau de choix qui lui est passé');
});

// ─────────────────────── Résumé ───────────────────────

console.log('');
console.log(`adoption.test.cjs : ${passed} cas ok, ${failed} cas en échec, ${passed + failed} cas au total.`);
process.exit(failed === 0 ? 0 : 1);
