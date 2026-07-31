# REL-038B — Une seule opération active et réconciliation idempotente

- **Issue** : #256 · **Tier** : T2 (fiabilité — travail dupliqué + état bloqué)
- **Dépend de** : REL-038A — mergé.
- **Périmètre** : `src/forgeai/web/server.py`, `tests/test_rel038b_unicite.py` (nouveau),
  `stories/REL-038B.md`.

## 1. Problème (code réel MESURÉ)
Le **déploiement** possède déjà sa garde d'unicité (l.1249 : `409 "déploiement déjà en cours"`,
vérifiée sous `_DEPLOY_STATE["lock"]`). La **préparation de nœud** n'en a AUCUNE : `POST
/api/nodes/prepare` marque l'état puis lance un thread sans jamais vérifier qu'une préparation du
même hôte est déjà en cours. Deux requêtes concurrentes (double-clic de l'UI, re-tentative réseau)
lancent **deux threads qui exécutent la même préparation sur le même nœud** — commandes SSH
dupliquées, écritures d'état entrelacées, résultat final indéterminé (le dernier thread à terminer
écrase l'autre).

### 1b. Défaut LATENT introduit par REL-038A (mesuré, à traiter ici)
Depuis REL-038A, l'état de préparation **survit au redémarrage**. Une préparation interrompue par un
crash laisse donc sur disque une entrée `{"done": false}` — « en cours » — alors qu'**aucun thread ne
survit à un redémarrage**. Une garde d'unicité naïve fondée sur `done == False` **verrouillerait
définitivement cet hôte** : plus aucune préparation possible, sans aucun moyen de débloquer. La garde
et la réconciliation doivent donc être conçues ENSEMBLE.

## 2. Décision
1. **Unicité PAR HÔTE, pas globale.** Un ensemble runtime `_PREPARE_ACTIVE: set[str]` protégé par
   `_PREPARE_LOCK`. `POST /api/nodes/prepare` : sous le verrou, si l'hôte y figure → **409
   « préparation déjà en cours pour cet hôte »** ; sinon on l'y insère avant de lancer le thread
   (test-et-marquage **atomiques** — sinon deux requêtes voient toutes deux « libre »). Le thread se
   retire dans un `finally` (une exception ne doit jamais laisser un hôte verrouillé).
   Le choix **par hôte** est délibéré : préparer plusieurs nœuds *différents* en parallèle est un cas
   d'usage légitime d'un toolkit multi-nœuds ; une garde globale le casserait sans gain.
2. **`_PREPARE_ACTIVE` est runtime-only** (jamais persisté) : après un redémarrage il est vide, donc
   il ne peut par construction pas provoquer de blocage persistant.
3. **Réconciliation idempotente au chargement.** `_load_prepare_state()` convertit toute entrée
   restaurée `done: false` en état **terminal** : `{"done": true, "resultat": null, "erreur":
   "préparation interrompue par un redémarrage"}`. Aucun thread n'ayant survécu, « en cours » est un
   mensonge ; l'UI doit voir un état franc et l'hôte redevient préparable. **Idempotente** : ré-appeler
   la réconciliation sur un état déjà réconcilié ne change plus rien (point fixe).

## 3. TDAD (RED d'abord) — `tests/test_rel038b_unicite.py`
- **G1** deux `POST /api/nodes/prepare` concurrents sur le MÊME hôte → un 202 et un **409** ; le
  travail n'est exécuté qu'**une seule fois** (compteur de `preparer_noeud`).
- **G2** deux hôtes DIFFÉRENTS en parallèle → deux 202 (le multi-nœuds n'est pas bridé).
- **G3** après la fin de la préparation, un nouveau POST sur le même hôte → 202 (l'hôte est libéré).
- **G4** si le thread lève, l'hôte est quand même libéré (`finally`) → POST suivant = 202.
- **G5** réconciliation : un fichier persisté contenant `{"done": false}` → après `_load_prepare_state()`
  l'entrée est terminale (`done: true`, `erreur` mentionnant le redémarrage) ; un POST est de nouveau accepté.
- **G6** idempotence : appeler `_load_prepare_state()` deux fois de suite laisse l'état identique.
- **Mutation** : retirer le test-et-marquage → G1 tombe ; retirer la réconciliation → G5 tombe ;
  sortir le `discard` du `finally` → G4 tombe.

## 4. Critères d'acceptation
- **CA1** une seule préparation active par hôte (409 sinon), test-et-marquage atomique sous verrou.
- **CA2** hôtes distincts toujours parallélisables ; hôte libéré même en cas d'exception.
- **CA3** réconciliation au chargement : aucune entrée « en cours » fantôme ne survit à un
  redémarrage ; opération idempotente (point fixe).
- **CA4** non-régression : garde de déploiement inchangée ; suite complète verte, couverture ≥ 85 %.
