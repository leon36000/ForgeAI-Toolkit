# Référence CLI ForgeAI

La source de vérité reste `forgeai <commande> --help`. Le gate `scripts/gate_docs.py` vérifie qu’aucune commande n’est ajoutée sans documentation.

## Codes de sortie

### Codes globaux

Ces codes s'appliquent à toute commande :

- **0** — succès.
- **1** — échec générique (exception non prévue).
- **130** — interrompu (SIGINT/Ctrl-C).

### forgeai budget

- **10** — budget set quota/agent invalide (BudgetError)
- **10** — budget status agent inconnu (BudgetError)

### forgeai export

- **11** — échec export du bundle portable (PortabilityError)

### forgeai gateway

- **10** — gateway set-url URL/config invalide (GatewayError)
- **10** — gateway wire câblage brique→route invalide (GatewayError)
- **10** — gateway verify GatewayError
- **10** — gateway verify invariant violé, brique hors gateway détectée

### forgeai gpu

- **12** — gpu drivers échec détection/plan pilotes (DriverError)

### forgeai ide

- **12** — ide configure gateway non configuré (GatewayError)
- **12** — ide configure IDEError
- **12** — ide mcp spec --server malformée, absence de =
- **12** — ide mcp IDEError
- **12** — ide governance IDEError

### forgeai import

- **11** — échec import du bundle (PortabilityError)

### forgeai loop

- **14** — loop run timeout d'une commande step/until (RunnerTimeoutError)
- **15** — loop run commande annulée (RunnerCancelledError)
- **12** — loop run échec de boucle générique (LoopError)
- **13** — loop run budget --max-iter épuisé sans que --until réussisse

### forgeai model

- **9** — model add-cloud RouteError
- **9** — model add-local LocalModelError
- **9** — model test route/passphrase invalide (RouteError/KeyError)
- **9** — model test test de connexion échoué (result.ok faux)

### forgeai node

- **12** — node probe RemoteProbeError
- **12** — node tailscale TailscaleError/BootstrapError
- **12** — node add variable d'env mot de passe vide/absente
- **12** — node add échec bootstrap SSH (NodeAddError/RemoteProbeError)
- **11** — node prepare PrepareError
- **12** — node discover --hostkey requis manquant
- **12** — node discover --user/--keyfile requis manquants
- **12** — node discover DiscoverError
- **8** — node status lecture cluster impossible (ClusterError)

### forgeai operators

- **8** — operators opérateur nommé inconnu, hors OPERATORS

### forgeai route

- **9** — route configure RouteError, config cache invalide

### forgeai strategy

- **10** — strategy set StrategyError, rôles/stratégie invalides
- **10** — strategy set reconfiguration d'une stratégie déjà définie sans --confirm

### forgeai template

- **12** — template show TemplateError, template/alias inconnu
- **12** — template resolve TemplateError

### forgeai wizard

- **7** — wizard échec dérivation profil hardware hors --dry-run (ProfileError)
- **8** — wizard validation stack inconnu
- **8** — wizard validation sélection illisible
- **8** — wizard validation briques inconnues
- **8** — wizard validation modèles inconnus
- **8** — wizard validation moteurs inconnus
- **8** — wizard validation moteur/vendor incompatible
- **8** — wizard validation nœuds invalides
- **8** — wizard validation embeddings hors famille
- **8** — wizard validation rag_node invalide
- **9** — wizard rag_node distant incompatible avec --backend compose
- **8** — wizard adopt référence des services absents du plan
- **6** — wizard backend cible indisponible après préflight
- **8** — wizard échec de déploiement compose/k3s (DeployError, déclenché L433 openbao_k3s ou L452 healthchecks_k3s)
- **9** — wizard fait attendu absent de la réponse RAG, vérification factuelle échouée

### forgeai web

Aucun code de sortie spécifique identifiable depuis `cli.py` — le handler `web_command` est défini dans le module `forgeai.web`, hors périmètre de cet inventaire. Traité comme commande binaire standard (0/1) ; voir le module `forgeai.web` pour le détail.

> **Note :** Le code `8` est réutilisé avec des significations différentes selon la commande — par exemple validation de sélection/stack et échec de déploiement pour `wizard`, opérateur inconnu pour `operators`, ou lecture cluster impossible pour `node status`. Il n'existe pas de convention globale par valeur : chaque commande définit sa propre sémantique pour ce code.

## Variables d'environnement

### FORGEAI_LANG

Définit la langue par défaut de l'ensemble de la CLI, en surcharge de l'option `--lang`. Si la variable est absente ou contient une valeur hors des locales disponibles, la CLI retombe sur `fr`. Elle est évaluée au démarrage dans `_run()`.

### FORGEAI_DEBUG

Si cette variable est définie et non vide, les exceptions non prévues par un handler spécifique sont relevées avec leur traceback complet au lieu d'être capturées et transformées en message d'erreur avec code `1`. Elle est évaluée dans `main()` et sert uniquement au débogage. Elle n'est jamais nécessaire en usage normal.

> **Note :** Les options `--password-env` (`node add`) et le paramètre interne `env_var` de `_read_secret()` ne sont pas des variables d'environnement fixes : le nom de la variable à lire est paramétrable par l'utilisateur. Elles sont donc documentées via leurs options CLI respectives et ne figurent pas dans cette section.

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

## Langue de cette référence

Cette référence est rédigée en français, dans la continuité de l'intégralité de la documentation du dépôt (`forgeai --help` lui-même est en français). Le critère d'acceptation de l'issue #443 demande une documentation « FR/EN » ; produire une version anglaise complète de cette référence est un changement de politique documentaire à l'échelle du dépôt (aucun autre document n'a d'équivalent anglais séparé aujourd'hui), pas une simple extension de cette story — la décision revient à une story de suivi distincte plutôt qu'à un arbitrage unilatéral ici.

## `forgeai budget`

### Rôle

`forgeai budget` gère les quotas des agents et affiche leur état.

### Quand l'utiliser

Un opérateur l'utilise pour définir le quota d'un agent ou consulter les budgets agents.

### Invocation

```shell
forgeai budget set --agent AGENT --quota QUOTA
forgeai budget status
forgeai budget status --agent AGENT
```

#### `forgeai budget set`

Définit le quota d'un agent.

##### Invocation

```shell
forgeai budget set --agent AGENT --quota QUOTA
forgeai budget set --agent AGENT --quota QUOTA --alert ALERT
```

##### Options

- `--agent AGENT` : indique l'agent concerné.
- `--quota QUOTA` : indique le quota à définir.
- `--alert ALERT` : indique le seuil d'alerte.
- `--home HOME` : indique le répertoire local.
- `--registre REGISTRE` : indique le registre à utiliser.

#### `forgeai budget status`

Affiche l'état des budgets agents.

##### Invocation

```shell
forgeai budget status
forgeai budget status --agent AGENT
```

##### Options

- `--agent AGENT` : limite l'affichage à un agent.
- `--home HOME` : indique le répertoire local.

### Ce que la commande ne fait pas

Elle ne documente pas d'autre opération que la définition et la consultation des budgets agents.

## `forgeai catalogue`

### Rôle

`forgeai catalogue` consulte le catalogue des briques disponibles.

### Quand l'utiliser

Un opérateur l'utilise pour afficher le catalogue ou lister la brique par défaut de chaque catégorie.

### Invocation

```shell
forgeai catalogue
forgeai catalogue --defaults
forgeai catalogue --catalogue CATALOGUE
```

### Options

- `--defaults` : liste la brique par défaut de chaque catégorie.
- `--catalogue CATALOGUE` : indique le chemin vers le catalogue JSON.

### Ce que la commande ne fait pas

Cette commande est en lecture seule et n'a pas d'effet de bord.

## `forgeai export`

### Rôle

`forgeai export` exporte l'état local vers un bundle portable.

### Quand l'utiliser

Un opérateur l'utilise pour écrire une sauvegarde de l'état local pouvant être réimportée ultérieurement.

### Invocation

```shell
forgeai export --out OUT
forgeai export --out OUT --home HOME
forgeai export --out OUT --home HOME --registre REGISTRE
```

### Options

- `--out OUT` : indique le chemin du bundle à écrire.
- `--home HOME` : indique le répertoire local à exporter.
- `--registre REGISTRE` : indique le registre à utiliser.

### Ce que la commande ne fait pas

Elle ne réimporte pas un bundle. L'importation relève de `forgeai import`.

## `forgeai gateway`

### Rôle

`forgeai gateway` configure et vérifie le gateway unique des briques.

### Quand l'utiliser

Un opérateur l'utilise pour définir le gateway, câbler une brique vers une route ou vérifier l'invariant selon lequel aucune brique ne pointe directement vers un modèle.

### Invocation

```shell
forgeai gateway set-url --url URL
forgeai gateway wire --brick BRICK --role ROLE --route ROUTE
forgeai gateway verify
```

#### `forgeai gateway set-url`

Définit le gateway unique.

##### Invocation

```shell
forgeai gateway set-url --url URL
```

##### Options

- `--url URL` : indique l'URL du gateway.
- `--key-env KEY_ENV` : indique la variable d'environnement portant la clé.
- `--home HOME` : indique le répertoire local.
- `--registre REGISTRE` : indique le registre à utiliser.

#### `forgeai gateway wire`

Câble une brique, par rôle et par route, vers le gateway.

##### Invocation

```shell
forgeai gateway wire --brick BRICK --role ROLE --route ROUTE
```

##### Options

- `--brick BRICK` : indique la brique à câbler.
- `--role ROLE` : indique le rôle de la brique.
- `--route ROUTE` : indique la route à utiliser.
- `--home HOME` : indique le répertoire local.
- `--registre REGISTRE` : indique le registre à utiliser.

#### `forgeai gateway verify`

Vérifie l'invariant selon lequel aucune brique ne se trouve hors du gateway.

##### Invocation

```shell
forgeai gateway verify
```

##### Options

- `--home HOME` : indique le répertoire local.

##### Code de retour

Contrairement à `forgeai status`/`forgeai operators` (dégradation gracieuse, toujours 0), cette
commande est une VALIDATION : elle échoue avec le code 10 (`ECHEC GATEWAY : gateway non
configuré`) si `forgeai gateway set-url` n'a pas encore été exécuté (vérifié par exécution
réelle). Ce n'est donc pas un exemple à code de retour garanti.

### Ce que la commande ne fait pas

Elle ne permet pas à une brique de pointer directement vers un modèle lorsque l'invariant du gateway s'applique.

## `forgeai hardware`

### Rôle

`forgeai hardware` sonde le matériel local, notamment le CPU et le GPU.

### Quand l'utiliser

Un opérateur l'utilise pour consulter les caractéristiques matérielles disponibles localement.

### Invocation

```shell
forgeai hardware
```

### Ce que la commande ne fait pas

Cette commande ne modifie pas le matériel local.

## `forgeai ide`

### Rôle

`forgeai ide` liste les IDE supportés et configure leur branchement au stack ForgeAI.

### Quand l'utiliser

Un opérateur l'utilise pour consulter les IDE pris en charge, générer une configuration de branchement, préconfigurer des serveurs MCP ou préparer la gouvernance d'un IDE.

### Invocation

```shell
forgeai ide list
forgeai ide configure --ide IDE --model MODEL
forgeai ide mcp --ide IDE --server NAME=URL
forgeai ide governance
```

#### `forgeai ide list`

Liste les IDE supportés.

##### Invocation

```shell
forgeai ide list
```

##### Options

Aucune option supplémentaire.

#### `forgeai ide configure`

Génère et écrit la configuration de branchement d'un IDE.

##### Invocation

```shell
forgeai ide configure --ide IDE --model MODEL
forgeai ide configure --ide IDE --model MODEL --dest DEST
```

##### Options

- `--ide {aider,claude-code,cline,cursor,opencode}` : indique l'IDE à configurer.
- `--model MODEL` : indique le modèle à utiliser.
- `--dest DEST` : indique la destination de la configuration.
- `--gateway-url GATEWAY_URL` : indique l'URL du gateway.
- `--key-env KEY_ENV` : indique la variable d'environnement portant la clé.
- `--home HOME` : indique le répertoire local.
- `--registre REGISTRE` : indique le registre à utiliser.

#### `forgeai ide mcp`

Préconfigure les serveurs MCP du stack.

##### Invocation

```shell
forgeai ide mcp --ide IDE --server NAME=URL
forgeai ide mcp --ide IDE --server NAME=URL --transport http
forgeai ide mcp --ide IDE --server NAME=URL --transport sse
```

##### Options

- `--ide {aider,claude-code,cline,cursor,opencode}` : indique l'IDE concerné.
- `--server NAME=URL` : indique un serveur MCP sous la forme `NAME=URL`.
- `--transport {http,sse}` : indique le transport du serveur.
- `--dest DEST` : indique la destination de la configuration.
- `--registre REGISTRE` : indique le registre à utiliser.

#### `forgeai ide governance`

Préconfigure la liste autorisée des skills et les hooks de gouvernance.

##### Invocation

```shell
forgeai ide governance
forgeai ide governance --ide IDE
forgeai ide governance --skill SKILL --hook HOOK
```

##### Options

- `--ide {aider,claude-code,cline,cursor,opencode}` : indique l'IDE concerné.
- `--skill SKILL` : indique un skill à prendre en compte.
- `--hook HOOK` : indique un hook à prendre en compte.
- `--dest DEST` : indique la destination de la configuration.
- `--registre REGISTRE` : indique le registre à utiliser.

### Ce que la commande ne fait pas

Elle ne documente pas d'IDE en dehors des IDE pris en charge par ses options.

## `forgeai import`

### Rôle

`forgeai import` réimporte un bundle portable dans l'état local.

### Quand l'utiliser

Un opérateur l'utilise pour restaurer un état précédemment exporté par `forgeai export`.

### Invocation

```shell
forgeai import --bundle BUNDLE
forgeai import --bundle BUNDLE --force
forgeai import --bundle BUNDLE --home HOME --registre REGISTRE
```

### Options

- `--bundle BUNDLE` : indique le chemin du bundle à importer.
- `--home HOME` : indique le répertoire local cible.
- `--force` : écrase les fichiers existants.
- `--registre REGISTRE` : indique le registre à utiliser.

### Ce que la commande ne fait pas

Elle ne crée pas un bundle d'exportation. L'exportation relève de `forgeai export`.

## `forgeai loop`

### Rôle

`forgeai loop` exécute des commandes répétées selon une condition de complétion et un budget d'itérations.

### Quand l'utiliser

Un opérateur l'utilise pour répéter une étape jusqu'à ce que la commande de complétion retourne zéro ou que le budget soit atteint.

### Invocation

```shell
forgeai loop run --max-iter MAX_ITER --step STEP --until UNTIL
forgeai loop run --max-iter MAX_ITER --step STEP --until UNTIL --timeout TIMEOUT
```

#### `forgeai loop run`

Répète une commande d'étape jusqu'à ce que la commande de complétion retourne zéro ou que le budget soit atteint.

##### Invocation

```shell
forgeai loop run --max-iter MAX_ITER --step STEP --until UNTIL
forgeai loop run --max-iter MAX_ITER --step STEP --until UNTIL --timeout TIMEOUT
```

##### Options

- `--max-iter MAX_ITER` : indique le budget d'itérations maximum.
- `--step STEP` : indique la commande exécutée à chaque itération.
- `--until UNTIL` : indique la commande de complétion ; un code de sortie nul indique que le traitement est terminé.
- `--timeout TIMEOUT` : indique la durée maximale, en secondes, par commande ; l'arbre est tué au-delà. La valeur par défaut est illimitée.
- `--registre REGISTRE` : indique le registre à utiliser.

### Ce que la commande ne fait pas

Elle ne poursuit pas les itérations au-delà du budget maximum indiqué.

## `forgeai model`

### Rôle

`forgeai model` gère les routes de modèles cloud et locaux.

### Quand l'utiliser

Un opérateur l'utilise pour ajouter une route cloud, déployer et tester un modèle local, lister les routes ou retester une route existante.

### Invocation

```shell
forgeai model add-cloud --name NAME --provenance PROVENANCE --model-id MODEL_ID
forgeai model add-local --name NAME --engine ENGINE --model-ref MODEL_REF --url URL --sha256 SHA256 --vram-required-mb VRAM_REQUIRED_MB --vram-mb VRAM_MB --engine-url ENGINE_URL
forgeai model list
forgeai model test --name NAME
```

#### `forgeai model add-cloud`

Ajoute une route cloud après un test réel requis.

##### Invocation

```shell
forgeai model add-cloud --name NAME --provenance PROVENANCE --model-id MODEL_ID
forgeai model add-cloud --name NAME --provenance PROVENANCE --model-id MODEL_ID --base-url BASE_URL
```

##### Options

- `--name NAME` : indique le nom de la route.
- `--provenance {openrouter,deepinfra,nim,direct,autre}` : indique la provenance.
- `--model-id MODEL_ID` : indique l'identifiant du modèle.
- `--base-url BASE_URL` : indique l'endpoint compatible OpenAI, requis pour les provenances `direct` et `autre`.
- `--api-key-env API_KEY_ENV` : indique la variable d'environnement portant la clé ; la clé n'est jamais passée en argument.
- `--passphrase-env PASSPHRASE_ENV` : indique la variable d'environnement portant la phrase secrète.
- `--home HOME` : indique le répertoire local.
- `--registre REGISTRE` : indique le registre à utiliser.

#### `forgeai model add-local`

Télécharge, vérifie par hachage, déploie et teste un modèle local.

##### Invocation

```shell
forgeai model add-local --name NAME --engine ENGINE --model-ref MODEL_REF --url URL --sha256 SHA256 --vram-required-mb VRAM_REQUIRED_MB --vram-mb VRAM_MB --engine-url ENGINE_URL
```

##### Options

- `--name NAME` : indique le nom du modèle.
- `--engine {ollama,llamacpp,vllm}` : indique le moteur.
- `--model-ref MODEL_REF` : indique la référence du modèle.
- `--url URL` : indique l'URL du modèle.
- `--sha256 SHA256` : indique le hachage SHA-256 attendu.
- `--vram-required-mb VRAM_REQUIRED_MB` : indique la VRAM requise.
- `--vram-mb VRAM_MB` : indique la VRAM du nœud cible.
- `--engine-url ENGINE_URL` : indique l'endpoint compatible OpenAI du moteur.
- `--dest DEST` : indique la destination.
- `--timeout TIMEOUT` : indique le délai d'attente.
- `--registre REGISTRE` : indique le registre à utiliser.

#### `forgeai model list`

Liste les routes, sans afficher les clés.

##### Invocation

```shell
forgeai model list
forgeai model list --home HOME
```

##### Options

- `--home HOME` : indique le répertoire local.

#### `forgeai model test`

Reteste une route existante.

##### Invocation

```shell
forgeai model test --name NAME
forgeai model test --name NAME --passphrase-env PASSPHRASE_ENV
```

##### Options

- `--name NAME` : indique le nom de la route à tester.
- `--passphrase-env PASSPHRASE_ENV` : indique la variable d'environnement portant la phrase secrète.
- `--home HOME` : indique le répertoire local.

### Ce que la commande ne fait pas

Elle n'accepte pas de clé en clair dans la ligne de commande. L'option `--api-key-env` désigne une variable d'environnement et la clé n'est jamais passée en argument.

## `forgeai operators`

### Rôle

`forgeai operators` sonde l'état de fusion des opérateurs Kubernetes connus.

### Quand l'utiliser

Un opérateur l'utilise pour consulter l'état d'un opérateur précis ou de tous les opérateurs connus.

### Invocation

```shell
forgeai operators
forgeai operators external-secrets-operator
forgeai operators argo-cd
forgeai operators kserve
```

Les opérateurs connus sont `external-secrets-operator`, `argo-cd` et `kserve`.

### Options

- `name` : indique l'opérateur précis à sonder. Par défaut, tous les opérateurs connus sont concernés.

### Ce que la commande ne fait pas

Cette commande est en lecture seule et ne modifie pas l'état des opérateurs.

## `forgeai strategy`

### Rôle

`forgeai strategy` choisit et affiche la stratégie de fonctionnement, qui détermine le nombre de slots.

### Quand l'utiliser

Un opérateur l'utilise pour consulter la stratégie courante ou en choisir une nouvelle.

### Invocation

```shell
forgeai strategy set --strategy STRATEGY
forgeai strategy show
```

#### `forgeai strategy set`

Choisit la stratégie.

##### Invocation

```shell
forgeai strategy set --strategy STRATEGY
forgeai strategy set --strategy STRATEGY --confirm
```

##### Options

- `--strategy {cerveau-unique,equipe,hybride}` : indique la stratégie.
- `--roles ROLES` : indique les rôles concernés.
- `--confirm` : applique explicitement une reconfiguration entraînant un changement de slots.
- `--home HOME` : indique le répertoire local.
- `--registre REGISTRE` : indique le registre à utiliser.

#### `forgeai strategy show`

Affiche la stratégie courante.

##### Invocation

```shell
forgeai strategy show
forgeai strategy show --home HOME
```

##### Options

- `--home HOME` : indique le répertoire local.

### Ce que la commande ne fait pas

Elle n'applique pas une reconfiguration de slots sans confirmation explicite lorsque celle-ci est requise.

## `forgeai template`

### Rôle

`forgeai template` liste, affiche, valide et résout les templates de déploiement.

### Quand l'utiliser

Un opérateur l'utilise pour consulter les templates disponibles, vérifier un template contre le catalogue ou produire un cœur déployable après filtrage du matériel.

### Invocation

```shell
forgeai template list
forgeai template show NAME
forgeai template resolve NAME
```

#### `forgeai template list`

Liste les templates disponibles.

##### Invocation

```shell
forgeai template list
```

##### Options

Aucune option supplémentaire.

#### `forgeai template show`

Affiche et valide un template contre le catalogue.

##### Invocation

```shell
forgeai template show NAME
forgeai template show --catalogue CATALOGUE NAME
```

##### Options

- `--catalogue CATALOGUE` : indique le chemin vers le catalogue.
- `name` : indique le nom du template.

#### `forgeai template resolve`

Résout un template par filtrage du matériel afin d'obtenir un cœur déployable.

##### Invocation

```shell
forgeai template resolve NAME
forgeai template resolve --registre REGISTRE NAME
```

##### Options

- `--registre REGISTRE` : indique le registre à utiliser.
- `name` : indique le nom du template.

### Ce que la commande ne fait pas

Elle ne résout pas un template sans le nom du template demandé.
