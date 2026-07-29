# ADR D2 — Brancher l'ADOPTION au déploiement

**Statut** : Proposé
**Références** : D1 (`network/discover.py` livré), FAI-0006 (pattern d'injection additive par paramètre optionnel), HEALTH-028A (contrat de santé non-vacu), SEC-YAML-INJECT (validation à la source dans `__post_init__`)

---

## 1. Point d'insertion : la construction du PLAN (option a)

**Décision : la décision « adopter vs déployer » est prise pendant la construction du plan. Le plan sort annoté ; renderers, santé, secrets et CLI ne font qu'exécuter une décision déjà prise.**

Justification : le plan est l'unique source de vérité consommée par les deux renderers, `render_litellm_config`, `bootstrap_secrets`, le contrat de santé et le rapport JSON — décider en amont est le seul point où une seule décision alimente tous les consommateurs sans changer aucune de leurs signatures.

**Ce que (b) — le rendu — casserait** : la décision devrait être implémentée deux fois (`render_compose` ET `render_k3s`), avec un risque de divergence structurel entre les deux chemins, et le plan continuerait à mentir aux autres consommateurs — `render_litellm_config` câblerait vers un service absent du manifeste, le rapport CLI compterait comme « déployé » un service omis, et les NetworkPolicies symétriques référenceraient un workload inexistant.

**Ce que (c) — le déploiement — casserait** : l'artefact écrit sur disque décrirait une infrastructure que nous ne gérons pas, donc tout `compose_down` / suppression de manifeste ultérieur deviendrait une commande potentiellement destructive sur l'existant — violation directe de la règle produit absolue ; de plus, filtrer des documents YAML après rendu est fragile (multi-documents, références croisées par nom) et exigerait de modifier les signatures de `compose_up`/`k3s_apply`, ce que la contrainte d'API stable interdit.

---

## 2. Structure de données : un champ unique sur `ServiceSpec`

**Décision : ajout de `adopted_endpoint: Optional[str] = None` à `ServiceSpec`, déclaré en fin de dataclass (après les champs santé), jamais en positionnel.**

- **Un seul champ, pas de booléen `adopted` séparé** : la présence de l'endpoint EST le marqueur d'adoption — deux champs pourraient se contredire (`adopted=True` avec `endpoint=None`), un seul ne le peut pas.
- **Défaut `None` = « déployé par nous » = comportement actuel** : compatibilité totale avec les appelants et les tests hérités, selon le précédent établi par les champs RES-012B et santé ajoutés avec défauts.
- **Champ sur `ServiceSpec` plutôt que structure séparée** : une `AdoptionMap` externe devrait être passée à `render_compose`, `render_k3s`, `render_litellm_config`, à la santé et au CLI (cinq signatures modifiées, risque de désynchronisation plan/adoption), tandis que le champ voyage avec le service et que `dataclasses.replace` respecte le gel de la dataclass.
- **Validation dans `__post_init__`** (cohérent avec SEC-YAML-INJECT) : rejet des caractères de contrôle et forme stricte `hôte:port` avec port numérique, car cette valeur atteint en brut le YAML et les variables d'environnement des dépendants.

Le rapport JSON écrit par `cli.py` gagne une clé `adoptes: [{name, endpoint, via}]` : la preuve de détection (`via` : binaire/port/conteneur) relève de l'audit et du message à l'utilisateur, elle n'a pas à vivre dans `ServiceSpec`.

---

## 3. Raccordement : le nom du service reste la clé, seule la résolution change

**Contrat fondamental : un dépendant référence toujours sa dépendance par le NOM du service du plan ; l'adoption ne change que la résolution de ce nom, jamais la clé de configuration ni le graphe `depends`.** Une adoption qui change la clé casserait chaque brique consommatrice ; une adoption qui ne change que la valeur est transparente.

**Compose (cible de la tranche minimale)** : le renderer omet le workload adopté (aucune section `redis:` dans le fichier) et, pour chaque dépendant, injecte l'endpoint traduit en forme atteignable depuis un conteneur : `host.docker.internal:<port découvert>`, plus `extra_hosts: ["host.docker.internal:host-gateway"]` sur le dépendant — forme déterministe, stdlib pure, valide sur Linux/Docker ≥ 20.10. Le port utilisé est celui de l'endpoint découvert, pas le `host_port` du catalogue : **l'existant prime sur le catalogue**.

**K3s (design fixé, hors tranche minimale)** : le renderer émettra un Service ClusterIP **sans selector** portant le nom du service, plus un `Endpoints` manuel pointant vers IP:port découverts — les dépendants gardent `<nom>:<container_port>` strictement inchangé. Blocage assumé : l'inventaire rend aujourd'hui `127.0.0.1:<port>`, invalide comme cible d'Endpoints depuis un pod ; tant que l'inventaire ne rapporte pas une IP de nœud joignable, `render_k3s` **refuse** tout plan contenant un service adopté (erreur explicite) plutôt que de rendre un câblage faux.

**Re-sonde au déploiement** : la détection a eu lieu au moment du plan ; au moment du déploiement, chaque service adopté est re-sondé (connexion TCP stdlib sur l'endpoint) et un échec bloque le READY si `health_required` — cohérent avec HEALTH-028A : l'adoption n'est pas un blanc-seing de santé, et un service adopté mort ne produit jamais un READY vacu.

**Secrets** : pour un service adopté, `bootstrap_secrets` ne génère rien ; les credentials de l'existant (ex. mot de passe du postgres détecté) sont demandés à l'utilisateur — générer un secret pour une brique qu'on ne déploie pas créerait une fausse croyance de contrôle sur celle-ci.

---

## 4. Sécurité / refus : jamais d'adoption implicite

- **R1 — Adoption explicite uniquement** : un service détecté n'est marqué adopté que sur choix de l'utilisateur (prompt du wizard listant nom, endpoint, `via` ; ou flag non-interactif `--adopt <nom>` / `--adopt-all`). Justification : adopter en aveugle peut brancher litellm sur le redis de production d'un autre usage.
- **R2 — Conflit sans décision = échec net** : en non-interactif, un service du plan détecté sur le port visé sans `--adopt` produit une `DeployError` nommant le service, l'endpoint et les deux issues (adopter, ou changer `host_port`) ; rien n'est démarré, rien n'est écrit. Justification : déployer par-dessus échouerait au bind ou écraserait l'existant — l'échec net est
**5a. Tranche minimale prouvable (fichiers modifiés)**  
- `src/models/spec.py` : ajout du champ `adopted_endpoint: Optional[str] = None` avec validation `__post_init__` (format `hôte:port` uniquement).  
- `src/plan/plan.py` : lors de la construction du plan, propagation du endpoint pour les services passés via `--adopt`, marquage `adopted=True` (via présence du endpoint).  
- `src/cli.py` : ajout de l’argument `--adopt` (répétable, format `nom=endpoint`), conflit non arbitré → `SystemExit`.  
- `src/rendering/compose.py` :  
  - filtrage des services adoptés du bloc `services:` (pas de définition de container).  
  - injection de `host.docker.internal:<port découvert>` dans les variables d’environnement des dépendants à la place du `host_port` catalogue.  
  - ajout global `extra_hosts: ["host.docker.internal:host-gateway"]`.  
- `src/rendering/k3s.py` : levée d’une `AdoptionRefuseeK3S` si un service du plan a `adopted_endpoint` non `None`.  
- `tests/test_adoption.py` : nouveau fichier contenant tous les critères d’acceptation.  

**5b. Critères d’acceptation testables**  
- CA-1 : étant donné un plan avec un service adopté (`adopted_endpoint = "localhost:4000"`), quand on génère le `docker-compose.yml`, alors le service adopté est **totalement absent** du dictionnaire `services`.  
- CA-2 : étant donné un service dépendant B qui référence le service adopté A (via le catalogue), quand A est adopté, alors dans le compose le conteneur B reçoit la variable d’environnement pointant vers `host.docker.internal:<port>` (issue de l’`adopted_endpoint`) **et non** vers le `host_port` du catalogue.  
- CA-3 : quand le plan contient au moins un service adopté, le fichier compose produit contient `extra_hosts` avec l’entrée `host.docker.internal:host-gateway`, quel que soit le nombre d’adoptés.  
- CA-4 : quand on tente un rendu K3s avec un service adopté, le renderer lève une exception de type `AdoptionRefuseeK3S` avec un message explicite, avant toute écriture.  
- CA-5 : étant donné un `ServiceSpec` instancié avec `adopted_endpoint = "mauvais_format"`, la construction (`__post_init__`) lève une `ValueError` contenant le motif de rejet.  
- CA-6 : comportement par défaut (`adopted_endpoint = None`) : le plan, le compose et le k3s restent strictement identiques à la version avant l’introduction de la feature (test de non‑régression par comparaison d’empreinte YAML).  
- CA-7 : appel CLI avec deux fois `--adopt` pour le même service (`--adopt svc1=... --adopt svc1=...`), le programme termine avec un code d’erreur non nul et un message indiquant le conflit.  

**5c. Ce que la tranche NE fait PAS**  
- **Pas de re‑sonde TCP au déploiement** : la vérification qu’un service adopté est effectivement vivant est laissée à l’étape de santé (hors tranche).  
- **Pas d’intégration avec un catalogue externe** : l’endpoint est fourni manuellement par l’opérateur, aucune découverte automatique n’est activée dans cette tranche.  
- **Aucun support K3s au‑delà du refus** : le renderer K3s ne tente aucune adaptation, il bloque simplement pour éviter un manifeste inexploitable.  
- **Pas d’interface utilisateur (UI) ni de modification du contrat de santé** : les health‑checks existants ne sont pas modifiés ; un service adopté mort n’entraînera pas de READY, mais cela ne fait pas partie du code livré ici.  
- **Aucune modification des briques non détectables** (CI, report JSON, autres) : leur comportement reste inchangé, elles consommeront le plan annoté tel quel dans les itérations suivantes.
