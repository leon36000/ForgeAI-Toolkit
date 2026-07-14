<!-- Consolidation MiMo (provider_id=MiMo-Pro-V2, 2026-07-14) — corrections Fable appliquées et journalisées :
     table des stories réalignée sur Phase-A/stories-kimi.md (la sortie brute décalait S03-S10),
     tally corrigé (plan-freeze: ≥7/9; par story: 3 verdicts 3 vendors + zéro critique — la sortie disait « 2/3 »),
     références corrigées (scripts/ et Registres/ — pas de répertoire gates/), risques réalignés sur risques-deepseek.md. -->
# MASTER-PLAN ForgeAI Toolkit v1.0

> **Statut** : Phase A livrée (8/9 livrables, 1 BLOCKED journalisé) — plan gelé consolidé.
> **Moteur par défaut (Minimal)** : Ollama · **Licence** : Apache 2.0 · **Cible** : Python ≥ 3.10, TDD, BMAD.

## 1. Mission et périmètre

ForgeAI Toolkit est le **déployeur de référence d'infrastructures IA agentiques** :
wizard TUI (Textual, hardware-aware), catalogue de **1 021 briques** (FR/EN), rendu double
backend (Docker Compose + K3s), multi-nœuds Tailscale (P2), gouvernance par registres
JSONL hash-chaînés. Réf. complète : `CANON/PLAN-MAITRE-EXECUTION-BMAD-v1.0.md`.

## 2. Équipe et gouvernance

| Agent | Rôle principal | Route |
|---|---|---|
| **Fable** | Orchestrateur, juge/validateur d'étapes, codeur du difficile | session Claude Code |
| **GLM-5.2** | Architecte permanent | glm52 |
| **DeepSeek V4 Pro** | Juge indépendant — reviewer aveugle 1 | deepseek |
| **Kimi K2.7** | Codeur long-horizon | kimi |
| **Composer 2.5** | TUI/UX | composer |
| **Grok 4.5** | Tests + codeur parallèle | Grok-4.5 |
| **Gemini 3.1 Pro** | Reviewer aveugle 2 (multimodal) | Gemini-3.1-Pro |
| **Qwen 3.7 Max** | Catalogue bilingue | Qwen3.7-Max |
| **LongCat 2.0** | Reviewer aveugle 3 + sécurité | LongCat-2.0 |
| **MiMo** | Synthèse des preuves | MiMo-Pro-V2 |
| **Nathan** | Gardien T3 (secrets prod, paiements, suppressions) | humain |

**Revue** : aveugle scellée ×3 (3 vendors distincts, verdicts JSON dans `reviews/`, tally par
script — jamais un LLM). Code Fable → reviewers non-Anthropic uniquement. Paire interdite :
composer+grok (même vendor).

## 3. Architecture cible

```
src/
├── tui/          # Wizard Textual (bascule langue in-place, mode --ci, 80×24)
├── hardware/     # Détection CPU/GPU/RAM/disque multi-vendor → HardwareProfile
├── catalogue/    # 1021 briques, validation, hash du catalogue
├── rag/          # Ingestion + requête (preuve e2e)
├── planner/      # Profils, assemblage DeploymentPlan
├── renderers/    # RenderTarget: Compose | K3s
├── network/      # Multi-nœuds Tailscale (P2)
└── core/         # Dataclasses, hooks typés, registre, config
```

Dataclasses : `HardwareProfile`, `Brick`, `DeploymentPlan`, `NodeSpec`, `RenderTarget`.
Pipeline : détection → sélection → assemblage → rendu → déploiement → preuve.
Détail : `Phase-A/architecture-glm.md`.

## 4. Phases et critères de sortie

### P1 — Détection + Minimal single-node (machine nue → RAG prouvé)
| Story | Livrable | Codeur |
|---|---|---|
| S01 | Hardware discovery (JSON normalisé, unsupported si < seuils) | fable |
| S02 | Dérivation profil Minimal | fable |
| S03 | Catalogue load + validation hash | grok |
| S04 | Assemblage stack RAG (ollama, vector-store, rag-api) | composer |
| S05 | Bootstrap sécurisé local (secrets 0600, zéro clair) | fable |
| S06 | Deploy Compose + healthchecks | composer |
| S07 | Deploy K3s single-node | grok |
| S08 | Ingestion documents RAG | kimi |
| S09 | Preuve e2e : réponse contenant un fait ingéré | kimi |
| S10 | Wizard --ci bout-en-bout + preuve au registre | fable |

**Chemin critique (corrigé rounds 1-2)** : S01 → S02 → S03 → S04 → S05 → S06 → S08 → S09 → S10.
S07 (K3s) est hors chemin critique mais **reste un critère de sortie P1**, prouvé par la
**séquence de parité complète** (amendement round 2, objection Gemini intégrée) : après la preuve
Compose (S06→S08→S09) et son teardown complet, la même séquence tourne sur K3s —
S07 → S08′ (ingestion) → S09′ (question/réponse) → teardown. La parité e2e exige que les deux
backends répondent correctement à la même question sur le même document. S07 n'est PAS un
prérequis de S08 (graphe : S08 dépend de S06); la validation P1 est un événement de fin de phase
qui exige les DEUX preuves.

**Règles de résolution du round 1 (objections critiques résolues) :**
1. **Backends séquentiels, jamais simultanés** : S06 et S07 s'exécutent l'un après l'autre sur le
   même nœud avec teardown complet entre les deux (`down -v` / suppression namespace). La parité
   Compose/K3s se mesure sur preuves successives — aucune collision ports/CIDR possible.
2. **Traductions manquantes ≠ stub** : P1 charge le catalogue en FR (langue source complète),
   fallback FR quand l'EN manque; les 742 entrées en attente portent un statut de données explicite
   hérité du catalogue maître — c'est un état documenté, pas un marqueur de code inachevé, et le
   no-stub-scan ne porte que sur le code. La preuve e2e S08/S09 ingère un document de test et
   interroge son contenu : elle ne dépend d'aucune traduction. Complétion EN = P2 (F23).

**Sortie P1** : couverture ≥85 % (95 % registre/gates), S09 prouvé au registre, S06 ET S07 prouvés
séquentiellement, gates verts, zéro stub.

### P2 — Multi-nœuds + catalogue complet
Préconditions : P1 validée + revue sécurité multi-nœuds levée (BLOCKED actuel).
Livrables : bootstrap ed25519/Tailscale, jonction nœud prouvée, 742 traductions EN,
231 entrées Atlas enrichies, sélection multi-nœuds wizard.

### P3 — Gouvernance complète + release
Profils Standard/Avancé, hooks post-merge canon, packaging PyPI, docs Diátaxis.

## 5. Pipeline par story

Issue → context pack → codeur (roles.yaml) → TDD RED-GREEN-REFACTOR → hooks locaux →
PR → gates CI → revue aveugle ×3 → tally → signature Fable → merge → registre → docs.
Chaque story : **DONE-avec-preuve ou BLOCKED-avec-raison** (§8bis, aucun troisième état).

## 6. Gates et enforcement

| Gate | Outil | Seuil |
|---|---|---|
| Lint | ruff | 0 violation |
| Types | mypy --strict | 0 erreur |
| Tests | pytest | ≥85 % global, ≥95 % registre/gates |
| Zéro stub | scripts/no_stub_scan.py | 0 hit (marqueurs + AST) |
| Secrets | gitleaks | 0 fuite |
| Images | trivy | 0 CVE HIGH/CRITICAL |
| Hash catalogue | vérification dédiée | hash conforme au registre |
| No-fake-done | vérification dédiée | DONE sans preuve = FAIL |
| Revue aveugle ×3 | scripts/tally.py | 3 verdicts, 3 vendors, zéro objection critique non résolue |
| Consensus de plan | scripts/tally.py | ≥7/9 APPROVE + zéro critique (plan-freeze uniquement) |
| Signature Fable | registre | par-dessus gates verts, jamais en substitut |
| T3 | Nathan | secrets prod, paiements, suppressions, engagements externes |

## 7. Risques et mitigations (top 5 — détail : Phase-A/risques-deepseek.md)

| ID | Risque | Mitigation |
|---|---|---|
| R-01 | Détection hardware échoue (matériel non standard) | mode « détection forcée » questionnaire ≤8 questions |
| R-05 | Divergence Compose ↔ K3s | tests de parité systématiques sur les deux backends |
| R-14 | Sous-estimation du réglage RAG | benchmark dès J1, réduction de périmètre documentée |
| R-03 | Clé compromise propagée au bootstrap | rotation post-déploiement, jamais de clé en clair au registre |
| R-06 | Consensus bloqué pour raisons stylistiques | checklist de notation objective + arbitrage Fable journalisé |

## 8. Références

| Chemin | Contenu |
|---|---|
| `CANON/` | Plan maître gelé + catalogue maître unifié (PDF 1021 + extraction) |
| `Phase-A/` | Livrables Phase A (architecture, risques, stories, TUI, tests, UX, pilote, manifestes) |
| `manifests/` | roles.yaml, routes.yaml, phases.yaml, gates.yaml |
| `Registres/` | mission.jsonl — preuves hash-chaînées |
| `reviews/` | verdicts de revue aveugle scellés |
| `scripts/` | registre.py, no_stub_scan.py, tally.py |

*Consolidé par MiMo, validé structurellement par Fable — gel v1.0, 2026-07-14.*
