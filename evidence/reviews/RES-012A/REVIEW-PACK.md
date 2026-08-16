# PACK DE REVUE — RES-012A (DESIGN_FIRST, ADR schéma de ressources, FAI-U-012)
## Défaut prouvé : k3s.py:72-77 code en dur requests cpu:100m/mem:128Mi + limits cpu:1/mem:1Gi pour TOUS les
## services (sidecar trivial comme LLM lourd) -> sur-souscription du scheduler + throttle/OOM d'un vrai LLM ;
## ServiceSpec n'a aucun champ de ressources. Ce package est DESIGN_FIRST : AUCUN fichier source modifié.
## Évaluer le DESIGN : classes de service aux valeurs DISTINCTES (llm/db/sidecar/utilitaire) ; validation des
## unités et limits>=requests ; contrat deploy-specs (plus de magic number renderer) ; rétro-compat/migration ;
## contrat concret pour RES-012B/PLACE-011 ; alternatives rejetées. Vérifier qu'il n'est PAS tronqué.

```markdown
# ADR RES-012A — Schéma de ressources par service (CPU/mémoire)

- **Statut** : PROPOSED — en attente d'approbation Nathan
- **Package** : RES-012A (DESIGN_FIRST — design pur, aucune implémentation produit)
- **Finding** : FAI-U-012
- **Packages dépendants** : RES-012B (implémentation du schéma + validation), PLACE-011 (placement / affectation des services aux nœuds)

---

## 1. Contexte et problème prouvé

`src/forgeai/renderers/k3s.py:72-77` (fonction `_resources_block`) code **en dur** les ressources de **tous** les services rendus :

- `requests: cpu: 100m, memory: 128Mi`
- `limits: cpu: "1", memory: 1Gi`
- (branche additionnelle : `nvidia.com/gpu: "1"` si `gpu_vendor == "nvidia"`)

Conséquences démontrées :

1. **Magic numbers dans le renderer.** Les valeurs sont des littéraux figés dans le code de rendu, invisibles pour l'auteur d'une brique et impossibles à ajuster sans modifier le renderer.
2. **Uniformité absurde.** Un sidecar trivial (proxy) et un runtime LLM lourd (ollama, backend d'inférence) reçoivent des valeurs **identiques**. Le scheduler Kubernetes compte par `requests` : 100m/128Mi pour un LLM = **sur-souscription** (le pod est placé sur un nœud qui ne peut pas le servir). À l'inverse, `limits: 1 CPU / 1Gi` pour un vrai LLM = **throttle CPU et OOMKill** garantis en charge.
3. **Aucun support dans le modèle.** La dataclass `ServiceSpec` (`src/forgeai/core/models.py` — champs actuels : `name, image, host_port, container_port, volumes, env, healthcheck_url, gpu, gpu_vendor, depends, command, node`) n'a **aucun** champ de ressources. Le renderer ne peut donc rien lire d'autre que ses littéraux.
4. **Blocage de PLACE-011.** Le placement multi-nœud (champ `node`, scheduling) ne peut pas raisonner sur l'affinité capacitaire tant que les `requests` sont mensongers.

Le socle existant qui fonctionne (specs `deploy-specs.json` : `litellm`, `redis`, `qdrant` — images épinglées par digest, ports, healthchecks, volumes, `depends`) **ne doit pas être cassé** : la présente décision s'y greffe par extension additive.

---

## 2. Décision (synthèse)

Nous adoptons un modèle **« classes + dérogations explicites »** :

1. `ServiceSpec` est étendu avec un **`resource_class`** (enum à 4 valeurs : `llm`, `db`, `sidecar`, `utilitaire`) **et** une **dérogation explicite optionnelle** (`resources` : requests/limits CPU+mémoire) qui prime sur la classe.
2. Quatre classes de service aux valeurs **distinctes et justifiées** (§4).
3. Validation **stricte des unités** et de la cohérence **limits ≥ requests**, vivant dans `models.py` (`__post_init__`) avec re-validation à l'assemble des specs JSON (§5).
4. Chaque brique déclare sa classe (ou ses ressources) dans `deploy-specs.json` ; le renderer **lit exclusivement** les valeurs résolues du spec — plus aucun magic number (§6).
5. Rétro-compatibilité : classe par défaut **`utilitaire`** pour les specs non annotés, avec plan de migration assignant explicitement les classes aux briques existantes (§7).

---

## 3. Extension de `ServiceSpec` (décision 1)

### 3.1 Forme retenue : les deux (classe **et** dérogation)

| Option | Verdict | Justification |
|---|---|---|
| Valeurs explicites seules | Rejetée (seule) | Chaque auteur de brique réinvente des nombres → dérive, revues impossibles, aucune homogénéité. |
| `resource_class` seule | Rejetée (seule) | Tout cas atypique force à mal classer la brique ou à faire grossir l'enum à chaque exception. |
| **Classe + dérogation optionnelle** | **Retenue** | La classe donne un défaut sûr, relu et homogène ; la dérogation couvre l'exception sans toucher à l'enum. |

### 3.2 Champs ajoutés à `ServiceSpec` (concepts, pas de code)

- `resource_class : str` — une de `{"llm", "db", "sidecar", "utilitaire"}` ; **défaut `"utilitaire"`**.
- `resources` — dérogation optionnelle, structure à 4 valeurs : `requests.cpu`, `requests.memory`, `limits.cpu`, `limits.memory`. **Règle tout-ou-rien** : si `resources` est présent, les 4 valeurs sont **obligatoires** (pas de fusion partielle avec la classe — les combinaisons implicites non relues sont refusées).
- **Valeurs effectives résolues** : après construction, le spec expose des ressources **toujours résolues (jamais `None`)** : dérogation si fournie, sinon valeurs de la classe. C'est ce que lit le renderer. `resource_class` reste porté par le spec pour l'audit, les tests et PLACE-011.

### 3.3 Ordre de résolution

1. `resources` explicite (validée) → valeurs effectives.
2. Sinon `resource_class` → valeurs de la table de classes (unique, dans `models.py`).
3. Sinon (absent) → classe `utilitaire`.

---

## 4. Classes de service et valeurs (décision 2)

| Classe | requests.cpu | requests.memory | limits.cpu | limits.memory |
|---|---|---|---|---|
| `llm` | 1000m | 4Gi | 4000m | 8Gi |
| `db` | 250m | 512Mi | 1000m | 2Gi |
| `sidecar` | 100m | 128Mi | 500m | 512Mi |
| `utilitaire` | 50m | 64Mi | 250m | 256Mi |

Les quatre classes sont **deux à deux distinctes** (aucun quadruplet identique — garanti par un invariant testé, cf. §9).

### Justifications par classe

- **`llm`** — runtimes d'inférence (ex. `ollama`, backends type vLLM). Les poids de modèles et le KV cache vivent en RAM : `requests.memory: 4Gi` empêche le placement sur un nœud incapable et l'OOMKill en rafale. `requests.cpu: 1000m` garantit un cœur pour le débit de tokens ; `limits: 4000m / 8Gi` autorise le burst tout en protégeant les colocataires. **Hors scope** : la VRAM reste gouvernée par `gpu` / `gpu_vendor` (branche `nvidia.com/gpu` de `k3s.py:72-77`, inchangée) — les accélérateurs ne sont **jamais** dans les classes.
- **`db`** — briques stateful mémoire-centric (`qdrant` : buffers vecteurs/mmap ; `redis` : dataset en RAM). La mémoire garantie (512Mi) évite l'OOMKill d'un pod stateful (redémarrage = interruption + recovery). CPU modéré : le goulot est la mémoire et l'I/O, pas le calcul. Limit mémoire 2Gi pour absorber les pics d'indexation/flush sans famine.
- **`sidecar`** — passerelles et proxies (`litellm`, web `langfuse`). Latence-sensibles mais empreinte faible. `requests` **identiques aux valeurs actuelles** (100m/128Mi) = continuité de comportement ; `limits` **resserrés** (500m/512Mi au lieu de 1/1Gi) pour corriger la sur-souscription historique.
- **`utilitaire`** — jobs d'init, migrations, tâches ponctuelles, daemons minimaux. Quasi nul au repos ; limits bas car aucun burst légitime.

Ces valeurs sont des **points de départ sûrs**, figées dans l'ADR ; toute révision passe par une évolution de table relue (§9, T1).

---

## 5. Validation (décision 3)

### 5.1 Règles de forme (rejet net sinon)

- **CPU** : `^\d+m?$` — entier éventuellement suffixé `m` (`"100m"`, `"2"`). La notation décimale (`"0.5"`) est **volontairement exclue** : on écrit `"500m"`.
- **Mémoire** : `^\d+(Mi|Gi)$` — entier suffixé `Mi` ou `Gi` uniquement (`Ki`, `Ti`, `M`, `G` refusés).
- **Classe** : doit appartenir à l'enum ; toute classe inconnue est refusée (défaut-deny).

### 5.2 Règle de cohérence

Comparaison **numérique normalisée**, par ressource :

- CPU → milliCPU (`"2"` = 2000m).
- Mémoire → MiB (`"1Gi"` = 1024 Mi).
- **`limits < requests` est refusé** pour CPU **et** pour mémoire, indépendamment. L'égalité est autorisée (elle ouvre la QoS `Guaranteed`, souhaitable pour `db`/`llm`).

### 5.3 Où vit la validation

- **Point unique d'autorité : `models.py`, dans `__post_init__`** de la structure de ressources (et de `ServiceSpec` pour la résolution classe/dérogation). Échec = exception dédiée portant un code d'erreur stable (famille `ERR_RES_*`), fail-fast à la construction : **aucun spec invalide ne peut exister**, quel que soit le renderer (k3s, compose, futurs).
- **Re-validation à l'assemble** des `deploy-specs.json` : le JSON est une entrée non fiable ; l'assembleur reconstruit les objets `ServiceSpec`, ce qui déclenche naturellement la validation `__post_init__` (défense en profondeur sans duplication de logique).
- **Renderer : aucune validation.** Il reste « bête » : il lit les valeurs résolues. Un test structurel (§8) interdit toute réintroduction de littéral de ressource.

---

## 6. Contrat `deploy-specs.json` (décision 4)

Chaque brique gagne deux clés **optionnelles** :

- `"resource_class" : "llm" | "db" | "sidecar" | "utilitaire"`
- `"resources" : { "requests" : { "cpu", "memory" }, "limits" : { "cpu", "memory" } }` — tout-ou-rien (§3.2), ignorée si incomplète → **refusée** (une dérogation partielle est une erreur de spec, pas un défaut).

Règles du contrat :

1. **Priorité** : `resources` > `resource_class` > défaut `utilitaire`.
2. **Le renderer ne contient plus aucun magic number** : `_resources_block` (`k3s.py:72-77`) est réécrit pour **lire** les valeurs effectives du `ServiceSpec` ; seule la branche GPU (`gpu_vendor == "nvidia"` → `nvidia.com/gpu: "1"`) est conservée telle quelle, orthogonale au schéma CPU/mémoire.
3. Les clés existantes (`image`, `container_port`, `health_path`, `volumes`, `env`, `command`, `depends`) sont **inchangées** — extension purement additive.
4. Les specs source de vérité (`RES012-ctx-specs.json`) migrent par annotation (§7) : aucune image, aucun port, aucun wiring ne change.

---

## 7. Rétro-compatibilité et migration (décision 5)

### 7.1 Classe par défaut : `utilitaire`

Tout spec existant sans annotation reçoit la classe `utilitaire` (50m/64Mi ; 250m/256Mi). Justification du choix « plus petit » plutôt que « valeur actuelle » : **moindre privilège**. Conserver 1 CPU/1Gi par défaut perpétuerait la sur-souscription pour toute brique future non annotée ; sous-allouer par défaut fait **apparaître** le besoin (throttle observable en staging) et force une déclaration explicite relue.

### 7.2 Plan de migration (exécuté dans RES-012B, un seul changement)

1. **Inventaire et annotation** des briques existantes dans `deploy-specs.json` **dans le même commit** que l'activation du schéma, pour qu'aucune brique ne subisse le défaut :
   - `litellm` → `sidecar` (passerelle proxy ; requests inchangés, limits resserrés).
   - `redis` → `db`.
   - `qdrant` → `db`.
   - `ollama` → `llm`.
   - `langfuse` (web/worker) → `sidecar`.
   - Toute brique découverte sans annotation dans l'inventaire reçoit une classe **explicite** (jamais le défaut).
2. **Golden manifests** régénérés ; diff relu ligne à ligne (seuls les blocs `resources` doivent bouger).
3. **Soak en staging** : vérifier l'absence de throttle/OOM inattendu sur `sidecar`/`utilitaire` (limits resserrés) et le bon dimensionnement de `llm`.

### 7.3 Impact connu et assumé

Les manifestes changent → **rolling restart** des pods au prochain déploiement. Aucune migration de données (les manifestes sont des artefacts générés, sans état persisté par le renderer).

---

## 8. Contrats d'implémentation, de test, de migration et de rollback

### 8.1 RES-012B — implémentation du schéma + validation

**Livrables** : extension `ServiceSpec` (§3) ; table de classes unique dans `models.py` (§4) ; validation `__post_init__` + erreur dédiée `ERR_RES_*` (§5) ; parsing des nouvelles clés à l'assemble (§6) ; réécriture de `_resources_block` pour lire le spec (§6.2), branche GPU conservée.

**Tests obligatoires (barrière de merge)** :

- Unitaires : unités valides/invalides (CPU `^\d+m?$`, mémoire `^\d+(Mi|Gi)$`, refus de `"0.5"`, `"1G"`, `"512"`) ; `limits < requests` refusé par ressource ; égalité acceptée ; classe inconnue refusée ; dérogation partielle refusée ; défaut `utilitaire`.
- Golden manifests : un manifeste par classe ; un manifeste à dérogation explicite ; non-régression GPU (`nvidia.com/gpu` présent si et seulement si `gpu_vendor == "nvidia"`).
- Structurel : **aucun littéral de ressource** (`100m`, `128Mi`, `1Gi`…) dans `renderers/` (le renderer lit le spec).
- Invariant de classes : pas deux classes avec des valeurs identiques (§9, I5).

**Migration** : §7.2 (annotation des briques dans le même commit).

**Rollback** : revert du commit + régénération des manifestes. Aucune donnée migrée, aucun état persisté → rollback trivial, coût = un redeploy.

### 8.2 PLACE-011 — placement

- **Contrat d'entrée** : post-RES-012B, les ressources effectives d'un `ServiceSpec` sont **toujours résolues, jamais `None`** — PLACE-011 les consomme sans repli ni valeur implicite.
- **Usage** : le raisonnement de placement (fit capacitaire par nœud, via le champ `node` et le scheduler) s'appuie sur les `requests` désormais honnêtes ; la somme des `requests` placés sur un nœud doit rester ≤ allocatable (garanti nativement par K8s une fois les `requests` véridiques).
- **Point d'extension futur** (hors scope RES-012) : le profil hardware dérivé par `planner/profile.py` (stories P1-S01/S02 : `minimal-cpu`, `minimal-gpu-cuda`…) pourra moduler les classes par profil de machine ; non retenu ici (§10, G).

---

## 9. Modèle de menace et invariants

### Menaces

- **T1 — Sur-souscription du scheduler** : `requests` fantaisistes → entassement. *Mitigation* : classes bornées et relues ; la table de classes est **unique** (dans `models.py`) et ne change que par décision relue.
- **T2 — Throttle/OOM d'un LLM** : `limits` trop bas. *Mitigation* : classe `llm` dimensionnée (§4) ; invariant I2.
- **T3 — Injection d'unités** : JSON non fiable portant des chaînes invalides. *Mitigation* : regex strictes, refus net `ERR_RES_*`, aucune valeur non validée n'atteint le renderer (I1).
- **T4 — Dérive du renderer** : réintroduction de magic numbers. *Mitigation* : test structurel (§8.1) ; le renderer lit exclusivement le spec (I4).
- **T5 — Régression GPU** : casse de la réservation `nvidia.com/gpu`. *Mitigation* : branche vendor inchangée ; les accélérateurs ne sont jamais membres des classes ; test de non-régression dédié.

### Invariants

- **I1** : toute valeur de ressource validée matche `^\d+m?$` (CPU) ou `^\d+(Mi|Gi)$` (mémoire).
- **I2** : pour chaque ressource, `limits ≥ requests` (comparaison normalisée milliCPU / MiB).
- **I3** : les ressources effectives sont **toujours résolues** (jamais `None`) à la sortie de `models.py`.
- **I4** : déterminisme — même spec ⇒ même manifeste, octet pour octet ; le renderer est une fonction pure du spec.
- **I5** : les quatre classes ont des valeurs **deux à deux distinctes** (testé).
- **I6** : `resource_class` inconnue ⇒ refus (défaut-deny, jamais de classe implicite autre que le défaut documenté `utilitaire`).

---

## 10. Alternatives considérées et rejetées

- **A. Statu quo + spécial-caser les LLM par nom de service** — Rejeté : heuristique par nom fragile (renommage = régression silencieuse) ; les magic numbers demeurent.
- **B. Valeurs explicites seules, sans classes** — Rejeté : dérive des valeurs entre briques, charge de revue ingérable, aucun défaut sûr.
- **C. Classes seules, sans dérogation** — Rejeté : toute exception force un mauvais classement ou un churn de l'enum ; la dérogation tout-ou-rien validée couvre l'atypique proprement.
- **D. Validation dans le renderer** — Rejeté : le renderer est le dernier maillon et il y en a plusieurs (k3s, compose) ; valider tard laisse exister des specs invalides. La validation vit à la construction (`models.py`), le renderer reste muet.
- **E. Quantités Kubernetes libres** (décimaux `"0.5"`, `Ki`/`Ti`, suffixes décimaux `M`/`G`) — Rejeté : parsing et comparaison non triviaux, ambiguïtés d'arrondi ; le sous-ensemble regex (§5.1) couvre tous les besoins constatés avec une comparaison entière exacte.
- **F. Délégation à Helm/Kustomize** — Rejeté : hors périmètre ; le toolkit rend des manifestes bruts et doit rester autonome.
- **G. Dimensionnement automatique depuis le profil hardware** (`planner/profile.py`, profils `minimal-*` des stories P1-S01/S02) — Rejeté **pour RES-012** : couplerait le sizing à la détection machine et mélangerait deux responsabilités ; conservé comme point d'extension (§8.2).

---

## 11. Conséquences

**Positives** : scheduler alimenté en `requests` honnêtes ; LLM protégé du throttle/OOM ; renderer débarrassé des magic numbers ; base capacitaire exploitable par PLACE-011 ; audit facilité (`resource_class` visible dans le spec).

**Coûts** : surface de validation à maintenir ; table de classes à faire évoluer par revue ; changement de manifestes ⇒ rolling restart au déploiement de RES-012B ; risque de sous-dimensionnement initial des briques oubliées par l'inventaire — neutralisé par §7.2 (annotation exhaustive dans le même commit) et le soak staging.

---

## 12. Traçabilité des critères d'acceptation

| Critère | Réponse |
|---|---|
| Chaque service a une classe OU des ressources explicites validées | §3 (classe + dérogation, défaut `utilitaire`) |
| Valeurs LLM/DB/sidecar/utilitaire NON identiques | §4 (table distincte, invariant I5 testé) |
| Unités invalides et `limits < requests` refusés | §5 (regex, comparaison normalisée, `ERR_RES_*`) |
| Format rétrocompatible ou migration documentée | §7 (défaut `utilitaire`, plan de migration, rollback §8.1) |
| Aucune implémentation produit (design pur) | Le présent ADR ne contient aucun code |

---

## 13. Conclusion

Le schéma « classes + dérogations explicites validées » supprime les magic numbers de `k3s.py:72-77`, donne au scheduler des `requests` véridiques, protège les LLM du throttle/OOM, et prépare le placement capacitaire de PLACE-011 — le tout par extension additive qui ne casse ni `ServiceSpec` ni les specs existants. RES-012B implémentera exactement ce contrat (schéma, validation `models.py`, renderer lisant le spec, tests barrières de merge, migration annotée atomique). **Approbation finale : Nathan.**
```
