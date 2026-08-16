# PACK DE REVUE (v3) — HEALTH-028A DESIGN_FIRST, ADR uniquement (aucun code modifié)
Ce package DESIGN_FIRST ne modifie AUCUN fichier source ; le SEUL objet de revue est l'ADR ci-dessous.
Cette version INTÈGRE la revue précédente : http_success_codes configurables, exec=argv liste (pas de shell),
précédence probe_type vs healthcheck_url legacy, validation health_timeout_s>0. Évalue le DESIGN final.

```markdown
# ADR HEALTH-028A — Contrat de santé non-vacu par service

- **Statut** : Proposé
- **Décideurs** : équipe architecture ForgeAI
- **Référence** : finding FAI-U-028 (prouvé), package d'implémentation ultérieur HEALTH-028B
- **Nature** : DESIGN_FIRST — ce document fixe le contrat ; aucune implémentation n'est livrée ici.

---

## 1. Contexte

### 1.1 Le défaut prouvé

`src/forgeai/deploy/compose.py:65` :

```python
if all(v == "healthy" for v in status.values()):
```

Quand `status` est le dictionnaire vide `{}` — c'est-à-dire quand **aucun** service du plan ne porte
de `healthcheck_url` — `all([])` s'évalue à `True`. Le déploiement est alors déclaré **healthy sans
qu'aucune sonde ait été exécutée** : c'est un faux READY par vacuité universelle. Le succès du
déploiement ne dépend plus de l'état réel des briques mais d'un artefact algébrique de `all()`.

### 1.2 Cause structurelle

`src/forgeai/core/models.py:89` : `ServiceSpec` ne porte qu'un champ
`healthcheck_url: Optional[str] = None`. Le modèle ne sait exprimer :

- ni qu'un service est **critique** (sa santé conditionne le READY global) ;
- ni le **type** de vérification (HTTP, TCP, commande interne) ;
- ni la distinction entre **transport** (le port répond) et **fonctionnel** (l'application répond
  correctement) ;
- ni une **politique d'absence** (que vaut la santé d'un service sans sonde ?).

Le renderer k3s (`src/forgeai/renderers/k3s.py`) connaît déjà des services internes
(`_INTERNAL_SERVICES` : redis, qdrant, immudb, openbao, postgres, tei) dont plusieurs n'ont pas de
`healthcheck_url` HTTP exploitable — exactement la population qui produit le `status == {}` vacu.

### 1.3 Exigences

1. Interdire structurellement le READY vacu (`all([]) == True` ne doit plus pouvoir signifier
   « sain »).
2. Distinguer criticité, type de probe, et niveau de préparation (transport vs fonctionnel).
3. Rester sérialisable (dataclass / `asdict` / JSON) et passer par la validation anti-injection
   existante (`_rejeter_caracteres_de_controle`, models.py).
4. Préserver la rétro-compatibilité des plans existants avec un défaut **sûr**.

---

## 2. Décision

### 2.1 Enums introduits (sérialisables en valeurs `str`)

```python
class ProbeType(Enum):
    HTTP = "http"
    TCP = "tcp"
    EXEC = "exec"
    NONE = "none"

class HealthState(Enum):
    FUNCTIONALLY_READY = "functionally_ready"  # réponse applicative correcte
    TRANSPORT_READY = "transport_ready"        # transport joignable, applicatif non prouvé
    UNKNOWN = "unknown"                        # aucune preuve disponible (pas de sonde)
    FAILED = "failed"                          # preuve d'échec ou contrat violé
```

### 2.2 Extension de `ServiceSpec` (signature illustrative, pas une implémentation)

```python
health_required: bool = False
probe_type: Optional[ProbeType] = None        # None = dérivation depuis healthcheck_url (§2.4)
probe_target: Optional[Union[str, tuple[str, ...]]] = None  # str pour http/tcp ; argv pour exec (§2.6)
http_success_codes: tuple[int, ...] = (200,)  # codes HTTP acceptés comme fonctionnels (§2.5)
health_timeout_s: float = 5.0                 # > 0 obligatoire (§2.7)
health_interval_s: float = 5.0                # > 0 obligatoire
health_retries: int = 12                      # > 0 obligatoire
```

### 2.3 Règle anti-vacuité (règle centrale, non contournable)

- Une liste de probes **vide** s'évalue en `UNKNOWN` pour un service `health_required=False`, en
  `FAILED` pour un service `health_required=True`. **Jamais** healthy.
- Toute agrégation de verdicts DOIT contenir une garde explicite du cas vide (du type
  `if not verdicts: return UNKNOWN`). L'usage de `all(...)` sur une collection potentiellement vide
  est interdit comme test de santé globale ; il remplace `all(v == "healthy" ...)` de
  compose.py:65 par un test sur une collection **prouvée non vide**.
- Le verdict global `READY` exige au moins un service évalué : un déploiement de zéro service
  sondé est `UNKNOWN`, jamais `READY`.

### 2.4 Précédence du raccourci legacy `healthcheck_url`

`healthcheck_url` (models.py:89) est conservé comme **raccourci** de compatibilité :

1. **`probe_type` explicite prime.** Quand `probe_type` est fourni, il définit seul le type de
   sonde ; `probe_target` est la cible.
2. **Dérivation en l'absence de `probe_type`.** Si `probe_type is None` et `healthcheck_url` est
   renseigné, le contrat effectif est `probe_type=HTTP` + `probe_target=healthcheck_url` avec les
   défauts `(200,)`, timeout/intervalle/retries par défaut.
3. **Conflit explicite ⇒ erreur de validation, fail-fast, jamais silencieux.** Exemples de
   conflits refusés (levée d'erreur à la construction/validation, comme
   `_rejeter_caracteres_de_controle`) : `healthcheck_url` renseigné avec `probe_type=TCP` ;
   `healthcheck_url` renseigné avec `probe_type=NONE` ; `probe_type=HTTP` sans cible ni
   `healthcheck_url`. Un conflit détecté n'est jamais « résolu » par une priorité implicite : il
   est **rejeté**.

### 2.5 Codes de succès HTTP configurables

- `http_success_codes: tuple[int, ...]`, **défaut `(200,)`**, tuple explicite de codes entiers
  (validation : tuple non vide, chaque code ∈ [100, 599]).
- Sémantique : `FUNCTIONALLY_READY` ⇔ la sonde HTTP obtient un code **∈ `http_success_codes`**.
  Un code 2xx autre que ceux listés, ou tout autre code, n'est **pas** fonctionnel.
- Cas documenté — **openbao** : selon sa configuration, l'endpoint de santé d'un openbao descellé
  peut répondre 200, mais aussi 429 (standby), 472, 473, 501 (non initialisé) ou 503 (scellé). Le
  contrat DOIT permettre de déclarer par exemple
  `http_success_codes=(200, 429, 472, 473, 501, 503)` quand la politique retenue est « joignable
  et répond selon son état de sceau », ou `(200,)` quand la politique est « descellé et actif ».
  C'est une décision de plan (assemble.py), pas du moteur : le moteur applique la liste, point.
- Choix du tuple explicite plutôt qu'une plage (« 2xx ») : précision, sérialisation JSON triviale,
  et possibilité d'exprimer des ensembles non contigus (cas openbao).

### 2.6 Sonde `exec` : ARGV, jamais de shell

- Pour `probe_type=EXEC`, `probe_target` est **`tuple[str, ...]`** : une argv (ex.
  `("pg_isready", "-U", "forge")`), exécutée **sans shell** — cohérent avec la posture
  0-injection-shell du produit : **aucun `shell=True`, aucune chaîne de commande interpétée**.
- Une chaîne `str` comme cible exec est **interdite** et refusée à la validation (fail-fast).
  Une argv vide est refusée.
- Chaque élément de l'argv passe `_rejeter_caracteres_de_controle` (comme `command` déjà validé
  dans `ServiceSpec.__post_init__`).
- Pour `HTTP` et `TCP`, `probe_target` reste une **chaîne** (URL pour http ; `host:port` pour tcp).
- Verdict exec : code de sortie 0 ⇒ `FUNCTIONALLY_READY` (une sonde exec exprime un test
  applicatif) ; code non nul ou timeout ⇒ échec de tentative.

### 2.7 Validation des temporisations

- `health_timeout_s`, `health_interval_s`, `health_retries` : **strictement positifs (> 0)**.
  Une valeur ≤ 0 lève une erreur de validation à la construction (même style que
  `_rejeter_caracteres_de_controle`), jamais un clamp silencieux.

### 2.8 Politique d'absence par criticité

| Situation | Verdict service |
|---|---|
| `health_required=True`, aucune probe effective (NONE ou cible absente) | `FAILED` (jamais healthy) — et validation du plan en erreur (§4.3) |
| `health_required=False`, aucune probe | `UNKNOWN` (jamais healthy, ne bloque pas READY) |
| Probe présente, critère non atteint après `health_retries` épuisés | `FAILED` |

---

## 3. Machine d'états d'évaluation

### 3.1 Transitions par tentative

```
                 ┌─────────────┐
   début ──────► │  évaluation  │
                 └──────┬──────┘
        ┌───────────────┼───────────────────────────┐
        ▼               ▼                           ▼
   probe absente    tentative probe           critère atteint
        │               │                           │
        ▼               ▼                           ▼
  required ?      échec + retries            HTTP : code ∈ http_success_codes
   ├─ True          restants ?                ⇒ FUNCTIONALLY_READY
   │  ⇒ FAILED     ├─ oui ⇒ nouvelle         TCP  : connexion établie
   └─ False        │    tentative             ⇒ TRANSPORT_READY (plafond)
      ⇒ UNKNOWN    └─ non ⇒ FAILED           EXEC : exit 0 ⇒ FUNCTIONALLY_READY
```

### 3.2 Invariants du moteur

1. **TCP ⇒ plafond `TRANSPORT_READY`.** Une sonde TCP ne produit **jamais**
   `FUNCTIONALLY_READY`, même en cas de succès répété. Un port ouvert ne prouve pas
   l'application.
2. **HTTP ⇒ double seuil.** Connexion TCP établie mais code hors `http_success_codes` :
   l'état courant est au mieux `TRANSPORT_READY` et la tentative est un échec fonctionnel.
3. **Garde anti-vacuité avant toute agrégation** : collection vide ⇒ `UNKNOWN` (ou `FAILED` si
   un service requis est concerné), jamais healthy. Remplace compose.py:65.
4. **Fail-fast global** : `FAILED` d'un service `health_required=True` termine l'attente en
   échec sans attendre les autres services.

### 3.3 Verdict global de `wait_healthy`

- `READY` ⇔ **au moins un service évalué** ET tous les services `health_required=True` sont
  `FUNCTIONALLY_READY` ET aucun service n'est `FAILED`.
- Conséquence assumée : un service critique déclaré en TCP-only rend READY **inatteignable** —
  c'est voulu : le plan doit alors soit doter le service d'une sonde HTTP/EXEC, soit le déclarer
  `health_required=False`. La politique est explicite et visible dans le plan, jamais implicite.
- Les services non requis en `UNKNOWN` n'empêchent pas READY (ils ne peuvent pas non plus le
  fabriquer : READY exige au moins un requis fonctionnel, ou — politique minimale — au moins un
  service sondé non vide ; le point fixe est : **jamais READY sur ensemble vide**).

---

## 4. Impact sur le code existant

### 4.1 `src/forgeai/core/models.py`

- Ajout des enums `ProbeType`, `HealthState` (valeurs `str` ⇒ sérialisation JSON directe via
  `asdict` + valeur d'enum).
- Ajout des champs §2.2 à `ServiceSpec` avec **défauts sûrs** (dataclass frozen : champs avec
  défaut, en queue, pour ne pas casser les constructions positionnelles existantes).
- Extension de `__post_init__` : `_rejeter_caracteres_de_controle` sur `probe_target` (chaîne) ou
  chaque élément d'argv (tuple) ; validations §2.4 (conflits), §2.5 (codes ∈ [100,599], tuple non
  vide), §2.6 (type de cible selon probe_type), §2.7 (> 0).
- Round-trip `asdict`/JSON garanti : enums en valeurs, tuples (pas de listes mutables) à la
  construction.

### 4.2 `assemble.py` (peuplement du contrat par brique)

Chaque brique du profil Minimal reçoit un contrat explicite au montage du plan, par exemple :

- openbao : HTTP avec `http_success_codes` déclarés selon la politique de sceau retenue
  (§2.5) — décision de plan documentée, pas implicite ;
- postgres : EXEC `("pg_isready", ...)` (argv) ;
- redis/qdrant/tei : TCP (⇒ plafond `TRANSPORT_READY`) ou HTTP selon leurs endpoints, avec
  `health_required` fixé selon leur criticité dans le profil.

### 4.3 `validation.py`

- Erreur de plan : service `health_required=True` sans probe effective (fail-fast à la
  validation ; l'évaluateur garde le filet `FAILED` en défense en profondeur, §2.8).
- Erreur de plan : conflit `healthcheck_url` × `probe_type` (§2.4).
- Avertissement : service du profil Minimal sans contrat (visibilité de la dette, sans bloquer).

### 4.4 `src/forgeai/deploy/compose.py:65`

L'agrégation `all(v == "healthy" ...)` est remplacée par l'évaluateur de la machine d'états §3
(implémentation : HEALTH-028B). La ligne fautive disparaît ; toute future agrégation passe par la
garde anti-vacuité.

---

## 5. Rétro-compatibilité

- Les constructions existantes de `ServiceSpec` (avec seul `healthcheck_url`) restent valides :
  dérivation §2.4, défauts `(200,)`, `health_required=False`.
- **Changement de comportement intentionnel et documenté** : un déploiement dont aucun service
  n'est sondé n'est plus « healthy par défaut » — il est `UNKNOWN`. C'est précisément la
  correction du finding FAI-U-028 ; tout plan qui comptait sur le READY vacu était déjà faux.
- Aucun plan existant valide ne devient invalide à la **construction** ; seuls les plans
  exprimant un conflit explicite (§2.4) ou des temporisations ≤ 0 sont rejetés — cas qui
  n'existaient pas dans les plans générés par le wizard.

---

## 6. Conséquences

### Positives

- Le faux READY vacu (compose.py:65) devient structurellement impossible.
- La criticité est explicite dans le plan (`health_required`), auditable, sérialisée avec lui.
- Distinction transport/fonctionnel : fin des « TCP ouvert = application saine ».
- Politique HTTP fine (openbao et ses codes multiples) sans heuristique cachée dans le moteur.
- Sonde exec cohérente avec la posture 0-injection-shell (argv sans shell).
- Défense en profondeur : validation à la construction (models), au plan (validation), et à
  l'évaluation (moteur).

### Négatives / coûts

- `ServiceSpec` s'alourdit (7 champs) ; assemble.py doit déclarer un contrat par brique
  (effort une fois, à maintenir avec le catalogue de briques).
- Un service critique TCP-only ne peut plus « suffire » : exige une décision de plan explicite
  (coût assumé, c'est le prix de l'honnêteté du verdict).
- Légère complexité de dérivation legacy (§2.4) à documenter/tester.

---

## 7. Alternatives rejetées

1. **Corriger compose.py:65 localement** (`if status and all(...)`). Rejeté : ne traite que le
   symptôme, sans criticité, sans types de probe, sans distinction transport/fonctionnel ; le
   prochain renderer réintroduira le défaut.
2. **Sonde TCP implicite pour tout service sans `healthcheck_url`.** Rejeté : transforme le faux
   READY vacu en faux READY transport — masque les pannes applicatives (violation du plafond
   TCP §3.2).
3. **Erreur de validation systématique sur tout service sans probe.** Rejeté : casse la
   rétro-compatibilité des plans simples ; préféré : `UNKNOWN` + opt-in `health_required`.
4. **Chaîne shell pour la sonde exec.** Rejeté : incompatible avec la posture 0-injection-shell
   du produit ; argv tuple sans shell, uniquement (§2.6).
5. **Plage de codes HTTP (« 2xx ») au lieu d'un tuple explicite.** Rejeté : moins précis,
   incapable d'exprimer l'ensemble non contigu d'openbao (200/429/472/473/501/503), sérialisation
   moins directe.

---

## 8. Critères d'acceptation (vérifiables par HEALTH-028B)

1. **Anti-vacuité** : une collection de verdicts vide s'évalue `UNKNOWN` (aucun requis) ou
   `FAILED` (un requis sans probe) — **jamais** healthy. Test : déploiement sans aucune sonde ⇒
   `wait_healthy` ne retourne pas READY.
2. **Criticité** : `health_required=True` sans probe effective ⇒ erreur de validation du plan
   ET `FAILED` à l'évaluation (défense en profondeur).
3. **Plafond TCP** : une sonde TCP en succès répété produit `TRANSPORT_READY` et jamais
   `FUNCTIONALLY_READY`.
4. **Codes HTTP configurables** : `FUNCTIONALLY_READY` ⇔ code ∈ `http_success_codes` ; défaut
   `(200,)` ; un plan déclarant `(200, 429, 472, 473, 501, 503)` (cas openbao) accepte ces codes.
5. **Précédence legacy** : `probe_type` explicite prime ; `healthcheck_url` seul dérive
   HTTP+cible ; conflit explicite (ex. URL fournie + `probe_type=TCP`) ⇒ erreur de validation
   fail-fast, jamais silencieux.
6. **Exec argv** : `probe_target` exec est un `tuple[str, ...]` non vide, exécuté sans shell
   (aucun `shell=True`) ; une chaîne comme cible exec est refusée à la validation.
7. **Temporisations** : `health_timeout_s`, `health_interval_s`, `health_retries` ≤ 0 ⇒ erreur
   de validation.
8. **Modèle** : round-trip `asdict`→JSON→reconstruction ; enums sérialisés en valeurs `str` ;
   nouveaux champs chaînes/argv passés par `_rejeter_caracteres_de_controle`.
9. **Régression** : la ligne compose.py:65 (`all(...)` sur collection non gardée) n'existe plus ;
   tout test de santé globale passe par la garde anti-vacuité.
```
