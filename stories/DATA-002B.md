# DATA-002B — Fermer la fenêtre de crash-consistency d'`add_cloud`

Issue #306. Origine : la revue multi-vendor **REV-043** a rejoué une revue scellée sur le diff
déjà mergé de DATA-002 ; **DeepSeek-V4-Pro** a émis une objection CRITIQUE que la revue d'origine,
mono-vendor, avait manquée. La revue à 3 vendors distincts a donc rempli exactement son office.

## 1. État mesuré

`RouteStore.add_cloud` (`src/forgeai/models/routes.py:172-178`) applique un write-ahead log :
journal du snapshot **pré-commit** → commit (`vault._save` puis `self._save`) →
`atomic_unlink(journal)`.

`recover_models_transaction_locked` (`_locking.py:167-180`) appelle **inconditionnellement**
`restore_models_transaction_locked` dès qu'un journal existe. Donc si le processus meurt entre le
commit réussi et l'unlink, le redémarrage **annule une transaction commitée** : perte de données
silencieuse.

Le commit est composé de **deux `os.replace` indépendants** (`routes.py:174-175`). Aucune
primitive stdlib ne rend deux remplacements atomiques entre eux — ce fait gouverne toute la
conception.

**Le journal contient déjà une image du coffre, mais CHIFFRÉE** : `previous_vault =
self.vault._load()` renvoie `{nom: base64(blob scellé)}` (`vault.py:337-344`), scellé par scrypt
2^16 + EtM. Aucun secret en clair n'y figure aujourd'hui.

## 2. Décision de conception, et ce qui a été réfuté

### Réfutation 1 — « écrire un marqueur de commit avant l'unlink »
**Ne ferme pas la fenêtre, la déplace.** Le commit étant deux `os.replace` distincts, un crash
après le remplacement de `routes.json` mais avant que le marqueur soit durable laisse un état
**intégralement publié** sans marqueur ⇒ rollback d'un commit réussi. La fenêtre passe de
`[commit → unlink]` à `[commit → marqueur]`, elle ne disparaît pas.

Aggravant mesuré : ce rollback est lui-même faillible et non ré-entrant proprement —
`restore_models_transaction_locked` **conserve le journal** si une des deux restaurations échoue
(`_locking.py:162-164`). Un état « publié puis à moitié dé-publié » se rejouerait alors à
**chaque** ouverture.

### Réfutation 2 — « enregistrer l'état CIBLE complet dans le journal »
Correct sur le fond, **rejeté sur la surface d'exposition**. Le journal contient déjà du chiffré,
donc ce n'est pas une fuite en clair ; mais y ajouter le blob scellé de la clé **nouvellement
créée** a une conséquence concrète : la suppression du journal est **conditionnelle**
(`_locking.py:162-164`), si bien qu'un utilisateur détruisant `vault.json` pour révoquer une clé
laisserait le chiffré de cette clé dans un journal résiduel. Le principe du moindre nécessaire
tranche pour l'empreinte.

### Réfutation 3 — « hasher les octets bruts des fichiers cibles »
**Piège vicieux.** Un simple passage de `indent=1` à `indent=2` dans `_save` (`routes.py:87-93`)
casserait toutes les empreintes, et le mode d'échec serait « discordance ⇒ rollback » —
c'est-à-dire **la perte de données d'origine, réintroduite silencieusement** par une modification
de style. L'empreinte porte donc sur une **sérialisation canonique** (`sort_keys=True`,
`separators=(",", ":")`) recalculée des deux côtés depuis le JSON **parsé**.

### Décision — empreinte canonique de l'état cible
`_write_transaction_journal` enregistre, à côté du snapshot pré-commit, l'empreinte SHA-256
canonique des **deux** états cibles. La cible du coffre est **capturée**, jamais recalculée :
`seal` tire salt et nonce aléatoires (`vault.py:295-296`), le chiffré n'est pas reproductible.

**Propriété exigée, en une phrase** : *la récupération ne défait une transaction que si l'état sur
disque **diffère** de la cible enregistrée ; si l'état disque est exactement la cible, le seul acte
autorisé est la suppression du journal.*

**Conjonction stricte** : on ne renonce au rollback que si les **deux** cibles existent **et**
que les **deux** empreintes correspondent. Toute correspondance partielle ⇒ rollback.

### Le cas où le rollback reste LÉGITIME et ne doit pas être neutralisé
Crash **entre** les deux `_save` : le coffre porte une clé scellée sans route correspondante —
la « clé orpheline ». Avec la conjonction, ce cas donne `vault == cible` mais `routes ≠ cible`
⇒ **rollback**, comportement inchangé. C'est précisément ce que couvrent les tests existants
`test_routestore_concurrence.py:473` et `:493`, qui doivent rester verts.

## 3. Deux tests existants encodent le DÉFAUT comme spécification

Point le plus lourd de la story, absent de l'énoncé de l'issue, et autorisé **explicitement** ici :

- **`test_export_recupere_le_wal_avant_de_lire_routes`** (`:658`) — la ligne 673 **constate** que
  le commit a abouti (`routes.json` contient `orpheline`) puis la ligne 677 **exige**
  `"routes.json" not in bundle["files"]`, c'est-à-dire l'annulation d'une transaction commitée.
- **`test_sigkill_apres_routes_replace_est_recupere_avant_precheck_add`** (`:681`) — même point de
  crash, puis ré-ajout d'`orpheline` avec un **nouveau** secret attendu en succès ; après
  correctif la route commitée survit, donc `add_cloud` doit lever « existe déjà ».

Ces deux tests deviendront **ROUGES**, et c'est la preuve que le correctif agit. Ils sont
**réécrits sémantiquement** : leur intention légitime (« la récupération précède toute lecture »)
est conservée, leur postulat (« une transaction commitée est révocable ») est corrigé. Le pack de
revue porte l'avant/après, faute de quoi le trio rejetterait à juste titre.

## 4. TDAD

- **G1 (ROUGE d'abord)** — SIGKILL entre le commit et l'unlink, puis nouvelle instance : la route
  commitée **survit**, le secret d'origine est lisible, le journal a disparu. Outillé par le
  helper existant `_add_cloud_pause_before_journal_unlink` (`:141-160`). Sur le code actuel
  `recovered.list() == []` ⇒ rouge garanti, **pour la bonne raison**, pas par plantage.
- **G2** — crash **entre** les deux `_save` : le rollback reste appliqué (clé orpheline nettoyée).
- **G3** — champ cible **manquant** dans le journal (écrit par un binaire antérieur) ⇒ rollback
  inconditionnel, par une branche **explicite**, jamais par un défaut implicite.
- **G4** — accès **direct** aux champs cibles, jamais `.get()` : le motif existant
  `snapshot.get("vault_name", "vault.json")` (`_locking.py:99`) rendrait
  `snapshot.get("cible") == calcule` vrai quand la clé manque **et** que le calcul vaut `None` —
  un journal pré-commit légitime serait alors lu comme « commit réussi », sautant le rollback du
  cas orphelin. Une cible **absente ou malformée** renvoie donc `False` — donc rollback.
  Précision issue de l'application : fail-closed signifie **revenir en arrière**, pas *planter*.
  Lever ici ferait échouer `RouteStore(home)` à chaque ouverture sur un journal abîmé, ce qui
  serait plus grave que la restauration qu'on cherche à éviter.
- **G5** — empreinte **canonique** : réécrire les mêmes données avec un `indent` différent ne
  change pas le verdict (sans quoi un changement de style provoquerait une perte de données).
- **G6** — correspondance **partielle** (une cible sur deux) ⇒ rollback.
- **G7** — les tests hérités du cas orphelin (`:473`, `:493`) restent **verts**.

Mutations à prouver : forcer « commit toujours appliqué » → les tests de **maintien du rollback**
rougissent (G6 et les tests hérités du cas orphelin) — et non G1, qui exige la survie et ne peut
donc pas détecter une mutation allant dans son sens ; remplacer la conjonction par une disjonction
→ **G6** rougit.

## 5. Critères d'acceptation

- **CA1** aucune transaction commitée n'est annulée par la récupération ; G1 le prouve de bout en
  bout via un vrai SIGKILL, pas un simulacre.
- **CA2** le rollback légitime (crash entre les deux `_save`) est **conservé** ; `:473` et `:493`
  restent verts.
- **CA3** fail-closed : champ absent, journal illisible, empreinte non parsable ou fichier cible
  absent ⇒ rollback, jamais un succès supposé. Aucun `except` large silencieux.
- **CA4** **aucune matière secrète supplémentaire** sur disque : l'empreinte est non réversible.
- **CA5** portée limitée à `add_cloud` — mesuré : `_write_transaction_journal` n'a qu'un seul
  appelant (`routes.py:172`), et `add_local` (`local.py:127-156`) ne touche ni `routes.json` ni
  `vault.json`.
- **CA6** suite complète verte (hors l'échec environnemental pré-existant de `tests/test_proc.py`,
  documenté et traité hors périmètre) ; couverture ≥ 85 %.

## 6. Extension signalée, hors périmètre

`import_setup` (`portability.py:266-275`) écrit **plusieurs** `SETUP_FILES` sans journal : un
crash au milieu laisse un setup partiellement importé. Défaut de la **même famille**, mais hors
#306 — signalé, non traité ici.

## 7. Preuve mesurée

**Le test rouge, sur un vrai SIGKILL.** Avant correctif, après un crash entre le commit et
l'unlink, `RouteStore(home).list()` renvoyait `[]` — la transaction commitée était annulée.
Après correctif, la route survit, le secret d'origine reste lisible, le journal disparaît.

**Les deux tests hérités ont bien rougi**, exactement comme la revue d'architecture l'avait
prédit, et pour les raisons prédites :
- `test_sigkill_apres_routes_replace_est_recupere_avant_precheck_add` →
  `RouteError: route 'orpheline' existe déjà` (la route commitée survit désormais) ;
- `test_export_recupere_le_wal_avant_de_lire_routes` → `routes.json` est maintenant **dans** le
  bundle.

Ils sont réécrits **sémantiquement**, pas neutralisés. Point de méthode important : leur détecteur
d'origine disparaît avec le correctif. Avant, « la route a disparu » prouvait que la récupération
avait tourné ; après, la présence de la route serait vraie **même sans récupération**, puisqu'elle
est déjà sur disque. Le seul détecteur d'ordre qui survit est donc **la disparition du journal**,
qui ne peut venir que de la récupération — c'est lui qui est asserté.

**Mutations vérifiées** : forcer « commit toujours appliqué » → les tests de rollback légitime
rougissent (`test_alias_hardlink_du_coffre_est_restaure_avant_put`,
`test_recovery_ne_suit_jamais_un_symlink_vault_externe`, G6) ; remplacer la conjonction par une
disjonction → **G6** rougit.

Note sur M1 : elle mute **vers** le comportement voulu, donc G1 (qui exige la survie) ne peut pas
la détecter — ce sont les tests qui exigent le **maintien** du rollback qui la détectent. Un jeu
de tests uniquement « positif » aurait laissé passer cette mutation.

**Écart trouvé et corrigé pendant l'application** : la première version levait `KeyError` sur une
section `cible` partielle. Fail-closed ne veut pas dire *planter* : cela aurait fait échouer
`RouteStore(home)` à **chaque ouverture** sur un journal abîmé, ce qui est plus grave que la
restauration qu'on cherche à éviter. Une cible malformée renvoie donc `False` — donc rollback.
