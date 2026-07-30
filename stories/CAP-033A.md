# CAP-033A — Aligner les claims GPU sur les preuves réellement disponibles

## Identité

- **Owner/repo** : `leon36000/ForgeAI-Toolkit`
- **Branche cible** : `main`
- **Branche de travail** : `docs/CAP-033A-gpu-claims-evidence`
- **Exécuteur** : `COPILOT`
- **Lane** : `capability-docs`
- **Statut** : implémentation (correctif documentaire, pas un ADR)
- **Priorité/Sévérité** : `P2_HIGH` / `S2_MEDIUM`
- **Issue** : `#281`
- **Dépendance** : `HW-037` — fusionné dans `main` (PR #290, `merge_commit` `75e663f` ;
  archivage `coordination/completed.json` via PR #293).

## Procédure exécutée

1. Lu l'issue `#281` (`[CAP-033A] Aligner les claims GPU sur les preuves réellement
   disponibles`) et `coordination/work-packages.json` (`allowed_paths` du package).
2. Vérifié via `scripts/coordination/validate_coordination.py` : `62 packages, 0 claims
   actifs, 28 complétés, zéro erreur` — lane `capability-docs` libre.
3. Créé la branche `docs/CAP-033A-gpu-claims-evidence` depuis le dernier `origin/main`
   (`984c74d64c1b8693994347619f847819245220da`, post-archivage HW-037 PR #293).
4. **Confirmé le défaut LIVE sur `origin/main`** : `CANON/ETAT-SYSTEME.md` affirmait
   (ligne 17, table CLI) « cycle de vie des drivers GPU NVIDIA/AMD/Intel » et (ligne 75,
   section « Extensions ») listait « drivers GPU » comme capacité `COUVERTE`, sans
   distinguer le niveau de preuve réel par vendeur :
   - **NVIDIA** : qualifié sur matériel réel (registre `HW-010`).
   - **AMD** : qualifié sur matériel réel (registre `HW-037`, PR #290 — chemin
     Instinct/CDNA→rocm vs Radeon/RDNA→vulkan, 12/12 `tests_drivers` dont 4 nouveaux,
     mutation testing appliqué).
   - **Intel** : `recommend_driver("intel", …)`/`plan_driver_op("intel", …)`
     (`src/forgeai/hardware/drivers.py`) sont implémentées et couvertes par des tests
     **unitaires** (`tests/test_intel_openvino_runtime.py`,
     `tests/test_gpu_reservation_vendor.py::test_render_intel_reserve_dri`,
     `tests/test_k3s_gpu_vendor.py::test_k3s_intel_sans_privileged` /
     `test_k3s_intel_passthrough_dri`) — mais **aucune qualification de bout en bout sur
     matériel réel** n'a eu lieu. L'issue `#284` (`[LAB-033I] Qualifier le chemin Intel de
     bout en bout en laboratoire`) est `EN ATTENTE`, explicitement bloquée sur `CAP-033A`
     dans `coordination/work-packages.json` (`dependencies: ["CAP-033A"]`).
5. **Écrit le test rouge** `tests/test_docs_consistency.py` (4 tests, assertions réelles,
   lit les vrais fichiers du dépôt — aucun mock de filesystem) :
   - `test_gpu_drivers_reference_doc_exists_and_traces_intel_issue` — exige
     `Docs/reference/gpu-drivers-support.md`, citant `nvidia`/`amd`/`intel` et `LAB-033I`.
   - `test_etat_systeme_refers_to_gpu_drivers_reference` — exige un renvoi vers ce document
     depuis `CANON/ETAT-SYSTEME.md`.
   - `test_etat_systeme_no_longer_claims_uniform_gpu_driver_coverage` — interdit la chaîne
     fautive exacte `cycle de vie des drivers GPU NVIDIA/AMD/Intel`.
   - `test_gpu_drivers_reference_covers_exact_code_vendors` — importe réellement
     `forgeai.hardware.drivers.VENDORS` et exige que le document cite EXACTEMENT ces
     vendeurs (aucune liste dupliquée en dur) : un futur ajout de vendeur dans le code
     casse ce test tant que la doc n'est pas mise à jour.
   **Confirmé rouge** contre le code original : 4/4 échecs (`Docs/reference/gpu-drivers-
   support.md` absent, ancienne chaîne non qualifiée toujours présente).
6. **Implémenté le correctif documentaire**, strictement dans le périmètre autorisé :
   - Nouveau `Docs/reference/gpu-drivers-support.md` : tableau à 4 colonnes (Vendeur |
     Implémentation | Preuve laboratoire | Tests) citant les fonctions réelles du code, le
     niveau de preuve exact par vendeur (`Qualifié sur matériel réel — registre HW-010`/
     `HW-037` pour NVIDIA/AMD ; `Implémenté — qualification laboratoire en attente. Issue
     LAB-033I` pour Intel) et les fichiers de test réels qui le couvrent aujourd'hui.
   - `CANON/ETAT-SYSTEME.md` ligne 17 (table CLI, commande `gpu`) et ligne 75 (« Extensions
     COUVERTE ») : reformulées pour ne plus affirmer un niveau de preuve uniforme entre
     vendeurs — NVIDIA/AMD marqués « qualifiés labo », Intel marqué « implémenté,
     qualification labo en attente », avec renvoi vers le nouveau document de référence.
     Aucune autre ligne du fichier modifiée.
   - `CANON/exigences-produit.md` (extraction verbatim d'un canon externe versionné),
     `README.md` et `MASTER-PLAN.md` **non modifiés** : mentions déjà génériques
     (`CPU/GPU`), aucune sur-affirmation par vendeur à corriger.
7. **Preuve rouge→vert (TDD strict)** : ré-exécution des 4 tests après le correctif —
   **4/4 verts**.
8. Gates exécutés : `pytest -q` complet (repo entier, après `git add -A`) → vert, aucun
   échec (seulement les skips préexistants) ; `no_stub_scan.py --all` → OK (276 fichiers,
   0 violation) ; `gitleaks detect --no-git -v --source .` → 0 fuite ; `git diff --cached
   --name-only` limité à `CANON/ETAT-SYSTEME.md`, `Docs/reference/gpu-drivers-support.md`,
   `tests/test_docs_consistency.py` (+ ce fichier story) — conforme au périmètre autorisé
   `allowed_paths` de `CAP-033A`, aucun fichier interdit touché (aucun fichier
   `src/forgeai/**` modifié : correctif purement documentaire).
9. **Codage délégué** : spécification écrite par l'Orchestrateur (`/tmp/cap033a/spec.md`),
   contexte réel fourni (`src/forgeai/hardware/drivers.py`, `CANON/ETAT-SYSTEME.md`, tests
   Intel existants), dispatché à `crew-coder-long` (Kimi K2.7 Code) via
   `~/proof-method/scripts/crew_dispatch.py`. L'Orchestrateur a appliqué, testé (rouge puis
   vert) et validé la sortie — n'a pas rédigé le contenu documentaire lui-même.
10. **Revue aveugle scellée — tour 1** (`CIV_MODELS=DeepSeek-V4-Pro,Gemini-3.1-Pro,LongCat-2.0`,
    3 vendors distincts du codeur Kimi/moonshot) : `Gemini-3.1-Pro` a échoué (`HTTP 429 Too Many
    Requests`, route instable — journalisée, jamais masquée, `tally_reviews.py` a correctement
    rapporté `INCOMPLET: 2/3 verdicts déposés`, exit 2). Les 2 verdicts obtenus étaient
    `APPROVE`/`APPROVE` ; `DeepSeek-V4-Pro` a soulevé une objection mineure fondée : le tableau
    affirmait que `LAB-033I` est « bloquée sur CAP-033A », affirmation qui devient immédiatement
    obsolète dès la fusion de cette PR. **Corrigé** dans
    `Docs/reference/gpu-drivers-support.md` : la ligne Intel ne réaffirme plus un statut de
    dépendance transitoire ; une note renvoie vers `coordination/work-packages.json` comme
    source vivante du statut de `LAB-033I`. Un APPROVE n'autorise pas à ignorer une objection
    fondée — corrigé avant la fusion, comme pour `PLACE-011`.

## Root cause

`CANON/ETAT-SYSTEME.md` (préambule : « État canonique des capacités **réellement livrées et
prouvées** ») affirmait une couverture uniforme « NVIDIA/AMD/Intel » pour le cycle de vie des
drivers GPU, alors que seuls NVIDIA et AMD disposent d'une qualification de bout en bout sur
matériel réel (registre `HW-010`/`HW-037`) ; Intel est implémenté et testé unitairement mais
sa qualification laboratoire (`LAB-033I`) reste explicitement en attente. C'est exactement
l'écart que ce package devait corriger : aligner l'affirmation documentaire sur la preuve
disponible, sans retirer la fonctionnalité Intel existante (le code reste inchangé) ni
inventer une preuve de qualification qui n'existe pas.

## Limites / non fait dans cette branche

- `CANON/exigences-produit.md` (DM-2) n'a pas été modifié : c'est une extraction verbatim
  d'un canon externe versionné (« Toute divergence … est un défaut à corriger côté repo » —
  le repo, pas cette extraction, porte la correction), hors périmètre de cette story.
- La qualification laboratoire réelle du chemin Intel (`LAB-033I`, `CLAUDE_CODE`) reste à
  faire séparément — ce package ne fait qu'aligner la documentation sur l'état actuel, il ne
  réalise pas la qualification elle-même.

## Rapport final

```text
PACKAGE: CAP-033A
REPOSITORY: https://github.com/leon36000/ForgeAI-Toolkit
BRANCH: docs/CAP-033A-gpu-claims-evidence
BASE_COMMIT: 984c74d64c1b8693994347619f847819245220da (origin/main, post-archivage HW-037 PR #293)
MERGE_SHA: PENDING (mis à jour après fusion)
FILES_CHANGED: CANON/ETAT-SYSTEME.md, Docs/reference/gpu-drivers-support.md,
  tests/test_docs_consistency.py, stories/CAP-033A.md, reviews/CAP-033A/**,
  Registres/PATCH-CAP-033A.jsonl
ROOT_CAUSE: CANON/ETAT-SYSTEME.md affirmait un niveau de preuve uniforme NVIDIA/AMD/Intel pour
  le cycle de vie des drivers GPU alors qu'Intel n'a pas de qualification laboratoire réelle
  (LAB-033I en attente), contrairement à NVIDIA (HW-010) et AMD (HW-037).
REPRODUCTION_BEFORE: chaîne fautive confirmée LIVE : « cycle de vie des drivers GPU
  NVIDIA/AMD/Intel » (ETAT-SYSTEME.md:17) et « drivers GPU » non qualifié (ETAT-SYSTEME.md:75).
IMPLEMENTATION: nouveau Docs/reference/gpu-drivers-support.md (matrice vendeur/preuve/tests) ;
  ETAT-SYSTEME.md lignes 17 et 75 reformulées (NVIDIA/AMD qualifiés labo, Intel implémenté +
  qualification labo en attente, renvoi vers le nouveau document).
FOCUSED_TESTS: pytest -q tests/test_docs_consistency.py → 4/4 vert (rouge confirmé avant le
  correctif : 4/4 échecs).
NEGATIVE_TESTS: test_etat_systeme_no_longer_claims_uniform_gpu_driver_coverage interdit le
  retour de la chaîne fautive exacte ; test_gpu_drivers_reference_covers_exact_code_vendors
  importe VENDORS réel du code (casse si un vendeur est ajouté sans mise à jour doc).
FULL_GATES: pytest -q (repo entier) vert ; no_stub_scan.py --all OK (276 fichiers, 0 violation) ;
  git diff --cached --name-only limité au périmètre allowed_paths.
SECURITY_SCANS: gitleaks detect --no-git -v --source . → 0 fuite.
EVIDENCE_PATH: stories/CAP-033A.md (ce fichier), Docs/reference/gpu-drivers-support.md,
  tests/test_docs_consistency.py, reviews/CAP-033A/*.verdict.json,
  Registres/PATCH-CAP-033A.jsonl.
ROLLBACK_RESULT: revert du commit de PR — aucun schéma/donnée persistante modifié
  (documentation pure), rollback trivial.
LIMITATIONS: CANON/exigences-produit.md (DM-2, extraction verbatim d'un canon externe) non
  modifié, hors périmètre ; qualification laboratoire Intel (LAB-033I) non réalisée par ce
  package, seulement débloquée.
REVIEW_STATUS: 2 tours de revue aveugle scellée. Tour 1 : `Gemini-3.1-Pro` route instable
  (`HTTP 429`), 2/3 verdicts déposés (`DeepSeek-V4-Pro`/`LongCat-2.0`, `APPROVE`/`APPROVE`) ;
  objection mineure fondée de `DeepSeek-V4-Pro` corrigée (formulation transitoire de
  `LAB-033I` retirée du document). Tour 2 (pack reconstruit, sceau frais
  `09b55a6a8d323a212a52d6c589b8dcfdbff6e33536fb61adee9990526a1c9827`) : route `Gemini-3.1-Pro`
  remplacée par `Qwen3.7-Max` (pool de swap, vendor `alibaba` distinct) — **APPROVE 3/3, zéro
  objection** (`DeepSeek-V4-Pro`/deepseek, `LongCat-2.0`/meituan, `Qwen3.7-Max`/alibaba, tous
  distincts du codeur `Kimi K2.7 Code`/moonshot). Dépouillement déterministe :
  `scripts/revue.py tally reviews/CAP-033A` → `APPROVE`, `bloquantes: []`. Preuve appendue à
  `Registres/PATCH-CAP-033A.jsonl` (seq 1-2, chaîne intègre vérifiée).
OPEN_RISKS: débloque LAB-033I (CLAUDE_CODE, qualification laboratoire Intel réelle) ; DOC-032
  reste bloqué (dépend aussi de OPS-031E, lui-même bloqué sur OPS-031C, CODEX).
READY_FOR_PR: YES
STATUS: PENDING (fusion à venir)
```
