# HEALTH-029 — Les healthchecks Compose ne peuvent jamais passer

Trouvé en **déployant réellement** la stack par défaut depuis le wheel installé en salle blanche,
pas en lisant le code. Le manifeste est correct à l'œil ; c'est l'exécution qui révèle le défaut.

## 1. État mesuré

Déploiement réel de `forgeai wizard --ci --backend compose` (stack `minimal`, profil
`minimal-gpu-cuda`), puis inspection Docker :

```
$ curl http://127.0.0.1:16333/readyz     ->  all shards are ready      (le service MARCHE)
$ docker inspect ... .State.Health.Status ->  unhealthy                 (Docker dit le contraire)
$ docker inspect ... .State.Health.Log    ->  exec: "curl": executable file not found in $PATH
```

**Deux défauts indépendants, chacun suffisant à rendre tout healthcheck impossible.**

### D1 — mauvais point de vue : le port hôte utilisé pour une sonde interne
`planner/assemble.py:140-143` **et** `:173-176` construisent
`healthcheck_url = f"http://127.0.0.1:{host_port}{health_path}"`.

Ce champ unique alimente **deux consommateurs dont le point de vue est opposé** :

| Consommateur | S'exécute depuis | Port correct | Ce qu'il reçoit |
|---|---|---|---|
| `deploy/compose.py:219` (sonde post-déploiement) | l'**hôte** | `host_port` | correct |
| `renderers/compose.py:46` (healthcheck Docker) | **dans** le conteneur | `container_port` | **faux** |

Mesuré : qdrant écoute sur **6333** dans le conteneur ; la sonde vise **16333**.

### D2 — le binaire de sonde n'existe pas dans les images
Mesuré dans les images réellement déployées par la stack par défaut :

| Image | `curl` | `wget` | `nc` | `bash` | autre |
|---|---|---|---|---|---|
| `qdrant/qdrant` | **non** | non | non | **oui** | — |
| `ollama/ollama` | **non** | — | — | **oui** | CLI `ollama` |

`renderers/compose.py:39` et `:46` émettent `["CMD","curl","-fsS",...]`, et `:42` émet
`["CMD","nc",...]`. **Aucun des deux binaires n'existe** dans les deux services livrés par défaut.

### Ce que le défaut ne fait PAS — à dire aussi
- Le déploiement **n'est pas bloqué** : `depends_on` n'utilise `service_healthy` que pour openbao
  (`renderers/compose.py:222`), tout le reste est `service_started`.
- Les services **fonctionnent réellement** — vérifié par requête HTTP depuis l'hôte.
- Le verdict de santé de ForgeAI reste **juste**, parce qu'il vient de la sonde **hôte**
  (`deploy/compose.py:218`), qui utilise le bon port. C'est précisément ce qui a masqué le défaut :
  ForgeAI se déclare en bonne santé pendant que Docker affiche `unhealthy`.

Le préjudice réel est donc la **divergence des deux verdicts** : `docker ps` et toute supervision
qui lit l'état Docker voient un service en panne permanente, et toute dépendance future en
`service_healthy` bloquerait indéfiniment.

### Le rendu K3s, lui, est CORRECT
`renderers/k3s.py:291-292` n'extrait que le **chemin** et reconstruit avec `svc.container_port` ;
les sondes `httpGet` sont exécutées par le kubelet, donc **sans binaire dans l'image**. Vérifié
dans le manifeste rendu : `port: 11434` (interne, correct). La bonne conception existe déjà dans
le dépôt — le rendu Compose ne l'a simplement pas suivie.

## 2. Décision de conception, et ce qui a été réfuté

### Réfutation 1 — « corriger seulement le port »
**Insuffisant, et le pire des correctifs** : il produirait une sonde correctement adressée mais
toujours inexécutable (pas de `curl`), donc un défaut identique avec une cause plus difficile à
diagnostiquer. Les deux défauts doivent tomber ensemble.

### Réfutation 2 — « ajouter curl aux images »
Rejeté : ForgeAI ne construit pas les images, il déploie des images **officielles épinglées par
digest** (`SUPPLY-018`). Les modifier détruirait la chaîne d'approvisionnement vérifiable, pour un
bénéfice de confort.

### Réfutation 3 — « ne plus émettre de healthcheck du tout »
Honnête mais appauvrissant : l'utilisateur perdrait tout signal côté Docker. À ne retenir que si
aucune sonde exécutable n'est démontrable.

### Décision
1. **Reconstruire la cible interne** dans le rendu Compose à partir de `container_port` + chemin,
   exactement comme `renderers/k3s.py` le fait déjà. `healthcheck_url` reste **inchangée** pour le
   consommateur hôte, qui en a besoin telle quelle.
2. **Ne plus supposer `curl`.** Mesuré : `bash` est présent dans les deux images livrées, et
   `exec 3<>/dev/tcp/HOTE/PORT` y **fonctionne** (vérifié en exécution). La sonde de repli devient
   donc un test TCP `bash`, strictement meilleur que `curl` : elle réussit là où `curl` échouait,
   et n'échoue que sur des images sans `bash`, cas plus rare que l'absence de `curl`.
3. **Déclarer explicitement** la sonde des services de la stack livrée, via le mécanisme
   `ProbeType` qui existe déjà et n'était jamais alimenté.

## 3. TDAD

- **G1 (ROUGE d'abord)** — le healthcheck rendu ne doit contenir **ni le port hôte**, ni un
  binaire absent de l'image. Sur le code actuel : la cible contient `16333` ⇒ rouge.
- **G2** — la cible interne est reconstruite depuis `container_port` + chemin ; `healthcheck_url`
  (consommateur hôte) est **inchangée** — sans quoi on corrigerait un point de vue en cassant l'autre.
- **G3** — sonde de repli exécutable : le test émis n'invoque pas `curl`/`nc`.
- **G4** — **preuve d'exécution réelle** : après déploiement, `docker inspect` rapporte
  `healthy`. C'est le seul test qui prouve la propriété ; les autres ne valident que le rendu.
- **G5** — le rendu K3s reste inchangé (il était déjà correct) : non-régression.
- **G6** — un `ProbeType` explicitement déclaré prime sur le repli.

Mutation à prouver : remettre `host_port` dans la cible interne → G1 rougit ; remettre `curl` dans
le repli → G3 rougit.

## 4. Critères d'acceptation

- **CA1** un déploiement Compose de la stack par défaut atteint `healthy` sous Docker — prouvé par
  `docker inspect`, pas par lecture du manifeste.
- **CA2** `healthcheck_url` conserve le `host_port` pour la sonde hôte : les deux points de vue
  sont servis correctement et séparément.
- **CA3** aucune sonde émise n'invoque un binaire absent des images livrées par défaut.
- **CA4** rendu K3s inchangé ; suites existantes vertes.
- **CA5** couverture ≥ 85 % ; suite complète verte hors l'échec environnemental documenté de
  `tests/test_proc.py`.

## 5. Preuve par déploiement réel

| | Avant | Après |
|---|---|---|
| `docker inspect .State.Health.Status` | **`unhealthy`** | **`healthy`** |
| dernier code de sonde | `-1` (`exec: "curl": not found`) | **`rc=0`** |

Sondes retenues, **vérifiées en exécution dans les images épinglées** :
- `ollama` → `["ollama","list"]` — la CLI est dans l'image ; renvoie **1** sans serveur (discriminante).
- `vector-store` → HTTP en **builtins bash purs** (`exec 3<>/dev/tcp`, `printf`, `read`, `[[ ]]`).
  Vérifié : `/readyz` → rc=0, chemin inexistant → **échec**. Elle prouve donc la **réponse**
  applicative, pas seulement l'ouverture du port.

## 6. Amendements imposés par la revue d'architecture

La revue a réfuté ma conception initiale sur deux points décisifs :

1. **Déclarer `probe_type=HTTP` aurait re-cassé qdrant** : cette branche appelle toujours `curl`.
   Le service serait resté `unhealthy` avec un diagnostic plus difficile — exactement la
   Réfutation 1 que la story prétendait écarter. Les sondes livrées sont donc des `EXEC`
   explicites, dont l'argv est mesuré comme exécutable dans chaque image.
2. **Un repli TCP aurait créé un faux signal**, et pas seulement un signal faible :
   `deploy/compose.py:226` promeut un `healthy` Docker en `FUNCTIONALLY_READY`, alors que
   `core/models.py:354` établit qu'un port ouvert n'est que `TRANSPORT_READY`. Pour **openbao**,
   dont la santé signifie *coffre descellé*, une sonde TCP passerait **coffre scellé** — donc
   strictement pire que le défaut d'origine. D'où le choix d'une sonde HTTP en builtins bash,
   qui prouve la réponse sans exiger de client HTTP dans l'image.

## 7. Deux défauts d'intégration révélés en chemin

Le champ `probe_type` existait depuis HEALTH-028B mais **n'avait jamais été peuplé de bout en
bout**. Le peupler a fait apparaître deux ruptures que personne n'avait pu rencontrer :
- `ServiceSpec` exige un **tuple** ; JSON ne produit que des listes → `ValueError` au premier
  service déclaré. La validation, fail-closed, a correctement refusé.
- `DeploymentPlan.to_json` ne sérialisait pas l'enum → `plan.json` n'était plus écrit du tout.

C'est le schéma « mécanisme défini mais jamais invoqué », ici au niveau des **données** : un champ
déclaré, validé, rendu — mais dont aucun chemin réel ne s'était jamais servi.

## 8. Reste à traiter, signalé explicitement (hors de ce correctif)

- Les branches `ProbeType.HTTP` (`compose.py:39`) et `ProbeType.TCP` (`:42`) invoquent toujours
  `curl` et `nc`. Elles ne sont pas sur le chemin des stacks livrées, mais un utilisateur qui
  déclare `probe_type=HTTP` sur une image sans `curl` retomberait sur le même défaut.
- Le **repli hérité** (`:46`) construit toujours sa cible depuis le port hôte. Aucun test ne le
  couvrait, et il n'est plus atteint par les stacks livrées.
- **openbao émet deux blocs `healthcheck:`** dans le même mapping (`compose.py:206` puis `:267`) :
  PyYAML garde le dernier, un analyseur plus strict rejetterait. Atteignable via les stacks
  `mlops`/`automatisation`/`tout-en-un`.
