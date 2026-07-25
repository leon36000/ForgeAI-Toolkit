# ADR HEALTH-028A — Contrat de santé non-vacu par service

- **Statut** : Proposé
- **Date** : 2026-07-25
- **Décideurs** : équipe ForgeAI (revue architecture)
- **Finding d'origine** : FAI-U-028 (prouvé)
- **Package d'implémentation ultérieur** : HEALTH-028B (DESIGN_FIRST → IMPLÉMENTATION séparée)

---

## 1. Contexte

### 1.1 Le défaut prouvé

`src/forgeai/deploy/compose.py:65` contient :

```
if all(v == "healthy" for v in status.values()):
```

Or `status` est construit à la ligne de tête de `wait_healthy` (compose.py, fonction `wait_healthy`) par :

```
status = {s.name: "waiting" for s in plan.services if s.healthcheck_url}
```

Lorsque **aucun** service du plan ne porte de `healthcheck_url`, `status == {}`. En Python, `all([]) == True` : la boucle d'attente sort immédiatement et `wait_healthy` retourne `{}` — le déploiement est déclaré **healthy sans qu'aucune sonde n'ait été exécutée**. C'est un **faux READY vacu** : le système affirme une propriété (tous les services sont sains) sur un ensemble vide de preuves.

### 1.2 Cause structurelle

`ServiceSpec` (`src/forgeai/core/models.py:89`) n'expose qu'un seul champ de santé :

```
healthcheck_url: Optional[str] = None
```

Il n'existe aucune notion de :

- **santé requise** : rien ne distingue un service critique (LLM, coffre de secrets) d'un service auxiliaire ;
- **type de sonde** : `healthcheck_url` ne couvre que HTTP ; un service n'exposant que TCP (base de données, coffre scellé) n'a aucun contrat exprimable ;
- **niveau de préparation** : rien ne distingue « le port répond » (transport) de « l'application répond correctement » (fonctionnel) ;
- **politique d'absence** : l'absence de sonde est silencieusement équivalente à « sain », ce qui est l'inverse du défaut sûr.

Le durcissement anti-injection existant (`ServiceSpec.__post_init__` → `_rejeter_caracteres_de_controle`, models.py) valide déjà les scalaires ; tout nouveau champ chaîne DOIT passer par le même rejet.

### 1.3 Portée de ce document

Ce package est **DESIGN_FIRST** : il fixe le contrat et la sémantique. Aucune implémentation n'est livrée ici ; HEALTH-028B implémentera et prouvera les critères d'acceptation de la section 8.

---

## 2. Décision

### 2.1 Extension du contrat `ServiceSpec`

Quatre champs ajoutés (illustration de types, pas d'implémentation) :

```python
health_required: bool = False
probe_type: ProbeType = ProbeType.NONE      # enum sérialisable : "http" | "tcp" | "exec" | "none"
probe_target: Optional[str] = None          # URL http, "host:port" tcp, ou commande exec
health_timeout_s: Optional[float] = None    # None = défaut de l'évaluateur
```

Règles de cohérence (validées à la construction, en plus de `_rejeter_caracteres_de_controle`) :

- `probe_type == NONE` **implique** `probe_target is None` ;
- `probe_type != NONE` **implique** `probe_target` non vide ;
- `health_required == True` et `probe_type == NONE` est une **combinaison invalide** : rejetée dès `__post_init__` (fail-fast, jamais différée au déploiement) ;
- `healthcheck_url` (existant) reste accepté comme **raccourci legacy** : s'il est renseigné et que `probe_type == NONE`, il est normalisé en `probe_type=HTTP, probe_target=healthcheck_url` (voir §5).

`ProbeType` est un `enum.Enum` à valeurs chaînes (`str, Enum`) afin de rester sérialisable en JSON via `dataclasses.asdict` + conversion de valeur, sans dépendance externe.

### 2.2 États de santé

L'évaluation d'un service produit **exactement un** état terminal ou transitoire :

| État | Sens | Terminal ? |
|---|---|---|
| `waiting` | sonde pas encore concluante | non |
| `transport_ready` | le transport répond (TCP ouvert, ou handshake réussi) — **sans preuve applicative** | oui |
| `functionally_ready` | l'application répond correctement (HTTP 2xx/3xx attendu, ou `exec` exit 0) | oui |
| `unknown` | aucune sonde définie **et** service non critique | oui |
| `failed` | sonde définie mais en échec au-delà du timeout, **ou** sonde absente sur service `health_required=True` | oui |

**Règle d'adéquation sonde/état (non contournable)** :

- `probe_type == TCP` ⇒ l'état terminal maximal atteignable est `transport_ready`. Une sonde TCP **ne peut JAMAIS** produire `functionally_ready` : un port ouvert ne prouve rien de l'application.
- `probe_type == HTTP` ou `EXEC` ⇒ l'état terminal de succès est `functionally_ready`.
- `probe_type == NONE` ⇒ `unknown` (non critique) ou `failed` (critique) — **jamais** un état `*_ready`.

### 2.3 Règle anti-vacuité (interdiction du `all([]) == True`)

L'évaluateur agrégé (successeur de `wait_healthy`) **DOIT** :

1. Construire la table d'états sur **tous** les services du plan, pas seulement ceux qui ont une sonde : un service sans sonde reçoit `unknown` (non critique) ou `failed` (critique), jamais une absence silencieuse ;
2. Refuser le succès sur ensemble vide : un plan dont la table est vide, ou dont **aucun** service n'atteint un état `*_ready`, **ne peut pas** être déclaré sain ;
3. Définir le succès agrégé comme : **chaque** service est dans un état terminal **et** aucun service n'est `failed` **et** au moins un service est `transport_ready` ou `functionally_ready`. `unknown` n'est acceptable que pour les services non critiques et ne compte pas comme preuve.

Formellement, le succès exige :

```
∀ s ∈ plan : état(s) ∈ {transport_ready, functionally_ready, unknown}
∧ ∃ s ∈ plan : état(s) ∈ {transport_ready, functionally_ready}
∧ ¬∃ s ∈ plan : état(s) = failed
```

`all(...)` seul est **insuffisant** ; la condition existentielle (point 2) est obligatoire.

### 2.4 Politique d'absence par criticité

| `health_required` | `probe_type` | État terminal imposé |
|---|---|---|
| `False` | `NONE` | `unknown` — toléré, signalé dans le rapport d'état |
| `False` | `TCP` | `transport_ready` si succès, `failed` si timeout |
| `False` | `HTTP`/`EXEC` | `functionally_ready` si succès, `failed` si timeout |
| `True` | `NONE` | **interdit à la construction** (§2.1) — et, défense en profondeur, traité comme `failed` si jamais rencontré à l'évaluation |
| `True` | `TCP` | `transport_ready` minimum exigé ; `failed` si timeout |
| `True` | `HTTP`/`EXEC` | `functionally_ready` exigé ; `failed` si timeout |

L'absence de sonde ne produit donc **jamais** un état `*_ready`.

---

## 3. Machine d'états d'évaluation

```
                 ┌─────────┐
                 │ waiting │ (état initial de tout service sondé)
                 └────┬────┘
        ┌─────────────┼──────────────────────┐
        │ sonde TCP   │ sonde HTTP/EXEC      │ sonde NONE
        ▼             ▼                      ▼
 ┌──────────────┐  ┌────────────────────┐   ┌─────────────┐
 │transport_    │  │ functionally_ready │   │   unknown   │ (non critique)
 │  ready       │  └────────────────────┘   └─────────────┘
 └──────────────┘                           ┌─────────────┐
        │ échec après timeout               │   failed    │ (critique)
        ▼                                   └─────────────┘
 ┌─────────────┐
 │   failed    │
 └─────────────┘
```

Obligations de l'évaluateur (successeur de `wait_healthy`, compose.py) :

1. **Initialisation totale** : la table d'états contient **chaque** service du plan, initialisé à `waiting` si une sonde existe, sinon directement à `unknown`/`failed` selon la politique d'absence (§2.4). Un service sans sonde n'entre **jamais** dans `waiting`.
2. **Sortie de boucle** : la boucle d'attente ne se termine en succès que si la condition agrégée du §2.3 est satisfaite — y compris sa clause existentielle. Une table vide ou uniformément `unknown` prolonge l'attente jusqu'au timeout puis conclut en échec explicite (`DeployError` avec la table complète).
3. **Timeout** : tout service encore `waiting` à l'échéance passe à `failed`. Le rapport d'erreur liste l'état exact de **chaque** service (comportement actuel conservé et étendu).
4. **Monotonie** : un état terminal n'est jamais révisé ; `transport_ready` ne « monte » pas vers `functionally_ready`.
5. **Liste vide** : un plan sans aucun service, ou dont toutes les sondes sont absentes, conclut `unknown`/`failed` selon criticité — **jamais** sain. C'est le point exact du défaut compose.py:65, désormais interdit par construction.

---

## 4. Impact sur le code existant

### 4.1 `src/forgeai/core/models.py` (`ServiceSpec`)

- Ajout des quatre champs du §2.1, avec valeurs par défaut choisies pour la rétro-compatibilité (§5) : `health_required=False`, `probe_type=NONE`, `probe_target=None`, `health_timeout_s=None`.
- `__post_init__` : extension des rejets `_rejeter_caracteres_de_controle` à `probe_target` ; ajout des validations de cohérence du §2.1 ; normalisation du raccourci legacy `healthcheck_url` (§5).
- Sérialisation : le dataclass reste `frozen` ; `dataclasses.asdict` + JSON restent fonctionnels (enum à valeurs chaînes, `Optional` uniquement). Un test de round-trip `asdict → json.dumps → json.loads` est exigé (§8).

### 4.2 `assemble.py` (peuplement du contrat)

Le module qui instancie les `ServiceSpec` DOIT peupler explicitement le contrat par brique :

- services critiques de la stack (LLM/Ollama, coffre openbao, routeur liteLLM) : `health_required=True` avec une sonde `HTTP` quand un endpoint applicatif existe, `TCP` sinon (avec la limitation `transport_ready` assumée et documentée) ;
- openbao : la sonde applicative tolère les codes « scellé / non initialisé » (paramètres `standbyok/sealedcode/uninitcode`, déjà traités côté renderer k3s) — le contrat transporte l'URL, l'évaluateur HTTP accepte les codes configurés ;
- services auxiliaires : `health_required=False`, sonde si disponible, sinon `NONE` ⇒ `unknown` assumé.

Aucune brique critique ne peut rester à `probe_type=NONE` sans que la construction lève une erreur (§2.1).

### 4.3 `validation.py`

- Ajout d'une validation de plan : tout service `health_required=True` possède une sonde cohérente **avant** le rendu ; la validation de plan rejette un plan dont la table d'états serait structurellement incapable de satisfaire la clause existentielle du §2.3 (aucun service sondé dans tout le plan) — sauf plan explicitement dégradé accepté par l'appelant (option documentée, jamais implicite).
- La validation reste pure (aucune sonde réseau exécutée à cette étape).

### 4.4 `src/forgeai/deploy/compose.py` (`wait_healthy`)

- La ligne compose.py:65 est remplacée par l'évaluation agrégée du §2.3 (implémentation en HEALTH-028B). Le présent ADR impose la sémantique, pas le diff.

---

## 5. Rétro-compatibilité

- Les plans existants construits avec seul `healthcheck_url` continuent de fonctionner : `__post_init__` normalise `healthcheck_url` en `probe_type=HTTP, probe_target=<url>` quand `probe_type` n'est pas fourni. Comportement d'évaluation inchangé pour ces services (`functionally_ready` attendu).
- Les services existants **sans** `healthcheck_url` changeant de sémantique : ils passent de « implicitement sains » (le défaut) à `unknown`. C'est un **changement de comportement volontaire et documenté** : `unknown` ne bloque pas le succès agrégé pour un service non critique, mais il ne contribue plus à la preuve de santé, et il apparaît dans le rapport d'état.
- Défaut sûr : tout champ omis retombe sur la politique la plus prudente (`health_required=False` ⇒ `unknown` ; jamais `*_ready` sans sonde).
- Aucune migration de données : `ServiceSpec` est construit en mémoire à chaque plan ; la sérialisation enrichie est additive.

---

## 6. Conséquences

### Positives

- Élimination du faux READY vacu (FAI-U-028) par construction, pas par convention.
- Distinction explicite transport/fonctionnel : fini les « healthy » de services TCP dont l'application est en réalité en échec.
- Criticité déclarée : l'absence de sonde sur un service critique devient une erreur de construction, détectée avant tout déploiement.
- Rapport d'état exhaustif : chaque service du plan a un état, y compris `unknown`.
- Couverture de tous les renderers : le contrat vit dans le modèle partagé (models.py), pas dans un renderer.

### Négatives / coûts

- `ServiceSpec` gagne quatre champs ; les constructeurs existants doivent être audités (assemble.py) pour peupler la criticité.
- Changement observable : un plan sans aucune sonde, auparavant « healthy » immédiat, échouera désormais au timeout avec un état explicite. C'est le but, mais cela peut révéler des plans historiquement incomplets (à traiter en peuplant leurs contrats, pas en contournant la règle).
- Légère complexité d'évaluation (machine à cinq états vs. booléen), jugée acceptable au regard du risque éliminé.

### Alternatives rejetées

1. **Garde locale minimale** (`if not status: raise DeployError` à compose.py:65) : corrige le cas vide mais laisse intacts les autres manques (pas de criticité, pas de transport/fonctionnel, absence silencieuse par service). Insuffisant au regard du finding.
2. **`health_required` implicite** (tout service sans sonde est `failed`) : trop strict, casse les services auxiliaires légitimement sans sonde ; frein à l'adoption.
3. **Sondes déclarées au niveau renderer** (k3s/compose) plutôt que dans le modèle : duplique le contrat par cible de rendu et laisse `wait_healthy` sans source de vérité. Rejeté au profit du modèle partagé.
4. **Traiter TCP comme fonctionnel** : rejeté ; un port ouvert ne prouve pas l'application (contre-exemple : coffre scellé écoutant sur son port).

---

## 7. Sérialisation et validation (engagements)

- `ProbeType` sérialisé par sa valeur chaîne (`"http"`, `"tcp"`, `"exec"`, `"none"`).
- `dataclasses.asdict(spec)` suivi de `json.dumps`/`json.loads` fonctionne sans encodeur custom (les valeurs d'enum `str, Enum` sont des `str`).
- Tout champ chaîne nouveau (`probe_target`) passe `_rejeter_caracteres_de_controle` en `__post_init__`, à l'identique des champs existants — l'anti-injection SEC-YAML-INJECT (#151) reste intégrale.
- Aucun secret dans le contrat : `probe_target` est une URL, un `host:port` ou une commande de sonde, jamais un identifiant.

---

## 8. Critères d'acceptation (vérifiables par HEALTH-028B)

Le package d'implémentation DEVRA prouver, par tests :

1. **Anti-vacuité** : un plan dont la table d'états est vide, ou dont aucun service n'atteint `transport_ready`/`functionally_ready`, n'est **jamais** déclaré sain ; le succès exige la clause existentielle du §2.3. Régression directe de compose.py:65 : `all([]) == True` ne peut plus produire un succès.
2. **Criticité** : un service `health_required=True` sans sonde est rejeté à la construction de `ServiceSpec` ; à l'évaluation, toute absence de sonde sur service critique conclut `failed` (défense en profondeur).
3. **TCP-only** : un service sondé en TCP atteint au maximum `transport_ready`, jamais `functionally_ready`, même si le port répond.
4. **Politique d'absence** : un service non critique sans sonde termine en `unknown` ; `unknown` seul ne suffit pas au succès agrégé et n'empêche pas le succès si d'autres services prouvent leur santé.
5. **Timeout exhaustif** : à l'échéance, tout service `waiting` devient `failed` et le `DeployError` rapporte l'état de **chaque** service du plan (y compris les `unknown`).
6. **Sérialisation** : round-trip `asdict → json → dict` d'un `ServiceSpec` enrichi sans erreur ni perte ; `probe_target` à caractères de contrôle rejeté en `__post_init__`.
7. **Rétro-compatibilité** : un `ServiceSpec` construit avec seul `healthcheck_url` est normalisé en sonde HTTP et évalué `functionally_ready` en cas de succès, comme avant.

---

## 9. Références

- Finding FAI-U-028 (faux READY vacu), défaut : `src/forgeai/deploy/compose.py:65`, champ insuffisant : `src/forgeai/core/models.py:89`.
- Anti-injection existante : `ServiceSpec.__post_init__` / `_rejeter_caracteres_de_controle` (SEC-YAML-INJECT, #151).
- Probes openbao tolérantes au scellement : renderer k3s (`_probes_block`) et sidecar/unsealer (`forgeai.renderers._openbao`).
