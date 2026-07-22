'use strict';
/* Story S6b — preuve Node (V8, même moteur que le navigateur) des fonctions PURES de filtrage
 * moteur<->vendor. Exécution : `node tests/js/engine_filter.test.cjs` (assertions réelles ;
 * exit != 0 si une seule casse). NON câblé dans les gates CI (pas de runner JS au dépôt) — c'est
 * une preuve locale re-jouable, pas un badge. Le rendu DOM (engineOptions/select) = vérif navigateur.
 */
const assert = require('node:assert');
const F = require('../../src/forgeai/web/assets/engine_filter.js');

// Données réelles = data/moteurs-inference.json (gpu_vendors par moteur).
const ENGINES = [
  { id: 'vllm', name: 'vLLM', gpu_vendors: ['nvidia', 'amd'] },
  { id: 'sglang', name: 'SGLang', gpu_vendors: ['nvidia', 'amd'] },
  { id: 'llama-cpp', name: 'llama.cpp', gpu_vendors: ['nvidia', 'amd', 'intel', 'apple', 'cpu'] },
  { id: 'ollama', name: 'Ollama', gpu_vendors: ['nvidia', 'amd', 'apple', 'cpu'] },
  { id: 'tensorrt-llm', name: 'TensorRT-LLM', gpu_vendors: ['nvidia'] },
  { id: 'lorax', name: 'LoRAX', gpu_vendors: ['nvidia'] },
  { id: 'lmdeploy', name: 'LMDeploy', gpu_vendors: ['nvidia'] },
  { id: 'mlc-llm', name: 'MLC-LLM', gpu_vendors: ['nvidia', 'amd', 'intel', 'apple'] },
];

// 1. Nœud AMD : cache tensorrt-llm / lorax / lmdeploy (nvidia-only), garde le reste.
//    Miroir EXACT du contrat serveur compatible_engines('amd') prouvé en S4/S6.
const amd = F.filterEnginesByVendor(ENGINES, 'amd').map((e) => e.id);
assert.deepStrictEqual(amd, ['vllm', 'sglang', 'llama-cpp', 'ollama', 'mlc-llm']);
assert.ok(!amd.includes('tensorrt-llm'));
assert.ok(!amd.includes('lorax'));
assert.ok(!amd.includes('lmdeploy'));

// 2. Nœud NVIDIA : tous les moteurs listent nvidia -> aucun masqué.
assert.strictEqual(F.filterEnginesByVendor(ENGINES, 'nvidia').length, ENGINES.length);

// 3. Nœud Intel : seuls llama-cpp et mlc-llm restent.
assert.deepStrictEqual(F.filterEnginesByVendor(ENGINES, 'intel').map((e) => e.id),
  ['llama-cpp', 'mlc-llm']);

// 4. Vendor inconnu / vide / nul => AUCUN filtrage (fallback : tout afficher).
assert.strictEqual(F.filterEnginesByVendor(ENGINES, '').length, ENGINES.length);
assert.strictEqual(F.filterEnginesByVendor(ENGINES, null).length, ENGINES.length);
assert.strictEqual(F.filterEnginesByVendor(ENGINES, undefined).length, ENGINES.length);

// 5. Vendor d'un nœud : unique -> ce vendor ; mixte/sans-sonde/local/auto/inconnu -> null.
const NODES = [
  { name: 'worker-amd', vendors: ['amd'] },
  { name: 'worker-mix', vendors: ['nvidia', 'amd'] },
  { name: 'worker-nosonde', vendors: [] },
];
assert.strictEqual(F.nodeVendorForFilter(NODES, 'worker-amd'), 'amd');
assert.strictEqual(F.nodeVendorForFilter(NODES, 'worker-mix'), null);   // mixte => pas de filtrage
assert.strictEqual(F.nodeVendorForFilter(NODES, 'worker-nosonde'), null);
assert.strictEqual(F.nodeVendorForFilter(NODES, 'local'), null);
assert.strictEqual(F.nodeVendorForFilter(NODES, 'auto'), null);
assert.strictEqual(F.nodeVendorForFilter(NODES, 'inconnu'), null);
assert.strictEqual(F.nodeVendorForFilter(NODES, ''), null);
assert.strictEqual(F.nodeVendorForFilter(null, 'worker-amd'), null);

// 6. engineChoices : le moteur DÉJÀ sélectionné reste visible même incompatible (pas de saut
//    silencieux de valeur), sans doublon quand il est compatible.
const kept = F.engineChoices(ENGINES, 'amd', 'tensorrt-llm').map((e) => e.id);
assert.ok(kept.includes('tensorrt-llm'), 'sélection incompatible conservée');
assert.ok(kept.includes('vllm'), 'compatibles présents');
const compat = F.engineChoices(ENGINES, 'amd', 'vllm').map((e) => e.id);
assert.strictEqual(compat.filter((x) => x === 'vllm').length, 1, 'pas de doublon');
// sans vendor => liste complète, sélection inchangée
assert.strictEqual(F.engineChoices(ENGINES, null, 'lorax').length, ENGINES.length);

console.log('OK — 6 groupes d\'assertions passés (filtrage moteur<->vendor S6b, données réelles)');
