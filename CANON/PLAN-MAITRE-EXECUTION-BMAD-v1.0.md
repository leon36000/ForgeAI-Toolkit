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
