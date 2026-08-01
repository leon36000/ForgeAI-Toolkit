# Référence CLI ForgeAI

La source de vérité reste `forgeai <commande> --help`. Le gate `scripts/gate_docs.py` vérifie qu’aucune commande n’est ajoutée sans documentation.

## `forgeai status`

### Rôle

`forgeai status` affiche l’état agrégé des backends, du cluster, du déploiement et du matériel.

### Quand l’utiliser

Un opérateur l’utilise pour vérifier rapidement l’état courant de l’environnement et repérer un composant indisponible.

Les sondes sont réelles. La commande applique une dégradation gracieuse : un composant injoignable est signalé comme « indisponible » et ne fait pas échouer la commande.

### Invocation

```shell
forgeai status
forgeai status --json
```

Options :

- `--json` : produit une sortie destinée aux traitements machine.

### Ce que la commande ne fait pas

Elle ne répare pas un composant indisponible et ne relance pas un déploiement.

## `forgeai logs`

### Rôle

`forgeai logs` affiche le journal du dernier déploiement.

### Quand l’utiliser

Un opérateur l’utilise pour examiner les événements récents d’un déploiement, limiter le volume affiché ou rechercher une sous-chaîne précise.

La sortie est bornée par défaut à 200 lignes. Le plafond dur est de 5000 lignes. Les secrets sont rédigés, y compris dans les journaux écrits par une version antérieure.

L’option `--grep` applique un filtre littéral par sous-chaîne. Ce filtre n’est jamais une expression régulière.

### Invocation

```shell
forgeai logs
forgeai logs --tail 100
forgeai logs --grep "erreur"
forgeai logs --tail 100 --grep "backend"
forgeai logs --json
```

Options :

- `--tail TAIL` : indique le nombre de lignes à afficher. La valeur est bornée, avec un plafond dur de 5000 lignes.
- `--grep GREP` : filtre par sous-chaîne littérale, jamais par expression régulière.
- `--json` : produit une sortie destinée aux traitements machine.

### Ce que la commande ne fait pas

Elle ne restitue pas des secrets en clair, même si un journal ancien en contenait avant rédaction.

## `forgeai diagnostic`

### Rôle

`forgeai diagnostic` produit un bundle de support reproductible et rédigé.

### Quand l’utiliser

Un opérateur l’utilise pour transmettre un état de diagnostic à un support ou pour conserver un artefact d’analyse.

À état identique et horodatage identique, le bundle produit les mêmes octets et la même empreinte SHA-256. Un bundle quitte la machine : aucune donnée sensible ne doit donc s’y trouver.

### Invocation

```shell
forgeai diagnostic
forgeai diagnostic --out diagnostic.bundle
forgeai diagnostic --tail 100
forgeai diagnostic --out diagnostic.bundle --tail 100
```

Options :

- `--out OUT` : écrit le fichier de sortie indiqué. Par défaut, la sortie est envoyée vers stdout.
- `--tail TAIL` : indique le nombre de lignes de logs incluses. La valeur est bornée.

### Ce que la commande ne fait pas

Elle ne doit pas produire un bundle contenant des données sensibles. Elle ne modifie pas l’état du déploiement.

## `forgeai web`

### Rôle

`forgeai web` sert l’interface web ForgeAI.

L’interface fournit un panneau opérateur avec les vues Status, Logs et Diagnostic.

### Quand l’utiliser

Un opérateur l’utilise pour consulter ces vues depuis un navigateur, selon le niveau d’exposition explicitement choisi.

Par défaut, l’écoute est liée à `127.0.0.1` et n’est jamais exposée sans action explicite.

La sécurité de l’interface comprend :

- une authentification fail-closed sur une écoute non loopback ;
- une limitation de débit contre le bruteforce ;
- des en-têtes de sécurité ;
- un mode TLS explicite ;
- le refus des identifiants lorsqu’une écoute réseau est utilisée sans TLS.

### Invocation

```shell
forgeai web
forgeai web --host 127.0.0.1
forgeai web --port 8000
forgeai web --no-browser
forgeai web --host 127.0.0.1 --port 8000 --no-browser
```

Options :

- `--host HOST` : définit l’adresse d’écoute. La valeur par défaut est `127.0.0.1`.
- `--port PORT` : définit le port d’écoute.
- `--no-browser` : n’ouvre pas automatiquement le navigateur.

### Ce que la commande ne fait pas

Elle ne doit pas accepter des identifiants sur une écoute réseau sans TLS. Elle ne désactive pas les protections de sécurité pour permettre une exposition implicite.

## `forgeai doctor`

### Rôle

`forgeai doctor` effectue des vérifications de l’environnement.

### Quand l’utiliser

Un opérateur l’utilise pour examiner l’environnement avant ou pendant une opération de déploiement.

### Invocation

```shell
forgeai doctor
```

Cette commande n’a pas d’option supplémentaire documentée dans son aide réelle.

## Gouvernance des registres

Le script `scripts/registre.py` expose cinq sous-commandes : `append`, `verify`, `completude`, `checkpoint` et `ancrage`.

### `append`

```shell
python scripts/registre.py append
```

Cette sous-commande appartient aux opérations d’ajout au registre. Les options et les paramètres effectifs sont ceux fournis par l’aide du script.

### `verify`

```shell
python scripts/registre.py verify
```

`verify` prouve l’intégrité de la chaîne de hachage du registre.

Cette vérification ne prouve pas que la chaîne est complète. Une chaîne tronquée peut rester parfaitement valide : les entrées restantes forment toujours une chaîne de hachage cohérente.

### `completude`

```shell
python scripts/registre.py completude
```

`completude` vérifie que chaque story terminée porte bien une attestation de revue.

Elle répond donc à une exigence de couverture des stories terminées, et non à la seule cohérence cryptographique de la chaîne.

### `checkpoint`

```shell
python scripts/registre.py checkpoint
```

Cette sous-commande fait partie des opérations de checkpoint du registre. Les options et les paramètres effectifs sont ceux fournis par l’aide du script.

### `ancrage`

```shell
python scripts/registre.py ancrage
```

`ancrage` compare chaque registre à l’état déjà mergé de `origin/main`.

Il détecte :

- une troncature ;
- un rollback ;
- une réécriture totale cohérente.

`ancrage` ne se contente donc pas de vérifier la chaîne locale. Il vérifie sa correspondance avec l’état de référence déjà mergé.

En CI, cette vérification exige `fetch-depth: 0`, afin que l’historique et la référence nécessaires soient disponibles. Si la référence est inaccessible, la commande échoue. Elle ne verdit pas en silence.

### Différence entre les vérifications

`verify` répond à la question : « La chaîne de hachage présente est-elle intègre ? »

`ancrage` répond à la question : « Le registre présent correspond-il à l’état déjà mergé dans `origin/main` ? »

`completude` répond à la question : « Chaque story terminée porte-t-elle une attestation de revue ? »

Ces contrôles sont distincts. Une chaîne peut être intègre tout en étant tronquée ; l’ancrage détecte cette divergence par comparaison avec l’état déjà mergé.
