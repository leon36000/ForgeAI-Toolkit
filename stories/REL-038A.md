# REL-038A — Persister l'état de préparation avec schéma et écriture atomique

- **Issue** : #247 · **Tier** : T2 (fiabilité — perte d'état + intégrité sur disque)
- **Dépend de** : PERF-030B — mergé.
- **Périmètre** : `src/forgeai/web/server.py`, `tests/test_rel038a_prepare_persist.py` (nouveau),
  `stories/REL-038A.md`.

## 1. Problème (code réel)
`_PREPARE_STATE` (l.335) est un `OrderedDict` **en mémoire seulement**, borné LRU à 256. Un
redémarrage du serveur (mise à jour, crash, reboot) **perd tout l'état de préparation des nœuds** :
l'UI qui interroge `/api/nodes/prepare/<host>` retombe sur `{"done": False}` alors qu'une préparation
a peut-être abouti — l'opérateur ne peut plus savoir où il en est. L'état de déploiement, lui, EST
persisté (`_persist_deploy_state`/`_load_deploy_state`, #139) : l'asymétrie n'est pas justifiée.

## 2. Décision
Persister l'état de préparation, avec **schéma versionné** et **écriture atomique**.

- **Schéma** : `{"version": 1, "hosts": {<host>: {"done": bool, "resultat": …, "erreur": str|None}}}`.
  Le champ `version` permet une évolution future sans casser un fichier existant.
- **Validation au chargement (fail-safe)** : fichier absent/illisible/JSON invalide/`version` inconnue
  /forme inattendue → on repart d'un état **vide** plutôt que de propager une structure douteuse.
  Chaque entrée d'hôte est validée individuellement : une entrée corrompue est ignorée sans
  invalider les autres.
- **Écriture atomique** : réutilisation de `forgeai.models._locking.atomic_write_text` plutôt qu'une
  ré-implémentation. Cette fonction fait mkstemp + `os.fchmod(0600)` + **fsync** + `os.replace` —
  strictement plus forte que le bloc inline de `_persist_deploy_state`, qui omet le fsync (perte
  possible sur coupure) et le mode 0600. L'état de préparation nomme des hôtes d'infrastructure :
  il n'a pas à être lisible par les autres comptes de la machine.
- **Rédaction avant persistance** : `erreur` est rédigé (`redact_text`) avant écriture — même
  discipline qu'ERR-041A/`_persist_deploy_state`, un message `PrepareError` pouvant porter un chemin.
- **Best-effort** : la persistance ne doit JAMAIS faire échouer une préparation (try/except borné),
  au même titre que `_persist_deploy_state`.
- **Borne LRU conservée** : au chargement comme à l'écriture, au plus `_PREPARE_MAX` hôtes.

### 2b. Conséquence MESURÉE : écriture dans `FORGEAI_HOME` pendant les tests
Le dépôt n'a pas de `conftest.py` isolant `FORGEAI_HOME` ; `forgeai_home()` vaut `$FORGEAI_HOME` sinon
`~/.forgeai`. Ajouter la persistance à `_prepare_state_set` fait donc écrire
`~/.forgeai/prepare/prepare-state.json` lors des suites qui exercent une préparation. **Mesuré** :
c'est exactement le comportement déjà établi par `_persist_deploy_state` (`~/.forgeai/deploy/` et une
dizaine d'autres artefacts y sont écrits par les tests existants) — ce n'est donc pas une nouvelle
classe d'effet de bord. Le même contrôle a confirmé le mode réel du fichier produit : `-rw-------`
(0600), c'est-à-dire que la protection ne dépend pas du bac à sable des tests.

## 3. TDAD (RED d'abord) — `tests/test_rel038a_prepare_persist.py`
`forgeai_home` redirigé vers `tmp_path` (monkeypatch) pour ne rien écrire hors du bac à sable.
- **G1** un `_prepare_state_set` écrit le fichier ; le JSON contient `version` et l'hôte.
- **G2** après purge de l'état mémoire, `_load_prepare_state()` restaure l'entrée (survie au redémarrage).
- **G3** le fichier est écrit en mode **0600** (droits) et de façon **atomique** (aucun `.tmp` résiduel).
- **G4** un fichier corrompu (JSON invalide) ou de `version` inconnue → chargement sans exception,
  état vide (fail-safe).
- **G5** une entrée d'hôte malformée est ignorée SANS perdre les entrées valides du même fichier.
- **G6** l'`erreur` persistée est rédigée (un faux-secret n'apparaît pas dans le fichier).
- **G7** la borne LRU est respectée après chargement (≤ `_PREPARE_MAX`).
- **Mutation** : remplacer l'écriture atomique par une écriture directe → G3 tombe ; retirer la
  validation → G4/G5 tombent.

## 4. Critères d'acceptation
- **CA1** l'état de préparation survit à un redémarrage (persisté + rechargé).
- **CA2** schéma versionné, validation fail-safe (corrompu → vide, entrée invalide → ignorée seule).
- **CA3** écriture atomique avec fsync et mode 0600 ; `erreur` rédigée ; jamais d'exception propagée.
- **CA4** non-régression : `_prepare_state_get/set` inchangés côté API ; suite complète verte,
  couverture ≥ 85 %.
