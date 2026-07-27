# DATA-003 — Writer commun, atomique et sécurisé pour les secrets OpenBao

## Calibration

- Profil : `PROOF-Team`
- Risque : `T2`
- Branche : `security/DATA-003-secure-atomic-secret-writer`
- Base initiale : `2ed262e2c31a311134ff63c1336e50ddb23d0555`
- Base finale après synchronisation : `35b0ad6e54f31f33416a7baaa7aa51cbdfccd92f`
- Candidat fonctionnel revu : `fdf6a20f965fe48a1e2922491f2e479c801c8a1f`
- Issue : package externe, aucune issue GitHub à créer
- Claim Codex : tracé dans le ledger PROOF externe

## Cause racine vérifiée

Les writers de secrets utilisaient plusieurs chemins d’écriture distincts.
Certains créaient ou réécrivaient la cible avant d’imposer son mode final,
certains remplaçaient directement son contenu et les lectures acceptaient des
types de fichiers non réguliers. Cette dispersion laissait des fenêtres
write-then-chmod, des lectures déchirées et des comportements divergents entre
le bootstrap, le coffre et les stores OpenBao.

Les tests RED ont notamment démontré :

- un mode dépendant de l’umask pendant la création ;
- des lectures concurrentes pouvant observer un contenu partiel ;
- des courses entre régénération et republication du bootstrap ;
- des parents ou verrous remplaçables par symlink ;
- des répertoires de clés existants en `000`/`0500` restaurés en `0700`
  plutôt qu’au mode final exact `0711`.

## Invariants implémentés

Le module `forgeai.models.vault` fournit désormais les primitives communes :

- création et validation sans suivi de symlink de la chaîne de répertoires ;
- modes finaux exacts, indépendants de l’umask, établis par des descripteurs ;
- verrou régulier `0600` validé par inode et nombre de liens ;
- temporaire dans le même répertoire, créé directement avec le mode final ;
- écriture complète, `fsync` du fichier, `os.replace`, puis `fsync` du
  répertoire ;
- lecture bornée avec refus des symlinks et fichiers non réguliers ;
- republication atomique d’un secret existant sans mutation d’un inode partagé.

`bootstrap_secrets`, `Vault`, `FileSecretStore` et `FileKeyStore` réutilisent
ces primitives. Le bootstrap sérialise régénération et republication sous un
verrou commun. Les parents de secrets restent `0700`, les secrets privés
`0600`, et le key store OpenBao conserve exactement `0711`/`0644` lorsque
l’unsealer doit traverser le répertoire et lire sa clé.

## Sécurité et concurrence

- la cible finale ne peut pas être un symlink ;
- les parents, verrous et lectures échouent fermés sur symlink, FIFO ou inode
  remplacé ;
- un échec après `fsync` du temporaire mais avant `replace` conserve
  l’ancienne cible ;
- les lectures concurrentes ne voient que l’ancienne ou la nouvelle valeur ;
- 1 000 remplacements avec lecteurs concurrents passent sans contenu partiel ;
- les assertions, exceptions et journaux de test n’exposent pas la valeur des
  secrets.

La solution est explicitement POSIX : elle dépend de `O_NOFOLLOW`,
`O_DIRECTORY`, `fcntl` et des garanties de remplacement atomique dans un même
répertoire. Le fallback pathname de changement de mode reste limité aux
plateformes POSIX où le parent est contrôlé par l’opérateur.

## Boucles de revue

Sept tours de revue ont empêché un faux DONE. Les objections élevées ont été
reproduites en RED puis corrigées : course de symlink, mutation de hardlink,
messages d’assertion contenant un secret, republication concurrente,
répertoires/`.env` non sécurisés, umask restrictif, lectures et parents du
coffre, parents des stores OpenBao, puis restauration exacte de `0711`.

Après trois avancées successives de `origin/main` (sept, deux puis six commits),
toujours sans chevauchement avec DATA-003, les douze commits fonctionnels ont
été rebasés proprement. Chaque revue portant un ancien SHA a été invalidée et
toutes les preuves ont été rejouées.

Le pack final rebased porte les hashes :

- artefact : `0ee864238d6ac41421aaf755c353b9ed7d64496a576c96b891f94bc84cc88174` ;
- prompt : `d0ab88238730bba87670e186c0b28b7e3bccfa1ee6556202433a00371409b6ff`.

Trois revues OpenAI ont rendu `APPROVE` sans objection bloquante : deux
`gpt-5.6-sol` et une `gpt-5.6-terra`. Ces revues réutilisent des contextes,
proviennent d’un seul fournisseur et ne sont pas présentées comme une
validation multi-vendeurs. Le modèle `gpt-5.5` demandé n’était pas disponible.

## Preuves locales finales

- suite ciblée exacte : `74 passed` ;
- suite complète macOS : tous les tests passent sauf le flake préexistant
  `tests/test_immudb.py::test_record_puis_history_round_trip`, qui réinitialise
  la connexion de son faux serveur ; le même test isolé passe `4/4` ;
  couverture calculée `90,26 %` (seuil `85 %`) ;
- `forgeai/core/registre.py` : `98 %` (seuil `95 %`) ;
- no-stub : `264` fichiers, zéro violation ;
- catalogue : `1 577` entrées, zéro ambiguïté ;
- registres existants et revues scellées existantes : PASS ;
- Gitleaks `8.30.1` : zéro fuite sur la tête complète scannée ;
- gate PROOF : périmètre, secrets et stubs propres ;
- Ralph Wiggum gouvernée : complétion à l’itération `1/3`, registre à deux
  entrées et chaîne valide.

Les autres avertissements locaux concernent le nettoyage de répertoires
temporaires macOS après les tests concurrents et la dépréciation de `fork`
depuis un processus multithreadé. Le gate Linux GitHub doit confirmer la suite
complète avant toute fusion.

## Rollback

Dans un worktree détaché éphémère, les douze commits ont été inversés avec
`git revert --no-commit`, du plus récent au plus ancien. L’index et le worktree
obtenus sont identiques à la base finale `35b0ad6…`. Les 29 tests ciblés de la
base passent, puis le worktree de preuve est supprimé.

## Gates externes

Les contrôles locaux autorisent la publication, pas la fusion. SonarCloud,
GitGuardian/Gitleaks GitHub, CodeRabbit et toute la CI doivent encore devenir
verts sur le SHA publié. Nathan a autorisé une fusion directe seulement après
ces validations exactes.
