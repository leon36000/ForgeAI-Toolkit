# CAP-033A — Aligner les claims GPU sur les preuves réellement disponibles

## Contexte

Package coordination CAP-033A (issue #281, lane `capability-docs`, source CURSOR, exécuté par
COPILOT). Dépendance HW-037 satisfaite (mergée, PR #290, commit
`75e663fac71de4c71031f22dcdbe3af70d834e7a`) : la recommandation AMD/ROCm suit désormais le GPU
réellement détecté, message mort supprimé côté CLI.

La story vérifie que la documentation publique dans `allowed_paths` (README.md, AGENTS.md,
MASTER-PLAN.md, CANON/ETAT-SYSTEME.md, CANON/exigences-produit.md, Docs/**) décrit fidèlement
les capacités GPU réellement prouvées par le code — pas des promesses obsolètes ou optimistes.

## Audit (grep exhaustif du périmètre `allowed_paths`)

Mots-clés cherchés : `GPU|NVIDIA|AMD|ROCm|Intel|CUDA|nvidia-smi|iGPU|VRAM|Vulkan|dGPU|Instinct
|Radeon|CDNA|RDNA`.

| Fichier | Constat |
|---|---|
| `README.md` | « `forgeai doctor` sonde… CPU/GPU… » — fidèle à `preflight`/`hardware/detect.py`. Rien à corriger. |
| `AGENTS.md` | Aucune mention GPU. Rien à corriger. |
| `MASTER-PLAN.md` | « `hardware/` Détection CPU/GPU/RAM/disque multi-vendor → HardwareProfile » — c'est l'archi cible figée Phase A, fidèle à `hardware/detect.py::detect_gpus`. Rien à corriger. |
| `Docs/**` (README, reference/*, how-to, explanation, audit) | Aucune mention GPU. Rien à corriger. |
| `CANON/exigences-produit.md` (DM-2) | Réclame « détecter ET installer ET mettre à jour » les drivers GPU. **Intentionnellement non modifié** — voir « Décision » ci-dessous. |
| `CANON/ETAT-SYSTEME.md` | **2 écarts factuels prouvables** — voir détail ci-dessous. Ce fichier se définit lui-même (ligne 3) comme l'« état canonique des capacités réellement livrées et prouvées » : c'est le seul document dont l'exactitude vis-à-vis du code est non négociable. |

### Écart 1 — chemin de module fantôme

`CANON/ETAT-SYSTEME.md` ligne 48 :
> « **hardware/** détection ; **planner/** … **gpu/** (drivers GPU). »

Aucun package `src/forgeai/gpu/` n'existe. Le code du cycle de vie des drivers GPU vit dans
`src/forgeai/hardware/drivers.py` (vérifié : `find src/forgeai -iname "*gpu*"` ne retourne rien
en dehors de `hardware/`).

### Écart 2 — capacité d'exécution surclamée

`CANON/ETAT-SYSTEME.md` ligne 17 (table Surface CLI) et ligne 75 (État des phases) décrivent la
commande `gpu` comme gérant le « cycle de vie des drivers GPU » et classent « drivers GPU »
COUVERTE dans Extensions, au même niveau que des capacités pleinement livrées (UI Web 6 étapes,
plugins, réévaluation des défauts).

Or `_gpu_drivers` (`src/forgeai/cli.py`, appelée par `forgeai gpu drivers --action
install|update`) ne fait que :
1. détecter l'état du driver (`detect_driver_state`) ;
2. calculer un plan (`plan_driver_op` → `install_argv`/`rollback_argv`) ;
3. **imprimer** ce plan et le **journaliser** au registre.

Aucune exécution de commande sur l'hôte n'a jamais lieu (`test_cli_gpu_drivers_amd` dans
`tests/test_drivers.py` le confirme déjà : le test vérifie la sortie imprimée, jamais un effet
système). C'est un écart **déjà connu et assumé** dans `stories/HW-037.md`, section « Écart
résiduel (à ne pas masquer) » : *« L'exécution du plan d'installation des drivers attend
CLI-036 (CODEX : runner borné et annulable). La présente story couvre uniquement la
recommandation et son affichage, pas l'exécution. »* — mais cette réserve n'est **jamais
répercutée** dans `CANON/ETAT-SYSTEME.md`, qui reste donc en avance sur la réalité du code pour
quiconque le lit sans connaître `stories/HW-037.md`.

## Décision — `CANON/exigences-produit.md` non modifié

`CANON/exigences-produit.md` est un « extrait figé » (son propre en-tête, ligne 3-4) de
`CANON/plan-integral.md`, lui-même reproduction intégrale du plan maître externe
`FORGEAI-TOOLKIT-PLAN-INTEGRAL-20260714.md` (v2.0). Son en-tête dit explicitement : *« Toute
divergence entre ce canon et le PRD/stories du repo est un défaut à corriger côté repo. »*
Éditer ce fichier pour affaiblir DM-2 (« installer ET mettre à jour ») romprait son rôle de
reproduction fidèle d'une source externe et déplacerait la responsabilité de la divergence du
repo (où elle appartient, via une future story CLI-036) vers le canon des exigences (où elle
n'appartient pas). Le fichier reste donc **inchangé** ; la story se limite à
`CANON/ETAT-SYSTEME.md`, seul document qui prétend décrire l'état **livré**.

## Décision — correctif

Dans `CANON/ETAT-SYSTEME.md` uniquement :
1. Corriger la référence au sous-système : remplacer `**gpu/**` par le chemin réel
   `hardware/drivers.py`.
2. Ajouter une réserve explicite, visible près de la table Surface CLI, précisant que
   `gpu drivers --action install|update` affiche et journalise un plan mais **n'exécute
   jamais** de commande sur l'hôte, avec renvoi vers `stories/HW-037.md` et CLI-036.
3. Nuancer la ligne « Extensions COUVERTE » (État des phases) pour ne plus mettre « drivers
   GPU » au même niveau de complétude inconditionnelle que le reste.

Aucun changement de code : l'écart est documentaire, le comportement du code est déjà correct
et testé (`tests/test_drivers.py`).

## Critères d'acceptation (testables — `tests/test_docs_consistency.py`)

- [x] T1 : `CANON/ETAT-SYSTEME.md` ne référence plus `**gpu/**` (chemin inexistant) et cite
  `hardware/drivers.py`.
- [x] T2 (garde-fou anti-régression) : `_gpu_drivers` (`src/forgeai/cli.py`) n'exécute jamais
  `plan.install_argv`/`plan.rollback_argv` via un runner ou `subprocess` — seulement
  impression + journalisation. Ce test épingle un comportement déjà correct aujourd'hui.
- [x] T3 : `CANON/ETAT-SYSTEME.md` documente explicitement l'absence d'exécution réelle
  (mention de `CLI-036` ou équivalent).
- [x] T1 et T3 échouent (ROUGE) avant le correctif de `CANON/ETAT-SYSTEME.md`, passent (VERT)
  après.
- [x] `pytest` (suite complète) et `python3 scripts/no_stub_scan.py --all` verts après
  correctif.

## Revue aveugle scellée

Tentative via `~/proof-method/scripts/civ_review.py` + bridge LiteLLM (`localhost:4000`). Si
l'infrastructure n'est pas joignable dans cet environnement d'exécution, ce sera documenté ici
et dans le registre comme **BLOCKED-avec-raison**, sans jamais fabriquer de verdict.

## Périmètre respecté

`allowed_paths` de CAP-033A uniquement : `stories/CAP-033A.md` (ce fichier),
`tests/test_docs_consistency.py`, `CANON/ETAT-SYSTEME.md`, `Registres/PATCH-CAP-033A.jsonl`,
`reviews/CAP-033A/**` (si revue exécutée). Aucun autre fichier touché.
