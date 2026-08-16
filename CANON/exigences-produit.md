# ForgeAI Toolkit — Exigences produit canon

**Source unique versionnée** : extrait de `CANON/plan-integral.md` (PARTIE 1),
lui-même reproduction intégrale de `FORGEAI-TOOLKIT-PLAN-INTEGRAL-20260714.md` (v2.0).
Toute divergence entre ce canon et le PRD/stories du repo est un défaut à corriger côté repo.

Légende des statuts de spécification (au moment de la consolidation) :
✅ PLAN-MAÎTRE · 📎 ANNEXE (risque de non-transmission) · 🆕 NOUVEAU (jamais écrit avant ce canon).

## 1. Identité du produit
| ID | Exigence | Spéc |
|---|---|---|
| ID-1 | Produit **pour tout le monde** (dev solo, homelab, PME, équipe infra) — jugé à l'aune d'un externe qui n'a jamais vu Forge. | 📎 |
| ID-2 | **Solution clé en main** : télécharger → suivre les phases → infra fonctionnelle. Aucune édition manuelle de fichier pour un déploiement standard. | 📎 |
| ID-3 | **La référence** : défauts ⭐ = meilleurs choix éprouvés, réévalués par benchmark à chaque release; mises à jour continues. | 📎 |
| ID-4 | **Interface intuitive, moderne, esthétique** : TUI moderne (critères d'acceptation esthétiques) puis UI web (design system avant le code). | 📎 |
| ID-5 | **Bilingue FR/EN natif** (interface + catalogue), i18n extensible. | 📎 |

## 2. Déploiement et matériel
| ID | Exigence | Spéc |
|---|---|---|
| DM-1 | Détection matérielle auto (OS/CPU/RAM/disque/GPU vendor+VRAM+drivers) filtrant les options; une option incompatible n'est jamais affichée. | 📎 |
| DM-2 | **Cycle de vie des drivers GPU : détecter ET installer ET mettre à jour** — NVIDIA (GPU Operator + Container Toolkit), AMD (device plugins, Vulkan sur RDNA4), Intel (OpenVINO, device plugins). Mise à jour journalisée + rollback. | 🆕 |
| DM-3 | Multi-nœuds : phase connexion (IP + user + mot de passe/clé SSH), bootstrap ed25519, Tailscale auto, sondage distant, matrice backend par nœud, rôles proposés. | 📎 |
| DM-4 | Deux backends depuis le même catalogue : Docker Compose (Minimal/Standard) et K3s+Helm+ArgoCD (Complet/Production). | ✅ |
| DM-5 | Modèles (locaux ET cloud) téléchargés/installés/configurés/testés par le wizard; cloud = nom + provenance (menu) + clé API sécurisée + test de connexion réel. | 📎 |
| DM-5b | **Phase Stratégie modèle** : Cerveau unique / Équipe spécialisée / Hybride avant sélection; détermine les slots; écrit au canon; changement = diff explicite. | 📎 |
| DM-6 | Branchement auto : aucune brique ne pointe vers un modèle — tout via le gateway unique; prompt caching par route; preuve par test traversant réel. | 📎 |

## 3. Contenu déployé
| ID | Exigence | Spéc |
|---|---|---|
| CD-1 | Stacks pré-préparés par domaine (Dev Agentic, RAG souverain, Lab fine-tuning, Production souveraine, Vide) — chacun un système COMPLET fonctionnel. | 📎 |
| CD-2 | Stack déployé branché et fonctionnel : harnesses, ledgers, guardrails, frameworks, RAG complet, mémoire, selon les briques choisies. | 📎 |
| CD-3 | **Modulable** : architecture plugin; contribution communautaire avec vérification obligatoire avant merge. | 📎 |
| CD-4 | **Import/export** : `forge export` → bundle portable (briques+versions, stratégie modèle, routes SANS clés, config nœuds anonymisée, canon) → `forge import` recrée le setup. Versionné, hash-vérifié. | 🆕 |

## 4. Template Dev Agentic
| ID | Exigence | Spéc |
|---|---|---|
| DA-1 | IDE/CLI choisi (Cline, Cursor, Claude Code, OpenCode, Aider) livré **entièrement branché** : config injectée, parle au stack dès l'ouverture. | 📎 |
| DA-2 | Branchement IDE inclut : serveurs MCP, skills allowlistés, BMAD + prompt manager, hooks de gouvernance. | 🆕 |
| DA-3 | **Loop engineering** : Ralph Wiggum loop préconfigurée (plugin Anthropic + primitives /loop natives) avec garde-fous (budget itérations, condition de complétion, journal). | 🆕 |
| DA-4 | **Token economy** : budgets par agent/mission au gateway (quota/alerte/coupure), consommation mesurée et journalisée. | 🆕 |

## 5. Qualité et gouvernance (déjà canon)
| ID | Exigence | Spéc |
|---|---|---|
| QG-1 | No-stub / no-fake-done : DONE-avec-preuve ou BLOCKED-avec-raison, enforcement déterministe. | ✅ |
| QG-2 | Validation 3 modèles / 3 vendors + signature Fable; revue aveugle scellée; dépouillement par script. | ✅ |
| QG-3 | Vérification post-déploiement RÉELLE : health checks + test bout-en-bout fonctionnel. | ✅ |
| QG-4 | Gates T0-T3; T3 (paiements, secrets prod, suppressions, engagements externes) = humain. | ✅ |

## 6. Optimisation continue
| ID | Exigence | Spéc |
|---|---|---|
| OC-1 | **Cycle de recherche multi-modèles** à chaque release majeure du catalogue : recherche profonde ciblée par catégorie, réévaluation des ⭐, changement journalisé avec preuve comparative. | 🆕 |

---
Le statut réel de chaque exigence dans le repo est audité dans
`archive/rapports/conformite-v2.0-integrale.md` (Section B) et suivi comme stories dans
`manifests/backlog.yaml`.
