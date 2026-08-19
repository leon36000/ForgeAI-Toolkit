# Annexe — inventaire exhaustif des codes de sortie de src/forgeai/cli.py (#443 incrément 2a)

Source : lecture complète du fichier (1724 lignes) + traçage de chaque `return <N>` (N≠0,1)
jusqu'à sa condition de déclenchement, exécution réelle de `gate_docs.py::sous_commandes()` pour
confirmer les 21 commandes de premier niveau. NE JAMAIS RE-DÉRIVER — utiliser ces valeurs telles
quelles pour construire `Docs/exit-codes.json` et les nouvelles sections de `Docs/reference/cli.md`.

## Codes globaux (s'appliquent à toute commande, gérés dans `_run()`/`main()`)

- `0` : succès.
- `1` : échec générique — exception non prévue par un handler spécifique (`except Exception`,
  ligne 1720).
- `130` : commande interrompue au clavier (`KeyboardInterrupt`, ligne 1714 — convention Unix
  128+SIGINT).
- `8` (cas global additionnel) : `DeployError` capturé ligne 1703 — en pratique atteignable
  uniquement via `wizard` (aucun autre handler n'appelle compose_up/compose_down/k3s_*).

## Codes par commande (10 codes numériques distincts documentés au total : 6,7,8,9,10,11,12,13,
14,15 — correction 2026-08-19 : le texte original comptait "13 codes" en listant en réalité 10
valeurs ; erreur de comptage repérée en round 4 de revue scellée sur l'incrément 2a, sans lien
avec le point ci-dessous)

**Périmètre du gate mécanique `scripts/gate_exit_codes.py` (précision ajoutée round 4, revue
scellée #443 2a)** : le gate vérifie que la ligne enregistrée contient littéralement la
sous-chaîne `return <code>` — 8 des 10 codes ci-dessus (tous sauf `13` et une occurrence de `9`)
s'expriment ainsi dans le code réel et sont vérifiés mécaniquement (50 entrées dans
`Docs/exit-codes.json`). Les 2 cas suivants s'expriment via une expression ternaire Python
(`return X if cond else <code>`, qui ne contient jamais littéralement `return <code>`) : `13` —
`loop run` budget `--max-iter` épuisé (L1254) ; `9` — `model test` test de connexion échoué
(L1016). Après 4 rounds de revue scellée ayant exploré toutes les combinaisons (accepter le
ternaire dans le gate → viole la règle littérale ; l'exiger strictement → ces 2 lignes ne peuvent
jamais la satisfaire, quel que soit le pattern), ces 2 cas sont documentés UNIQUEMENT en
narratif dans `Docs/reference/cli.md` (note explicite sur chaque puce concernée), hors du
registre structuré vérifiable — décision qui privilégie la règle littérale de vérification
mécanique (zéro faux positif possible) plutôt que l'exhaustivité totale du registre structuré, un
arbitrage entre deux exigences de cette story qui se sont révélées mutuellement incompatibles
pour ces 2 lignes précises, sans solution technique qui satisfasse les deux simultanément.

- **budget** (non binaire) : `10` — `budget set` quota/agent invalide (BudgetError, L1126) ;
  `10` — `budget status` agent inconnu (BudgetError, L1145).
- **catalogue** : binaire standard (0/1 seulement).
- **diagnostic** : binaire standard.
- **doctor** : binaire standard.
- **export** (non binaire) : `11` — échec export du bundle portable (PortabilityError, L1262).
- **gateway** (non binaire) : `10` — `set-url` URL/config invalide (GatewayError, L1024) ;
  `10` — `wire` câblage brique→route invalide (GatewayError, L1038) ;
  `10` — `verify` GatewayError (L1053) ;
  `10` — `verify` invariant violé, brique hors gateway détectée (L1058).
- **gpu** (non binaire) : `12` — `gpu drivers` échec détection/plan pilotes (DriverError, L613).
- **hardware** : binaire standard.
- **ide** (non binaire, sauf `list`=binaire) : `12` — `configure` gateway non configuré
  (GatewayError, L1168) ; `12` — `configure` IDEError (L1174) ; `12` — `mcp` spec `--server`
  malformée, absence de `=` (L1192) ; `12` — `mcp` IDEError (L1198) ; `12` — `governance`
  IDEError (L1214).
- **import** (non binaire) : `11` — échec import du bundle (PortabilityError, L1279).
- **logs** : binaire standard.
- **loop** (non binaire) : `14` — `run` timeout d'une commande step/until (RunnerTimeoutError,
  L1241) ; `15` — `run` commande annulée (RunnerCancelledError, L1245) ; `12` — `run` échec de
  boucle générique (LoopError, L1248) ; `13` — `run` budget `--max-iter` épuisé sans que
  `--until` réussisse (L1254).
- **model** (non binaire, sauf `list`=binaire) : `9` — `add-cloud` RouteError (L959) ;
  `9` — `add-local` LocalModelError (L988) ; `9` — `test` route/passphrase invalide
  (RouteError/KeyError, L1012) ; `9` — `test` test de connexion échoué (`result.ok` faux, L1016).
- **node** (non binaire, sauf `cluster`=binaire) : `8` — `status` lecture cluster impossible
  (ClusterError, L912) ; `12` — `add` variable d'env mot de passe vide/absente (L807) ;
  `12` — `add` échec bootstrap SSH (NodeAddError/RemoteProbeError, L816) ;
  `12` — `tailscale` TailscaleError/BootstrapError (L788) ; `12` — `probe` RemoteProbeError
  (L754) ; `11` — `prepare` PrepareError (L836) ; `12` — `discover` `--hostkey` requis manquant
  (L871) ; `12` — `discover` `--user`/`--keyfile` requis manquants (L874) ; `12` — `discover`
  DiscoverError (L882).
- **operators** (non binaire) : `8` — opérateur nommé inconnu, hors `OPERATORS` (L733).
- **route** (non binaire) : `9` — `configure` RouteError, config cache invalide (L1108).
- **status** : binaire standard.
- **strategy** (non binaire, sauf `show`=binaire) : `10` — `set` StrategyError, rôles/stratégie
  invalides (L1070) ; `10` — `set` reconfiguration d'une stratégie déjà définie sans `--confirm`
  (L1077).
- **template** (non binaire, sauf `list`=binaire) : `12` — `show` TemplateError, template/alias
  inconnu (L1313) ; `12` — `resolve` TemplateError (L1332).
- **web** : aucun code identifiable depuis `cli.py` (handler `web_command` importé de
  `forgeai.web`, défini hors de ce fichier — hors périmètre de cette annexe). Traiter comme
  binaire standard dans la doc, avec une note « voir le module `forgeai.web` pour le détail ».
- **wizard** (non binaire) : `6` — backend cible indisponible après préflight (L404) ;
  `7` — échec dérivation profil hardware hors `--dry-run` (ProfileError, L185) ;
  `8` — erreurs de validation `--stack`/`--selection` (stack inconnu L204, sélection illisible
  L232, briques inconnues L238, modèles inconnus L252, moteurs inconnus L257, moteur/vendor
  incompatible L271, nœuds invalides L277, embeddings hors famille L283, `rag_node` invalide
  L288, `adopt` référence des services absents du plan L306) ; `8` — échec de déploiement
  compose/k3s (`DeployError`, capté ligne 1703, déclenché notamment L433/L452 dans `wizard_ci`) ;
  `9` — `rag_node` distant incompatible avec `--backend compose` (L292) ; `9` — fait attendu
  absent de la réponse RAG, vérification factuelle échouée (L518).

## Notes transverses

- Le code `8` est réutilisé avec des significations DIFFÉRENTES selon la commande (`wizard` :
  validation sélection/stack + échec déploiement ; `operators` : nom d'opérateur inconnu ;
  `node status` : erreur cluster) — pas de convention globale par valeur, chaque commande définit
  sa propre sémantique localement. À noter explicitement dans la doc pour éviter toute confusion.
- Le code `2` (erreurs d'usage argparse, ex. option manquante) n'est JAMAIS écrit explicitement
  dans `cli.py` — comportement implicite de la bibliothèque `argparse` elle-même, pas une valeur
  à inventorier dans `Docs/exit-codes.json` (aucune ligne `return 2`/`sys.exit(2)` du code
  applicatif à laquelle l'attribuer).

## Variables d'environnement (4 usages trouvés, 2 fixes documentables)

- `FORGEAI_LANG` (ligne ~1369, `_run()`) : override de la langue par défaut de la CLI entière
  (`--lang`), retombe sur `"fr"` si absente ou invalide (valeur hors des locales disponibles).
- `FORGEAI_DEBUG` (ligne ~1717, `main()`) : si définie et non vide, les exceptions non prévues
  par un handler sont RE-LEVÉES avec traceback complet au lieu d'être capturées proprement
  (message rédigé + `return 1`). Utile pour le débogage, jamais nécessaire en usage normal.
- `args.password_env` (`node add --password-env NOM_VAR`, ligne ~804) : PAS une variable fixe —
  le NOM de la variable à lire est un paramètre CLI. Documenté via l'option `--password-env`
  elle-même dans la section existante de `node add`, PAS dans la nouvelle section « Variables
  d'environnement » (qui ne couvre que les 2 variables FIXES ci-dessus).
- `_read_secret(env_var, ...)` (fonction interne partagée, ligne ~936) : même traitement — nom
  paramétrable selon la commande appelante, pas une variable fixe à documenter globalement.
