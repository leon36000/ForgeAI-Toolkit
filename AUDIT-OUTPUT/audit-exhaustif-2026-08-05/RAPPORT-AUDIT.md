# Audit exhaustif ForgeAI-Toolkit — rapport

**Cible figée** : `leon36000/ForgeAI-Toolkit` @ `0e2181eb03e39d708c4e88c5a73536c143f3bce3`
(merge PR #394, 2026-08-04T08:31:43Z) · **Date d'audit** : 2026-08-05 · **Périmètre** : 1564 blobs

---

## Limites de cet audit — à lire avant les résultats

1. **L'absence de faille est indémontrable.** Ce rapport dit « aucune vulnérabilité détectée par
   [outil, version] sous [configuration] au SHA [X] » — jamais « le dépôt est sûr ».
2. **La couverture n'est pas la correction.** 93 % de lignes+branches exécutées ne prouve pas
   qu'elles sont correctes.
3. **Le matériel n'est pas auditable ici** (GPU, k3s réel) : classé `EXCLU avec raison`, pas « vérifié ».
4. **Le consensus valide un raisonnement, pas des faits.** Les modèles reçoivent du texte, pas le
   dépôt. L'exactitude repose sur la capture déterministe et la rejouabilité au SHA figé.
5. **L'audit ne peut pas prouver sa propre intégrité.** `no_stub_scan` ne scanne pas `Rapports/` ni
   `AUDIT-OUTPUT/`.

**Compteurs séparés, jamais additionnés** (48 constats au total, chacun dans exactement un statut) :

| Statut | Nombre | Ventilation par sévérité |
|---|---|---|
| **CONFIRMÉ** (artefact rejouable) | **45** | 3 CRITICAL + 5 HIGH + 14 MEDIUM + 6 LOW + 17 NONE |
| **HYPOTHÈSE** (non vérifiée individuellement) | **2** | 1 MEDIUM + 1 LOW |
| **RÉFUTÉ** par la mesure | **1** | 1 NONE |

Les 17 `NONE` confirmés sont les **points forts mesurés** (un 18ᵉ `NONE` relève du statut RÉFUTÉ).
Chaque ligne se somme à son propre total ; les trois statuts ne se cumulent pas en un score unique.

---

## Les 4 questions de Nathan — réponses directes

### 1. « Y a-t-il une faille exploitable maintenant ? »

**Non détectée.** Aucune vulnérabilité exploitable n'a été confirmée par PoC.

Ce qui a été activement cherché et **n'a rien donné** : injection de commande (0 `shell=True`,
0 `eval`, 0 `exec`, 0 `pickle` dans tout `src/`), injection d'argument via l'API web (fermée par
liste blanche — `--dry-run`, `; rm -rf /`, `$(id)`, `` `id` ``, `../../etc/passwd` sont tous rejetés
par exécution réelle), XSS dans `app.js` (18 gabarits `innerHTML` analysés, les 7 interpolations
brutes sont toutes des compteurs numériques ou des fragments qui échappent en interne), fuite de
secret (gitleaks sur **678 commits** : 0).

Un seul défaut de validation réel : `NODE_NAME_RE` accepte un `\n` final (le `$` de Python matche
avant un saut de ligne terminal). **Non exploitable en l'état** — la valeur part dans `argv` (pas de
shell) et `json.dumps` échappe le `\n` au stockage. Remède : `re.fullmatch` ou `\Z`.

### 2. « Ai-je régressé sur quelque chose de déjà fermé ? »

**Non dans le code — mais oui dans le contrôle.**

Le différentiel SAST contre la baseline SAST-042 (versions d'outils **identiques** : bandit 1.9.4,
semgrep 1.168.0) donne +10 signaux, entièrement expliqués par l'extraction de `core/proc.py` depuis
`cli.py` et par du nouveau code SSH. Aucune régression des correctifs #107-#123.

En revanche, **14 PR (#356-#369) ont fusionné dans `main` avec zéro check CI** — +4 613 lignes non
vérifiées pendant la coupure GitHub Actions du 2026-08-01. Y compris, ironiquement, REG-029B
(+2 088 lignes), le mécanisme d'ancrage anti-rollback du registre lui-même.

### 3. « Où en suis-je vraiment vs le plan ? »

**L'ingénierie dépasse le plan. La gouvernance est en grande partie du théâtre.**

Sur les **11 gates déclarés `bloquant: true`**, **2 bloquent réellement** (`no-stub-scan`, `gitleaks`) :

| Gate | Déclaré | Réel |
|---|---|---|
| G01 ruff `--select ALL`, 0 violation | bloquant | pre-commit seul, `select=["E9","F"]`, **aucun job CI** |
| G02 mypy `--strict`, 0 erreur | bloquant PR | **jamais exécuté** — mesuré : 374 erreurs |
| G03 pytest 3 seuils | bloquant | 2 seuils ; le 3e vise `forgeai/gates`, **module inexistant** |
| G04 no-stub-scan | bloquant | ✅ implémenté **et requis** |
| G05 gitleaks | bloquant | ✅ implémenté **et requis** |
| G06 trivy, 0 CVE | bloquant | **jamais installé ni invoqué** |
| G07 hash catalogue | bloquant | vérifié au runtime produit, mais `catalogue_gate.py` **ne calcule aucun sha256** (0 occurrence `hashlib`) et le job n'est pas requis |
| G08 no-fake-done | bloquant | **non implémenté** |
| G09 revue aveugle ×3 | bloquant | implémenté mais **non requis** |
| G10 signature-fable | bloquant | **non implémenté** |
| G11 tally fin-de-phase | bloquant | **non implémenté** |

`MASTER-PLAN.md` §6 publie cette table sans réserve, alors que sa source `manifests/gates.yaml`
porte elle-même l'en-tête `claim: UNVERIFIED`.

### 4. « Qualité, perf, dette ? »

**Solide.** 1891 tests collectés : **1884 passent, 7 sont skippés**.

> **CORRECTION post-publication (2026-08-05)** — la première version de ce rapport affirmait
> « 1891 tests, tous verts, 0 skippé ». C'était **faux** : mon filtre de lecture avait manqué la ligne
> de résumé de pytest. Le chiffre exact est 1884 passés + 7 skippés. Les 7 skips sont **justifiés et
> tracés** (5 preuves e2e Docker lourdes, rejouables via `FORGEAI_E2E=1` ; 2 comportements Windows qui
> tournent sur les runners Windows), chacun renvoyant à une preuve d'exécution réelle au registre —
> c'est l'inverse du « skip silencieux » que le lot L02 cherchait.

**93 % de couverture branches incluses** — alors que le gate n'exige que 85 % en lignes seules. Quasi aucun code mort (3 signalements, tous des faux
positifs de signature). Le dépôt est **vert sous sa propre configuration ruff**.

La dette réelle est concentrée : `cli.py::wizard_ci` (complexité 109), `web/server.py::do_GET` (66)
et `do_POST` (59), indice de maintenabilité C (0.00) sur ces deux fichiers. Aucun gate ne mesure la
complexité.

---

## Les 3 constats CRITICAL

**C1 — 14 PR fusionnées avec zéro check CI** (`L03-001`).
Pendant la coupure Actions du 2026-08-01, PR #356 à #369 n'ont porté qu'un seul check (GitGuardian,
app externe hors Actions). Les 5 checks requis basés sur Actions étaient **absents**. La fusion a été
possible car `enforce_admins: false`. Contenu non vérifié : correctif de fuite du flux de déploiement
(#356), ancrage anti-rollback du registre (#365, +2088), réconciliation documentaire (#368, +1107).
*Preuve* : `gh api repos/.../commits/<head>/check-runs` sur chacune des 96 PR fusionnées.

**C2 — Le gate de revue scellée ne bloque rien** (`L03-002`).
`reviews-sealed` n'est pas dans `required_status_checks`, alors que le job existe depuis `beaa629`
(2026-07-16). Le pilier de la méthodologie PROOF n'a jamais pu empêcher une fusion. Plus largement :
**12 jobs CI définis, 4 seulement requis** (les 2 autres contextes requis sont des apps externes,
pas des jobs). 8 jobs ne bloquent rien.

**C3 — `reviews_gate` est fail-open et son message de succès est mensonger** (`L10-001`).
Prouvé par mutation : vider **ou** supprimer `reviews/BINDING.txt` fait sortir le gate en `exit 0`
en imprimant *« GATE OK : toutes les revues liantes sont APPROVE 3/3 »* alors que **zéro** revue a été
vérifiée. `check()` initialise `ok=True` et se contente d'un avertissement si le manifeste est vide.
Contre-épreuve : un verdict liant muté en REJECT produit bien `exit 1` — le gate fonctionne quand il
a quelque chose à vérifier ; le défaut est l'absence de garde sur le manifeste.

---

## Ce qui tient — 17 points forts mesurés

- **Intégrité parfaite des 34 registres** (501 entrées) vérifiée par une implémentation
  **indépendante** : 0 hash divergent, 0 `prev_hash` rompu, 0 saut de séquence.
- **Catalogue intègre** : sha256 concordant avec son sidecar, 1576 ids tous uniques.
- **Intégrité structurelle parfaite des 135 revues liantes** : 0 sans 3 vendors distincts, 0 sceau
  `prompt_sha256` divergent, 0 verdict non-APPROVE. *Quand le mécanisme est appliqué, il l'est
  correctement — le défaut est dans son branchement, pas dans le sceau.*
- **0 fuite de secret sur 678 commits.**
- **0 dépendance runtime** (`dependencies = []`) : surface supply-chain du produit livré nulle.
- **Gardes fail-closed avant tout routage** : `do_POST` applique rate-limit et garde de mutation
  (jeton/CSRF/anti-rebinding) *avant* toute comparaison de route — une route mutante ajoutée par
  erreur hérite des gardes par construction.
- **Validation par liste blanche** sur toutes les entrées de `/api/deploy`.
- Permissions CI en lecture seule · `actionlint` propre · 0 JSON/JSONL invalide · 1884 tests verts (7 skips justifiés et tracés) ·
  93 % de couverture branches · quasi aucun code mort.

---

## Discipline de preuve — ce qui a été écarté

Un audit honnête rapporte aussi ses propres erreurs.

| Fausse piste | Réfutation |
|---|---|
| 16 paquets vulnérables (pip-audit) | `pip-audit` avait résolu vers le binaire système et audité **l'environnement du poste** (383 paquets : ansible, aiohttp…). Refait sur un venv contenant uniquement les dev-deps du projet : **94 paquets, 1 vulnérable** (`cryptography 48.0.1`, transitif via ggshield). |
| B108 « usage de /tmp non sûr » dans `k3s.py` | Le littéral `/tmp` alimente les chemins de volumes `emptyDir` d'un manifeste Kubernetes, générés **parce que** `readOnlyRootFilesystem: true`. C'est du durcissement, que bandit lit à l'envers. |
| 14 interpolations XSS dans `app.js` | Défaut de **mon** détecteur (drapeau d'état non réinitialisé, confusion avec `textContent`). Repris avec bornes correctes : 7 interpolations, toutes sûres. |
| `ServiceSpec` n'a pas `ressources_effectives` (mypy) | Réfuté par exécution : l'attribut est posé par `object.__setattr__` dans `__post_init__` (dataclass gelée), invisible à mypy. |
| L'API GitHub tree serait plafonnée à 1000 entrées | Réfuté : `truncated: false`, 1898 entrées d'arbre, 1564 blobs livrés. |
| Le dépôt aurait des sous-modules masquant des fichiers | Réfuté : 0 entrée `type=commit`, `.gitmodules` absent. |
| « 5419 violations ruff » | **Chiffre faux, mesuré sur le checkout périmé** (68 fichiers `.py` au lieu de 281). Total réel au commit figé : **17 620**. Et il reste trompeur comme indicateur de dette : 3511 sont des `assert` de tests (les interdire contredirait frontalement `no_stub_scan`), 3052 des lignes longues, 3970 des annotations manquantes (`ANN*`), 1094 des docstrings absentes — soit **11 627 sur 17 620 (66 %) purement cosmétiques**, issus de 4 familles de règles. Le dépôt est **vert** sous sa configuration propre (`select=["E9","F"]`). |

**Deux constats me sont imputables** : les documents annoncent 1577 briques pour 1576 réelles (j'ai
retiré l'entrée morte en PR #393 sans mettre à jour la doc), et I18N-041/I18N-042 sont déclarés
COMPLETED sans entrée au registre — ce que le gate G08, déclaré bloquant et jamais implémenté,
aurait dû bloquer sur mes propres PR.

---

## Recommandations, par ordre de valeur

1. **Ajouter `reviews-sealed` aux `required_status_checks`** — sans quoi tout le dispositif PROOF est
   décoratif. (T3 Nathan : modifie la branch protection.)
2. **Corriger le fail-open de `reviews_gate`** : manifeste vide ou absent ⇒ `ok=False`, et supprimer
   le message de succès mensonger.
3. **Aligner `MASTER-PLAN.md` §6 et `manifests/gates.yaml` sur la réalité** — ou implémenter les
   gates annoncés. Publier une table de conformité fausse est le risque le plus insidieux du dépôt.
4. **Politique de reprise après coupure CI** : rejouer les checks sur les 14 PR de la fenêtre du
   2026-08-01, ou acter explicitement le risque au registre.
5. Épingler les 17 GitHub Actions par SHA · activer mypy en mode non-strict ciblé (130 candidats) ·
   câbler un linter JS sur `app.js` (53 Ko livrés au navigateur, aucun gate) · `re.fullmatch` sur
   `NODE_NAME_RE` · réduire `wizard_ci` (complexité 109).

---

## Reproductibilité

Toute mesure de ce rapport est rejouable au SHA figé. Artefacts sous `AUDIT/` :
`toolchain.lock` (21 outils versionnés) · `evidence/` (sorties brutes) · `findings/TOUS.json`
(48 constats, 48 empreintes de déduplication uniques) · `coverage-ledger` (inventaire 1564 blobs concordant entre
3 sources indépendantes, 0 sous-module).
