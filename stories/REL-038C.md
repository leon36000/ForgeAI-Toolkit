# REL-038C — Gérer les process groups et nettoyer les orphelins

- **Issue** : #259 · **Tier** : T2 (fiabilité — processus orphelins, signaux mal cloisonnés)
- **Dépend de** : REL-038B — mergé.
- **Périmètre** : `src/forgeai/core/proc.py`, `src/forgeai/web/server.py`,
  `tests/test_rel038c_process_groups.py` (nouveau), `stories/REL-038C.md`.

## 1. État MESURÉ de l'existant
Le chemin **CLI** est déjà traité par **CLI-036** : `core/proc.py` lance avec
`start_new_session=True` (groupe de processus dédié) et possède `_kill_tree(proc, grace_seconds)` —
SIGTERM au **groupe**, délai de grâce, puis SIGKILL, avec branche Windows.

**Gap réel : le chemin WEB.** Le sous-processus de déploiement (`subprocess.Popen`, server.py l.1334)
est lancé **sans `start_new_session`** — il reste donc dans le groupe de processus du **serveur**.
Deux conséquences mesurées :
1. **Signaux mal cloisonnés** : un `Ctrl-C` destiné au serveur est délivré à tout le groupe, donc
   **tue un déploiement en cours** (docker compose / k3s interrompu au milieu).
2. **Orphelins** : `serve()` intercepte `KeyboardInterrupt` puis appelle `shutdown()` /
   `server_close()` **sans jamais terminer le déploiement** ; sur un arrêt propre (SIGTERM,
   `systemctl stop`), le sous-processus survit au serveur — **orphelin** poursuivant un déploiement
   que plus personne ne supervise ni ne peut interrompre.

## 2. Décision
1. **Groupe dédié pour le déploiement web**, réglé **par plateforme** (même convention que CLI-036
   dans `core/proc.py`) : `start_new_session=True` sous POSIX, `CREATE_NEW_PROCESS_GROUP` sous
   Windows. Le déploiement cesse d'être collatéralement tué par un signal destiné au serveur et
   devient **adressable en tant que groupe**.

   **Mesuré** (objection de revue vérifiée dans la source CPython) : `start_new_session` est
   *accepté* sous Windows — il ne lève donc pas — mais il y est **silencieusement ignoré**
   (`unused_start_new_session` dans la branche Windows de `_execute_child`). Le passer seul aurait
   laissé l'isolation **absente sous Windows** alors que le code aurait eu l'air de la fournir —
   un trou silencieux, d'autant moins acceptable que la CI teste `windows-latest`.
2. **Réutiliser la sémantique éprouvée de CLI-036** plutôt que la ré-implémenter : exposer
   `kill_tree(proc, grace_seconds)` en API **publique** de `core/proc.py` (mince enveloppe autour de
   `_kill_tree`, additive — aucun appelant existant modifié, donc aucun risque pour CLI-036).
3. **Nettoyage des orphelins à l'arrêt** : `_terminate_active_deploy()` termine le groupe du
   déploiement s'il tourne encore ; appelé depuis `serve()` dans un `finally`, de sorte qu'il couvre
   l'arrêt normal ET le `KeyboardInterrupt`. Best-effort : l'arrêt du serveur ne doit jamais lever.

## 3. TDAD (RED d'abord) — `tests/test_rel038c_process_groups.py`
- **G1** le déploiement web est lancé avec `start_new_session=True` (le `Popen` reçoit bien l'option).
- **G2** un sous-processus RÉEL de longue durée enregistré comme déploiement actif est effectivement
  **tué** par `_terminate_active_deploy()` (vérification par `proc.poll()` non-None).
- **G3** le groupe est bien distinct : le PGID du sous-processus diffère de celui du processus de test.
- **G4** sans déploiement actif (ou déjà terminé), `_terminate_active_deploy()` est un **no-op** qui ne
  lève pas.
- **G5** `serve()` appelle le nettoyage même sur `KeyboardInterrupt` (fumée : le `finally` est bien
  emprunté).
- **Mutation** : retirer `start_new_session` → G1/G3 tombent ; retirer l'appel de nettoyage → G2 tombe.

## 4. Critères d'acceptation
- **CA1** le déploiement web tourne dans son propre groupe de processus.
- **CA2** aucun orphelin : l'arrêt du serveur termine un déploiement encore actif (grâce puis SIGKILL).
- **CA3** réutilisation de `kill_tree` (CLI-036), aucun appelant existant modifié ; nettoyage
  best-effort (n'empêche jamais l'arrêt).
- **CA4** non-régression : suite complète verte, couverture ≥ 85 %.
