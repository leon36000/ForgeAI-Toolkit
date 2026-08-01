# OPS-031E — Interface opérateur Status / Logs / Diagnostic

- **Issue** : #257 · **Tier** : T2 (surface web + exposition d'état d'infrastructure)
- **Dépend de** : OPS-031C — mergé.
- **Périmètre** : `src/forgeai/web/assets/index.html`, `app.js`, `app.css`,
  `src/forgeai/data/locales/{fr,en}.json`, `tests/test_ops031e_ui_operateur.py` (nouveau),
  `stories/OPS-031E.md`.

## 1. État MESURÉ
Les trois capacités existent déjà côté backend/CLI (OPS-031A/B/C) : `GET /api/status` (santé profonde,
sensible d'office), `GET /api/deploy/events` (flux de lignes **rédigées à l'ingestion**),
`forgeai logs`, `forgeai diagnostic`. Un visualiseur de logs existe même déjà dans l'UI :
`<pre id="deploy-log">` alimenté par `EventSource('/api/deploy/events')` (app.js l.567).

**Le manque n'est donc pas la capacité, c'est son ACCESSIBILITÉ.** Ce visualiseur vit dans la
`section[data-step-panel="7"]`, et l'étape 7 est **verrouillée tant qu'aucune stack n'est
sélectionnée** : `NEEDS_STACK = {3, 4, 5, 7}` (app.js) et `stepAllowed` refuse la navigation quand
`state.selectedId` est faux. Comme `selectedId` n'est **jamais persisté** (aucun `localStorage` dans
`app.js`), **tout rechargement de page re-verrouille l'étape 7** — donc le seul visualiseur de logs
existant. L'écran qui montre ce qui ne va pas est ainsi hors d'atteinte au premier chargement,
précisément quand on en a besoin. Et aucune surface n'expose `/api/status`.

> Formulation corrigée après vérification : la version initiale de cette story disait « inaccessible
> tant que l'installation n'est pas terminée », ce qui est **faux** — le verrou porte sur la sélection
> d'une stack, pas sur l'achèvement. Le défaut reste réel, mais il fallait l'énoncer juste.

## 2. Décision
1. **Surface d'exploitation HORS du rail verrouillé.** Un panneau opérateur accessible depuis
   l'en-tête (`.controls`, à côté des bascules langue/thème), donc **jamais gated**. Une 8ᵉ étape de
   rail serait verrouillée par construction et reproduirait exactement le défaut constaté.
2. **Réutiliser le flux existant, ne pas le dupliquer.** Le panneau consomme le MÊME
   `EventSource('/api/deploy/events')` — les lignes sont déjà rédigées à l'ingestion (OPS-031B), donc
   la surface n'introduit aucune voie de fuite nouvelle.
3. **Statut** : appel `GET /api/status`. En loopback il répond ; sur un bind réseau sans jeton il
   renvoie **401** — l'UI doit afficher un état explicite (« authentification requise ») plutôt
   qu'une erreur muette, sans jamais exposer le détail interne (WEB-015).
4. **Diagnostic : aucune route de téléchargement web.** Le bundle est conçu pour **quitter la
   machine** ; offrir un téléchargement en un clic depuis un navigateur élargirait la surface
   d'exfiltration pour un gain marginal, alors que `forgeai diagnostic --out` sert déjà l'opérateur.
   L'UI **affiche la commande exacte à exécuter** — c'est l'aide utile sans le risque.
5. **i18n obligatoire** (fr/en) : le projet est destiné au monde entier ; une surface anglaise-only
   ou française-only contredirait cette ambition.

## 3. TDAD (RED d'abord) — `tests/test_ops031e_ui_operateur.py`
Tests statiques sur les assets (patron de `tests/test_ui_7_etapes.py` : lecture de `index.html`,
`app.js`, `fr.json`, `en.json`).
- **G1** le panneau opérateur existe et n'est **PAS** un `data-step-panel` (donc hors rail verrouillé).
- **G2** son déclencheur est dans l'en-tête `.controls`, pas dans `#step-rail`.
- **G3** `app.js` appelle `/api/status` et réutilise `/api/deploy/events` (pas de second flux).
- **G4** le cas **401** est traité explicitement (message d'authentification), sans afficher de détail interne.
- **G5** **aucune** route de téléchargement de bundle n'est appelée depuis l'UI ; la commande CLI est
  affichée à la place.
- **G6** toutes les clés i18n introduites existent **dans fr.json ET en.json** (aucune clé orpheline
  dans un seul des deux).
- **Mutation** : déplacer le panneau sous `data-step-panel` → G1 tombe ; retirer une clé de `en.json`
  → G6 tombe.

## 4. Critères d'acceptation
- **CA1** surface d'exploitation atteignable **sans avoir terminé l'installation**.
- **CA2** statut + logs affichés en réutilisant les routes existantes ; 401 rendu explicitement.
- **CA3** aucun téléchargement de bundle depuis le web ; commande CLI indiquée.
- **CA4** i18n fr+en complète ; suite complète verte, couverture ≥ 85 %.
