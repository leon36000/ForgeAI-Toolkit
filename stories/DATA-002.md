# DATA-002 — Transaction locale RouteStore/Vault

## Calibration

- Profil : `PROOF-Team`
- Risque : `T2`
- Branche : `fix/DATA-002-routestore-atomic-transaction`
- Base initiale : `c14430057823cdc9eb6f0d5ae22ed84dd8a4b8d1`
- Base finale après synchronisation : `9ef84cc2bcf2ceacf3cd564ff8eb73a749bbfeeb`
- Issue : `#164`
- Claim Codex : actif dans le ledger PROOF externe

## Cause racine vérifiée

Le correctif historique `FAI-0010` protège séparément les read-modify-write de
`routes.json` et `vault.json`. Il ne crée pas de transaction commune :

1. `configure_cache` charge puis réécrit `routes.json` sans verrou ;
2. `RouteStore._save` et `Vault._save` tronquent directement le fichier cible ;
3. `add_cloud` persiste la clé au coffre avant le commit de la route, sans
   compensation si ce commit échoue ;
4. les locks distincts de `routes.json` et `vault.json` ne sérialisent pas une
   opération qui touche les deux ressources.

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
  automatiquement à la prochaine ouverture du `RouteStore`.

## Implémentation

- verrou commun `.models-transaction.lock` pour les mutations et lectures
  `RouteStore`/`Vault` ;
- écriture temporaire dans le même répertoire, permissions `0600`, `fsync` du
  fichier, `os.replace`, puis `fsync` du répertoire ;
- write-ahead journal `.models-transaction.json` contenant l’état antérieur
  chiffré du coffre et les anciennes routes ;
- rollback idempotent après exception ou reprise à la première opération d’une
  instance neuve ou déjà existante ;
- probe réseau exécuté hors verrou, entre le précontrôle atomique et le commit.

## Résultats vérifiés

- 39 tests ciblés : PASS ;
- 13 tests de concurrence et de panne, avec six arrêts `SIGKILL` réels
  répartis sur les fenêtres de commit : PASS ;
- 100 configurations concurrentes, lecteur JSON brut actif et probe hors
  verrou : PASS en `0,31 s` ;
- suite complète : PASS, couverture globale `89,70 %` (seuil `85 %`) ;
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
puis re-revus sans constat critique ou important. Cette revue interne ne compte
pas parmi les trois verdicts multi-vendeurs requis.

## Rollback

Le rollback de données est couvert par :

- échec injecté avant `os.replace` pour `routes.json` et `vault.json` ;
- échec du commit route après écriture du coffre ;
- `SIGKILL` entre le remplacement du coffre et celui des routes, avec état vide
  puis état préexistant ;
- récupération depuis une instance `RouteStore` créée avant le crash.

Le rollback Git du commit candidat `1b64e62` a été rejoué dans un worktree
éphémère isolé. Après inversion complète du patch, les 24 tests ciblés de la
base passent ; le worktree de preuve a ensuite été supprimé.

## Gates encore externes

SonarQube, CodeRabbit/Bugbot, les trois verdicts indépendants et la merge queue
nécessitent la PR. Aucun verdict n’est préfabriqué localement.
