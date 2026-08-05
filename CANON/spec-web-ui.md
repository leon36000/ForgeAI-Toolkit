# spec-web-ui.md — Interface web ForgeAI Toolkit (décomposition BMAD de B-02)

- **Exigence** : ID-4 (« Interface intuitive, moderne, esthétique : TUI moderne **puis UI web (design system avant le code)** »). Ce document réalise la moitié **UI web** de ID-4.
- **Remplace** : la piste TUI Textual de B-02 (`spec-tui-composer.md`, jamais écrite). Décision Nathan (2026-07-17) : la surface v1 est une **interface navigateur**, plus simple et plus visuelle qu'un TUI terminal. La CLI déjà livrée reste la surface terminal.
- **Phase produit** : P5 (« Catalogue communautaire + **UI web** + cycle de recherche »).
- **Méthode** : BMAD complet (Analyste → PM → Architecte → PO). Chaque artefact relit le brief. Toute fonctionnalité hors périmètre v1 est signalée §7 comme extension.
- **Claim** : UNVERIFIED jusqu'à exécution + revue aveugle 3 vendors par sous-story.

---

## §0 — Décision & principe directeur

**Décision technique (Nathan, 2026-07-17)** : web-app locale légère — backend **Python stdlib** (`http.server`), frontend **HTML/CSS/JS vanilla** servi en local. Pas de framework, pas d'étape de build, pas de `node_modules`.

**Principe directeur — AUTO-SUFFISANCE TOTALE** (contrainte dure Nathan, 2026-07-17, verbatim : *« il doit être auto suffisant … utilisable par tout le monde et moi même … même si je formatte tous mes nœuds »*) :

> ForgeAI Toolkit doit tourner **sur une machine fraîchement formatée**, **hors-ligne / air-gap**, **sans dépendre de l'état du système de l'opérateur**, et être **utilisable par n'importe qui**.

Conséquences non négociables, dérivées de ce principe :
1. **Zéro dépendance runtime** hors stdlib Python 3.11+ (aucun `pip install` d'un framework web).
2. **Zéro fetch réseau au chargement** : aucune CDN, aucune police web, aucun script/feuille de style/police/icône distants. Tous les assets sont **embarqués dans le paquet** et **inlinés** (data-URI ou polices système).
3. **Zéro étape de build** : le frontend est servi tel quel depuis les données du paquet.
4. **Souverain par défaut** : bind `127.0.0.1` uniquement ; aucune exposition LAN sans action explicite.

Ce principe est **hérité par toutes les sous-stories** comme critère d'acceptation (§5) et testé (§6).

---

## §1 — Brief (Analyste)

**Produit** (récap Nathan, 2026-07-17) : ForgeAI Toolkit est un **logiciel de déploiement clé-en-main d'infrastructures IA modulables**. Base fortement optimisée + stacks pré-préparés. **~1000 briques** (frameworks, plugins, ledgers, harness, guardrails…). L'utilisateur choisit un profil et un stack de domaine (ex. **Agentic → il choisit son IDE préféré**) ; l'outil déploie **de la base jusqu'à l'optimisation finale** une infra IA **100 % opérationnelle / optimale / qualitative**, **clé-en-main**, via une **interface de configuration dédiée**. Multi-nœuds : **pages dédiées pour saisir IP / user / mot de passe** de chaque nœud.

**Besoin** : la surface actuelle est une CLI complète (moteur prouvé). Il manque une **interface visuelle, moderne, intuitive** rendant le déploiement clé-en-main accessible sans connaissance de la ligne de commande.

**Le moteur existe déjà** (livré + prouvé, main) — la web-UI est une **surface, pas une réécriture** : détection hardware, profils (`derive_profile`), catalogue 1576 briques + schéma, templates Dev-Agentic/RAG/Lab/Production, modèles cloud/local + vault, gateway unique, stratégie, budgets, **multi-nœuds** (add/tailscale/probe, secret éphémère), IDE (list/configure/MCP/gouvernance), export/import, drivers GPU, et l'orchestration bout-en-bout `wizard_ci` (`cli.py`). La web-UI **rappelle ces fonctions ; elle n'ajoute aucune logique métier**.

**Contraintes héritées** (invariants PROOF + canon) :
- **Souveraineté / hors-ligne** (voir §0).
- **FR/EN natif** (ID-5), i18n = source unique `forgeai/i18n`.
- **Secrets** : mot de passe de nœud et clé API **jamais** sur disque / argv / registre — uniquement en mémoire le temps du bootstrap, puis empreinte + référence d'environnement (réutilise B-05/B-09).
- **Frontières T3 = Nathan seul** : aucun paiement, publication, secret prod, suppression définitive ni engagement externe déclenché par l'UI.
- **stdlib pure**, no-stub / no-fake / no-TODO-en-diff.

---

## §2 — PRD (PM)

### Personas
- **P1 — Opérateur souverain (Nathan)** : power user auto-hébergé ; reformate ses nœuds ; doit pouvoir **tout redéployer de zéro, hors-ligne, à tout moment**.
- **P2 — Nouvel utilisateur** : veut du **clé-en-main** ; choisit un profil + un stack de domaine + un IDE, clique « déployer », obtient une infra IA fonctionnelle **sans CLI**.
- **P3 — Admin multi-nœuds** : saisit IP / user / mot de passe de plusieurs nœuds pour former un cluster.

### Parcours v1 — une page par décision (miroir visuel de `wizard_ci`)
1. **Accueil** — bascule langue FR/EN, thème sombre/clair, **résumé du matériel détecté** (`GET /api/detect`) + santé (`GET /api/doctor`).
2. **Profil & Template** — profil (Minimal / Standard / Complet / Personnalisé) + template de domaine (Dev-Agentic / RAG souverain / Lab fine-tuning / Production souveraine / Vide) ; **reco pré-sélectionnée**, **filtrée par le matériel**.
3. **Modèles & IDE** — routes modèle (cloud / local, **filtrées par VRAM**) ; pour un stack Agentic, **choix de l'IDE** (list + configure, MCP/gouvernance préconfigurés).
4. **Nœuds** — pages multi-nœuds : ajout d'un nœud (**IP / user / mot de passe éphémère** → bascule clé ed25519), sonde matérielle distante, statut du cluster. *Mono-nœud : étape sautable.*
5. **Résumé pré-déploiement** — **ce qui sera installé** (briques, services, ports, disque, durée estimée), **modifiable**, avec **friction explicite** avant de forcer un choix hors-reco.
6. **Déploiement & Preuve** — lance l'équivalent `wizard_ci`, **progression en direct** (SSE), **preuve e2e** (santé des services + smoke test RAG), **rapport final** + export.

### Périmètre v1 vs roadmap
- **v1** : pages 1→6 (config + déclenchement du déploiement + progression live + preuve), FR/EN in-place, thème sombre/clair, hors-ligne, responsive, accessible clavier.
- **Roadmap (hors v1, §7)** : édition avancée du catalogue dans l'UI, tableaux de bord post-déploiement temps-réel, multi-utilisateur/auth, thèmes personnalisés, i18n au-delà de FR/EN.

### Critères de succès (mesurables)
- **CS-1** : un nouvel utilisateur déploie un stack (ex. RAG souverain) **de bout en bout via le navigateur, sans CLI**, sur une machine fraîchement formatée, **hors-ligne**.
- **CS-2** : **zéro fetch réseau** au chargement de l'UI (fonctionne air-gap) — vérifié par test.
- **CS-3** : bascule **FR/EN in-place** (sans rechargement) ; thème sombre/clair.
- **CS-4** : **aucun secret en clair** sur disque / argv / registre après un parcours nœud + modèle cloud.

---

## §3 — Architecture (Architecte) — chaque décision justifiée

Nouveau module : `src/forgeai/web/`.

| Composant | Décision | Justification (1 phrase) |
|---|---|---|
| `server.py` | `ThreadingHTTPServer` + `BaseHTTPRequestHandler` + routeur | l'auto-suffisance interdit un framework ; `http.server` est présent sur tout Python 3.11. |
| `api.py` | endpoints JSON, chacun **adaptateur mince** sur une fonction existante | réutiliser le moteur prouvé ; la couche web n'ajoute aucune logique métier. |
| `assets/` | `index.html` + `app.css` + `app.js` (vanilla) servis depuis les données du paquet, polices/icônes inlinées | hors-ligne / air-gap : aucune CDN, aucun build, aucun fetch réseau. |
| bind | `127.0.0.1` par défaut, port configurable, ouverture navigateur | souverain et sûr par défaut ; pas d'exposition LAN sans action explicite. |
| i18n | réutilise `forgeai/i18n` (dictionnaires FR/EN embarqués côté JS) | source unique de vérité des traductions (ID-5). |
| déploiement | **extraire** le cœur réutilisable de `wizard_ci` en `run_deploy(config, emit)` appelable | CLI et web partagent **un seul** moteur de déploiement, zéro duplication. |
| secrets | mot de passe/clé postés sur localhost, gardés **en mémoire**, consommés au bootstrap, jamais écrits (réutilise B-05/B-09) | invariant T3 + hygiène des secrets. |
| progression | **Server-Sent Events** (stdlib : `text/event-stream` en chunked) | progression live sans websockets ni dépendance. |

### Design system (ID-4 : « design system avant le code »)
- **Tokens** : palette (sombre/clair via CSS custom properties + `prefers-color-scheme`), échelle d'espacement, échelle typographique (**pile de polices système**, aucune police web), rayons, élévations.
- **Composants** : coquille de page (en-tête : bascule langue + thème, stepper), cartes (profil / template / modèle / nœud), contrôles de formulaire, table de résumé, panneau progression/log, badges de preuve/verdict.
- **Accessibilité** : navigation clavier, états de focus visibles, ARIA, contraste AA.
- **Critère esthétique** : hérite de « le terminal peut être beau » → **« l'interface web est soignée »** est un critère d'acceptation (B-02f).

---

## §4 — Contrat API v1 (localhost, JSON)

- `GET /api/detect` → rapport matériel (`HardwareDetector.full_report()`).
- `GET /api/doctor` → backends disponibles / préflight.
- `GET /api/profiles` → profils + reco. `GET /api/templates` → templates (filtrés matériel, reco flaggée).
- `GET /api/catalogue?category=…` → briques.
- `GET /api/models` (liste, jamais les clés) · `POST /api/models` (add-cloud / add-local / test — test de connexion **réel** obligatoire).
- `GET /api/ides` · `POST /api/ide/configure`.
- `GET /api/nodes/status` · `POST /api/nodes` (add : IP/user/mot de passe → clé) · `POST /api/nodes/probe`.
- `POST /api/plan/preview` → plan résolu (services, ports, disque, durée).
- `POST /api/deploy` → démarre un job · `GET /api/deploy/stream` (SSE) → progression + preuve · `GET /api/deploy/report`.
- `POST /api/export` · `POST /api/import`.

Localhost uniquement, sans auth en v1 (mono-utilisateur local ; l'auth est roadmap — le bind localhost **est** la frontière v1).

---

## §5 — Sous-stories (PO) — critères testables

Chacune : assez petite pour un contexte propre ; passe le pipeline (codeur → TDD → gates → **revue aveugle scellée 3 vendors** → merge). Tiers indicatifs (params réels : `tier_params.py`).

### B-02a — Socle serveur web + `/api/detect` + accueil · Tier T1
- **Livrable** : `forgeai/web/server.py` + `api.py` + assets minimaux ; commande `forgeai web [--host 127.0.0.1] [--port N] [--no-browser]`.
- **Critères** :
  - `GET /api/detect` → 200 + JSON matériel valide (réutilise `HardwareDetector`) ; `GET /` → 200 + coquille d'app (bascule langue, résumé matériel).
  - **Auto-suffisance** : les assets ne référencent **aucun** hôte non-localhost (test statique : zéro `http(s)://` externe, zéro `//cdn`, zéro `@import url(http`).
  - route inconnue → 404 ; assets → 200.
- **Test** : serveur démarré sur port éphémère dans un thread ; assertions HTTP réelles ci-dessus.

### B-02b — Page Profil & Template · Tier T1
- **Critères** : `GET /api/profiles` + `GET /api/templates` renvoient les profils et **les 4 templates réels** avec nombre de briques ; **filtrage matériel** (les templates GPU-only exclus sans GPU) ; reco flaggée ; la page rend les cartes et pré-sélectionne la reco.
- **Test** : `api/templates` liste dev-agentic(37)/rag/lab/prod ; fixture sans GPU exclut les templates GPU-only ; la page servie contient les cartes de template.

### B-02c — Page Modèles & IDE · Tier T2 (surface secrets)
- **Critères** : `GET /api/models` (jamais les clés) ; `POST /api/models` add-cloud/add-local/test avec **test de connexion réel** ; `GET /api/ides` + `POST /api/ide/configure` (réutilise B-17/18). **Clé API jamais persistée en clair** (référence d'environnement + empreinte).
- **Test** : liste OK ; add-cloud avec route factice passe par le test de connexion (mocké) ; la clé **n'apparaît dans aucun fichier ni registre**.

### B-02d — Pages Multi-nœuds · Tier T2 (secrets)
- **Critères** : `GET /api/nodes/status` ; `POST /api/nodes` (IP/user/mot de passe → ed25519, éphémère) ; `POST /api/nodes/probe` (réutilise B-05/06/07). Mot de passe **en mémoire seulement** ; la réponse renvoie l'**empreinte de clé**, jamais le mot de passe.
- **Test** : après un add, **ni le registre ni aucun fichier** ne contiennent le mot de passe — seulement empreinte + référence d'environnement ; `probe` renvoie le matériel du nœud (SSH mocké).

### B-02e — Résumé pré-déploiement + Déploiement + Preuve · Tier T2
- **Critères** : `POST /api/plan/preview` → services/ports/disque/durée (réutilise `assemble_plan`) ; page résumé **modifiable** + **friction FORCER** explicite. Extraire `run_deploy(config, emit)` de `wizard_ci` ; `POST /api/deploy` démarre le job ; SSE émet les étapes ; **preuve finale** (santé + smoke RAG). Chemin d'échec → événement **BLOCKED avec raison**.
- **Test** (équivalent HTTP du parcours headless attendu) : `plan/preview` renvoie ports/services réels pour un profil ; un déploiement en backend **dry-run** émet des événements d'étape **ordonnés** + un événement terminal de preuve ; le chemin d'échec émet BLOCKED.

### B-02f — Design system, i18n in-place, thème, accessibilité · Tier T1
- **Critères** : tokens CSS ; sombre/clair via `prefers-color-scheme` + bascule ; **FR/EN in-place sans rechargement** ; navigation clavier ; ARIA ; contraste AA.
- **Test** : bascule langue met à jour les libellés sans reload (preview eval) ; la bascule thème pose `data-theme` ; les éléments clés portent rôles/labels ARIA ; **couverture i18n** : chaque clé utilisée existe en FR **et** EN.

### Ordre & dépendances
`B-02a` → (`B-02b`, `B-02c`, `B-02d` parallélisables) → `B-02e` → `B-02f`.

L'extra `[tui]` du pyproject est **caduc** (pas de dépendance runtime ajoutée — stdlib). Aucun nouvel extra requis.

---

## §6 — Stratégie de preuve

- **Endpoints backend** : tests unitaires — serveur démarré dans un thread sur port éphémère, assertions HTTP réelles (statut, schéma JSON, absence de secret).
- **Rendu frontend** : outils Claude Preview — `.claude/launch.json` lance `forgeai web` ; `preview_snapshot` / `preview_inspect` vérifient le DOM/rendu réels (présence des cartes, `data-theme`, libellés FR/EN, rôles ARIA).
- **Preuve de déploiement headless** : backend **dry-run** émettant de **vrais** événements d'étape ordonnés + preuve terminale (équivalent HTTP du test Textual Pilot initialement prévu pour le TUI).
- **Auto-suffisance** : test statique sur les assets (zéro référence réseau externe) + vérification que le serveur répond sans accès réseau.

---

## §7 — Hors périmètre v1 (extensions signalées)

Édition avancée du catalogue dans l'UI · tableaux de bord post-déploiement temps-réel · multi-utilisateur / authentification / exposition réseau · thèmes personnalisés · i18n au-delà de FR/EN · packaging desktop (Tauri/Electron). Chacune = extension future, **hors** ID-4 v1.

---

## §8 — Invariants respectés

- **Souveraineté / hors-ligne** : stdlib pure, assets embarqués, zéro fetch réseau, bind localhost (§0).
- **Secrets** : mot de passe/clé en mémoire uniquement ; disque/argv/registre ne portent qu'empreinte + référence d'environnement (§5 B-02c/d, CS-4).
- **T3 = Nathan** : l'UI ne déclenche aucun paiement / publication / secret prod / suppression / engagement externe.
- **Pipeline PROOF** : chaque sous-story branchée, codée par difficulté, TDD, gates, **revue aveugle scellée 3 vendors ≠ codeur**, merge `--no-ff`. Preuve avant DONE.
- **Docs = gate** : ce document est l'artefact BMAD versionné **avant la première sous-story** (proof-bmad).
