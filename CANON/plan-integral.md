# FORGEAI TOOLKIT — PLAN INTÉGRAL
# ÉDITION CONSOLIDÉE COMPLÈTE — LE VIEUX ET LE NEUF, VERBATIM
**Version 2.0-INTÉGRALE — 14 juillet 2026**
**Statut : DOCUMENT DE RÉFÉRENCE UNIQUE. Ce document contient l'intégralité, mot pour mot, de tous les documents de plan en vigueur. Il remplace la dispersion en 6 fichiers qui a causé les écarts de transmission constatés.**

---

## PRÉAMBULE — POURQUOI CETTE ÉDITION EXISTE

Défaut constaté et corrigé : des exigences fondatrices (phase Nœuds IP/user/mot de passe, configuration des modèles cloud avec clés API, « pour tout le monde », clé en main, import/export...) vivaient dans des addenda traités comme « annexes de référence » — jamais garantis d'être dans le contexte de l'équipe d'exécution. Résultat : des écarts entre la vision et le PRD du repo.

Cette édition règle ça par le verbatim intégral : TOUT est ici, dans un seul fichier, dans l'ordre de lecture obligatoire. Aucun document externe n'est requis pour connaître le plan complet.

**Exclusion documentée :** le plan v1 (FORGEAI-TOOLKIT-PLAN-PROMPT-20260713, « suite d'outils de gouvernance ») est exclu de cette édition car explicitement supersédé par le pivot v2 (déployeur). L'inclure réintroduirait des instructions contradictoires. Il reste archivé hors de ce document.

---

## INVARIANTS MÉTHODOLOGIQUES — RIEN NE CHANGE, ET C'EST UNE RÈGLE

Instruction explicite de Nathan : les méthodes établies restent EXACTEMENT les mêmes. Cette édition consolide le contenu; elle ne modifie AUCUNE méthode. Pour lever toute ambiguïté, les invariants intouchables :

1. **Méthodologie BMAD** pour la structuration (PRD, architecture, stories) — inchangée.
2. **Gates T0-T3** — inchangés. T3 (paiements, secrets prod, suppressions définitives, engagements externes — dont la publication PyPI) = approbation humaine de Nathan.
3. **No-stub / no-fake-done (§8bis du Plan Maître)** — inchangé. Deux états de sortie : DONE-avec-preuve ou BLOCKED-avec-raison. Le no-stub-scan bloque sans exception, y compris le code de Fable.
4. **Revue aveugle scellée + validation à 3 modèles de 3 vendors différents + signature Fable** — inchangée. Dépouillement par script, jamais par un LLM. Rounds Delphi anonymisés si pas de consensus.
5. **Indépendance critique** — inchangée. Aucune discussion inter-modèles avant vote; Composer et Grok (même vendor xAI) jamais appariés comme reviewers l'un de l'autre.
6. **Fable = orchestrateur unique, juge, validateur d'étapes, codeur du difficile** — désigne toujours et uniquement l'instance Claude Fable 5 dans Claude Code. Fable ne se relit jamais lui-même (reviewers non-Anthropic sur son code).
7. **Preuve réelle avant DONE** — inchangée. Tests bout-en-bout fonctionnels (le RAG répond, le nœud joint, le modèle complète), registres append-only horodatés, hash vérifiés.
8. **Un seul control plane par fonction** — inchangé. Un seul gateway, une seule autorité d'état, une seule voie de production.
9. **Prompt managing / compression de contexte** — inchangé. Context packs scopés par story, manifestes YAML machine-lisibles, préfixes stables pour le cache.
10. **Aucun LLM n'écrit un score de qualité** — inchangé. Les verdicts sont des fonctions pures de gates binaires.

---

## SOMMAIRE DE L'ÉDITION INTÉGRALE

- **PARTIE 1 — EXIGENCES PRODUIT CANON** (l'autorité : les 25 exigences, anciennes et nouvelles, avec statut de spécification)
- **PARTIE 2 — PLAN MAÎTRE D'EXÉCUTION BMAD v1.0 revalidée** (équipe, méthodes, gouvernance, pipeline, §8bis)
- **PARTIE 3 — PLAN V2 : LE DÉPLOYEUR** (vision produit, analyse concurrentielle, wizard, profils, templates, phasage)
- **PARTIE 4 — ADDENDUM v2.1 : CATALOGUE, BILINGUISME, DESIGN** (1021 entrées, FR/EN, catalogue embarqué, esthétique)
- **PARTIE 5 — ADDENDUM v2.2 : MULTI-NŒUDS & TAILSCALE** (phase Nœuds IP/user/mot de passe, bootstrap ed25519, matrice backends par GPU, rôles par nœud)
- **PARTIE 6 — ADDENDUM v2.3 : STRATÉGIE, MODÈLES & BRANCHEMENT** (phase Stratégie modèle, modèles locaux/cloud avec clés API, câblage automatique via gateway, prompt caching)
- **PARTIE 7 — INSTRUCTION DE RELECTURE INTÉGRALE ET RAPPORT DE CONFORMITÉ** (la mission de vérification anti-déviation)

---

-e 
---
---

# PARTIE 1 — EXIGENCES PRODUIT CANON
*(Document source : EXIGENCES-PRODUIT-CANON-20260714 — reproduit intégralement)*

# FORGEAI TOOLKIT — EXIGENCES PRODUIT CANON
**Version 1.0 — 14 juillet 2026**
**Statut : DOCUMENT CANONIQUE UNIQUE des exigences produit. Toute divergence entre ce canon et le PRD/stories du repo est un défaut à corriger côté repo. Ce document supersède, pour les exigences produit, les formulations dispersées dans le Plan Maître et les addenda v2/v2.1/v2.2/v2.3.**

---

## 0. Pourquoi ce document existe

Défaut récurrent constaté : des exigences fondatrices vivaient dans des annexes que l'équipe d'exécution ne lisait pas, ou uniquement dans la tête de Nathan. Ce canon consolide TOUT en un seul endroit, avec pour chaque exigence son statut de spécification au moment de la consolidation — pour que le diff avec le PRD du repo soit mécanique.

Légende des statuts :
- ✅ **PLAN-MAÎTRE** : déjà dans le document qui a piloté l'exécution
- 📎 **ANNEXE** : spécifié, mais seulement dans un addendum (risque de non-transmission — à vérifier dans le PRD)
- 🆕 **NOUVEAU** : jamais écrit dans aucun document avant ce canon

---

## 1. Identité du produit

| ID | Exigence | Statut |
|---|---|---|
| ID-1 | Le Toolkit est un produit **pour tout le monde** — développeurs solo, homelabs, PME, équipes infra — pas un outil interne. Tout choix de design se juge à l'aune d'un utilisateur externe qui n'a jamais vu Forge. | 📎 (plan v2, jamais dans le Plan Maître) |
| ID-2 | **Solution clé en main** : télécharger l'application → suivre les phases de configuration → obtenir une infrastructure fonctionnelle, branchée, opérationnelle. Aucune édition manuelle de fichier requise pour un déploiement standard. | 📎 (addendum v2.1) |
| ID-3 | **La référence en la matière, rien de moins** — opérationnalisé comme discipline continue, pas comme slogan : les défauts ⭐ de chaque catégorie sont les meilleurs choix éprouvés du moment, réévalués par benchmark à chaque release; une brique supérieure remplace l'ancienne (règle de sélection Atlas). Mises à jour continues pour suivre la technologie. | 📎 (plan v2 §catalogue) |
| ID-4 | **Interface très intuitive, moderne, très esthétique** : TUI moderne (critères d'acceptation esthétiques explicites) puis UI web avec design system défini avant le code. Critère : un utilisateur externe qualifie spontanément l'interface de soignée. | 📎 (addendum v2.1 §5) |
| ID-5 | **Bilingue FR/EN natif** (interface + catalogue), architecture i18n extensible. | 📎 (addendum v2.1 §2) |

## 2. Déploiement et matériel

| ID | Exigence | Statut |
|---|---|---|
| DM-1 | Détection matérielle automatique (OS/CPU/RAM/disque/GPU vendor+VRAM+drivers) filtrant toutes les options en aval; une option incompatible n'est jamais affichée. | 📎 (plan v2 Étape 0) |
| DM-2 | **Cycle de vie des drivers GPU : détecter ET installer ET mettre à jour** — NVIDIA (drivers + NVIDIA GPU Operator + Container Toolkit), AMD (AMD GPU Operator/device plugins, Vulkan forcé sur RDNA4), **Intel (solutions comparables : OpenVINO, device plugins Intel, drivers iGPU/NPU)**. La mise à jour des drivers est une opération journalisée au registre avec rollback. | 🆕 (la détection + operators étaient en annexe v2.2; la MISE À JOUR des drivers et le volet Intel complet n'étaient spécifiés nulle part) |
| DM-3 | Multi-nœuds : phase de connexion des machines (IP + utilisateur + mot de passe/clé SSH), bootstrap sécurisé ed25519, Tailscale automatique, sondage distant, matrice backend par nœud, attribution de rôles proposée. | 📎 (addendum v2.2 — intégralement) |
| DM-4 | Deux backends de rendu depuis le même catalogue : Docker Compose (Minimal/Standard) et K3s+Helm+ArgoCD (Complet/Production). | ✅ |
| DM-5 | Les modèles (locaux ET cloud) sont téléchargés, installés, configurés et testés par le wizard; cloud = nom + provenance (menu : direct fournisseur, OpenRouter, NIM, DeepInfra, autre) + clé API sécurisée + test de connexion réel. | 📎 (addendum v2.3) |
| DM-5b | **Phase Stratégie modèle** : choix explicite Cerveau unique / Équipe spécialisée / Hybride avant la sélection des modèles; détermine le nombre de slots ouverts; écrit au canon du projet; changement ultérieur = diff de reconfiguration explicite, jamais silencieux. | 📎 (addendum v2.3 §2) |
| DM-6 | Branchement automatique : aucune brique ne pointe directement vers un modèle — tout passe par le gateway unique; prompt caching configuré par route au gateway; preuve de branchement par test traversant réel. | 📎 (addendum v2.3) |

## 3. Contenu déployé (le « déjà optimisé et éprouvé »)

| ID | Exigence | Statut |
|---|---|---|
| CD-1 | Stacks pré-préparés par domaine (Dev Agentic, RAG souverain, Lab fine-tuning, Production souveraine, Vide) — chaque stack déploie un système COMPLET et fonctionnel, jamais des morceaux à assembler. | 📎 (plan v2 Étape 2) |
| CD-2 | Le stack déployé inclut, branchés et fonctionnels : harnesses, ledgers/registres, guardrails, frameworks, RAG complet (ingestion→embeddings→vectordb→reranker), mémoire — selon les briques choisies parmi le catalogue 1021. | 📎 (dispersé v2/v2.1/v2.3) |
| CD-3 | **Modulable** : architecture plugin — chaque brique est un plugin; contribution communautaire possible avec vérification obligatoire avant merge. | 📎 (plan v2 §architecture) |
| CD-4 | **Import/export de setup** : `forge export` produit un bundle portable (profil complet : briques+versions, stratégie modèle, routes [SANS les clés API — jamais exportées], config nœuds anonymisée, canon du projet) → `forge import` recrée le setup sur une autre machine/parc, en re-demandant uniquement les secrets. Format versionné, hash-vérifié. C'est aussi le mécanisme de partage de « builds éprouvés » entre utilisateurs. | 🆕 |

## 4. Template Dev Agentic — profondeur du « tout branché »

| ID | Exigence | Statut |
|---|---|---|
| DA-1 | L'IDE/CLI choisi (Cline, Cursor, Claude Code, OpenCode, Aider) est livré **entièrement branché et fonctionnel** : config générée et injectée, l'IDE parle au stack local dès l'ouverture. | 📎 (plan v2 Étape 2) |
| DA-2 | Le branchement IDE inclut, préconfigurés : **les serveurs MCP** du stack, **les skills** (registre allowlisté), **BMAD avec prompt manager** (dispatch de contexte scopé), et les hooks de gouvernance (no-stub, no-fake-done, preuve au registre). | 🆕 (MCP/skills étaient esquissés; BMAD+prompt manager préconfigurés dans l'IDE livré n'étaient spécifiés nulle part) |
| DA-3 | **Loop engineering intégré** : la **Ralph Wiggum loop** est disponible comme composant préconfiguré du template — via le plugin officiel Anthropic (Stop hook qui re-injecte le prompt jusqu'à complétion) ET les primitives natives Claude Code (/loop, /goal, /batch), au choix de l'utilisateur, avec garde-fous (budget d'itérations max, condition de complétion vérifiable, journal au registre). Éprouvé et vérifié : plugin officiel anthropics/claude-code. | 🆕 |
| DA-4 | **Token economy** : budgets de tokens par agent/mission configurables au gateway (quota, alerte, coupure), consommation mesurée et journalisée (pattern OpenMeter/premium_cost_gate de l'Atlas), visibles dans un rapport de mission. Le contexte est géré en discipline (packs scopés, compression avant appel cloud, préfixes stables pour le cache). | 🆕 (la compression était au Plan Maître §2; les BUDGETS par agent n'étaient spécifiés nulle part) |

## 5. Qualité et gouvernance (rappel — déjà canon)

| ID | Exigence | Statut |
|---|---|---|
| QG-1 | No-stub / no-fake-done : deux états de sortie (DONE-avec-preuve, BLOCKED-avec-raison), enforcement déterministe. | ✅ (§8bis) |
| QG-2 | Validation à 3 modèles de 3 vendors + signature Fable; revue aveugle scellée; dépouillement par script. | ✅ (§3, §8bis) |
| QG-3 | Vérification post-déploiement RÉELLE : health checks + test bout-en-bout fonctionnel (le RAG répond, le nœud joint, le modèle complète). | ✅ |
| QG-4 | Gates T0-T3; T3 (paiements, secrets prod, suppressions, engagements externes) = humain. | ✅ |

## 6. Optimisation continue du build de base

| ID | Exigence | Statut |
|---|---|---|
| OC-1 | **Cycle de recherche multi-modèles** : à chaque release majeure du catalogue, l'équipe de modèles conduit une recherche approfondie et CIBLÉE (par catégorie de brique : nouveaux entrants, benchmarks récents, changements de licence/maintenance) pour réévaluer les défauts ⭐. Formulation honnête : recherche profonde ciblée multi-sources — pas « sonder le web au grand complet », qui n'est ni faisable ni nécessaire; la couverture vient de la récurrence du cycle, pas d'un scan total mythique. Chaque changement de défaut est journalisé avec preuve comparative. | 🆕 (le principe de réévaluation existait; le cycle de recherche multi-modèles récurrent n'était spécifié nulle part) |

---

## 7. INSTRUCTION DE REPRISE POUR FABLE (à coller tel quel dans la session)

```
MISSION PRIORITAIRE AVANT DE POURSUIVRE P2 :

1. Lis EXIGENCES-PRODUIT-CANON (ce document) intégralement.
2. Diffe-le contre le PRD et les stories actuels du repo, exigence
   par exigence (ID-1 à OC-1).
3. Produis un RAPPORT D'ÉCART au registre : pour chaque exigence,
   statut réel dans le repo (COUVERTE / PARTIELLE / ABSENTE) avec
   référence de fichier/story comme preuve. Attention particulière
   aux exigences marquées 📎 (risque de non-transmission des annexes)
   et 🆕 (jamais spécifiées avant ce canon).
4. Pour chaque ABSENTE ou PARTIELLE : crée les stories BMAD
   correspondantes, insérées dans le phasage existant (sans casser
   les stories en cours), avec critères d'acceptation testables.
5. Le rapport d'écart + les nouvelles stories passent le circuit
   normal : revue aveugle 3 modèles/3 vendors, puis validation.
6. SEULEMENT ENSUITE : reprends P2 (bootstrap multi-nœuds EX-1..5,
   traductions restantes, enrichissements Atlas).

Ce canon est désormais versionné au repo (CANON/exigences-produit.md)
et toute modification future passe par le circuit de gouvernance.
```
-e 
---
---

# PARTIE 2 — PLAN MAÎTRE D'EXÉCUTION BMAD v1.0 REVALIDÉE
*(Document source : FORGEAI-TOOLKIT-PLAN-MAITRE-EXECUTION-BMAD-20260713 — reproduit intégralement)*

# FORGEAI TOOLKIT — PLAN MAÎTRE D'EXÉCUTION BMAD
**Version 1.0 — REVALIDÉE le 13 juillet 2026 (passe de cohérence complète + règle no-stub §8bis + validation à 3 modèles)**
**Consolide et supersède : plan v2 + addenda v2.1 (catalogue/bilinguisme), v2.2 (multi-nœuds/Tailscale), v2.3 (stratégie/modèles/branchement). Ces documents restent les annexes techniques de référence.**

---

## 0. Mission en une phrase

Construire le ForgeAI Toolkit — le déployeur de référence d'infrastructures IA agentiques (wizard hardware-aware, catalogue 1021 entrées bilingue, multi-nœuds, gouvernance intégrée) — via la méthodologie BMAD, exécuté de façon autonome par une équipe de modèles premium orchestrée dans Claude Code, avec Fable comme juge et validateur d'étapes, jusqu'à complétion prouvée et testée de chaque fonctionnalité.

---

## 1. L'ÉQUIPE — 10 membres, rôles nominatifs

**Phase A = finition du plan (pré-exécution). Phase B = exécution.**

| Membre | Rôle Phase A (finir le plan) | Rôle Phase B (exécution) | Justification |
|---|---|---|---|
| **Fable (= toujours l'instance Claude Fable 5 opérant dans Claude Code)** | Validation finale du plan après consensus; arbitre des objections non résolues | **ORCHESTRATEUR DE MISSION (session lead Claude Code) + juge/validateur de chaque étape + codeur des aspects les plus difficiles** (détection hardware, rendu double backend, bootstrap sécurisé multi-nœuds) | Demande explicite; Claude Code est le harness d'exécution et Fable en est le lead unique |
| **GLM-5.2** | Architecture technique détaillée (modules, schémas de données, API des hooks) | Architecte permanent — revue d'architecture de chaque story avant codage | Rôle ARCHITECTE déjà locké à l'Atlas |
| **DeepSeek V4 Pro** | Registre des risques + mitigations; revue critique du PRD | **Juge/critique indépendant** — reviewer aveugle #1 sur chaque PR | Rôle JUGE/CRITIQUE déjà locké à l'Atlas |
| **Kimi K2.7 Code** | Découpage du plan en stories BMAD exécutables (sa force long-horizon) | Codeur des missions longues multi-fichiers (scaffolder complet, moteur de catalogue) | Rôle CODE LONG déjà locké à l'Atlas |
| **Composer 2.5** | Spécification du TUI (écrans du wizard, flux d'interaction) | Codeur des itérations rapides TUI/UX; sessions interactives | Modèle natif IDE, vitesse d'itération |
| **Grok 4.5** | Spécification des tests (matrice de couverture par fonctionnalité) | Codeur parallèle sur stories indépendantes (git worktrees) | Token-efficient; ⚠️ même vendor que Composer depuis l'acquisition Cursor/xAI — voir §3.4 |
| **Gemini 3.1 Pro** | Revue UX/design du wizard + diagrammes d'architecture | Reviewer aveugle #2 (multimodal : vérifie captures TUI vs specs) | Force multimodale/raisonnement (OPTION PREMIUM Atlas) |
| **Qwen 3.7 Max** | **Enrichissement du catalogue : 742 descriptions EN + revue des 231 entrées Atlas** (force multilingue) | Mainteneur du catalogue bilingue; traduction continue des nouvelles briques | Meilleur profil multilingue de l'équipe |
| **LongCat 2.0** | Second lot de descriptions (partage avec Qwen, échantillons croisés 10%) + revue critique du protocole multi-nœuds | **Reviewer aveugle #3 (pool de rotation) + second-opinion sécurité/secrets** | Validé par les tests directs de Nathan; vendor distinct (Meituan) — précieux pour la décorrélation du pool de revue |
| **MiMo 2.5 Pro** | **Consolidation : fusionne les 5 documents de plan + PDF 93 pages en un MASTER-PLAN unique + manifestes YAML machine-lisibles** (contexte 1M) | Synthétiseur de preuves — compile les sorties de gates en rapports d'étape pour Fable | Seul contexte 1M de l'équipe |

**Notes d'honnêteté sur l'équipe :**
- Gemini 3.1 Pro et Qwen 3.7 Max sont **API-only (closed-weight)** — parfaits comme routes cloud, aucune option locale.
- Composer 2.5 et Grok 4.5 partagent désormais le même fournisseur (xAI) : ils ne sont **jamais appariés comme reviewers indépendants l'un de l'autre** (corrélation d'erreur probable). Ils reçoivent des rôles complémentaires (TUI vs stories parallèles), pas redondants.
- LongCat 2.0 : promu sur la base des tests directs de Nathan (évidence de première main, ce qui compte). Pour la traçabilité du registre, une passe de benchmark formalisée en Phase A (subset SWE-bench ou équivalent interne, résultat journalisé) reste souhaitable — comme confirmation documentée, pas comme condition. Son vendor distinct (Meituan) élargit réellement la décorrélation du pool de reviewers aveugles : c'est un gain structurel, pas juste un modèle de plus.

---

## 2. PROMPT MANAGING & COMPRESSION DE CONTEXTE — la constitution d'exécution

Tout est pensé pour faciliter la tâche des modèles, y compris le plan lui-même :

1. **Le plan devient des données, pas de la prose.** MiMo produit en Phase A : `MASTER-PLAN.md` (lisible humain) + `manifests/` en YAML (`bricks.yaml`, `phases.yaml`, `roles.yaml`, `gates.yaml`, `routes.yaml`). Les modèles lisent les manifestes, jamais 5 documents markdown.
2. **Context packs par story.** Chaque story BMAD reçoit un pack généré : slice de canon pertinent (jamais AGENTS.md complet) + la story + les interfaces des modules touchés + rien d'autre. C'est le Context Pack Compiler de l'Atlas, appliqué au chantier lui-même.
3. **Préfixes stables pour le prompt caching.** Les packs sont structurés préfixe-stable (canon d'abord, variable ensuite) pour maximiser le cache des fournisseurs cloud — coût réduit sur les 9 routes premium.
4. **Isolation par subagent.** Dans Claude Code, chaque tâche déléguée tourne dans un subagent à contexte propre; le lead ne reçoit que le résumé. La recherche va en subagent; les éditions sous approbation restent dans la session parent (limite structurelle documentée : un subagent ne peut pas demander d'approbation en cours de tâche).
5. **Compression avant appel cloud.** Sorties d'outils volumineuses compressées avant injection (politique de conservation de preuve : l'original va au registre, le compressé au contexte).

---

## 3. INDÉPENDANCE CRITIQUE — le protocole anti-influence

Exigence explicite : les modèles ne doivent pas s'influencer. Voici le mécanisme structurel, pas une consigne de politesse :

### 3.1 Revue aveugle scellée
- Chaque artefact à valider (plan, PR, étape) est distribué **simultanément** aux reviewers assignés.
- Chaque reviewer produit son verdict dans un **fichier scellé** (`reviews/<étape>/<modèle>.verdict.json`) committé sur une branche isolée — **sans accès aux verdicts des autres**. Le format : `{verdict: APPROVE|REJECT, objections: [{sévérité: critique|majeure|mineure, description, preuve}], date, heure}`.
- Les verdicts ne sont **révélés qu'une fois tous déposés** (script de tally qui vérifie les timestamps de commit — un verdict déposé après révélation est invalide).

### 3.2 Dépouillement déterministe
- Un script compte : jamais un LLM. Seuil de consensus : **7/9 APPROVE ET zéro objection critique non résolue**.
- Pas de consensus → **round 2 façon Delphi** : les objections (anonymisées, sans attribution de modèle) sont redistribuées, chaque reviewer re-vote en aveugle. Maximum 2 rounds; ensuite Fable arbitre sur pièces, et l'arbitrage est journalisé avec justification.

### 3.3 Anti-ancrage
- Aucune discussion inter-modèles avant vote. Jamais de "voici ce que GLM en pense, qu'en dis-tu?" — c'est le vecteur d'influence numéro 1.
- Les prompts de revue ne contiennent jamais le verdict attendu, le nombre d'approbations déjà reçues, ni l'identité des autres reviewers.

### 3.4 Décorrélation par vendor
- Les paires de reviewers aveugles sur une même story viennent de **vendors différents** (ex. DeepSeek + Gemini; jamais Composer + Grok ensemble).

---

## 4. GATE DE CONSENSUS PRÉ-EXÉCUTION

Séquence obligatoire avant la première ligne de code :

```
1. Phase A terminée (tous les livrables de la table §1 déposés au repo)
2. MiMo consolide → MASTER-PLAN.md + manifestes YAML → commit "plan-freeze"
3. Les 9 modèles reçoivent le plan gelé → revue aveugle scellée (§3.1)
4. Tally déterministe : ≥7/9 + zéro critique non résolue
   → sinon round Delphi (max 2), corrections, re-freeze, re-vote
5. Fable : validation finale sur pièces (verdicts + objections + réponses)
6. Nathan : approbation T3 (lancement d'exécution autonome = engagement 
   de ressources = tier humain, conformément au modèle de gates)
7. Tag Git "plan-v1.0" signé → l'exécution autonome démarre
```

---

## 5. RÔLE DE FABLE — ORCHESTRATEUR, juge, validateur d'étapes, codeur du difficile

**Définition contractuelle : « Fable » désigne toujours et uniquement l'instance Claude Fable 5 opérant dans Claude Code (session lead). Toute référence à Fable dans les manifestes, les hooks et les registres pointe vers cette instance — jamais vers une autre interface ou un autre déploiement du modèle.**

**Fable est l'orchestrateur unique de la mission.** Il tient la session lead Claude Code, décompose les stories, spawne les subagents (chaque membre de l'équipe = un subagent avec son modèle routé via le gateway), séquence les phases, et arrête le pipeline quand une étape n'est pas validée. Il n'y a AUCUN orchestrateur parallèle — un seul control plane par fonction, conformément à la règle Atlas.

**Garde-fou CIV — la concentration de rôles, nommée et contenue :** Fable orchestre, code ET valide — c'est une concentration réelle qui contredirait le pattern CIV (coordinateur → implémenteur → validateur indépendant) si elle n'était pas contenue par trois mécanismes structurels : (1) Fable ne se relit JAMAIS lui-même — son code passe en revue aveugle par des vendors tiers (DeepSeek, Gemini, LongCat); (2) les gates déterministes (hooks, CI) restent l'autorité bloquante que Fable ne peut pas contourner; (3) le dépouillement des consensus est un script, pas Fable. Le coordinateur n'est jamais son propre validateur indépendant.

**Le contrat exact, avec la nuance de gouvernance qui protège tout le reste :**

- **Fable ne remplace jamais les gates déterministes.** Les hooks/CI (lint, tests, couverture, sécurité, hash) sont l'autorité bloquante — "les guardrails vont dans les hooks; tout le reste est une suggestion polie" (pratique documentée Claude Code 2026). Fable **signe par-dessus des gates verts** : sa validation est une signature requise EN PLUS, jamais un substitut. Aucun LLM — Fable inclus — n'écrit un score de qualité; les scores restent des fonctions pures de gates binaires. C'est la leçon cycle140, appliquée y compris au juge.
- **Validation d'étape** : à la fin de chaque story/phase, Fable reçoit le rapport de preuves compilé par MiMo (sorties de gates, verdicts aveugles, artefacts) et valide la progression vers l'étape suivante. Étape non validée = pipeline arrêté, pas contourné.
- **Codeur du plus difficile** : détection hardware multi-vendor, moteur de rendu Compose/K3s double backend, bootstrap SSH/ed25519/Tailscale, moteur de registres append-only hash-chaînés. Le code de Fable passe par les MÊMES gates et la MÊME revue aveugle que celui des autres — aucune exemption du juge.
- **T3 reste Nathan** : paiements, secrets de production, suppressions définitives, engagements externes. Le consensus recommande; l'humain lève. Non négociable, conformément au modèle de gates établi.

---

## 6. GITHUB — intégration 100%, nouveau repo

- **Nouveau repo dédié** (nom : décision ouverte #1 — vérifier GitHub org + PyPI + domaine avant P0).
- **Structure canonique** dès le premier commit : `AGENTS.md`, `CANON/`, `manifests/`, `Registres/` (JSONL hash-chaînés, in-repo), `Docs/` (Diátaxis), `src/`, `reviews/`, `Sandbox/`.
- **Tout passe par PR — zéro commit direct sur main.** Branch protection : gates CI requis + **3 revues aveugles requises (3 modèles, 3 vendors différents)** + signature Fable (CODEOWNERS) + commits signés.
- **GitHub Actions = les gates déterministes** : lint, tests unitaires, tests e2e, couverture minimale, scan sécurité (Trivy), détection de secrets (Gitleaks), vérification de hash du catalogue, `no-fake-done-check` (un PR marqué DONE sans preuve au registre échoue), et **no-stub-scan** (détection déterministe de stubs et de faux — voir §8bis, gate bloquant).
- **Issues = stories BMAD** (une issue par story, labels par phase/rôle/modèle assigné); **Projects** = tableau de mission; **Releases** = fins de phase taguées et signées.
- **Git worktrees** pour les codeurs parallèles (Grok/Kimi sur stories indépendantes) — pattern documenté pour éviter les collisions de contexte.

---

## 7. ARCHITECTURE D'EXÉCUTION DANS CLAUDE CODE

Fondée sur les capacités vérifiées (recherche 13 juillet 2026) :

- **Agent Teams / subagents** : Fable, orchestrateur unique (session lead), délègue aux subagents spécialisés — chaque membre de l'équipe = une définition d'agent dans `.claude/agents/` avec son modèle assigné via la route gateway (« model-per-agent : dépenser le budget frontier seulement là où il rapporte »), ses outils scopés, son prompt de rôle.
- **Hooks = enforcement déterministe** : pre-commit (Gitleaks, lint), SubagentStop (aucun subagent ne termine sans avoir déposé sa preuve au registre), post-merge (mise à jour canon obligatoire — un merge sans update de doc/canon est rejeté par hook).
- **Skills = méthodologies** : BMAD et Superpowers (TDD strict RED-GREEN-REFACTOR) chargés comme skills; jamais les deux méthodologies actives sur la même story (règle établie).
- **Dynamic Workflows** pour le fan-out massif : les 742 traductions EN = un fan-out de subagents parallèles avec **Performance Outcomes** (grader séparé qui renvoie chaque subagent réviser jusqu'à conformité à la rubrique) + échantillon de 10% vérifié par Qwen 3.7 Max croisé LongCat, puis gate humain léger avant merge du lot.
- **Limites connues, designées autour** : pas de subagents imbriqués (le lead chaîne); les éditions nécessitant approbation restent dans la session parent; `bypassPermissions` interdit hors sandbox jetable.

---

## 8. PIPELINE AUTONOME PAR STORY — de l'issue au merge prouvé

```
Issue (story BMAD)
  → Context pack généré (canon slice + story + interfaces)
  → Assignation codeur (manifeste roles.yaml : Kimi/Grok/Composer/Fable selon type)
  → TDD : tests d'abord (Superpowers RED) → code (GREEN) → refactor
  → Hooks locaux (lint, secrets, preuve au registre)
  → PR → GitHub Actions (gates déterministes complets)
  → SI gates verts : revue aveugle scellée ×3 (trois modèles, trois vendors différents)
  → Tally déterministe → SI approve : signature Fable sur pièces
  → Merge → registre horodaté → canon/docs mis à jour (hook obligatoire)
  → Fin de phase : test bout-en-bout RÉEL de chaque fonctionnalité livrée
    (le RAG répond, le nœud joint, le modèle complète — jamais "les
    containers tournent"), rapport MiMo, validation d'étape Fable
```

**Preuve par fonctionnalité — le contrat de complétion :** l'exécution n'est terminée que lorsque CHAQUE fonctionnalité du manifeste `phases.yaml` a son test e2e vert ET son entrée de preuve au registre. Une fonctionnalité sans test n'existe pas. Un test sans preuve journalisée n'existe pas. C'est le no-fake-done appliqué à la mission entière.

**Rigueur maintenue sur la durée :** les vérificateurs (reviewers aveugles), l'orchestrateur (Fable lead + hooks), et les testeurs (suite e2e + Promptfoo/DeepEval sur les composants LLM du Toolkit lui-même) tournent à CHAQUE story, du premier au dernier commit — la discipline ne se relâche pas en fin de mission, structurellement : les hooks ne fatiguent pas.

---

## 8bis. INTERDICTION ABSOLUE DES STUBS ET DU FAUX — règle de complétion

**Principe : une story démarrée n'a que deux états de sortie possibles — DONE-avec-preuve ou BLOCKED-avec-raison. Il n'existe aucun troisième état. Aucune exception.**

### Ce qui est interdit dans tout code mergé (liste exécutoire, pas indicative)
- Stubs et corps vides : `pass`, `NotImplementedError`, `...` (Ellipsis), fonctions/handlers vides, `return None` masquant une implémentation absente
- Marqueurs de travail inachevé : `TODO`, `FIXME`, `HACK`, `XXX`, `PLACEHOLDER` dans le diff mergé
- Faux vert : tests sans assertion réelle, `assert True`, assertions commentées, `pytest.skip`/`xfail` sans justification journalisée au registre
- Fausses données : données codées en dur simulant un résultat réel, fixtures présentées comme sortie de production, valeurs de retour inventées
- DONE partiel : une fonctionnalité livrée à moitié et marquée complète — c'est la définition même du fake-done

### Ce qui est permis, strictement borné
- Mocks et fixtures **uniquement dans le code de test** (`tests/`), **uniquement pour simuler des services externes** (API tierces, hardware absent du CI), jamais dans `src/`, et déclarés dans le manifeste de la story.

### Enforcement — déterministe, pas déclaratif
- **no-stub-scan** (hook pre-commit + gate CI bloquant) : greps + analyse AST détectant chaque item de la liste interdite dans le diff. Un seul hit = PR bloquée, sans discussion, sans exception, y compris pour le code de Fable.
- **SubagentStop hook** : aucun subagent ne peut clore sa tâche sans avoir déposé sa preuve au registre; un subagent qui ne peut pas terminer dépose un statut BLOCKED avec raison précise — jamais un stub pour « passer ».
- **Escalade BLOCKED** : story bloquée → pipeline arrêté sur cette branche → Fable analyse et soit débloque (nouvelle approche, re-scope documenté au registre), soit escalade à Nathan. Le blocage honnête est un résultat acceptable; le faux avancement ne l'est jamais.

### Validation à trois modèles — le verrou final
**Chaque story mergée est validée par un minimum de TROIS modèles différents, issus de TROIS vendors différents** : trois reviewers aveugles scellés (§3), plus la signature d'étape de Fable par-dessus. Pour le code écrit par Fable lui-même : les trois reviewers sont obligatoirement non-Anthropic (DeepSeek, Gemini, LongCat — rotation possible avec Kimi, Qwen, MiMo). Le pool de 9 vendors distincts de l'équipe rend cette rotation triviale à satisfaire.

---

## 9. SÉQUENCE DE LANCEMENT (checklist ordonnée)

1. ☐ Nathan tranche : nom du repo (+ vérif disponibilité), licence (MIT/Apache 2.0), moteur défaut Minimal (Ollama vs vLLM)
2. ☐ Création du repo + structure canonique + branch protection + hooks + Actions
3. ☐ Routes gateway configurées pour les 9 modèles (clés API, test de connexion réel chacune)
4. ☐ Définitions d'agents `.claude/agents/` (une par membre, modèle + outils scopés)
5. ☐ Phase A lancée : chaque membre exécute sa tâche de finition (table §1)
6. ☐ MiMo consolide → plan-freeze
7. ☐ Consensus aveugle 9 modèles → tally → (Delphi si besoin) → Fable → Nathan (T3)
8. ☐ Tag plan-v1.0 signé → exécution autonome P1 (Détection + Minimal : machine nue → RAG fonctionnel prouvé)

---

## 10. Décisions ouvertes restantes (héritées, inchangées)

1. Nom du repo/produit — bloque l'étape 1 de la checklist
2. Licence MIT vs Apache 2.0
3. Moteur par défaut du profil Minimal (Ollama = simplicité vs vLLM = performance de référence)
4. Séquencement GRS : ce plan lance la Phase A (finition, coût faible, parallélisable avec GRS activation); l'exécution P1+ engage des ressources réelles — la décision de gel/priorité posée en début de session reste à réaffirmer ou lever explicitement à l'étape 7 (c'est précisément pour ça qu'elle est un gate T3 humain).
-e 
---
---

# PARTIE 3 — PLAN V2 : LE DÉPLOYEUR
*(Document source : FORGEAI-TOOLKIT-PLAN-V2-DEPLOYEUR-20260713 — reproduit intégralement)*

# ForgeAI Toolkit v2 — Déployeur d'infrastructure IA agentique
**Version : 13 juillet 2026 — Réanalyse complète, focus déploiement**
**Repo : dépôt GitHub dédié (nom à vérifier : disponibilité GitHub + PyPI + domaine)**
**Statut : DRAFT — remplace le plan v1 (archivé)**

---

## 1. Repositionnement : de "suite d'outils de gouvernance" à "déployeur de référence"

**Ce que c'est maintenant :** un logiciel qui déploie de A à Z une infrastructure IA agentique complète, fonctionnelle et gouvernée — depuis une machine nue jusqu'à un stack opérationnel vérifié. L'utilisateur répond à une série d'**options présentées par étapes** (jamais de questions ouvertes, jamais 50 questions d'un coup), et l'outil installe, configure, branche et PROUVE que tout fonctionne.

**L'ambition explicite : devenir LA référence du déploiement d'infra agentique** — ce que kubeadm est à Kubernetes, ce que Coolify est au self-hosting web.

## 2. Analyse concurrentielle (recherche 13 juillet 2026)

| Outil | Ce qu'il fait | Pourquoi il ne suffit pas |
|---|---|---|
| **av/harbor** (concurrent le plus proche) | CLI + app, stack LLM pré-câblé en une commande, ~100+ services Docker Compose | Son propre README le dit : « not designed as a deployment solution, but rather as a helper for the local LLM development environment ». Pas de production, pas de K8s/GitOps, pas de gouvernance, pas de vérification post-déploiement, pas de wizard hardware-aware |
| **hwdsl2 self-hosted-ai-stack / local-ai-packaged** | Starters Docker Compose | Statiques : un fichier à copier, aucune détection matérielle, aucun choix guidé, aucun registre |
| **Ollama** | Runtime one-command | Une seule brique, pas une infrastructure |
| **KubeAI / llm-d / GPUStack** | Serving K8s | Couche serving seulement — supposent que le cluster, le RAG, la mémoire, la gouvernance existent déjà |
| **NVIDIA AI Workbench** | Environnements dev reproductibles | Dev/prototypage, vendor-locked NVIDIA, pas d'infra complète |

**Le trou dans le marché, confirmé :** personne ne combine (1) wizard guidé hardware-aware, (2) déploiement production-grade (containers → K3s → GitOps), (3) gouvernance intégrée (registres, canon, vérification), (4) stacks par domaine avec branchement IDE/CLI. Harbor s'arrête au dev local. C'est exactement l'espace à prendre.

---

## 3. L'expérience utilisateur : le wizard par étapes

**Principe : chaque étape = un écran, des options claires avec description courte, une recommandation pré-sélectionnée (le meilleur choix par défaut), et la possibilité de tout accepter d'un coup ("Express") ou d'affiner ("Personnalisé").**

### Étape 0 — Détection automatique (zéro question)
L'outil scanne la machine avant de poser quoi que ce soit :
- OS et version, CPU (AVX-512?), RAM, disque disponible
- GPU : vendor (NVIDIA/AMD/Intel), modèle, VRAM, drivers présents, CUDA/ROCm/Vulkan disponibles
- Déjà installé : Docker? Podman? K3s? Python? Node?
- Réseau : ports libres, accès internet

**→ Tout ce qui suit est filtré par cette détection. C'est le différenciateur numéro 1 :**
- GPU NVIDIA Blackwell détecté → TensorRT-LLM et vLLM proposés, NVIDIA AI Workbench offert
- GPU AMD RDNA4 détecté → llama.cpp/Vulkan proposé, TensorRT-LLM et ROCm **jamais affichés** (pas une erreur à l'exécution — une option qui n'apparaît simplement pas)
- 16GB RAM → les stacks lourds affichent un avertissement de dimensionnement AVANT le choix, pas un crash après

### Étape 1 — Profil de déploiement
| Option | Description affichée |
|---|---|
| **Minimal** ⭐ recommandé pour débuter | Stack RAG complet et fonctionnel de A à Z : moteur d'inférence + modèle + embeddings + base vectorielle + ingestion + interface chat. Léger, mais COMPLET — tout marche dès la fin du déploiement. |
| **Standard** | Minimal + orchestration d'agents (LangGraph) + mémoire + observabilité de base |
| **Complet** | Standard + guardrails + gateway multi-modèles + registres complets + GitOps |
| **Personnalisé** | Choix brique par brique, guidé par catégorie |

**Règle clé : "Minimal" ne veut PAS dire incomplet.** Minimal déploie un RAG bout-en-bout qui répond à une question sur un document ingéré dès la première minute. C'est l'anti-pattern des starters qui te laissent avec 12 containers et rien qui se parle.

### Étape 2 — Domaine (templates/stacks pré-faits)
| Template | Ce qui est déployé et branché |
|---|---|
| **Dev Agentic** | LangGraph + moteur d'inférence + serveurs MCP essentiels + **branchement IDE/CLI au choix** (Cline, Cursor config, Claude Code, OpenCode, Aider — config générée et injectée automatiquement, l'IDE parle au stack local dès l'ouverture) |
| **Base de connaissances RAG** | Ingestion (Docling + Crawl4AI) + chunking AST pour code + Qdrant + embeddings + reranker + Open WebUI |
| **Lab fine-tuning** | Unsloth + W&B + pipeline datasets + export vers le serving local |
| **Production souveraine** | Le stack complet sur K3s + ArgoCD + observabilité + guardrails + secrets |
| **Vide (à la carte)** | Structure canonique seulement, briques au choix |

### Étape 3 — Runtime & fondations (filtré par détection)
- **Conteneurisation :** Docker ⭐ / Podman — installés automatiquement s'ils manquent
- **Orchestration :** aucune (Compose seul) ⭐ pour Minimal / K3s pour Standard+ — installé et configuré automatiquement
- **Livraison :** manuelle ⭐ / GitOps (ArgoCD) — pour Complet/Production
- **Moteur d'inférence :** liste filtrée par GPU détecté, avec pour chaque option une ligne de contexte réel (ex. « vLLM : débit maximal en concurrence; Ollama : simplicité, plafonne à 4 requêtes parallèles »)

### Étape 4 — Options par phase (au fil du déploiement, pas tout d'avance)
Le wizard revient vers l'utilisateur SEULEMENT quand une phase ouvre un vrai choix :
- Phase serving terminée → « Quel modèle initial? » (liste filtrée par VRAM détectée)
- Phase RAG → « Sources à ingérer maintenant? » (optionnel, skippable)
- Phase IDE (si Dev Agentic) → « Quel(s) cockpit(s) brancher? »

### Étape 5 — Aperçu, déploiement, PREUVE
1. **Aperçu complet** avant exécution : liste exacte de ce qui sera installé, où, ports utilisés, espace disque estimé, durée estimée — modifiable, annulable
2. **Déploiement** avec progression par brique, logs accessibles, idempotent (relançable sans casser), rollback par phase
3. **Vérification automatique** (le no-fake-done appliqué au déploiement) :
   - Health check de chaque brique
   - **Test de bout en bout réel** : pour un stack RAG, l'outil ingère un document témoin et pose une question — si la réponse cite le document, c'est GREEN. Pas « les containers tournent » — « le système FONCTIONNE ».
4. **Rapport final** : ce qui est installé (vrais noms, versions), les URLs d'accès, le tout écrit au registre horodaté

---

## 4. Ce qui est conservé du v1 (la gouvernance devient le moteur interne)

Les 5 piliers v1 ne disparaissent pas — ils deviennent l'infrastructure interne du déployeur :
- **Scaffolder** → la structure canonique est générée par le déploiement (taxonomie, vrais noms, AGENTS.md, CANON/)
- **Registres** → chaque install/uninstall/reinstall/upgrade journalisé automatiquement, horodaté, append-only; `forge history <brique>` fonctionne dès le premier déploiement
- **Canon engine** → le canon-etat-courant.yml reflète TOUJOURS l'état réel déployé (généré par l'outil, jamais à la main)
- **Catalogue vérifié** → seules des briques vérifiées (API GitHub : existence, licence, maintenance) entrent au catalogue; « les meilleures briques installées automatiquement » = les défauts ⭐ de chaque catégorie sont les choix vérifiés supérieurs, réévalués par benchmark à chaque release
- **Gates T0-T3** → appliqués aux opérations du déployeur lui-même (un upgrade destructif = T2; toucher aux secrets = T3)

## 5. Architecture technique

- **Noyau Python** (écosystème LangGraph/ML) + **TUI riche** (wizard terminal type Textual) — le CLI EST le wizard; UI web locale en phase ultérieure
- **Moteur de déploiement à deux backends :** Docker Compose (Minimal/Standard) et K3s+Helm+ArgoCD (Complet/Production) — même catalogue de briques, deux cibles de rendu
- **Détection matérielle** : module dédié (lspci/nvidia-smi/rocm-smi/vulkaninfo + parsing), matrice de compatibilité brique×hardware maintenue dans le catalogue
- **Catalogue** : YAML par brique — nom officiel exact, repo, version épinglée, licence, description une-phrase, compatibilités hardware, dépendances, health check, test bout-en-bout
- **Chaque brique = un plugin** : la communauté peut soumettre des briques, mais la vérification (API GitHub + licence + health check fonctionnel) est obligatoire avant merge — c'est la barrière qualité qui fait la référence

## 6. Phasage v2

| Phase | Livrable | Preuve de done |
|---|---|---|
| **P0 — Spec BMAD** | PRD + architecture + stories P1-P2 | Validé triple consensus + Nathan |
| **P1 — Détection + Minimal** | Wizard étapes 0-1, profil Minimal déploie un RAG A-Z complet sur Docker | Machine nue → RAG qui répond à une question sur un doc ingéré, en une session, registre rempli |
| **P2 — Templates + moteurs** | Étapes 2-3 : Dev Agentic + branchement IDE, choix vLLM/SGLang/llama.cpp/Ollama filtrés hardware | Dev Agentic déployé, Cline branché et fonctionnel sur le stack local |
| **P3 — K3s + GitOps** | Backend K3s, ArgoCD, profil Production | Stack complet sur K3s, déployé via GitOps, vérifié |
| **P4 — TensorRT-LLM + NVIDIA AI Workbench + Podman** | Options avancées hardware-spécifiques | Chaque option vérifiée sur hardware réel correspondant |
| **P5 — Catalogue communautaire + UI web** | Pipeline de contribution vérifiée, interface web locale | Une brique externe soumise, vérifiée, mergée; un utilisateur externe déploie sans aide |

**P1 est le pari produit : si "machine nue → RAG fonctionnel prouvé en une session guidée" est réussi, la référence est en marche. Tout le reste s'empile dessus.**

---

## 7. PROMPT MAÎTRE DE DÉVELOPPEMENT (à donner à BMAD pour P0)

```
MISSION : Produire le PRD, l'architecture et les stories P1-P2 du ForgeAI
Toolkit — un déployeur d'infrastructure IA agentique destiné à devenir la
référence du domaine.

POSITIONNEMENT : Aucun outil existant ne combine wizard guidé hardware-aware,
déploiement production-grade et gouvernance intégrée. Harbor (concurrent le
plus proche) se limite explicitement au dev local sans gouvernance ni
production. Le ForgeAI Toolkit prend l'espace au-dessus : de la machine nue
au stack agentique complet, vérifié et gouverné.

EXPÉRIENCE UTILISATEUR (contrat ferme) :
- Wizard par ÉTAPES : un écran par décision, OPTIONS présentées avec
  description courte (jamais de questions ouvertes), recommandation ⭐
  pré-sélectionnée sur chaque écran, mode Express (tout accepter) et mode
  Personnalisé (affiner).
- Étape 0 automatique : détection OS/CPU/RAM/disque/GPU(vendor, VRAM,
  drivers, CUDA/ROCm/Vulkan)/outils déjà présents. TOUTES les options
  suivantes sont filtrées par cette détection : une brique incompatible
  avec le hardware détecté n'est jamais affichée (ex. TensorRT-LLM
  absent sur AMD; llama.cpp/Vulkan proposé sur RDNA4).
- Profils : Minimal / Standard / Complet / Personnalisé. RÈGLE ABSOLUE :
  Minimal déploie un RAG COMPLET et FONCTIONNEL de A à Z (inférence +
  modèle + embeddings + base vectorielle + ingestion + interface chat) —
  minimal signifie léger, jamais incomplet.
- Templates par domaine : Dev Agentic (avec branchement IDE/CLI
  automatique — Cline, Cursor, Claude Code, OpenCode, Aider : config
  générée et injectée, l'IDE parle au stack dès l'ouverture), Base de
  connaissances RAG, Lab fine-tuning, Production souveraine, Vide.
- Questions au fil des phases : le wizard ne redemande quelque chose que
  lorsqu'une phase ouvre un vrai choix (modèle initial après serving,
  sources après RAG, cockpits après IDE).
- Avant exécution : aperçu complet modifiable (briques, versions, ports,
  disque, durée). Pendant : progression par brique, idempotence, rollback
  par phase. Après : VÉRIFICATION RÉELLE (health check par brique + test
  bout-en-bout fonctionnel — ex. le RAG répond correctement à une question
  sur un document témoin ingéré) et rapport final au registre horodaté.

CAPACITÉS D'INSTALLATION (périmètre) :
- Prérequis : Docker, Podman, drivers/toolkits GPU (NVIDIA Container
  Toolkit), K3s, ArgoCD, Helm — installés automatiquement si absents et
  requis par le profil choisi.
- Moteurs d'inférence : vLLM, SGLang, llama.cpp, Ollama, TensorRT-LLM
  (NVIDIA seulement), avec matrice de compatibilité hardware au catalogue.
- Option NVIDIA AI Workbench pour les environnements dev sur hardware
  NVIDIA.
- Briques du catalogue : chacune définie en YAML (nom OFFICIEL exact,
  repo, version épinglée, licence, description une-phrase, compatibilités,
  dépendances, health check, test bout-en-bout). Les défauts ⭐ de chaque
  catégorie sont les meilleures briques vérifiées, réévaluées par
  benchmark à chaque release.

GOUVERNANCE INTERNE (héritée du plan v1, non négociable) :
- Structure canonique générée (taxonomie stricte, vrais noms officiels,
  AGENTS.md, CANON/, Registres/, Docs/, Sandbox/).
- Registres append-only horodatés pour chaque install/uninstall/
  reinstall/upgrade; commande history par brique; preuve obligatoire
  pour tout DONE.
- canon-etat-courant.yml généré par l'outil, reflète toujours l'état
  réellement déployé.
- Gates T0-T3 appliqués aux opérations du déployeur (upgrade destructif
  = T2 : sandbox + consensus 3 modèles premium; secrets/suppressions
  définitives = T3 : + approbation humaine).
- Aucun LLM n'écrit un score : les verdicts sont des fonctions pures de
  gates binaires.

ARCHITECTURE IMPOSÉE :
- Noyau Python, wizard TUI (type Textual), UI web locale en P5.
- Deux backends de rendu depuis le même catalogue : Docker Compose
  (Minimal/Standard) et K3s+Helm+ArgoCD (Complet/Production).
- Système de plugins pour les briques; contribution communautaire
  possible mais vérification obligatoire (API GitHub + licence + health
  check) avant merge.
- 100% local-first, aucune dépendance cloud obligatoire.
- Repo GitHub dédié, licence open-source (MIT ou Apache 2.0 au PRD).

PHASAGE IMPOSÉ : P1 Détection+Minimal (machine nue → RAG fonctionnel
prouvé) → P2 Templates+moteurs+IDE → P3 K3s+GitOps → P4 options
hardware avancées → P5 catalogue communautaire+UI web. Chaque phase a
sa preuve au registre avant la suivante.

LIVRABLES : 1) PRD (personas : dev solo, homelab, PME, équipe infra;
user journeys par profil), 2) architecture détaillée (module détection,
schéma YAML du catalogue, moteur de rendu double backend, format des
registres), 3) stories P1-P2 seulement, 4) risques et mitigations.

CONDUITE : relire ce prompt avant chaque livrable; aucune fonctionnalité
hors périmètre sans la signaler comme extension; chaque choix technique
justifié en une phrase; question plutôt que supposition en cas
d'ambiguïté.
```

---

## 8. Points ouverts

1. **Nom + repo GitHub** : vérifier disponibilité (GitHub org, PyPI, domaine) avant P0.
2. **T3 humain vs consensus** : reporté du v1, toujours à trancher.
3. **Licence** : MIT vs Apache 2.0.
4. **Briques défaut ⭐ du profil Minimal** : proposition initiale — Ollama (simplicité premier contact) OU vLLM (si l'ambition "référence" exige la performance d'emblée)? À trancher : le défaut du Minimal définit la première impression du produit.
5. **Séquencement GRS** : inchangé — P0 (spec BMAD) peut tourner en parallèle de GRS activation; P1+ attend.
-e 
---
---

# PARTIE 4 — ADDENDUM v2.1 : CATALOGUE COMPLET, BILINGUISME, DESIGN
*(Document source : FORGEAI-TOOLKIT-ADDENDUM-CATALOGUE-20260713 — reproduit intégralement)*

# ForgeAI Toolkit — Addendum v2.1 : Catalogue complet, bilinguisme, design
**13 juillet 2026 — complète le plan v2 (déployeur)**

---

## 1. Le catalogue complet est maintenant GÉNÉRÉ (livrable concret, pas une promesse)

Le répertoire docx (841 entrées vérifiées) a été parsé programmatiquement en catalogue machine-lisible :

**`forge-catalog-seed.json` — 779 briques uniques**
- Le delta 841 → 779 est documenté, pas caché : **55 doublons inter-sections fusionnés** (ex. DSPy listé dans 3 catégories → une seule entrée avec `also_in`), et ~7 lignes de format atypique à récupérer manuellement en revue.
- Schéma par brique : `id`, `name` (nom officiel exact), `category`, `subcategory`, `description_fr`, `description_en`, `repo_slug`, `repo_url`, `archived`, `verified_source`
- **100% des briques ont un lien repo** (héritage de la vérification API GitHub du répertoire source)
- Répartition : inférence/serving 129 · frameworks d'agents 139 · training/fine-tuning 116 · RAG/mémoire 113 · MCP/protocoles 99 · harness/méthodologies 69 · éval/guardrails/sécurité 114

## 2. Bilinguisme FR/EN — architecture i18n

**Décision d'architecture : le logiciel est bilingue natif (fichiers i18n, pas de traduction à la volée), et chaque brique du catalogue porte `description_fr` ET `description_en`.**

État actuel et pipeline :
- ✅ `description_fr` : 779/779 (source : répertoire vérifié)
- ✅ `description_en` : 37/779 faites à la main — **la totalité du template Dev Agentic est déjà bilingue**
- ⏳ 742 restantes : **pipeline de traduction batch** défini — job local (Gemma 4 27B-it ou DeepSeek V4 Pro), descriptions courtes techniques, puis **gate de revue** : échantillon de 10% vérifié humainement avant merge; toute traduction douteuse marquée `needs_review`. Coût quasi nul, une soirée de batch. La traduction n'est PAS faite par l'app à l'exécution — elle est figée au catalogue, versionnée, auditable.
- L'interface (wizard, messages, rapports) : anglais et français dès la v1, structure i18n standard (fichiers de locale) permettant d'autres langues par contribution.

## 3. « Téléchargées dans le logiciel » — la distinction qui évite le désastre

Clarification d'architecture importante :
- **Ce qui EST embarqué dans le logiciel : le CATALOGUE complet** (779+ briques, métadonnées bilingues, ~2 Mo) — navigable hors-ligne, recherche instantanée, chaque brique avec sa description dans la langue de l'utilisateur.
- **Ce qui N'est PAS pré-téléchargé : les briques elles-mêmes** (les dépôts/images = des dizaines de Go, impossibles à maintenir à jour dans un binaire). Elles sont téléchargées **à l'installation**, version épinglée, hash vérifié, journalisé au registre.
- C'est exactement le modèle apt/npm/cargo : la liste complète embarquée, les paquets à la demande. C'est ce qui rend « clé en main » ET maintenable.
- Mode air-gapped (roadmap) : `forge bundle <template>` pré-télécharge toutes les briques d'un template dans une archive portable pour déploiement sans internet.

## 4. Template Dev Agentic — COMPLET et livré

**`template-dev-agentic.json` — 37 briques, toutes bilingues, tous les rôles couverts :**

| Rôle | Briques (⭐ = défaut) |
|---|---|
| Orchestration | LangGraph ⭐, n8n |
| Programmation LM | DSPy ⭐ |
| Méthodologies | BMAD-METHOD ⭐, Superpowers ⭐, GitHub Spec-Kit, TDAD, GSD, Agent OS, cc-sdd |
| Inférence (filtrée hardware) | vLLM ⭐, SGLang, llama.cpp, Ollama, TensorRT-LLM (NVIDIA only) |
| Gateway | Bifrost ⭐, LiteLLM |
| RAG | Qdrant ⭐, Docling ⭐, Crawl4AI ⭐, Firecrawl, LlamaIndex |
| Mémoire | Mem0 ⭐, Graphiti |
| Éval/Observabilité | Langfuse ⭐, Promptfoo ⭐, Ragas, DeepEval |
| Guardrails | NeMo Guardrails ⭐, Llama Guard |
| Sandbox/workers | E2B, OpenHands |
| Cockpits IDE/CLI (branchés auto) | Cline ⭐, Aider, OpenCode, Claude Code |
| Interface chat | Open WebUI ⭐ |

Chaque brique : description FR + EN, repo vérifié, rôle explicite, flag défaut. Les ⭐ constituent le déploiement Express du template; le mode Personnalisé ouvre les alternatives.

## 5. Design — exigence produit formalisée

Ajout au contrat UX du plan v2 :
- **TUI (v1)** : wizard terminal moderne (framework type Textual) — cartes d'options, navigation clavier fluide, progression visuelle par phase, thème sombre/clair, langue FR/EN commutable à l'écran d'accueil. Le terminal peut être beau; c'est un critère d'acceptation, pas un nice-to-have.
- **UI web locale (P5)** : design system défini AVANT le code (typographie, palette, composants) — objectif explicite : l'esthétique d'un produit de référence, pas d'un outil interne. Navigation du catalogue par catégorie avec recherche bilingue instantanée, fiches de brique riches (description, repo, licence, compatibilités, historique d'installation).
- Critère d'acceptation P5 : un utilisateur externe qualifie spontanément l'interface de « polished » lors du test sans aide.

## 6. Mise à jour du prompt maître BMAD (delta à intégrer)

Ajouter aux CONTRAINTES du prompt maître v2 :
```
BILINGUISME : interface et catalogue nativement FR/EN (fichiers i18n);
chaque brique porte description_fr et description_en; architecture de
locale extensible à d'autres langues par contribution.

CATALOGUE EMBARQUÉ : le catalogue complet (779+ briques bilingues,
seed fourni : forge-catalog-seed.json) est embarqué dans le logiciel
et navigable hors-ligne; les briques sont téléchargées à l'installation
(version épinglée, hash vérifié, journalisé). Mode bundle air-gapped
en roadmap.

TEMPLATE DEV AGENTIC : implémenter d'après template-dev-agentic.json
(37 briques bilingues, défauts ⭐ définis, filtrage hardware sur
l'inférence, branchement IDE/CLI automatique).

DESIGN : TUI moderne (Textual ou équivalent) avec critères
d'acceptation esthétiques explicites; design system de l'UI web
défini avant implémentation.
```

## 7. Ce qui reste ouvert
1. Revue des ~7 lignes non parsées du répertoire (récupération manuelle)
2. Lancement du batch de traduction des 742 descriptions EN restantes (job local, une soirée)
3. Les points ouverts du plan v2 (nom/repo, T3, licence, moteur défaut Minimal, séquencement GRS) — inchangés
-e 
---
---

# PARTIE 5 — ADDENDUM v2.2 : MULTI-NŒUDS & TAILSCALE
*(Document source : FORGEAI-TOOLKIT-ADDENDUM-V22-MULTINODES-20260713 — reproduit intégralement)*

# ForgeAI Toolkit — Addendum v2.2 : Téléchargement, Multi-nœuds & Tailscale
**13 juillet 2026 — complète le plan v2 et l'addendum v2.1**

---

## 1. Téléchargement des logiciels : chaque brique porte déjà ses liens

Confirmation d'architecture : **le catalogue livré (`forge-catalog-seed.json`) contient déjà le lien officiel de chacune des 779 briques** (`repo_url`, 100% de couverture, héritée de ta vérification API GitHub). Le logiciel télécharge depuis ces liens — jamais depuis des miroirs non vérifiés.

Le schéma de brique s'enrichit d'un bloc `install` qui précise COMMENT télécharger/installer depuis ce lien :

```yaml
id: vllm
repo_url: https://github.com/vllm-project/vllm
install:
  methods:
    - type: docker            # méthode préférée
      image: vllm/vllm-openai
      tag_pinned: "v0.9.2"    # version épinglée, jamais "latest"
      digest: "sha256:..."    # hash vérifié avant exécution
    - type: pip               # fallback
      package: vllm
      version_pinned: "0.9.2"
  requires: [docker|podman, gpu-backend]
  healthcheck: "GET :8000/health == 200"
  e2e_test: "completion 'ping' retourne une réponse non vide"
```

**Règles de téléchargement (non négociables) :**
- Version épinglée + digest/hash vérifié pour chaque artefact — un download dont le hash ne correspond pas est REJETÉ et journalisé
- Chaque téléchargement écrit au registre : `{brique, version, source_url, hash, date, heure, nœud cible}`
- Retry avec reprise sur les gros artefacts (images de plusieurs Go, poids de modèles)
- Cache local partagé : une brique téléchargée une fois est réutilisée pour tous les nœuds (pas re-téléchargée N fois)

---

## 2. NOUVELLE PHASE DU WIZARD : « Nœuds » (multi-machines)

S'insère entre l'Étape 0 (détection locale) et l'Étape 1 (profil). Skippable — machine seule par défaut.

### 2.1 Ajout d'un nœud — l'écran

```
┌─ Ajouter un nœud ────────────────────────────────┐
│ Adresse IP        [ 192.168.0.42        ]        │
│ Utilisateur SSH   [ nathan              ]        │
│ Authentification  (•) Mot de passe  ( ) Clé SSH  │
│ Mot de passe      [ ************        ]        │
│                                                  │
│ [ Tester la connexion ]   [ Ajouter ]            │
└──────────────────────────────────────────────────┘
```

### 2.2 Sécurité du bootstrap — le contrat (c'est ici que "très sécurisé" se joue)

1. **Le mot de passe sert UNE fois, au bootstrap, et n'est JAMAIS écrit sur disque.** Il vit en mémoire le temps de la connexion initiale, point.
2. Au premier contact, l'outil **génère une paire de clés ed25519 dédiée au déploiement**, pousse la clé publique sur le nœud (`authorized_keys`), puis **bascule immédiatement sur l'authentification par clé**. Toutes les opérations suivantes passent par la clé.
3. La clé privée est stockée **chiffrée dans le trousseau de l'OS** (keyring) ou dans un vault local chiffré (age) — jamais en clair dans le dossier projet.
4. **Le registre journalise l'ajout du nœud (IP, user, date, empreinte de clé) — JAMAIS le mot de passe ni la clé privée.** Les secrets ne touchent structurellement pas les registres.
5. Option recommandée post-bootstrap (proposée, pas imposée) : désactiver l'auth par mot de passe SSH sur le nœud.
6. Vérification d'empreinte hôte (TOFU affichée à l'utilisateur) — protection MITM de base dès le premier contact.

### 2.3 Sondage distant automatique

Dès la connexion établie, **l'Étape 0 s'exécute sur le nœud distant** : OS, CPU, RAM, disque, GPU (vendor/modèle/VRAM), drivers présents. Chaque nœud obtient sa fiche matérielle au registre.

### 2.4 Sélection automatique du backend GPU par nœud — la matrice

C'est le cœur du multi-nœuds hétérogène (ton cas réel : NVIDIA Blackwell + AMD RDNA4 + Intel dans le même parc) :

| Hardware détecté sur le nœud | Backend déployé automatiquement | Jamais proposé |
|---|---|---|
| NVIDIA (Blackwell/Ada/Hopper) | CUDA → vLLM / TensorRT-LLM / SGLang | ROCm, OpenVINO |
| AMD CDNA / RDNA officiellement supporté ROCm | ROCm → vLLM-ROCm / llama.cpp-HIP | — |
| **AMD RDNA4 (gfx1201)** | **Vulkan → llama.cpp/Ollama** (ROCm trop instable sur cette génération) | **ROCm — jamais** |
| Intel (CPU/iGPU/NPU) | OpenVINO → optimum-intel / llama.cpp-SYCL | CUDA, ROCm |
| CPU seul | llama.cpp CPU / Ollama | tout backend GPU |

L'utilisateur voit la recommandation par nœud et peut la surcharger (mode Personnalisé) — mais la surcharge vers un backend incompatible affiche l'avertissement explicite et exige confirmation.

### 2.5 Maillage réseau : Tailscale déployé automatiquement

- L'outil installe Tailscale sur chaque nœud (lien officiel au catalogue, version épinglée)
- Authentification : l'utilisateur fournit une **auth key Tailscale** (champ sécurisé, même traitement que les mots de passe : mémoire seulement) OU flow de login interactif par nœud
- Une fois le mesh établi : **tous les services inter-nœuds se lient aux adresses tailnet**, pas aux IP LAN — chiffrement WireGuard bout-en-bout entre nœuds d'office
- Alternative offerte à cette étape : « LAN seulement (pas de mesh) » pour les parcs entièrement locaux — mais Tailscale est le défaut ⭐ recommandé

### 2.6 Attribution des rôles par nœud

Le wizard propose une répartition basée sur les fiches matérielles :

```
┌─ Répartition proposée ───────────────────────────────────┐
│ node-1 (NVIDIA 32GB VRAM)  → Inférence principale ⭐     │
│ node-2 (AMD RDNA4 48GB)    → Inférence Vulkan (gros      │
│                              modèles quantifiés) ⭐      │
│ node-3 (Intel NPU, 32GB)   → Embeddings + reranking ⭐   │
│ node-4 (CPU, gros disque)  → Qdrant + ingestion RAG ⭐   │
│ [ Accepter ]  [ Modifier la répartition ]                │
└──────────────────────────────────────────────────────────┘
```

Le RAG distribué qui en découle : ingestion sur le nœud stockage, embeddings sur le nœud le plus adapté, Qdrant là où le disque est, l'inférence là où la VRAM est — tout branché via tailnet, tout vérifié par le test bout-en-bout final (une question posée depuis n'importe quel nœud traverse toute la chaîne et cite le document témoin).

### 2.7 Orchestration multi-nœuds

- Profils Minimal/Standard multi-nœuds : Compose par nœud + câblage inter-services via tailnet
- Profils Complet/Production : **K3s multi-nœuds** — le premier nœud devient control plane, les autres joignent automatiquement (token géré comme les autres secrets), ArgoCD par-dessus

---

## 3. Delta au prompt maître BMAD (à intégrer)

```
TÉLÉCHARGEMENT : chaque brique du catalogue porte son lien officiel
(repo_url, 100% de couverture) et un bloc install (méthodes docker/pip/
binaire, version épinglée, digest vérifié, healthcheck, test e2e). Tout
téléchargement est hash-vérifié et journalisé; cache local partagé
entre nœuds; échec de hash = rejet.

PHASE NŒUDS (multi-machines) : écran d'ajout de nœud (IP + utilisateur
+ mot de passe OU clé SSH). Sécurité : mot de passe utilisé une seule
fois au bootstrap et jamais persisté; génération et poussée d'une clé
ed25519 dédiée; clé privée dans le keyring OS ou vault chiffré;
registres sans secrets (empreintes seulement); vérification
d'empreinte hôte. Sondage matériel distant automatique par nœud.

MATRICE BACKENDS PAR NŒUD : CUDA sur NVIDIA; ROCm uniquement sur AMD
officiellement supporté; Vulkan (llama.cpp/Ollama) obligatoire sur
AMD RDNA4/gfx1201 (ROCm jamais proposé); OpenVINO sur Intel
CPU/iGPU/NPU; CPU fallback. Surcharge possible avec avertissement
explicite.

MESH : déploiement automatique de Tailscale par nœud (auth key en
mémoire seulement ou login interactif); services inter-nœuds liés aux
adresses tailnet; option LAN-seulement. Multi-nœuds : Compose+tailnet
(Minimal/Standard) ou K3s multi-nœuds+ArgoCD (Complet/Production).
Attribution de rôles par nœud proposée d'après les fiches matérielles,
modifiable. Test bout-en-bout final traversant la chaîne distribuée.
```

## 4. Impact phasage

La phase Nœuds s'insère au phasage v2 comme **P2.5 — Multi-nœuds + Tailscale** (après P2 templates/moteurs, avant P3 K3s multi-nœuds qui en dépend). Preuve de done P2.5 : deux machines physiques hétérogènes (une NVIDIA, une AMD RDNA4) jointes par le wizard, backends corrects auto-sélectionnés sur chacune, RAG distribué répondant à une question de bout en bout via tailnet.
-e 
---
---

# PARTIE 6 — ADDENDUM v2.3 : STRATÉGIE, MODÈLES & BRANCHEMENT
*(Document source : FORGEAI-TOOLKIT-ADDENDUM-V23-MODELES-BRANCHEMENT-20260713 — reproduit intégralement)*

# ForgeAI Toolkit — Addendum v2.3 : Stratégie, Modèles & Branchement automatique
**13 juillet 2026 — complète le plan v2 et les addenda v2.1/v2.2**

---

## 1. Mécanique nœud : Operator GPU + moteur, formalisée

Confirmation et précision de ce qui était esquissé en v2.2 (matrice backend par nœud) — voici la séquence exacte exécutée automatiquement par nœud K3s :

```
Nœud rejoint le cluster
  → Fiche matérielle déjà connue (détection Étape 0 / sondage distant v2.2)
  → SI GPU NVIDIA détecté :
      installer NVIDIA GPU Operator (drivers, device plugin, DCGM exporter)
      → moteur : vLLM ou TensorRT-LLM ou SGLang, choisi à l'Étape 3 (filtré, jamais tous proposés en vrac)
  → SI GPU AMD détecté :
      installer AMD GPU Operator / device plugins
      → SI génération officiellement supportée ROCm : vLLM-ROCm ou llama.cpp-HIP
      → SI RDNA4/gfx1201 (non stable ROCm) : Vulkan forcé (llama.cpp/Ollama), ROCm jamais proposé
  → SI Intel CPU/iGPU/NPU : runtime OpenVINO (optimum-intel / llama.cpp-SYCL)
  → SI CPU seul : llama.cpp CPU / Ollama
  → KubeAI déployé par-dessus pour gérer placement, cache modèles, autoscaling, endpoints K8s
```

Chaque installation d'Operator est une brique du catalogue à part entière (déjà présente : NVIDIA GPU Operator, AMD GPU Operator/device plugins), donc soumise à la même discipline registre/preuve que toute brique — pas un raccourci caché.

---

## 2. NOUVELLE PHASE — Stratégie modèle (s'insère après le choix du template domaine, avant le choix des moteurs)

**Le principe que tu as décrit — un seul modèle branché à tout, versus une équipe — devient un choix explicite du wizard, pas une décision implicite.**

```
┌─ Stratégie modèle pour ce déploiement ──────────────────────────┐
│                                                                  │
│ ( ) Cerveau unique                                              │
│     Un seul modèle branché directement à la mémoire, au RAG,    │
│     aux outils MCP, au harness, aux ledgers et aux plugins.     │
│     Simple à raisonner, coût prévisible, un seul point de       │
│     défaillance de "jugement".                                  │
│                                                                  │
│ ( ) Équipe spécialisée ⭐ recommandé si Standard/Complet         │
│     Plusieurs modèles avec rôles distincts (architecture,       │
│     code, revue/critique, embeddings) + prompt manager qui       │
│     scope le contexte par agent. Meilleure économie de contexte │
│     et décorrélation d'erreur, plus complexe à opérer.          │
│                                                                  │
│ ( ) Hybride                                                      │
│     Cerveau unique pour les tâches simples, bascule vers         │
│     l'équipe pour les missions classées critiques (gates T2+).  │
│                                                                  │
│ [ Continuer ]                                                    │
└──────────────────────────────────────────────────────────────────┘
```

**Impact concret du choix, immédiatement visible à l'écran suivant :**
- **Cerveau unique** → l'Étape Modèles (section 3) ne demande qu'UN modèle principal; celui-ci est câblé (section 4) à toutes les briques de support choisies
- **Équipe spécialisée** → l'Étape Modèles s'ouvre en mode multi-slots : un slot par rôle détecté dans les briques sélectionnées (ex. le template Dev Agentic avec DSPy+méthodologies présent → slots Architecture / Coding / Revue indépendante / Embeddings apparaissent automatiquement, pré-remplis avec les défauts ⭐ mais modifiables)
- **Hybride** → les deux écrans, avec une règle de bascule affichée et modifiable (ex. "gates T2 et plus → équipe")

Ce choix est écrit au canon du projet (`canon-architecture.md`) — un changement de stratégie après coup est possible mais déclenche un diff de reconfiguration explicite, jamais silencieux.

---

## 3. NOUVELLE PHASE — Modèles (téléchargement, installation, configuration — locaux ET cloud)

**Principe : les modèles suivent la même discipline que les briques logicielles — catalogue vérifié, version épinglée, téléchargement hashé, registre horodaté — mais dans leur propre espace de noms (jamais comptés comme des briques, conformément à la règle Atlas déjà établie).**

### 3.1 Modèles locaux

```
┌─ Modèle local — rôle : Coding ──────────────────────────────────┐
│ Nœud cible        : node-2 (AMD RDNA4, 48GB VRAM, Vulkan)       │
│                                                                  │
│ ( ) Qwen3-Coder-Next  ⭐ recommandé pour ce nœud                │
│ ( ) Ornith 35B                                                  │
│ ( ) Devstral Small 2 24B                                        │
│ ( ) [voir plus — filtré par VRAM disponible et backend Vulkan]  │
│                                                                  │
│ [ Télécharger et déployer ]                                     │
└────────────────────────────────────────────────────────────────┘
```

- La liste est filtrée par : VRAM réellement disponible sur le nœud cible ET compatibilité avec le backend déjà déterminé pour ce nœud (section 1) — un modèle qui n'existe qu'en format incompatible avec le backend du nœud n'apparaît pas
- Téléchargement : poids depuis la source officielle (Hugging Face / repo du modèle), hash vérifié, reprise sur interruption, écrit au registre (`{modèle, version/quantification, nœud, date, heure, hash}`)
- Déploiement automatique sur le moteur déjà choisi pour ce nœud (vLLM/SGLang/TensorRT-LLM/llama.cpp/Ollama — aucun re-choix, cohérence avec la section 1)
- Vérification : requête de complétion réelle envoyée au endpoint, réponse non vide = GREEN, sinon échec explicite avec logs

### 3.2 Modèles cloud

```
┌─ Modèle cloud ───────────────────────────────────────────────────┐
│ Nom du modèle      [ GLM-5.2                          ]          │
│ Provenance         [ ▾ Direct (Z.ai)                  ]          │
│                       ▾ Direct (Z.ai)                            │
│                       ▾ OpenRouter                               │
│                       ▾ NVIDIA NIM                                │
│                       ▾ DeepInfra                                 │
│                       ▾ Autre (URL personnalisée)                 │
│ Clé API            [ ************************          ]          │
│                                                                    │
│ [ Tester la connexion ]   [ Ajouter ]                             │
└────────────────────────────────────────────────────────────────────┘
```

- **Catalogue de provenances connues embarqué** (mêmes garanties que le catalogue de briques — vérifié, pas deviné) : Direct par fournisseur (Z.ai/GLM, DeepSeek Platform, Moonshot/Kimi, MiniMax, Anthropic, xAI...), plus agrégateurs (OpenRouter, NVIDIA NIM, DeepInfra, Bifrost lui-même s'il expose des routes tierces). Chaque provenance connaît son format d'URL de base et son schéma d'authentification — l'utilisateur n'a qu'à choisir dans la liste, pas à deviner l'endpoint
- **Traitement de la clé API — même contrat de sécurité que les mots de passe SSH et l'auth key Tailscale (v2.2)** : saisie en mémoire, jamais journalisée en clair, stockée chiffrée dans le vault local (age) ou le keyring OS. Le registre journalise l'AJOUT de la route (modèle, provenance, date, heure, empreinte) — jamais la clé elle-même
- **Test de connexion réel avant validation** : un appel de complétion minimal est envoyé; échec = message clair (mauvaise clé? mauvaise provenance? modèle non servi par ce fournisseur?), pas un ajout silencieux d'une route cassée
- Chaque modèle cloud validé devient une route enregistrée — voir section 4

---

## 4. NOUVELLE PHASE — Branchement automatique (le câblage réel entre briques et modèles)

**C'est la phase qui répond directement à "il doit brancher tout les briques choisi sur la route".** Une fois briques ET modèles installés/validés, cette phase s'exécute automatiquement — aucune configuration manuelle de fichiers.

### 4.1 Principe directeur : un seul point de routage, jamais de branchement direct brique→modèle

Conformément à la règle déjà établie dans ton propre Atlas (*« ne jamais installer plusieurs control planes pour la même fonction »*) : **aucune brique ne pointe directement vers un modèle.** Tout passe par le gateway (Bifrost, ou le gateway défini par défaut dans le catalogue). Les modèles locaux ET cloud, une fois installés/validés (section 3), deviennent tous des routes dans le même gateway — c'est le gateway seul qui sait où vit chaque modèle.

```
Brique (n8n, Hermes Agent, OpenClaw, MemOS, etc.)
   → pointe vers → Gateway (Bifrost)
                        → route "architecture" → GLM-5.2 (cloud, direct Z.ai)
                        → route "coding-local" → Qwen3-Coder-Next (node-2, Vulkan)
                        → route "embeddings" → Qwen3-Embedding (node-3, NPU)
```

### 4.2 Ce qui est câblé automatiquement, par brique — exemples concrets de ta liste

| Brique | Ce que le wizard configure automatiquement |
|---|---|
| **n8n** | Variable d'environnement pointant vers l'endpoint Gateway; credential HTTP pré-rempli pour les nodes n8n qui appellent un LLM |
| **Hermes Agent / Hermes Orchestrator** | Graphe LangGraph câblé : nœud LLM → Gateway; nœud mémoire → MemOS/Mem0 (selon ce qui a été choisi); registre d'outils → serveurs MCP installés |
| **OpenClaw** | Route par défaut vers le Gateway; modèle par défaut = celui désigné "cerveau unique" ou le rôle "généraliste" de l'équipe (section 2) |
| **MemOS / Mem0 / Graphiti** (selon lequel des ~900 briques a été choisi) | Chaîne de connexion vers PostgreSQL/Qdrant/Neo4j déployés en Phase 1; endpoint exposé au Forge Memory MCP |
| **Frameworks RAG (Qdrant, Docling, Crawl4AI...)** | Pipeline câblé : ingestion → embeddings (route Gateway dédiée) → Qdrant → reranker → contexte livré à l'agent |
| **Serveurs MCP** | Enregistrés dans le registre d'outils de l'orchestrateur, scope de permissions appliqué (lecture seule par défaut, conformément à ta règle Atlas) |

### 4.3 Prompt caching — l'exemple que tu as nommé, concrètement

- Configuré au niveau du **Gateway**, pas brique par brique : chaque route de modèle porte un indicateur `cache: true/false` et une politique (TTL, clé de cache basée sur préfixe stable)
- Si LMCache ou équivalent est dans les briques choisies : le Gateway y délègue le cache KV distribué; sinon, cache exact au niveau du Gateway lui-même (comportement par défaut plus simple)
- Visible et modifiable après coup via `forge route list` / `forge route configure <nom>` — jamais enfoui dans un fichier YAML à éditer à la main

### 4.4 Preuve de branchement (s'ajoute au test bout-en-bout déjà défini en v2)

Avant de déclarer la phase Branchement GREEN : un test traverse RÉELLEMENT la chaîne complète pour chaque brique câblée — pas juste "la config existe". Exemple : n8n déclenche un workflow test → appelle le Gateway → reçoit une réponse du modèle configuré → écrit au registre. Si une seule route ne répond pas, la phase reste ROUGE et affiche précisément quel maillon a échoué.

---

## 5. Delta au prompt maître BMAD (à intégrer)

```
PHASE STRATÉGIE MODÈLE : écran de choix Cerveau unique / Équipe
spécialisée / Hybride, inséré après le choix du template domaine.
Le choix détermine le nombre de slots ouverts à la phase Modèles
(un slot en cerveau unique; un slot par rôle détecté dans les
briques sélectionnées en équipe spécialisée) et est écrit au canon.

PHASE MODÈLES : les modèles suivent la discipline catalogue/registre
des briques mais dans un espace de noms séparé (jamais comptés comme
brique). Locaux : liste filtrée par VRAM du nœud cible et backend déjà
déterminé (matrice v2.2); téléchargement hash-vérifié; déploiement sur
le moteur du nœud; test de complétion réel. Cloud : champ nom + menu
déroulant de provenances connues (direct par fournisseur, OpenRouter,
NVIDIA NIM, DeepInfra, autre/URL personnalisée) + champ clé API
(mémoire seulement, vault chiffré, jamais journalisée en clair,
registre limite à l'empreinte); test de connexion réel obligatoire
avant validation de la route.

PHASE BRANCHEMENT (automatique, après installation briques+modèles) :
aucune brique ne pointe directement vers un modèle — tout passe par
le Gateway unique (principe "un seul control plane par fonction").
Câblage automatique par brique selon son rôle (orchestrateur → graphe
LangGraph + mémoire + registre d'outils; interfaces → route par défaut
Gateway; mémoire → chaîne de connexion vers le store choisi; RAG →
pipeline ingestion-embeddings-vectordb-reranker). Prompt caching
configuré au niveau Gateway (par route, TTL/clé de cache), pas par
brique. Preuve de branchement : test bout-en-bout réel par brique
câblée, pas une vérification de présence de config.
```

## 6. Impact phasage (mise à jour)

Le phasage v2 reste valide; ces trois nouvelles phases du wizard (Stratégie, Modèles, Branchement) sont livrées avec **P2** (Templates + moteurs + IDE), puisqu'elles sont indissociables du template Dev Agentic qui les a motivées. **P2.5 Multi-nœuds** (v2.2) précède logiquement puisque le choix de nœud cible pour chaque modèle local en dépend.

Preuve de done mise à jour pour P2 : Dev Agentic déployé avec stratégie "Équipe spécialisée", au moins un modèle local (nœud filtré par hardware) et un modèle cloud (provenance + clé testée) tous deux câblés et répondant via le Gateway unique, test bout-en-bout traversant Hermes Orchestrator → mémoire → RAG → modèle → réponse.


---
---

# PARTIE 7 — INSTRUCTION DE RELECTURE INTÉGRALE ET RAPPORT DE CONFORMITÉ
## (À exécuter par Fable AVANT toute nouvelle story — mission de vérification anti-déviation)

```
MISSION PRIORITAIRE — RELECTURE INTÉGRALE ET CONFORMITÉ :

1. LIS CE DOCUMENT EN ENTIER, du préambule à cette instruction.
   Pas de survol, pas de résumé par échantillonnage : l'intégralité.
   C'est le document de référence unique; les 6 fichiers dispersés
   qu'il consolide ne font plus autorité individuellement.

2. VÉRIFIE LES INVARIANTS MÉTHODOLOGIQUES (préambule, points 1-10)
   contre l'état réel du repo : hooks actifs, workflow de revue,
   protection de branche, format des registres. Pour chacun des 10 :
   CONFORME ou DÉVIÉ, avec preuve (fichier/config/run à l'appui).
   Toute déviation méthodologique est un défaut CRITIQUE à corriger
   immédiatement — les méthodes ne changent pas, par instruction
   explicite de Nathan.

3. DIFFE LA PARTIE 1 (les 25 exigences ID-1 à OC-1) contre le PRD
   et les stories du repo. Pour chaque exigence : COUVERTE /
   PARTIELLE / ABSENTE, avec référence de fichier ou story comme
   preuve. Attention particulière aux exigences 📎 (risque de
   non-transmission des annexes) et 🆕 (jamais spécifiées avant le
   canon) — notamment : DM-2 (drivers update + Intel), DM-3 (phase
   Nœuds IP/user/mot de passe), DM-5 (modèles cloud + clés API),
   DM-5b (phase Stratégie modèle), CD-4 (import/export), DA-2/3/4
   (IDE entièrement branché, Ralph loop, token economy), OC-1
   (cycle de recherche).

4. VÉRIFIE LES PARTIES 3 À 6 contre l'implémentation : chaque écran
   de wizard, chaque phase, chaque règle de sécurité (mot de passe
   en mémoire seulement, clés API jamais journalisées, registres
   sans secrets) décrits dans ces parties doit avoir son
   correspondant dans le PRD/stories — sinon, écart à rapporter.

5. PRODUIS LE RAPPORT DE CONFORMITÉ au registre :
   - Section A : les 10 invariants, statut + preuve chacun
   - Section B : les 25 exigences, statut + preuve chacune
   - Section C : liste des écarts avec sévérité (critique/majeur/
     mineur) et story corrective proposée pour chacun
   - Section D : déclaration explicite — « aucune déviation
     méthodologique détectée » OU la liste exacte des déviations
   Ce rapport passe le circuit normal : revue aveugle 3 modèles /
   3 vendors, puis validation.

6. CRÉE LES STORIES CORRECTIVES pour chaque écart, insérées dans le
   phasage existant sans casser les stories en cours, avec critères
   d'acceptation testables.

7. VERSIONNE ce document au repo : CANON/plan-integral.md — il
   devient la référence; toute modification future passe par le
   circuit de gouvernance (revue 3 modèles + signature).

8. SEULEMENT APRÈS validation du rapport de conformité : reprends
   la file de travail (F24 si le document source Atlas est fourni,
   F25, puis le reste). La publication PyPI reste un gate T3 —
   recommandation possible, décision de Nathan uniquement.

RAPPEL FINAL : le blocage honnête est un résultat acceptable; le
faux avancement ne l'est jamais. Deux états de sortie : DONE-avec-
preuve ou BLOCKED-avec-raison. Rien d'autre.
```
