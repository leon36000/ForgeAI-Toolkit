# ADR SECRET-020A — Modèle de permission et unseal OpenBao

- **Statut** : `PROPOSED` — en attente d'approbation explicite de Nathan (critère d'acceptation
  obligatoire de `ISSUES/SECRET-020A.md`).
- **Package** : `SECRET-020A` (`DESIGN_FIRST` — aucune implémentation dans cette branche).
- **Finding source** : `FAI-U-020` (`ACCEPTED_EVIDENCE`, MEDIUM, confirmé LIVE sur `main` actuel).
- **Auteurs** : COPILOT (analyse), revue aveugle scellée 3/3 (recommandation), Nathan (décision).

## 1. Contexte

`src/forgeai/deploy/openbao_flow.py` gère le stockage des clés d'amorçage OpenBao pour deux
backends de déploiement :

- **Compose (Docker)** — `FileKeyStore` écrit deux fichiers sur le système de fichiers de
  l'**hôte** (bind-mount) : `root_token` (0600, isolé, jamais monté au sidecar unsealer) et
  `unseal_key` (**0644**, monté en lecture seule dans `openbao-keys/`, lu par le service
  `openbao-unsealer`).
- **K3s (Kubernetes)** — `KubectlKeyStore` écrit les deux valeurs dans un objet `Secret`
  Kubernetes ; seul l'item `unseal_key` est monté (lecture seule) dans le conteneur sidecar
  du Pod ; le contrôle d'accès relève de la RBAC/etcd du cluster, pas de permissions POSIX
  sur un fichier hôte.

Le finding `FAI-U-020` (vague V4, `ACCEPTED_EVIDENCE`) documente que `unseal_key` est
`0o644` — **lisible par tout compte local du système hôte**, pas seulement par le conteneur
unsealer. La cause racine documentée dans le code (`deploy/openbao_flow.py:53`) est correcte :
le conteneur `openbao-unsealer` tourne sous l'UID **non-root fixe de l'image officielle**
(utilisateur `openbao`, `UID:GID = 1000:1000` sur l'image Alpine `openbao/openbao:2.6.0`,
créé par `addgroup openbao && adduser -S -G openbao openbao` dans le Dockerfile officiel),
tandis que l'opérateur qui écrit le fichier depuis l'hôte a un UID différent. Un bind-mount
ne remappe pas les UID : un fichier `0600` possédé par l'opérateur serait illisible par le
conteneur (prouvé e2e S6 : re-unseal silencieusement muet après redémarrage).

## 2. Modèle de menace

| Backend | Surface d'exposition du fichier `unseal_key` à `0644` |
|---|---|
| Compose | **Tout processus/compte du système hôte** (autres services, cron, autres utilisateurs Unix ayant un accès shell/SSH à la machine) — surface large. |
| K3s | Uniquement les conteneurs du **même Pod** qui montent explicitement le volume `Secret` — le `Secret` k8s lui-même est protégé par la RBAC du cluster (`kubectl get secret` nécessite une permission API), l'exposition filesystem est confinée au namespace de montage du Pod. Surface bien plus étroite. |

Le document du code (`prepare_key_store`) argumente à juste titre que « la clé d'unseal est
co-localisée avec le storage scellé sur le même hôte (même frontière de confiance) » — un
attaquant qui lit déjà le disque hôte a, de toute façon, accès aux données scellées elles-mêmes.
**Cet argument reste valide contre un attaquant qui a déjà compromis root/disque**, mais ne
couvre PAS le cas d'un **compte non-privilégié tiers** sur un hôte partagé (ex. un autre
service applicatif tournant sous un UID différent, sans lien avec ForgeAI, sur le même
serveur) — c'est précisément ce cas que `0644` expose et qu'un modèle par groupe éliminerait.

## 3. Analyse de la raison actuelle (0644) — critère d'acceptation #1

La raison documentée (le conteneur non-root ne peut pas lire un `0600` possédé par
l'opérateur) est **réelle et vérifiée** (commentaire code + preuve e2e S6 citée). Le choix de
`0644` n'est donc pas arbitraire — c'est la solution la plus simple pour lever ce blocage.
Mais **ce n'est pas la solution qui réduit le plus la surface** : `0644` ouvre la lecture à
*tout le monde* alors que seul un UID/GID précis est requis.

## 4. Alternatives considérées

### 4.1 Permission par groupe (0640 + GID de l'image openbao) — **RETENUE (recommandation)**

Puisque l'UID/GID de l'image officielle (`1000:1000`, utilisateur `openbao`) est **connu et
stable** (Dockerfile officiel, vérifié auprès du dépôt source `openbao/openbao`), le design
recommandé pour le backend Compose est :

1. `chown` du fichier `unseal_key` (et du répertoire `keys_dir`) au **GID 1000** (groupe de
   l'utilisateur `openbao` dans l'image), en conservant l'opérateur comme propriétaire (UID).
2. Mode `0640` sur le fichier (`rw-r-----`) au lieu de `0644` (`rw-r--r--`) : lecture réservée
   au propriétaire ET au groupe `1000`, plus aucune lecture pour « autrui ».
3. Mode `0750` sur `keys_dir` (au lieu de `0711`) : traversée+listage réservés au propriétaire
   et au groupe `1000`, sans bit de lecture pour autrui (le sidecar doit toujours pouvoir
   `stat`/ouvrir le fichier par son nom exact, ce que `0750` permet pour le groupe).
4. **Garde de compatibilité obligatoire** : le GID de l'image DOIT être vérifié à l'exécution
   (ex. `docker run --rm <image> id -g`) avant d'appliquer le chown, et non supposé figé sans
   preuve — une mise à jour future de l'image amont pourrait changer cet UID/GID sans préavis.
   Le comportement de repli (`ALREADY_FIXED`/dégradation) si le GID diffère de l'attendu doit
   être : revenir à `0644` documenté (comportement actuel) plutôt qu'un échec silencieux de
   démarrage — **jamais une régression fonctionnelle non détectée**.

Compromis accepté : cette solution réduit la surface au groupe `1000` de l'hôte plutôt qu'à
« tout le monde », mais n'atteint pas un isolement parfait si un autre service du même hôte
utilise également le GID `1000` (collision de GID possible sur un hôte multi-services non
dédié). C'est une réduction de surface mesurable et sans coût fonctionnel, pas un isolement
absolu — documenté explicitement plutôt que présenté comme une solution parfaite.

### 4.2 `user:` compose matchant l'UID opérateur — REJETÉE

Faire tourner `openbao-unsealer` avec `user: "${UID}:${GID}"` (UID de l'opérateur) permettrait
un `0600` classique. **Rejetée** : l'image officielle attend d'écrire ses propres fichiers
internes (cache TLS, etc.) sous l'utilisateur `openbao` intégré ; forcer un UID arbitraire non
prévu par l'image casserait potentiellement des permissions internes à l'image (non testé,
risque non borné, changerait le comportement du conteneur au-delà du strict nécessaire pour ce
correctif). Rejetée par prudence — pas d'évidence contraire disponible sans test e2e dédié,
hors périmètre `DESIGN_FIRST`.

### 4.3 User namespace remapping Docker (`--userns-remap`) — REJETÉE

Remapperait TOUS les conteneurs de l'hôte, pas seulement openbao-unsealer — changement global
d'infrastructure disproportionné pour corriger un seul fichier, et non portable sur toutes les
configurations Docker cibles du produit (contrainte de portabilité multi-hôte du projet).
Rejetée.

### 4.4 Conserver 0644 tel quel (statu quo) — REJETÉE comme recommandation par défaut

Rejetée comme choix par défaut car elle ne satisfait pas le critère d'acceptation « le design
réduit la lecture au principal requis » : `0644` reste strictement plus permissif que
nécessaire quand une alternative par groupe est disponible sans coût significatif. Conservée
uniquement comme **repli documenté** si la vérification du GID (4.1 point 4) échoue à
l'exécution.

### 4.5 K3s (Secret + fsGroup) — déjà conforme, amélioration mineure optionnelle

Le backend K3s n'est PAS concerné par le défaut `FAI-U-020` (qui cible spécifiquement
`deploy/openbao_flow.py:53`, backend Compose). Amélioration optionnelle non bloquante :
définir explicitement `defaultMode: 0440` sur le volume `Secret` `openbao-keys` dans le
manifeste Pod (au lieu du défaut implicite `0644` de Kubernetes pour les volumes `Secret`),
pour appliquer la même discipline « lecture minimale nécessaire » au sein du Pod. Recommandé
en amélioration mineure, non requis pour satisfaire `FAI-U-020` qui ne cible pas ce backend.

## 5. Séparation root token / unseal key — critère d'acceptation #2

**Déjà conforme, aucun changement requis.** Vérifié dans le code actuel :
`root_token` est écrit dans `root_path`, un fichier **séparé**, **jamais monté** au conteneur
`openbao-unsealer` (ni en Compose — absent de son bind-mount `./openbao-keys:/keys:ro` — ni en
K3s — le sidecar ne monte que l'item `unseal_key` du Secret, jamais `root_token`). Ce critère
est satisfait par le design existant et doit être **préservé sans régression** par toute
implémentation future de cet ADR.

## 6. Défaut additionnel découvert pendant l'analyse — fenêtre de course avant chmod

En analysant le point « récupération avant chmod » de l'objectif de cette ADR, un **second
défaut réel, distinct de `FAI-U-020`**, a été identifié et reproduit :

`_write_file()` (`deploy/openbao_flow.py`) utilise le motif **non atomique** :
```python
path.write_text(content, encoding="utf-8")   # créé avec le umask du processus
os.chmod(path, mode)                          # durci APRÈS coup
```

**Preuve de reproduction** (environnement de cette session, umask hérité `0o002`) :
```
$ python3 -c "
from pathlib import Path
p = Path('/tmp/test_race_perm.txt')
p.write_text('secret-content\n', encoding='utf-8')
print(oct(p.stat().st_mode & 0o777))"
0o664
```
Entre `write_text()` et `chmod()`, le fichier existe brièvement avec les permissions dérivées
du **umask du processus** (`0o664` mesuré ici, potentiellement `0o666` si umask=`000`,
observé sur certaines images conteneur/services systemd) — **plus permissif** que la cible
finale. Ceci affecte `root_token` (cible `0600`) et le jeton applicatif de `FileSecretStore`
(cible `0600`), pas seulement `unseal_key` (dont la cible `0644` égale ou dépasse déjà le
umask par défaut — donc sans régression pratique pour ce fichier précis, mais la fenêtre de
course existe structurellement pour TOUT appelant de `_write_file`).

**Le codebase contient déjà le motif correct** ailleurs (`src/forgeai/models/vault.py`) :
```python
fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, "w", encoding="utf-8") as f:
    f.write(payload)
```
`os.open(..., mode)` applique le mode **atomiquement à la création** (le umask ne peut que
*retirer* des bits ; `0o600` n'ayant aucun bit groupe/autre à retirer, le résultat est garanti
`0o600` quel que soit le umask du processus) — aucune fenêtre de permissions plus larges que la
cible n'existe avec ce motif.

**Recommandation** : le package d'implémentation dépendant de cet ADR doit remplacer le motif
`write_text` + `chmod` de `_write_file()` par le motif `os.open(mode=...)` déjà éprouvé dans
`models/vault.py`, pour `root_token`, le jeton applicatif ET `unseal_key` (cohérence, même si
l'impact pratique sur `unseal_key` est nul compte tenu de sa cible déjà large).

## 7. Décision (recommandation soumise à Nathan)

1. Backend Compose : `unseal_key` passe de `0644` à `0640` + `chown` au GID vérifié à
   l'exécution de l'utilisateur `openbao` de l'image (§4.1), avec repli documenté vers `0644`
   si la vérification du GID échoue. `keys_dir` passe de `0711` à `0750` dans les mêmes
   conditions.
2. `_write_file()` doit utiliser le motif atomique `os.open(mode=...)` (§6) pour éliminer la
   fenêtre de course, aligné sur le motif déjà utilisé dans `models/vault.py`.
3. Aucun changement à la séparation `root_token`/`unseal_key` (§5) — déjà conforme.
4. Backend K3s : amélioration optionnelle non bloquante `defaultMode: 0440` (§4.5).
5. Le package d'implémentation doit inclure un test de non-régression reproduisant EXACTEMENT
   la preuve de `FAI-U-020` (`04/SYSTEM/SYSTEM-SECURITY.csv`) et confirmant `0640`/GID correct
   après le correctif, plus un test dédié pour la fenêtre de course (§6) qui échoue avant et
   passe après le motif atomique.
6. Rollback : revert du commit d'implémentation (aucune migration de données destructive —
   les clés existantes restent lisibles, seul le mode/propriétaire change).

## 8. Contrat pour le package d'implémentation dépendant

- **Ne pas** modifier `src/forgeai/**` dans la présente branche `docs/SECRET-020A-*`
  (`DESIGN_FIRST` — implémentation dans un package séparé, à créer/assigner après approbation
  de cet ADR).
- Le package d'implémentation doit :
  - vérifier le GID à l'exécution (jamais supposer `1000` sans vérification, cf. §4.1 point 4) ;
  - fournir le test rouge (permissions actuelles `0644`/`0711` + fenêtre de course) AVANT tout
    changement, puis le test vert après ;
  - ne régresser aucun invariant KEEP (registre crash-consistent, 0 `shell=True`, gitleaks=0,
    séparation root/unseal) ;
  - documenter le comportement de repli si le GID de l'image change.

## 9. Preuves à l'appui de cette ADR

- Code source lu intégralement : `src/forgeai/deploy/openbao_flow.py` (lignes 1-220),
  `src/forgeai/renderers/compose.py` (bloc `openbao-unsealer`), `src/forgeai/renderers/k3s.py`
  (bloc sidecar + volume Secret), `src/forgeai/models/vault.py` (motif atomique de référence).
- Finding source : `AUDIT-REFERENCE/ORIGINAL-ISSUES/FAI-U-020.md`.
- UID/GID de l'image officielle : vérifié par recherche du Dockerfile public
  `github.com/openbao/openbao/blob/main/Dockerfile` (utilisateur `openbao`, création via
  `addgroup`/`adduser -S`, UID/GID par défaut `1000:1000` sur base Alpine).
- Reproduction de la fenêtre de course avant `chmod` : script Python exécuté dans cette
  session (§6), résultat mesuré `0o664` (umask hérité `0o002`).
- Image de référence utilisée par le produit (vérifiée textuellement dans
  `src/forgeai/data/deploy-specs.json:81`) :
  `openbao/openbao:2.6.0@sha256:900bb64d0671cd1d82b693c56206f7263b582445f3a3bb6ba6e5213f524a6653`.
