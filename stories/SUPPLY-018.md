# SUPPLY-018 — Épingler, vérifier et licencier les briques avant exécution

- **Issue** : #263
- **Tier** : T2 (chaîne d'approvisionnement — empêcher le déploiement d'une brique non épinglée / non vérifiée / à licence risquée)
- **Dépend de** : ORCH-001 (mergé).
- **Reprise lane CODEX** (Codex retiré).
- **Périmètre fichiers** : `src/forgeai/catalogue/supply.py` (nouveau), `src/forgeai/planner/assemble.py`
  (adoption de la garde), `tests/test_supply018.py` (nouveau), `stories/SUPPLY-018.md`.

> **Provenance** : ADR crew (DeepSeek), validé par l'Orchestrateur contre le code réel (structure du
> catalogue, overlay `deploy-minimal.json`, distribution des licences, point d'insertion `assemble_plan`).

## 1. Objectif (CANON CD-3 : « chaque brique = un plugin, vérification obligatoire »)

Toute brique sur le point d'être **exécutée/déployée** est contrôlée AVANT tout déploiement, **fail-closed** :
1. **Épinglée (UNIVERSEL)** — image par digest (`@sha256:` présent), pour TOUTE brique (plugin
   communautaire ET brique first-party du châssis) ; un tag flottant seul → refus. C'est le contrôle
   d'intégrité de fond, applicable et non contournable dès aujourd'hui.
2. **Vérifiée (plugins CATALOGUÉS)** — pour une brique présente au catalogue communautaire, `verified == true`
   (déterministe, hors-ligne ; ré-vérification API GitHub = job séparé, hors périmètre). Une brique
   first-party/châssis (absente du catalogue, ex. `postgres`, `reranker`) est de confiance dès lors qu'épinglée.
3. **Licenciée (plugins CATALOGUÉS)** — une licence EXPLICITE hors allowlist SPDX (propriétaire, `BUSL-1.1`,
   `CC-BY`, copyleft hors liste…) → refus. `NOASSERTION`/vide = licence non assertée dans le catalogue
   communautaire (fréquent sur les briques curées first-party, ex. `litellm`) : le risque est couvert par
   l'exigence `verified`, on ne refuse donc pas sur ce seul motif.

> **Provenance & décision** : l'ADR crew proposait un allowlist strict + « absente du catalogue → refus ».
> L'Orchestrateur a RAFFINÉ la politique après confrontation aux DONNÉES réelles du catalogue (196 briques
> `NOASSERTION`, dont des composants châssis déployés comme `litellm`) : refuser sur `NOASSERTION` ou sur
> l'absence du catalogue casserait des déploiements légitimes first-party. La politique retenue — épinglage
> universel + vérif/licence sur les seuls plugins communautaires catalogués (licence explicite mauvaise
> refusée, `NOASSERTION` tolérée) — préserve l'intégrité sans casser le châssis. Décision soumise à la revue scellée.

## 2. Code réel (données validées)

- `catalogue.json` : `{entries:[…1577], version}` ; chaque brique a `id, license, verified (bool),
  verified_at, verify_method, source_url`. Distribution licences réelles : Apache-2.0 (680), MIT (533),
  NOASSERTION (196), AGPL-3.0 (39), BSD-3-Clause (28), GPL-3.0 (21), « service propriétaire » (18), MPL-2.0 (11)…
- `deploy-minimal.json` : services exécutables `{name, brick_id, image, container_port, …}` où `image`
  porte le digest, ex. `ollama/ollama:latest@sha256:ec24…`.
- `planner/assemble.py` `assemble_plan()` : itère `minimal_stack(deploy_overlay)` → `ServiceSpec(image=svc["image"],…)`
  puis les briques `stack`/`extra_bricks`. **Point de garde unique** : juste avant de figer le `DeploymentPlan`.

## 3. Décision d'architecture

1. **Module `catalogue/supply.py`** (stdlib + `forgeai.catalogue.loader`) : `SupplyChainError`,
   `SupplyPolicy` (constante figée), `verify_service_before_exec(service, catalog_by_id, policy) -> None`.
   *Justif :* politique centralisée, testable hors-ligne, fail-closed non ambigu.
2. **`SupplyPolicy` (frozen)** : `license_allowlist: frozenset[str]`, `require_digest=True`,
   `require_verified=True`. Allowlist SPDX FOSS OSI : `MIT, Apache-2.0, BSD-2-Clause, BSD-3-Clause, ISC,
   MPL-2.0, GPL-2.0, GPL-3.0, LGPL-2.1, LGPL-3.0, AGPL-3.0`. *Justif :* moindre privilège pour les licences
   EXPLICITES ; `NOASSERTION`/vide traités à part (cf. point 4).
3. **Épinglé** = `"@sha256:" in image`. **UNIVERSEL** (châssis inclus). *Justif :* explicite, contrôle de fond.
4. **`verify_brick_before_exec(brick_id, image, catalog_index, policy)`** : (a) digest requis pour TOUTE
   brique ; (b) si `brick_id ∉ catalog_index` → brique first-party/châssis, l'épinglage SUFFIT (return) ;
   (c) si cataloguée : `verified` doit être vrai ; (d) licence : refus si la licence est EXPLICITE
   (`lic and lic != "NOASSERTION"`) ET hors allowlist ; `NOASSERTION`/vide tolérées (couvert par `verified`).
   *Justif :* colle aux données réelles (196 `NOASSERTION` dont du châssis) sans casser les déploiements.
5. **Adoption** dans `assemble_plan` : `catalog_index = load_catalog_index()` (index `{id:{verified,license}}`
   lu du catalogue BRUT car `Brick` n'expose pas `verified`/`license` ; `@lru_cache` = un seul chargement
   par process) ; appel de la garde dans LES DEUX boucles (minimal_stack `svc["brick_id"]/svc["image"]` et
   extra/stack `brick_id/spec["image"]`) AVANT `services.append`. *Justif :* le `brick_id` n'existe que dans
   les boucles (perdu dans `ServiceSpec` qui ne garde que `name`) ; choke-point couvrant tous les chemins.
6. **Hors périmètre** : ré-vérification réseau GitHub, surveillance continue, apurement des licences
   `NOASSERTION`/apurement du catalogue (migration data séparée), gate sur un futur chemin d'exécution de
   plugins purement communautaires (aujourd'hui seules des briques curées sont déployables).

## 4. Stratégie TDAD (`tests/test_supply018.py` — RED d'abord)

Fixtures : un `ServiceSpec`-like + un index catalogue `{id: entry}` fabriqués en test (pas de dépendance au vrai fichier).
- **G1 non épinglée** : image `ollama/ollama:latest` (sans `@sha256:`) → `SupplyChainError`.
- **G2 non vérifiée** : `verified=false` → refus.
- **G3 licence EXPLICITE hors allowlist** : `service propriétaire` / `BUSL-1.1` / `CC-BY-4.0` (verified) → refus ;
  `NOASSERTION` / `""` sur brique `verified` → **passe** (tolérée).
- **G4 brique NON cataloguée (châssis)** : épinglée → **passe** ; non épinglée → refus (épinglage universel).
- **G5 chemin heureux** : image `@sha256:…` + `verified=true` + `license=MIT` → passe.
- **G6 chaque licence de l'allowlist passe** (paramétré) ; une licence explicite hors liste échoue.
- **load_catalog_index** lit le catalogue BRUT (verified/license absents de `Brick`).
- **G7 chemin réel** : `assemble_plan(...)` (mock de `minimal_stack` + `load_catalog_index` sur
  `forgeai.planner.assemble`) : overlay NON épinglé → `SupplyChainError` ; châssis non catalogué mais
  épinglé → plan produit ; overlay conforme → plan produit.
- **Détectance** : muter la garde (`require_digest=False`, ou accepter licence explicite hors liste) → un test tombe.

## 5. Critères d'acceptation

- **CA1** brique NON épinglée (toute) / cataloguée-non-vérifiée / licence EXPLICITE non autorisée →
  `SupplyChainError` AVANT tout déploiement.
- **CA2** brique conforme (épinglée + [si cataloguée : verified + licence OK/NOASSERTION]) → plan produit ;
  brique châssis non cataloguée mais épinglée → plan produit.
- **CA3** garde réellement appelée depuis `assemble_plan` (dans les deux boucles, chemin réel).
- **CA4** allowlist = constante figée ; licence explicite inconnue → refus ; `NOASSERTION` tolérée (fail-closed
  sur l'épinglage + `verified`, pas sur l'absence d'assertion de licence).
- **CA5** suite COMPLÈTE verte (fixtures de test pré-existantes épinglées pour respecter l'épinglage universel),
  no-stub, couverture ≥ 85 %.

## 6. Risques

- `verified` faux-positif (confiance dans la donnée curée) — atténué : c'est la meilleure source hors-ligne ; ré-véif API = suivi.
- Briques légitimes en `NOASSERTION`/licence non-SPDX bloquées — assumé (fail-closed) ; apurement data séparé.
- Contournement si un futur chemin d'exécution évite `assemble_plan` — couvert par G7 (test du chemin réel) + suivi.
- Overlay legacy sans digest → refus au déploiement — force l'épinglage (objectif de la story).
