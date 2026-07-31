# PERF-030A — Cache matériel TTL cohérent et invalidable

- **Issue** : #249 · **Tier** : T2 (performance + surface d'amplification)
- **Dépend de** : WEB-034B — mergé.
- **Reprise lane CODEX** · **Périmètre** : `src/forgeai/web/server.py`,
  `tests/test_perf030a_refresh.py` (nouveau), `stories/PERF-030A.md`.

## 1. État MESURÉ de l'existant (avant de coder)
Le cache demandé par cette story **existe déjà**, livré par **OPT-001** (complété) :
- **TTL** : `_HARDWARE_TTL_S = 60.0` (borné pour hotplug/driver) ;
- **cohérent** : `_hardware_lock = threading.RLock()` + verrouillage à double vérification ;
  RLock (et non Lock) car `_available_backends` appelle `_hardware_report()` en tenant déjà le
  verrou — l'interblocage est prouvé par `test_backends_et_hardware_sans_interblocage` ;
- **invalidable** : `_hardware_cache_clear()` purge le cache matériel ET le cache backends.

**Gap réel** (mesuré) : `_hardware_cache_clear()` n'a **aucun appelant de production** —
`grep -rn _hardware_cache_clear src/ tests/` ne renvoie que sa définition et des usages de **tests**.
Autrement dit l'invalidation existe mais est **inatteignable** : un opérateur qui branche un GPU
(ou installe un pilote) doit attendre l'expiration du TTL, sans aucun moyen de forcer une re-sonde.

## 2. Décision — rendre l'invalidation atteignable, sans refaire OPT-001
Ajouter **`POST /api/detect/refresh`** : purge explicite (`_hardware_cache_clear()`) puis renvoi d'un
rapport matériel **frais** (200, corps identique à `/api/detect`).

### 2b. Pourquoi POST (mutation) et non `GET /api/detect?refresh=1`
Un rafraîchissement **force des sondes sous-processus coûteuses** (c'est précisément le coût qu'OPT-001
a mesuré et supprimé : `/api/summary` 940→1583 ms, `_available_backends` 801 ms). Exposé en GET, il
deviendrait un **vecteur d'amplification** : n'importe quelle page tierce pourrait, par simple
`<img src>`, forcer des re-sondes en boucle (déni de service local à coût quasi nul pour l'attaquant).
En **POST**, la route hérite automatiquement de toute la chaîne de gardes déjà en place en tête de
`do_POST` — **WEB-016** (rate-limit + anti-bruteforce), **WEB-034B** (refus des identifiants en clair
sur le réseau), **WEB-001/017** (jeton Bearer, anti-CSRF `Sec-Fetch-Site`/`Origin`, anti-rebinding
`Host`) — sans une ligne de garde supplémentaire à écrire ni à maintenir.

### 2c. Hors périmètre (documenté)
TTL, verrou et fonction de purge : **déjà livrés par OPT-001**, non retouchés (aucune régression
introduite). Cette story n'ajoute que le **chemin d'accès** manquant.

## 3. TDAD (RED d'abord) — `tests/test_perf030a_refresh.py`
Compteur de sondes via un faux `HardwareDetector` monkeypatché (patron de `tests/test_server_cache.py`,
avec purge du cache module en fixture pour éviter la pollution inter-tests).
- **CA1** `POST /api/detect/refresh` en loopback → 200, corps = rapport matériel, et le compteur de
  sondes **augmente** (une nouvelle sonde a bien eu lieu) ;
- **CA2** deux `GET /api/detect` successifs ne sondent qu'**une** fois (cache OPT-001 intact) — puis un
  `refresh` force la re-sonde : la preuve que l'invalidation agit ;
- **CA3** la route est bien une **mutation gardée** : sur un bind non-loopback sans jeton →
  **401** (jamais 200) ; un `Sec-Fetch-Site: cross-site` → **403**. Aucune re-sonde n'a lieu lors d'un refus.
- **CA4** non-régression : `/api/detect` inchangé ; suite complète verte.
- **Mutation** : retirer l'appel `_hardware_cache_clear()` de la route → CA1/CA2 tombent.

## 4. Critères d'acceptation
- **CA1** `POST /api/detect/refresh` purge et renvoie un rapport frais (200).
- **CA2** l'invalidation est **effective** (re-sonde prouvée par compteur), le cache TTL restant actif sinon.
- **CA3** route protégée par la chaîne de gardes existante (401 sans jeton hors loopback, 403 cross-site),
  **sans re-sonde** en cas de refus (pas d'amplification).
- **CA4** non-régression : OPT-001 intact ; suite complète verte, couverture ≥ 85 %.
