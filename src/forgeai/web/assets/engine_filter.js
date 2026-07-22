/* Story S6b — filtrage moteur<->vendor côté client (fonctions PURES, testables hors navigateur).
 *
 * Miroir exact du contrat serveur /api/engines/compatible?vendor=X (S4/S6) : un moteur est
 * proposé dans le <select> d'un modèle ssi son gpu_vendors[] contient le vendor GPU du nœud
 * cible. Aucune I/O, aucun DOM — chargé comme <script> AVANT app.js (expose window.ForgeAIEngineFilter)
 * ET exporté en CommonJS pour la preuve Node (tests/js/engine_filter.test.cjs). La validation dure
 * reste côté serveur (wizard S4 rejette un couple incompatible) ; ceci n'est que du confort visuel.
 */
(function (root) {
  'use strict';

  function engineId(eng) {
    if (eng && (eng.id || eng.engine_id)) return eng.id || eng.engine_id;
    return String(eng);
  }

  // Vendor GPU d'un nœud pour le filtrage : le vendor UNIQUE si le nœud n'en a qu'un, sinon null
  // (nœud mixte, sans sonde, ou pseudo-nœud local/auto/inconnu) => pas de filtrage (fallback).
  function nodeVendorForFilter(nodes, nodeName) {
    if (!nodeName || nodeName === 'local' || nodeName === 'auto') return null;
    if (!Array.isArray(nodes)) return null;
    var node = null;
    for (var i = 0; i < nodes.length; i++) {
      var n = nodes[i];
      if (n && (n.name === nodeName || n.hostname === nodeName)) { node = n; break; }
    }
    if (!node || !Array.isArray(node.vendors)) return null;
    return node.vendors.length === 1 ? node.vendors[0] : null;
  }

  // Filtre les moteurs par vendor. vendor falsy => liste inchangée (fallback : tout afficher).
  function filterEnginesByVendor(engines, vendor) {
    if (!Array.isArray(engines)) return [];
    if (!vendor) return engines.slice();
    return engines.filter(function (eng) {
      var vendors = (eng && eng.gpu_vendors) || [];
      return Array.isArray(vendors) && vendors.indexOf(vendor) !== -1;
    });
  }

  // Liste FINALE des moteurs pour un <select> : filtrée par vendor, mais le moteur déjà
  // sélectionné reste TOUJOURS présent même s'il est incompatible (jamais de changement
  // silencieux de valeur — la validation serveur signalera l'incompatibilité au déploiement).
  function engineChoices(engines, vendor, selectedId) {
    var list = filterEnginesByVendor(engines, vendor);
    if (selectedId) {
      var present = false;
      for (var i = 0; i < list.length; i++) {
        if (engineId(list[i]) === selectedId) { present = true; break; }
      }
      if (!present && Array.isArray(engines)) {
        for (var j = 0; j < engines.length; j++) {
          if (engineId(engines[j]) === selectedId) { list = [engines[j]].concat(list); break; }
        }
      }
    }
    return list;
  }

  root.ForgeAIEngineFilter = {
    engineId: engineId,
    nodeVendorForFilter: nodeVendorForFilter,
    filterEnginesByVendor: filterEnginesByVendor,
    engineChoices: engineChoices
  };

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = root.ForgeAIEngineFilter;
  }
})(typeof window !== 'undefined' ? window : globalThis);
