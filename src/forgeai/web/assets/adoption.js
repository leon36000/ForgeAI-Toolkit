/*
 * adoption.js — Fonctions pures pour l'adoption des services détectés.
 *
 * Aucune dépendance. Compatible Node et navigateur. Aucune mutation
 * des arguments. Aucune exception levée : une entrée inattendue est
 * écartée plutôt qu'interprétée.
 */
(function(root){
  'use strict';

  /**
   * Vérifie qu'une chaîne a la forme "hôte:port" joignable.
   * Règles : non vide après trim, contient au moins un ":", la partie
   * hôte (avant le dernier ":") est non vide, la partie port n'est composée
   * que de chiffres et est non vide.
   * Pourquoi : on ne peut pas adopter ce qu'on ne sait pas joindre ; un
   * `endpoint` absent, vide ou mal formé signifie "non joignable".
   */
  function endpointValide(endpoint){
    if (typeof endpoint !== 'string') return false;
    var s = endpoint.trim();
    if (s.length === 0) return false;
    var idx = s.lastIndexOf(':');
    if (idx <= 0) return false;            // pas de ":" ou hôte vide
    var host = s.slice(0, idx);
    var port = s.slice(idx + 1);
    if (host.length === 0) return false;
    if (port.length === 0) return false;
    if (!/^[0-9]+$/.test(port)) return false;
    return true;
  }

  /**
   * servicesAdoptables — parmi les services détectés par /api/discover,
   * retourne ceux que l'utilisateur prévoit de déployer dans son plan
   * (donc adoptables). Renvoie un tableau {id, endpoint, via} trié par id.
   *
   * Robuste aux entrées dégradées :
   *  - inventaire null / absent / sans clé `services` => []
   *  - service sans `detecte`, sans `endpoint`, ou avec `endpoint: null`
   *    => simplement écarté
   *  - briquesDuPlan absent ou non-tableau => []
   */
  function servicesAdoptables(inventaire, briquesDuPlan){
    var result = [];
    if (!inventaire || typeof inventaire !== 'object') return result;
    var services = inventaire.services;
    if (!Array.isArray(services)) return result;
    if (!Array.isArray(briquesDuPlan)) return result;

    // Index pour recherche en O(1) des briques prévues au plan.
    var prevues = {};
    for (var i = 0; i < briquesDuPlan.length; i++){
      var b = briquesDuPlan[i];
      if (typeof b === 'string' && b.length > 0) prevues[b] = true;
    }

    for (var k = 0; k < services.length; k++){
      var svc = services[k];
      if (!svc || typeof svc !== 'object') continue;
      // Règle : détecté ET joignable ET prévu au plan — sinon écarté.
      if (svc.detecte !== true) continue;            // pas détecté : pas adoptable
      if (!endpointValide(svc.endpoint)) continue;    // pas joignable : pas adoptable
      var id = svc.id;
      if (typeof id !== 'string' || id.length === 0) continue;
      if (!prevues[id]) continue;                     // pas au plan : pas adoptable

      var via = Array.isArray(svc.via) ? svc.via : [];
      result.push({ id: id, endpoint: svc.endpoint, via: via });
    }

    // Tri stable par id pour un rendu déterministe côté UI.
    result.sort(function(a, b){
      if (a.id < b.id) return -1;
      if (a.id > b.id) return 1;
      return 0;
    });

    return result;
  }

  /**
   * construireAdopt — à partir des choix UI (cochés / non cochés),
   * produit le mapping {id: endpoint} envoyé au backend.
   * - Aucun choix coché => {} (l'appelant omettra alors le champ).
   * - Un choix coché sans endpoint valide est ignoré silencieusement
   *   (mieux vaut ne rien adopter qu'adopter une valeur invérifiable).
   */
  function construireAdopt(choix){
    var result = {};
    if (!Array.isArray(choix)) return result;

    for (var i = 0; i < choix.length; i++){
      var c = choix[i];
      if (!c || typeof c !== 'object') continue;
      if (c.adopte !== true) continue;                // non coché : ignoré
      if (typeof c.id !== 'string' || c.id.length === 0) continue;
      if (!endpointValide(c.endpoint)) continue;       // endpoint invalide : ignoré
      result[c.id] = c.endpoint;
    }

    return result;
  }

  root.ForgeAIAdoption = {
    servicesAdoptables: servicesAdoptables,
    construireAdopt: construireAdopt,
    endpointValide: endpointValide
  };

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = root.ForgeAIAdoption;
  }
})(typeof window !== 'undefined' ? window : globalThis);
