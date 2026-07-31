# PERF-030B — Benchmarks et seuils de non-régression de /api/detect

- **Issue** : #244 · **Tier** : T2 (garde-fou de performance en CI)
- **Dépend de** : PERF-030A — mergé.
- **Reprise lane CODEX** · **Périmètre** : `tests/test_perf030b_seuils.py` (nouveau),
  `stories/PERF-030B.md`. **Aucune modification de code de production.**

## 1. Problème
Le coût de `/api/detect` est aujourd'hui borné par le cache TTL (OPT-001) et son invalidation
ponctuelle (PERF-030A), mais **rien n'empêche une régression future** : un refactor qui retirerait le
cache (ou le rendrait inopérant) passerait la CI en silence — les tests existants vérifient le
comportement fonctionnel, pas le *coût*.

## 2. Décision — seuil DÉTERMINISTE en primaire, chronomètre en filet
Un seuil purement **chronométrique** est inutilisable comme garde en CI : sur des runners partagés à
charge variable, soit on le fixe si haut qu'il ne détecte plus rien, soit il **flake** (rouge sans
régression) — et un test qui flake finit désactivé, donc ne protège plus rien.

Le détecteur réel est donc le **TRAVAIL** effectué, qui est déterministe et observable : le **nombre de
sondes matérielles** pour une rafale de requêtes. Avec cache : **1 sonde pour N requêtes**. Sans cache :
**N sondes**. Le seuil est franc, reproductible, et indépendant de la machine.

Le chronomètre est conservé en **filet grossier secondaire** (plafond p95 large), explicitement
documenté comme tel dans son propre docstring pour qu'aucun futur lecteur ne le prenne pour la garde
principale.

### 2b. Seuils exprimés en constantes nommées
`N_REQUETES`, `SONDES_MAX_RAFALE`, `SONDES_MAX_PAR_REFRESH`, `PLAFOND_P95_S` — auto-documentés, pas de
nombres magiques. Un test vérifie leur **cohérence mutuelle** (`N_REQUETES > SONDES_MAX_RAFALE`, etc.)
afin qu'on ne puisse pas neutraliser silencieusement un seuil en le portant à une valeur absurde.

## 3. TDAD — `tests/test_perf030b_seuils.py`
Faux `HardwareDetector` à compteur (coût simulé ~20 ms) + purge du cache module en fixture `autouse`.
- **G1 (seuil primaire)** : `N_REQUETES` GET `/api/detect` → toutes 200, sondes ≤ `SONDES_MAX_RAFALE`.
- **G2** : un `POST /api/detect/refresh` coûte exactement `SONDES_MAX_PAR_REFRESH` sonde.
- **G3** : la rafale qui suit le refresh n'ajoute **aucune** sonde (cache de nouveau chaud).
- **G4 (filet chrono)** : p95 des `N_REQUETES` GET < `PLAFOND_P95_S`, docstring rappelant son rôle secondaire.
- **G5** : cohérence des seuils (impossible de les neutraliser en silence).
- **Détecteur** : si le cache disparaissait, G1 verrait `N_REQUETES` sondes au lieu de 1 → rouge.

## 4. Critères d'acceptation
- **CA1** une rafale de `N_REQUETES` sur `/api/detect` ne déclenche qu'**une** sonde (seuil déterministe).
- **CA2** l'invalidation reste ponctuelle : 1 sonde par refresh, puis cache chaud de nouveau.
- **CA3** filet chronométrique présent, documenté comme secondaire, à marge large (pas de flake).
- **CA4** aucun code de production modifié ; suite complète verte, couverture ≥ 85 %.
- **CA5** les seuils sont des constantes nommées et mutuellement cohérentes — un test les vérifie, de
  sorte qu'on ne puisse pas les neutraliser silencieusement (ex. `SONDES_MAX_RAFALE` porté à `N_REQUETES`).
