# DATA-002 — Transaction locale RouteStore/Vault

## Calibration

- Profil : `PROOF-Team`
- Risque : `T2`
- Branche : `fix/DATA-002-routestore-atomic-transaction`
- Base initiale : `c14430057823cdc9eb6f0d5ae22ed84dd8a4b8d1`
- Base finale après synchronisation : `7a1fbf1478e3dd89c5fbd0b4fa5e9da25726ac25`
- Issue : `#164`
- Claim Codex : tracé dans le ledger PROOF externe

## Cause racine vérifiée

Le correctif historique `FAI-0010` protège séparément les read-modify-write de
`routes.json` et `vault.json`. Il ne crée pas de transaction commune :

1. `configure_cache` charge puis réécrit `routes.json` sans verrou ;
2. `RouteStore._save` et `Vault._save` tronquent directement le fichier cible ;
3. `add_cloud` persiste la clé au coffre avant le commit de la route, sans
   compensation si ce commit échoue ;
4. les locks distincts de `routes.json` et `vault.json` ne sérialisent pas une
   opération qui touche les deux ressources ;
5. `forgeai import` et `forgeai export` accèdent à `routes.json` hors du verrou
   commun et peuvent respectivement écraser une mutation ou publier un état
   encore révocable par le journal ;
6. la récupération acceptait le chemin de n’importe quelle instance `Vault`,
   ce qui permettait à un coffre voisin de consommer le WAL canonique ;
7. la destination `export --out` pouvait chevaucher les routes, le coffre ou le
   WAL, et les alias de fichiers pouvaient contourner l’identité canonique.

La baseline ciblée existante passe 24 tests en environnement autorisant le
loopback, mais elle ne couvre pas ces interleavings ni les pannes avant rename.

## Hypothèse testée

Un verrou de transaction unique pour le répertoire modèles, combiné à des
écritures temporaires `fsync` puis `os.replace`, doit rendre chaque fichier
atomique et sérialiser `add_cloud`, `configure_cache` et `Vault.put`. Si le
commit de route échoue après l’écriture du coffre, un journal durable contenant
l’état antérieur doit permettre de restaurer les deux fichiers sous le même
verrou, y compris après l’arrêt brutal du processus.

## Preuves RED attendues

- 100 `configure_cache` concurrents perdent des mises à jour ou lisent un JSON
  tronqué avec l’implémentation actuelle ;
- un `add_cloud` suspendu pendant son commit écrase une configuration
  concurrente ;
- une panne injectée dans `os.replace` ne touche pas l’ancien fichier ;
- un échec du commit de route ne laisse aucune clé orpheline.
- un `SIGKILL` entre le remplacement du coffre et celui des routes est récupéré
  automatiquement à la prochaine ouverture du `RouteStore` ;
- un import suspendu à son commit écrase un `add_cloud` et un
  `configure_cache` concurrents ;
- un `Vault(home/"autre.json")` consomme le WAL de `RouteStore` et laisse la
  clé canonique orpheline ;
- un export effectué avant la suppression du WAL publie une route non commitée.

## Implémentation

- verrou commun `.models-transaction.lock` pour les mutations et lectures
  `RouteStore`/`Vault` ;
- écriture temporaire dans le même répertoire, permissions `0600`, `fsync` du
  fichier, `os.replace`, puis `fsync` du répertoire ;
- write-ahead journal `.models-transaction.json` contenant l’état antérieur
  chiffré du coffre, les anciennes routes et l’identité canonique `vault.json` ;
- rollback idempotent après exception ou reprise à la première opération d’une
  instance neuve ou déjà existante ;
- probe réseau exécuté hors verrou, entre le précontrôle atomique et le commit ;
- import et export sérialisés avec la transaction RouteStore, récupération du
  WAL avant lecture/écriture et remplacements atomiques `0600` à l’import ;
- refus de restaurer un WAL vers tout coffre autre que le `vault.json` auquel
  le journal est explicitement lié ;
- comparaison d’identité par inode (`samefile`) pour les alias casse/symlink/
  hardlink, restauration du canon et de l’alias avant suppression du WAL ;
- rejet de toute destination d’export chevauchant un fichier vivant du setup,
  puis écriture atomique `fsync`/`os.replace` du bundle.

## Extension de périmètre tracée

Trois revues OpenAI indépendantes ont découvert que le writer CLI de production
`src/forgeai/portability.py` contournait le verrou DATA-002. Ce fichier n’était
pas dans l’allowlist initiale. L’extension n’a pas été silencieuse : elle a été
annoncée comme STOP au cockpit, puis couverte par l’autorisation explicite de
Nathan d’effectuer toutes les corrections nécessaires jusqu’à complétion. Le
delta hors allowlist est limité à ce fichier et au chemin réel du défaut.

## Résultats vérifiés

- 57 tests ciblés : PASS ;
- 17 tests de concurrence et de panne, avec neuf arrêts `SIGKILL` réels
  répartis sur les fenêtres de commit : PASS ;
- 100 configurations concurrentes, lecteur JSON brut actif et probe hors
  verrou : PASS en `0,31 s` ;
- suite complète locale du delta final : tous les tests DATA-002 et UI passent ;
  l’unique échec restant est le faux serveur `tests/test_immudb.py`, qui
  réinitialise la connexion indépendamment de ce diff ; couverture globale
  `89,72 %` (seuil `85 %`) ;
- `forgeai/core/registre.py` : `98 %` (seuil `95 %`) ;
- no-stub, registres, catalogue et gate des revues existantes : PASS ;
- Gitleaks `8.30.1`, scan du worktree complet : aucune fuite.

Le premier passage complet a exposé une instabilité préexistante du faux serveur
`tests/test_immudb.py` (socket réinitialisée parce que le handler ne consomme pas
le corps de la requête d’audit). Le second passage complet est vert. Ce fichier
est hors périmètre DATA-002 et n’a pas été modifié.

La revue de code Codex interne a d’abord rejeté le patch pour deux fenêtres de
course supplémentaires : une opération `Vault` après crash pouvait être
acquittée puis annulée, et le premier contrôle de doublon n’était pas atomique
avec la récupération. Les deux constats ont été reproduits en rouge, corrigés,
puis re-revus sans constat critique ou important.

Trois autres revues OpenAI indépendantes ont ensuite rejeté le candidat
`f1b1a825` pour le writer import/export hors transaction, le détournement du WAL
par un coffre voisin et le pack de revue périmé. Chaque défaut fonctionnel a été
reproduit en rouge puis corrigé. Ces revues ne sont pas présentées comme trois
fournisseurs distincts et ne satisfont donc pas artificiellement une exigence
multi-vendeurs.

Le premier tour final sur le pack `23ec2b…` a encore découvert deux défauts
importants : collision de `export --out` avec l’état vivant et alias du coffre
sur volume insensible à la casse. Les reproductions CLI, case-insensitive/
hardlink et les corrections sont incluses dans le nouveau candidat; le pack
`23ec2b…` est donc superseded et doit être régénéré.

## Rollback

Le rollback de données est couvert par :

- échec injecté avant `os.replace` pour `routes.json` et `vault.json` ;
- échec du commit route après écriture du coffre ;
- `SIGKILL` entre le remplacement du coffre et celui des routes, avec état vide
  puis état préexistant ;
- récupération depuis une instance `RouteStore` créée avant le crash.

Le rollback Git du candidat final `de787be544b8bee4d5fea8fa0a9d6c55eabc6d69`
a été rejoué dans un worktree éphémère isolé : tous les commits de
`origin/main..HEAD` ont été inversés sans commit, puis `git diff --exit-code
origin/main` a confirmé une identité exacte. Les 24 tests ciblés de la base
passent (`sha256:12784721e0280443291002b595b03384e8588476665647b621a862f07297e08f`) ;
le worktree de preuve a ensuite été supprimé.

## Limite plateforme

Le verrou repose sur `fcntl`, et les tests de crash utilisent `fork`/`SIGKILL` :
la transaction reste donc explicitement POSIX. Cette contrainte existait avant
DATA-002 ; aucun support Windows non prouvé n’est revendiqué.

## Gates encore externes

Le nouveau SHA doit encore repasser SonarQube, GitGuardian, CodeRabbit et la CI.
La merge queue n’est pas configurée sur le dépôt ; Nathan a autorisé une fusion
directe tracée. Aucun verdict multi-vendeur n’est préfabriqué localement.
