# OPS-031A — `forgeai status` et une API de santé re-sondable

- **Issue** : #260 · **Tier** : T2 (exploitabilité + surface de sonde)
- **Dépend de** : OPS-031D — mergé.
- **Périmètre** : `src/forgeai/status.py` (nouveau), `src/forgeai/web/server.py`,
  `src/forgeai/cli.py`, `tests/test_ops031a_status.py` (nouveau), `stories/OPS-031A.md`.

## 1. Problème (mesuré)
- `/api/health` renvoie un `{"status": "ok"}` **statique** : il prouve que le processus répond, et
  **rien d'autre**. Aucun moyen de savoir si les backends sont disponibles, si le cluster répond, où
  en est le dernier déploiement.
- Aucune commande `forgeai status` de haut niveau. `doctor` existe mais répond à une autre question :
  « **ce que la machine peut faire** » (capacités, préflight), pas « **où en est le système
  maintenant** » (état d'exécution).

## 2. Décision — séparer *liveness* et *santé profonde*
1. **`/api/health` reste statique, bon marché et PUBLIC.** C'est une sonde de *liveness* destinée aux
   orchestrateurs. Lui faire faire des sondes profondes serait un contresens **et** un **vecteur
   d'amplification non authentifié** : les sondes matérielles/backends coûtent des sous-processus
   (OPT-001 a mesuré `_available_backends` à 801 ms). C'est exactement le raisonnement retenu en
   PERF-030A pour refuser un rafraîchissement en GET public.
2. **Nouvelle route `GET /api/status`** : santé **profonde**. Par la classification **fail-closed de
   WEB-017**, tout `/api/*` hors health/i18n est **sensible d'office** — elle hérite donc sans une
   ligne de garde du jeton hors loopback, de l'anti-CSRF/rebinding, du rate-limit (WEB-016) et de la
   politique de transport (WEB-034B). C'est la posture correcte pour un point qui **révèle l'état de
   l'infrastructure** *et* **coûte des sondes**.
3. **« Re-sondable »** : `/api/status` lit **à travers les caches TTL** (OPT-001) — il reflète donc
   l'état courant et **re-sonde quand le cache est périmé**, sans devenir un levier de déni de
   service. L'invalidation explicite existe déjà et reste une **mutation gardée**
   (`POST /api/detect/refresh`, PERF-030A).
4. **Source unique** : une fonction pure `collect_status(...)` dans `forgeai/status.py`, à dépendances
   **injectées** (runner, fournisseurs de backends/cluster/déploiement). La CLI et la route web
   l'appellent toutes deux — aucune logique d'état dupliquée, et le tout est testable sans sonde réelle.
5. **`forgeai status [--json]`** : même agrégat, calculé **localement** (aucun serveur requis), en
   sortie humaine ou JSON.
6. **Aucune fuite** : les erreurs de sonde (cluster injoignable, backends en échec) sont **rédigées**
   (`redact_text`) avant d'entrer dans l'agrégat — un message d'outil peut porter un chemin ou un
   fragment sensible (même discipline qu'ERR-041B/C et WEB-015).

### 2b. Le cache cluster manquait (objection de revue CONFIRMÉE, non réfutée)
La décision §3 promettait une lecture « à travers les caches TTL ». La revue a relevé que
`cluster_status` — qui lance **`kubectl`, un sous-processus** — n'était **caché nulle part** : chaque
`GET /api/status` en aurait relancé un, jusqu'à la limite de WEB-016. **La promesse de la story était
donc fausse dans le code.** Corrigé : `_cluster_status_cache()` applique le **même TTL et le même
verrou** que les caches d'OPT-001, et `_hardware_cache_clear()` le purge aussi — l'invalidation reste
cohérente. Un test (G8) **compte les sondes** : 5 requêtes → 1 seule sonde, sans quoi la promesse
resterait invérifiable.

Les deux autres objections étaient mineures : le paramètre inutilisé de `_sonder` a été retiré ;
celle sur les imports de `cluster_status`/`SubprocessRunner` est **réfutée par mesure** — ils sont
déjà globaux dans `server.py` (lignes 28 et 38).

## 3. TDAD (RED d'abord) — `tests/test_ops031a_status.py`
- **G1** `collect_status` agrège les sources injectées sans lever, même si **une** sonde échoue
  (dégradation gracieuse : la section en échec est marquée, les autres restent renseignées).
- **G2** un message de sonde porteur d'un faux-secret est **rédigé** dans l'agrégat.
- **G3** `GET /api/status` en loopback renvoie 200 et le même agrégat.
- **G4** `GET /api/status` sur bind non-loopback **sans jeton** → **401** (hérité de WEB-017) : la
  santé profonde n'est jamais anonyme.
- **G5** `/api/health` reste **200 sans jeton** et **statique** (non-régression : la liveness ne doit
  pas devenir coûteuse ni gardée).
- **G6** `forgeai status --json` imprime un JSON valide contenant les mêmes clés que la route.
- **Mutation** : rendre `/api/status` public → G4 tombe ; retirer la rédaction → G2 tombe.

## 4. Critères d'acceptation
- **CA1** `collect_status` : agrégat unique, dépendances injectées, dégradation gracieuse, sans fuite.
- **CA2** `GET /api/status` gardé d'office (401 hors loopback sans jeton), servi depuis les caches TTL.
- **CA3** `/api/health` inchangé : statique, public, bon marché.
- **CA4** `forgeai status [--json]` s'appuie sur la **même** fonction ; suite complète verte,
  couverture ≥ 85 %.
