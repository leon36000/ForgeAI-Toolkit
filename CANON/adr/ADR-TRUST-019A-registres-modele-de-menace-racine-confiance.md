# ADR TRUST-019A — Modèle de menace et racine de confiance des registres

- **Statut** : `PROPOSED` — en attente d'approbation explicite de Nathan (critère d'acceptation
  obligatoire de `ISSUES/TRUST-019A.md` : « Nathan approuve avant TRUST-019B/REG-029B »).
- **Package** : `TRUST-019A` (`DESIGN_FIRST` — aucune implémentation dans cette branche).
- **Finding source** : `FAI-U-019` / `FND-SEC-TAMPER-1` (`ACCEPTED_EVIDENCE`, MEDIUM, confirmé
  LIVE sur `main` actuel par analyse de code statique + reproduction empirique ci-dessous).
- **Auteurs** : COPILOT (analyse), revue aveugle scellée (recommandation), Nathan (décision).

## 1. Contexte

Le Toolkit tient deux mécanismes d'intégrité par empreinte SHA-256, tous deux **non gardés par
un secret** :

- **Registre append-only** (`src/forgeai/core/registre.py`, utilisé par `scripts/registre.py`,
  `Registres/mission.jsonl` et tous les `Registres/PATCH-<ID>.jsonl`) : chaque entrée porte
  `hash = sha256(entrée sans son champ hash)` et `prev_hash = hash de l'entrée précédente`
  (genèse = 64 zéros). `verify()` (lignes 78-88) rejoue la chaîne et compare chaque hash à sa
  valeur recalculée.
- **Catalogue** (`src/forgeai/catalogue/loader.py:verify_catalogue`, lignes 23-31) : le hash
  attendu est lu depuis un fichier `.sha256` **co-localisé** (même répertoire) que le catalogue
  qu'il est censé protéger.

Ces deux mécanismes sont **corrects pour leur objectif documenté** (détecter une altération
*accidentelle* — corruption disque, erreur de synchronisation, ligne tronquée) mais ne
documentent nulle part leurs limites contre un attaquant qui peut **écrire** sur le système de
fichiers hôte — ce que `FAI-U-019` désigne par « tamper-evident mais non tamper-proof ».
L'objectif de cette ADR (`ISSUES/TRUST-019A.md`) est de trancher, avant tout code, **quels
attaquants sont couverts, où vit la racine de confiance et quelles opérations exigent T3**.

## 2. Reproduction empirique (preuve rouge, chemin réel)

### 2.1 Registre — réécriture intégrale cohérente non détectée

```text
AVANT falsification :
  {'action': 'deploy', 'approved_by': 'nathan', 'target': 'prod'}
  {'action': 'delete_backup', 'approved_by': 'nathan', 'target': 'prod-2026-06'}
verify avant : None   (intègre)

[attaquant : accès écriture FS, PAS la clé — il n'y en a aucune. Réécrit le fichier ENTIER
 depuis la genèse avec un payload falsifié, en recalculant hash/prev_hash correctement.]

APRÈS falsification (ré-écriture intégrale, chaîne recalculée cohérente) :
  {'action': 'deploy', 'approved_by': 'nathan', 'target': 'prod'}
  {'action': 'delete_backup', 'approved_by': 'ATTAQUANT-FORGÉ', 'target': 'prod-2026-06'}
verify après : None   <-- AUCUNE DÉTECTION
```
Reproduit avec `scripts/registre.py` réel (`registre.append`/`registre.verify`), aucun mock.
`tests/test_registre.py` ne couvre QUE l'altération *partielle* (une entrée modifiée sans
recalcul en aval, lignes 25-39/79-91) — aucun test n'exerce une réécriture totale cohérente ;
c'est exactement l'angle mort que `FAI-U-019` documente.

### 2.2 Catalogue — `.sha256` co-localisé réécrit avec le fichier qu'il protège

```text
AVANT falsification, digest vérifié : ea8aded3...
[attaquant : accès écriture FS. Réécrit catalogue.json ET son catalogue.sha256 co-localisé.]
APRÈS falsification (catalogue.json ET .sha256 co-localisé réécrits) :
 verify_catalogue : 7cb5db27...   <-- passe, AUCUNE DÉTECTION
```
Reproduit avec `forgeai.catalogue.loader.verify_catalogue` réel.

### 2.3 Le gate CI `registres` ne détecte pas non plus une réécriture cohérente

`.github/workflows/gates.yml:21-26` — le job `registres` (vérification obligatoire, requis par
la protection de branche `main`) exécute uniquement `python3 scripts/registre.py verify
Registres/*.jsonl`. Comme démontré en §2.1, cette commande **retourne succès** sur une chaîne
entièrement réécrite de façon cohérente. Le gate protège contre un tamper *incompétent*
(édition partielle sans recalcul), pas contre un attaquant qui recalcule correctement — ce
qui donne un **faux sentiment de sécurité** au reviewer humain qui voit `registres ✓` sur une PR.

## 3. Modèle de menace

| Attaquant | Couvert par le mécanisme actuel (SHA-256 nu) ? |
|---|---|
| Corruption accidentelle (disque, troncature, erreur de synchronisation) | **OUI** — c'est la garantie *tamper-evident* réelle et suffisante de ce mécanisme. |
| Altération partielle par un opérateur distrait ou un outil tiers qui édite une ligne sans recalculer la chaîne | **OUI** — détecté par `verify()` (§2.1 avant falsification). |
| Attaquant avec accès **lecture seule** au registre (ex. un autre service, un compte non-privilégié qui peut lire mais pas écrire `Registres/`) | **OUI** — rien à falsifier sans écriture. |
| Attaquant avec accès **écriture** au fichier registre local (compromission de l'hôte, du compte CI, ou d'un processus tournant sous le même UID) | **NON** — §2.1/§2.2 le prouvent : il recalcule la chaîne, aucune détection locale possible, car **il n'existe aucun secret** que cet attaquant ne possède pas déjà. |
| Attaquant qui **supprime la fin** de la chaîne (rollback à un état antérieur légitime) | **NON** localement — une chaîne tronquée à `seq N` reste parfaitement valide pour `verify()` (voir `test_verify_detecte_une_entree_supprimee`, qui ne teste que la suppression de la **genèse**, pas la troncature de la **fin** — un rollback réaliste). |
| Attaquant qui force-push/réécrit l'historique **git** sur `origin/main` | **Partiellement** — la protection de branche actuelle du dépôt (vérifiée via l'API GitHub) a `allow_force_pushes: false` et `allow_deletions: false`, **mais `enforce_admins: false`** : un compte avec droits admin sur le dépôt **contourne ces protections**. `required_signatures: false` : rien n'empêche l'usurpation d'identité d'auteur de commit au niveau Git lui-même (au-delà du contrôle d'accès GitHub). |

**Limite root/local explicite (critère d'acceptation)** : **aucun mécanisme purement local ne
peut être rendu tamper-proof contre un attaquant qui a déjà un accès en écriture égal ou
supérieur à celui du processus qui écrit le registre** — c'est un fait cryptographique/systèmes,
pas une lacune corrigible par un meilleur hash. Une garantie *authenticated* (HMAC/signature)
élève la barre uniquement si la clé n'est **pas accessible** à cet attaquant (ex. UID différent,
détenteur humain, machine séparée). Une garantie *anti-rollback* exige en plus une **ancre
externe** au système de fichiers local (l'attaquant ne peut pas altérer ce qu'il ne peut pas
atteindre) — le hash-chain seul, même signé, ne l'offre jamais intrinsèquement : un attaquant
qui détient la clé peut toujours signer une *nouvelle* chaîne plus courte de façon parfaitement
valide.

## 4. Alternatives considérées

### 4.1 Statu quo (SHA-256 nu, non gardé) — **REJETÉE au-delà du tier « accidentel »**

Suffisant uniquement pour la détection d'altération accidentelle/partielle (§3). Ne satisfait
aucun des trois niveaux de garantie demandés par `ISSUES/TRUST-019A.md` (tamper-evident ✓,
authenticated ✗, anti-rollback ✗) au-delà de ce premier tier. Conservé comme **plancher**, pas
comme solution complète.

### 4.2 HMAC-SHA256 à clé locale (Tier « authenticated », attaquant à privilège moindre)

Remplacer `hash = sha256(entrée)` par `hash = HMAC-SHA256(clé_locale, entrée)`. **Réutilise la
construction déjà revue et approuvée** dans `src/forgeai/models/vault.py` (HMAC-SHA256 en
primitive stdlib pure, `hmac.compare_digest` pour la vérification en temps constant — aucune
nouvelle primitive crypto, zéro nouvelle dépendance). La clé vivrait dans un fichier dédié
(ex. `~/.forgeai/registre.key`, généré une fois, permission `0600`, jamais committé, jamais
loggé — seule son empreinte via `vault.fingerprint()` apparaîtrait dans les preuves).

- **Ce que ça défend** : un attaquant qui peut écrire `Registres/*.jsonl` mais **pas** lire
  `~/.forgeai/registre.key` (UID différent, processus/service tiers non-privilégié, compromission
  d'un composant qui n'a pas accès au répertoire de config utilisateur). C'est une amélioration
  réelle par rapport au statu quo pour ce cas précis.
- **Ce que ça NE défend PAS** : un attaquant root ou sous le **même UID** que celui qui écrit
  normalement le registre — il lit la clé au même titre que le registre. **Doit être documenté
  honnêtement comme tel dans le code/commentaire, pas présenté comme « sécurisé » sans
  qualification** (piège que `FAI-U-019` reproche déjà à la formulation actuelle).
- **Rotation** : chaque entrée porterait un `key_id` (empreinte publique de la clé, jamais la
  clé), permettant plusieurs clés valides dans le temps ; une nouvelle entrée `type=key_rotation`
  documenterait la transition (ancien `key_id` référencé, jamais la clé elle-même).

### 4.3 Ancrage externe périodique via l'historique Git/GitHub — **RETENUE (Tier « anti-rollback »)**

**Constat central de cette ADR** : une ancre externe **existe déjà implicitement** — tous les
`Registres/*.jsonl` sont des fichiers **suivis par git** et **poussés vers `origin` (GitHub)** à
chaque PR mergée (vérifié : `git log -- Registres/mission.jsonl` montre l'historique complet
depuis plusieurs PR). Un attaquant qui réécrit `Registres/mission.jsonl` **localement** ne peut
pas faire disparaître les versions déjà mergées dans l'historique de `main` sur GitHub sans
soit (a) passer par le même processus de PR + revues + gates que tout le monde, soit (b) forcer
un rewrite d'historique sur `main`, ce que la protection de branche actuelle bloque **sauf pour
un compte admin** (`enforce_admins: false` — lacune concrète identifiée en §3, à corriger
**hors code**, par configuration du dépôt).

- **Ce que ça défend** : rollback ou réécriture totale d'une chaîne **déjà mergée dans
  `main`** — l'historique Git/GitHub sert d'ancre hors de portée d'un attaquant qui ne contrôle
  que le poste de travail/CI local d'une PR en cours.
- **Ce que ça NE défend PAS** : falsification d'une entrée **avant** son premier merge (un
  attaquant qui contrôle la machine qui *produit* la preuve peut fabriquer n'importe quel
  contenu avant qu'il n'entre dans l'historique protégé — l'ancre ne protège que ce qui est
  déjà ancré, jamais la genèse de la preuve elle-même) ; ni un compte admin GitHub compromis
  tant que `enforce_admins=false`.
- **Coût** : **zéro nouvelle dépendance** — réutilise l'infrastructure Git déjà en place. Seul
  changement requis (hors code, configuration du dépôt) : activer `enforce_admins: true` et
  envisager `required_signatures: true` sur `main`.

### 4.4 immudb (mentionné explicitement par l'audit comme « le vrai coffre ») — **REJETÉE en défaut, retenue en option avancée**

L'audit source (`FAI-U-019`) nomme lui-même immudb comme la solution industrielle
tamper-proof correcte (serveur de ledger dédié, preuves cryptographiques de non-altération type
Merkle). **Rejetée comme mécanisme par défaut** : viole l'invariant de portabilité
`dependencies=[]` (stdlib pur) du profil Minimal — nécessite un service serveur additionnel à
déployer/opérer, hors scope d'un outil dont l'installation doit rester `pip install` seul.
**Retenue comme option documentée pour déploiements avancés** qui acceptent cette dépendance
(ex. un opérateur qui exploite déjà une infrastructure de journalisation centralisée) — non
mandataire, jamais requise pour le profil Minimal.

### 4.5 Signature asymétrique ed25519 détenue par Nathan (Tier « T3 »)

Pour les opérations qui exigent explicitement l'autorité T3 (AGENTS.md : paiements, secrets de
production, suppressions définitives, engagements externes), une entrée de registre
`type=governance` documentant une décision T3 **devrait porter une signature ed25519** (le
Toolkit utilise déjà cette primitive pour les clés SSH multi-nœuds — cohérence d'écosystème,
zéro nouvelle primitive) dont la clé privée n'existe **que** chez Nathan (jamais sur une machine
partagée par les agents). La clé publique correspondante serait committée dans `CANON/` et
vérifiable offline par quiconque, sans dépendre d'aucune ancre réseau. Ceci comble le trou du
§4.3 (« l'ancre ne protège pas la genèse de la preuve ») **spécifiquement** pour les décisions
qui exigent déjà, par la règle T3, l'implication humaine — la signature devient la preuve
cryptographique que cette implication a réellement eu lieu, et non une simple ligne
auto-déclarée par un agent.

## 5. Racine de confiance — où vit-elle, par tier

| Tier | Racine de confiance | Détient la clé/le secret | Protège contre |
|---|---|---|---|
| 0 — statu quo | Aucune (hash nu) | Personne (pas de secret) | Corruption accidentelle uniquement |
| 1 — HMAC local | Fichier `~/.forgeai/registre.key` (`0600`) | Le compte/processus qui écrit normalement le registre | Attaquant à UID/privilège **moindre** que l'écrivain légitime |
| 2 — ancrage Git/GitHub | Historique `main` protégé (`allow_force_pushes: false`, `allow_deletions: false`, **`enforce_admins` à activer**) | GitHub (infrastructure déjà en place, aucune nouvelle clé) | Rollback/réécriture d'une chaîne **déjà mergée** |
| 3 — signature T3 | Clé privée ed25519 **exclusivement chez Nathan**, jamais sur une machine d'agent | Nathan seul | Fabrication de la genèse d'une décision T3 par un agent (aucun tier inférieur ne le peut) |

Ces tiers sont **cumulatifs, pas exclusifs** : Tier 1 protège la fenêtre avant le premier merge,
Tier 2 protège après merge, Tier 3 authentifie spécifiquement les décisions T3 à la source.

## 6. Rotation, récupération, sauvegarde, offline (critère d'acceptation)

| Aspect | Tier 1 (HMAC) | Tier 2 (ancrage Git) | Tier 3 (signature T3) |
|---|---|---|---|
| **Rotation** | Nouvelle clé + entrée `type=key_rotation` référençant l'empreinte (jamais la clé) de l'ancienne ; anciennes entrées restent vérifiables sous leur `key_id` d'origine. | N/A (pas de clé secrète — la protection de branche est reconfigurée côté GitHub, sans impact sur l'historique existant). | Rotation de la clé ed25519 de Nathan = ré-signature explicite requise ; ancienne clé publique conservée dans `CANON/` pour vérifier les signatures historiques. |
| **Récupération** | Perte de la clé ⇒ le registre redevient Tier 0 à partir de ce point (documenté explicitement, jamais silencieux) ; les entrées passées restent vérifiables si un tiers a conservé l'ancienne clé/empreinte. | Perte d'accès dépôt ⇒ aucun impact sur l'intégrité déjà ancrée (l'historique Git local d'un clone tiers suffit à re-vérifier). | Perte de la clé privée de Nathan = incident T3 à documenter explicitement (registre `type=governance`, `event=t3_key_incident`) ; aucune décision T3 rétroactive ne peut être re-signée après coup — seule une nouvelle politique peut être adoptée en avant. |
| **Sauvegarde** | Clé et registre sauvegardés sur des **supports distincts** (sinon la sauvegarde reproduit exactement la faiblesse du §2 : les deux compromis ensemble = aucune protection). | Le clone Git de n'importe quel contributeur constitue déjà une sauvegarde indépendante hors du contrôle d'un attaquant local. | Clé privée de Nathan : sauvegarde hors-ligne exclusivement détenue par Nathan (HSM, coffre physique, ou équivalent — hors scope du Toolkit lui-même, décision humaine T3). |
| **Vérification hors-ligne** | Oui — `verify()` reste 100% local, aucune dépendance réseau (préserve l'invariant portabilité). | Oui pour un historique déjà cloné (`git log`/`git show` sur une copie locale suffit, pas besoin d'accès réseau à GitHub à l'instant de la vérification) ; nécessite un clone antérieur à la falsification suspectée. | Oui — vérification de signature ed25519 avec la clé publique committée, entièrement offline. |

## 7. Quelles opérations exigent T3 (Tier 3 — signature Nathan)

Conformément à AGENTS.md (« T3 = Nathan : paiements, secrets de production, suppressions
définitives, engagements externes. Le consensus recommande ; l'humain lève. ») :

- **Exigent Tier 3 (signature ed25519 Nathan obligatoire)** : toute entrée `type=governance`
  qui documente une approbation finale de package `DESIGN_FIRST`/ADR (ex. le futur
  `nathan_approval` de cette ADR elle-même et de `SECRET-020A`), toute décision de secrets de
  production, toute suppression définitive de données/registre, tout engagement externe.
- **Tier 2 suffit (ancrage Git implicite, aucune signature dédiée)** : les entrées de routine
  (verdicts de revue aveugle scellée, avancement de story BMAD, preuves de gates) — déjà
  protégées par le fait qu'elles ne deviennent définitives qu'après merge sur `main` protégé.
- **Tier 1 suffit (aucune signature, HMAC local seulement)** : les registres locaux de travail
  avant tout commit (ex. brouillons de session non encore poussés) — valeur purement
  opérationnelle, aucune conséquence T3.

## 8. Décision (recommandation soumise à Nathan)

1. **Adopter la distinction en 3 tiers ci-dessus** comme modèle de menace officiel des
   registres — documenter explicitement, partout où `registre.py`/`verify_catalogue` sont
   utilisés, qu'ils offrent une garantie **tamper-evident** (Tier 0) et non tamper-proof par
   défaut, avec un chemin d'amélioration Tier 1/2/3 selon la sensibilité de l'entrée.
2. **Corriger immédiatement (hors code, configuration dépôt, aucune implémentation requise
   dans le package dépendant)** : activer `enforce_admins: true` sur la protection de branche
   `main` — comble la lacune concrète identifiée en §3 sans écrire une ligne de code.
3. **Déléguer à un package d'implémentation séparé (`TRUST-019B`/`REG-029B`)** : l'ajout du
   HMAC-SHA256 à clé locale (Tier 1, §4.2) avec gestion d'epoch/rotation, et la signature
   ed25519 T3 (Tier 3, §4.5) pour les entrées `type=governance` à approbation Nathan.
4. **immudb (§4.4) reste une option documentée, jamais mandataire** pour le profil Minimal.

## 9. Contrat pour le package d'implémentation dépendant (`TRUST-019B`/`REG-029B`)

- Ajouter un champ `key_id` optionnel à chaque entrée du registre ; `verify()` doit rester
  rétro-compatible avec les entrées Tier 0 existantes (sans `key_id` ⇒ vérification SHA-256 nue
  comme aujourd'hui) — **aucune migration destructive de l'historique existant**.
- Nouvelle clé locale HMAC : générée par une commande explicite (`registre.py init-key`),
  jamais automatique/implicite ; permission `0600` dès la création (motif `os.open(mode=0o600)`
  déjà validé dans `models/vault.py`, pas de fenêtre de course write-puis-chmod).
- Signature ed25519 T3 : clé publique committée dans `CANON/keys/nathan-t3.pub` (nom indicatif) ;
  vérification offline sans dépendance réseau.
- Test rouge obligatoire avant le correctif : reproduire la réécriture totale (§2.1/§2.2)
  contre le NOUVEAU mécanisme et prouver qu'elle est désormais détectée (ou correctement
  qualifiée comme hors de portée du tier concerné, jamais silencieusement acceptée).
- `python3 scripts/no_stub_scan.py --all` + gates complets + revue aveugle scellée 3/3
  + approbation Nathan avant merge (même gate que cette ADR).
- Recommandation de configuration dépôt (§8.2) à appliquer indépendamment du code, dès que
  Nathan approuve cette ADR — ne nécessite aucun package séparé.

## 10. Preuves à l'appui de cette ADR

- Code source réel cité : `src/forgeai/core/registre.py` (lignes 24-27, 78-88),
  `src/forgeai/catalogue/loader.py` (lignes 23-31), `src/forgeai/models/vault.py` (construction
  HMAC-SHA256, lignes 45-83), `.github/workflows/gates.yml` (lignes 21-26, job `registres`).
  Ces références de lignes ont été revérifiées ligne par ligne contre le fichier réel au moment
  de la rédaction de cette note (round 2 de revue), postérieurement au diff soumis aux
  reviewers — d'où leur non-vérifiabilité depuis le diff seul, objection mineure et non
  bloquante du round 2 (`reviews/TRUST-019A/civ2/DeepSeek-V4-Pro.verdict.json`).
- L'affirmation « construction HMAC-SHA256 déjà revue et approuvée » (vault.py) renvoie à un
  fait d'historique Git vérifiable indépendamment de ce diff : commit `36ec4f0`
  (« feat(models): B-09 routes modèle cloud — provenance + coffre chiffré + test réel (DM-5) »)
  introduit `vault.py`, puis commit `7a2406b`
  (« chore(gov): revue aveugle 3 vendors du sous-système models/ + 2 durcissements ») et
  `6b4e265` (« fix(models): BC-models — corrige les 6 defauts de la revue scellee »)
  documentent la revue aveugle scellée et sa correction — cf. `reviews/BC-models-civ/`,
  `reviews/B-12-civ/`. Vérifiable par `git log --oneline -- src/forgeai/models/vault.py`.
- Reproduction empirique réelle (§2.1, §2.2) exécutée avec les modules réels du dépôt
  (`scripts/registre.py`, `forgeai.catalogue.loader`), aucun mock.
- Protection de branche `main` vérifiée via l'API GitHub (`allow_force_pushes: false`,
  `allow_deletions: false`, `enforce_admins: false`, `required_signatures: false`).
- Historique Git réel de `Registres/mission.jsonl` confirmant le suivi normal par git
  (`git log -- Registres/mission.jsonl`).
- Finding source : `AUDIT-REFERENCE/ORIGINAL-ISSUES/FAI-U-019.md`,
  `AUDIT-REFERENCE/04/SECURITY-FINDINGS.csv` (`FND-SEC-TAMPER-1`),
  `AUDIT-REFERENCE/08/ISSUE-REGISTER.csv`, `AUDIT-REFERENCE/04/THREAT-MODEL.md`.
- Tests existants examinés : `tests/test_registre.py` (couvre l'altération partielle, pas la
  réécriture totale — confirmé lu intégralement).
