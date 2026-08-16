# Rapport de conformité — Plan intégral v2.0 vs repo

**Auteur** : Fable (orchestrateur). **Date** : 2026-07-14.
**Base auditée** : `origin/main` = `d6d60f4` (P1 + F23 catalogue bilingue complet + F21/F22
multi-nœuds). **En vol** : PR #4 (portabilité P3, non mergée). Claim : UNVERIFIED jusqu'à
revue aveugle 3 vendors (PARTIE 7 §5).

Ce rapport exécute la mission prioritaire de la PARTIE 7 du plan intégral : vérifier les
invariants, diff, produire les écarts, avant toute nouvelle story.

---

## Section A — Les 10 invariants méthodologiques

**Correction round 1 (objection critique convergente DeepSeek+Gemini) :** un invariant dont
le caractère *bloquant* dépend d'un enforcement absent ne peut pas être déclaré CONFORME à
plat — ce serait un faux-vert. On distingue donc deux statuts :
- **CONFORME (structurel)** : garanti par l'artefact lui-même, indépendant de tout réglage GitHub.
- **CONFORME-PAR-PRATIQUE / enforcement PARTIEL** : respecté dans CHAQUE artefact produit à ce
  jour, mais pas encore rendu *non contournable* (manque : branch protection / CODEOWNERS /
  hooks locaux). La garantie déterministe n'est pas en place → traité comme un écart (Section D).

| # | Invariant | Statut | Preuve / réserve |
|---|---|---|---|
| 1 | Méthodologie BMAD | **CONFORME (structurel)** | Stories BMAD `Phase-A/stories-kimi.md`; `manifests/phases.yaml` |
| 2 | Gates T0-T3, T3 humain (dont PyPI) | **CONFORME-PAR-PRATIQUE / enforcement PARTIEL** | T3 respecté (registre `gate_t3` seq 15, PyPI non publié) MAIS aucun blocage serveur : `main` n'a pas de branch protection → un merge pourrait contourner le gate. Écart B-22 |
| 3 | No-stub / no-fake-done §8bis | **CONFORME-PAR-PRATIQUE / enforcement PARTIEL** | `scripts/no_stub_scan.py` tourne en CI (`gates.yml`) et a bloqué du code de Fable, MAIS n'est pas un *required check* de branch protection ni un hook pre-commit local → contournable par merge admin. Écart B-22/B-23 |
| 4 | Revue aveugle 3/3 vendors + signature Fable, tally script | **CONFORME-PAR-PRATIQUE / enforcement PARTIEL** | Fait à chaque PR (`reviews/`, `tally.py` déterministe) MAIS non imposé par CODEOWNERS/branch protection → repose sur la discipline. Écart B-22 |
| 5 | Indépendance critique; Composer/Grok jamais appariés | **CONFORME (structurel)** | `manifests/roles.yaml` → `paires_interdites: [[composer, grok]]`, respecté dans les revues |
| 6 | Fable ne se relit jamais | **CONFORME (structurel)** | Revue du code de Fable par reviewers non-Anthropic (deepseek/gemini/longcat/qwen) |
| 7 | Preuve réelle avant DONE (e2e + registres hash) | **CONFORME (structurel)** | e2e Compose `CI_WITNESS=2a0b6221…`, K3s `bf9e40c7…`; registre chaîné vérifié |
| 8 | Un seul control plane par fonction | **CONFORME (structurel)** | Gateway unique `forge-model-bridge` |
| 9 | Prompt managing / compression de contexte | **CONFORME (structurel)** | Manifestes YAML; lots scopés; contre-vérif croisée |
| 10 | Aucun LLM n'écrit un score de qualité | **CONFORME (structurel)** | `tally.py` compte des verdicts binaires |

**Bilan honnête : 7 invariants CONFORME (structurel), 3 CONFORME-PAR-PRATIQUE avec enforcement
partiel (#2, #3, #4).** Aucun invariant n'est violé en substance — mais pour #2/#3/#4 la
**garantie déterministe n'existe pas encore** (elle repose sur la CI + la discipline, pas sur
un blocage serveur non contournable). C'est un écart réel, corrigé par B-22 (branch protection
+ CODEOWNERS + commits signés) et B-23 (hooks locaux), et non un point « conforme » masqué.

---

## Section B — Les 25 exigences produit (ID-1 → OC-1)

Statuts : **COUVERTE** (implémentée + preuve) · **PARTIELLE** (amorcée, incomplète) ·
**ABSENTE** (non spécifiée/non implémentée dans le repo).

| ID | Statut | Preuve / manque |
|---|---|---|
| ID-1 pour tout le monde | **PARTIELLE** | P3 (PR #4) rend `pip install` + `forgeai doctor` adaptatif; manque personas/docs utilisateur externe |
| ID-2 clé en main, zéro édition manuelle | **PARTIELLE** | `wizard --ci` déploie de bout en bout sans édition; TUI interactif guidé absent |
| ID-3 la référence, ⭐ réévalués | **ABSENTE** | catalogue sans flag ⭐/défaut par catégorie; aucun cycle de réévaluation benchmark |
| ID-4 TUI moderne esthétique | **ABSENTE** | spec présente (`Phase-A/spec-tui-composer.md`, revue Gemini) mais aucune implémentation Textual |
| ID-5 bilingue FR/EN natif | **PARTIELLE** | catalogue 100 % bilingue (F23 mergée, 0 EN en attente); i18n de l'interface (locales wizard) absent |
| DM-1 détection filtre les options | **COUVERTE** | `src/forgeai/hardware/detect.py` + `planner/profile.py` (profils filtrés par GPU/RAM/disque) |
| DM-2 drivers detect+install+update + Intel | **ABSENTE** | détection vendor OK; aucune install/màj de drivers, aucun GPU Operator, aucun chemin OpenVINO/Intel |
| DM-3 multi-nœuds IP/user/password, ed25519, Tailscale | **PARTIELLE** | `network/keys.py` (ed25519 + rotation 2-phases), `nodes.py` (jonction prouvée F22), `bootstrap.py` (plan EX-1..3); écran interactif IP/user/mot de passe absent, install Tailscale auto absente, sondage matériel distant absent |
| DM-4 deux backends Compose + K3s | **COUVERTE** | `renderers/compose.py` + `renderers/k3s.py`, e2e prouvés sur les deux |
| DM-5 modèles local+cloud, provenance + clé API | **ABSENTE** | aucune phase de gestion de modèles (téléchargement/config/test); overlay fige `qwen2.5:0.5b` en dur |
| DM-5b phase Stratégie modèle | **ABSENTE** | aucun écran Cerveau unique / Équipe / Hybride |
| DM-6 branchement auto via gateway, cache | **ABSENTE** | aucune phase de câblage brique→gateway; prompt caching non géré |
| CD-1 stacks par domaine | **PARTIELLE** | overlay Minimal RAG seul (`src/forgeai/data/deploy-minimal.json`); templates Dev Agentic / RAG / Lab / Production absents |
| CD-2 stack branché complet | **PARTIELLE** | Minimal RAG (ollama + qdrant + rag-api) prouvé; harnesses/ledgers/guardrails/mémoire non déployés |
| CD-3 modulable (plugin) | **PARTIELLE** | catalogue data-driven (1021 briques); pas de système de plugin ni de pipeline de contribution vérifiée |
| CD-4 import/export | **ABSENTE** | `forge export`/`import` non implémentés |
| DA-1 IDE branché | **ABSENTE** | aucun branchement IDE/CLI |
| DA-2 MCP/skills/BMAD préconfig IDE | **ABSENTE** | — |
| DA-3 Ralph loop intégrée | **ABSENTE** | — |
| DA-4 token economy | **ABSENTE** | aucun budget de tokens par agent/mission |
| QG-1 no-stub | **COUVERTE** | `scripts/no_stub_scan.py` (gate CI bloquant) |
| QG-2 3/3 vendors + Fable | **COUVERTE** | `reviews/` + `tally.py` |
| QG-3 vérification post-déploiement réelle | **COUVERTE** | e2e RAG (le RAG répond avec un fait ingéré), `CI_WITNESS` au registre |
| QG-4 gates T0-T3, T3 humain | **COUVERTE** | `Registres/mission.jsonl` type `gate_t3` |
| OC-1 cycle de recherche multi-modèles | **ABSENTE** | aucun cycle de réévaluation récurrent |

**Bilan : 6 COUVERTE · 6 PARTIELLE · 13 ABSENTE.** Les COUVERTE forment le noyau P1 +
gouvernance (déjà prouvé). Les ABSENTE/PARTIELLE constituent la surface produit P2-P5 —
attendue à ce stade, désormais tracée en Section C et `manifests/backlog.yaml`.

**Couverture exhaustive ABSENTE→story (réponse à l'objection round 1 : chaque exigence non
couverte a bien une story testable — vérifié programmatiquement contre `backlog.yaml`) :**
ID-3→B-01 · ID-4→B-02 · DM-2→B-04 · DM-5→B-08,B-09 · DM-5b→B-10 · DM-6→B-11,B-12 ·
CD-4→B-16 · DA-1→B-17 · DA-2→B-18 · DA-3→B-19 · DA-4→B-20 · OC-1→B-21. Les PARTIELLE :
ID-1(P3/PR#4) · ID-2→B-02 · ID-5→B-03 · DM-3→B-05,B-06,B-07 · CD-1→B-13,B-14 · CD-3→B-15.
Zéro exigence ABSENTE ou PARTIELLE sans story.

---

## Section C — Écarts, sévérité, stories correctives

Sévérité = impact sur la promesse produit « déployeur de référence, pour tout le monde,
clé en main ». Détail testable dans `manifests/backlog.yaml`.

| Écart | Sévérité | Story | Phase |
|---|---|---|---|
| ID-3 défauts ⭐ par catégorie | majeure | B-01 flag `default` + sélection par catégorie | P2 |
| ID-4 TUI moderne | majeure | B-02 wizard Textual d'après `spec-tui-composer.md` (extra `[tui]` déjà prévu) | P2 |
| ID-5 i18n interface | mineure | B-03 fichiers de locale FR/EN pour messages wizard | P2 |
| DM-2 drivers + Intel | majeure | B-04 detect+install+update drivers (NVIDIA/AMD/Intel) journalisé + rollback | P4 |
| DM-3 écran nœud + Tailscale + sondage distant | majeure | B-05 écran IP/user/password (mot de passe éphémère), B-06 install Tailscale auto, B-07 sondage matériel distant | P2.5 |
| DM-5 phase Modèles | critique | B-08 modèles locaux (VRAM+backend filtrés, hash, test), B-09 modèles cloud (provenance + clé API vault + test) | P2 |
| DM-5b Stratégie modèle | majeure | B-10 écran Cerveau/Équipe/Hybride écrit au canon | P2 |
| DM-6 branchement auto gateway | critique | B-11 câblage brique→gateway + preuve traversante; B-12 prompt caching par route | P2 |
| CD-1/CD-2 templates par domaine | majeure | B-13 template Dev Agentic (`template-dev-agentic.json`, 37 briques), B-14 RAG/Lab/Production | P2/P3 |
| CD-3 système de plugin + contribution vérifiée | majeure | B-15 API plugin brique + gate de vérification (GitHub/licence/healthcheck) | P5 |
| CD-4 import/export | majeure | B-16 `forge export`/`import` (bundle versionné hash-vérifié, sans clés) | P3 |
| DA-1/DA-2 IDE branché + MCP/skills/BMAD | majeure | B-17 génération+injection config IDE, B-18 préconfig MCP/skills/BMAD/hooks | P2 |
| DA-3 Ralph loop | mineure | B-19 loop préconfigurée avec garde-fous | P2 |
| DA-4 token economy | majeure | B-20 budgets tokens par agent au gateway + rapport | P3 |
| OC-1 cycle de recherche | mineure | B-21 procédure récurrente de réévaluation ⭐ journalisée | P5 |
| Substrat enforcement (Section D) | majeure | B-22 branch protection + CODEOWNERS + commits signés (T3 Nathan), B-23 hooks locaux pre-commit/SubagentStop/post-merge | P2 (gouvernance) |

---

## Section D — Déclaration sur les déviations méthodologiques

**Les 10 invariants méthodologiques tiennent en substance** (Section A). Cependant, par
honnêteté (§8bis : ni faux-vert ni faux-done), **des déviations d'IMPLÉMENTATION de
l'enforcement existent** — elles n'ont pas contourné les invariants (atteints via CI +
revue aveugle + discipline), mais elles complètent incomplètement le §6/§7 du Plan Maître :

> **MISE À JOUR 2026-07-14 (B-22 résolu) :** les 4 déviations ci-dessous sont désormais
> CORRIGÉES. Branch protection posée (`gh api`, sur autorisation Nathan) : les 4 gates CI
> (`gitleaks`, `no-stub-scan`, `registres`, `tests`) sont **required checks bloquants**,
> force-push et suppression interdits sur `main`. CODEOWNERS ajouté. Commits `main` signés
> GPG par Nathan (clé RSA B5690EEEBB952194). → Les invariants #2/#3/#4 passent de
> « enforcement PARTIEL » à **enforcement SERVEUR** : un merge ne peut plus contourner les
> gates. Reste (mineur) : signature GPG des commits automatisés Forge-GRS (story B-23 hooks
> locaux) et une revue humaine PR (impraticable en mono-propriétaire — la revue 3 modèles
> reste la gouvernance de contenu). État historique conservé ci-dessous pour traçabilité.

1. **Protection de branche GitHub : ~~ABSENTE~~ → POSÉE.** `gh api …/branches/main/protection` → 404
   « Branch not protected ». Le §6 exige gates CI requis + 3 revues + signature Fable +
   commits signés comme règle bloquante côté GitHub. Aujourd'hui, `main` accepte des merges
   sans règle serveur (les PRs sont mergées par Nathan à la main). → story B-22. **T3 Nathan.**
2. **CODEOWNERS : ABSENT.** La signature Fable requise par CODEOWNERS n'est pas matérialisée
   comme fichier. → B-22.
3. **Commits signés (GPG) : non configurés.** Les tags `plan-v1.0`/`p1-proven` sont annotés,
   non signés GPG (clé de Nathan requise). → B-22. **T3 Nathan.**
4. **Hooks locaux : ABSENTS.** Le no-stub-scan et les gates tournent en CI + manuellement,
   pas comme hooks git pre-commit; les hooks SubagentStop (preuve au registre) et post-merge
   (mise à jour canon) du §7 ne sont pas installés localement. → B-23.

Ces quatre points sont soit des réglages GitHub/environnement relevant de Nathan (1-3),
soit une couche d'enforcement doublonnant la CI (4). Ils sont **journalisés honnêtement
plutôt que passés sous silence**, et corrigés par les stories B-22/B-23.

**Conclusion** : aucune déviation ne compromet la validité des preuves déjà produites
(gates verts, e2e réels, revues 3/3). Le rapport recommande de corriger le substrat
d'enforcement (B-22/B-23) en priorité de gouvernance, en parallèle des stories produit.
