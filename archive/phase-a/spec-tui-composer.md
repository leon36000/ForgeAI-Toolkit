<!-- Livrable Phase A — §1 plan maître
membre: composer (Composer-2.5 via forge-model-bridge, provider_id=composer)
date: 2026-07-14 | statut: DONE | claim: UNVERIFIED (revue aveugle à venir au plan-freeze)
-->
# ForgeAI Toolkit — Spécification TUI Wizard (Phase A)

### 1. Inventaire des écrans

| ID     | Nom                        | Objectif                                      | Éléments clés                              | Actions possibles                     | Transitions                  |
|--------|----------------------------|-----------------------------------------------|--------------------------------------------|---------------------------------------|------------------------------|
| SCR-01 | Accueil & Langue           | Choisir la langue et démarrer                 | Header, sélecteur FR/EN, bouton Continuer  | Sélection langue, Entrée              | → SCR-02                     |
| SCR-02 | Détection Hardware         | Lancer et suivre la détection                 | Barre de progression, logs condensés       | Annuler                               | → SCR-03 ou SCR-ERR-01       |
| SCR-03 | Résultats Hardware         | Afficher ce qui a été détecté                 | Tableau hardware, résumé, bouton Suivant   | Re-détecter, Suivant                  | → SCR-04                     |
| SCR-04 | Choix du Profil            | Sélectionner le niveau de déploiement         | Cartes de profil (Minimal/Standard/Avancé) | Sélection + Entrée                    | → SCR-05                     |
| SCR-05 | Catalogue Briques          | Sélectionner les composants                   | Filtre, tableau briques, sélection multiple| Filtrer, toggler, Suivant             | → SCR-06                     |
| SCR-06 | Validation & Compatibilité | Vérifier la cohérence                         | Liste sélectionnée, alertes incompatibilités| Retour, Forcer, Continuer             | → SCR-07                     |
| SCR-07 | Choix du Backend           | Choisir le mode de déploiement                | Radio Docker Compose / K3s                 | Sélection, Suivant                    | → SCR-08                     |
| SCR-08 | Preview Artefacts          | Visualiser ce qui va être généré              | Arborescence + extraits, boutons Générer   | Retour, Générer                       | → SCR-09                     |
| SCR-09 | Déploiement                | Exécuter le déploiement                       | Progression par étape + logs               | Annuler                               | → SCR-10 ou SCR-ERR-03       |
| SCR-10 | Validation E2E             | Confirmer que le système fonctionne           | Checklist, boutons de test, résumé         | Lancer tests, Terminer                | Fin ou SCR-ERR-04            |

### 2. Flux d'interaction principal (Happy Path Minimal)

1. **SCR-01** → Sélection FR → Entrée
2. **SCR-02** → Détection automatique (5-8s)
3. **SCR-03** → Affichage :
   - CPU : 8c/16t (Intel i7-13700)
   - RAM : 32 Go (31,2 Go disponibles)
   - GPU : NVIDIA RTX 3060 12 Go (CUDA 12.4)
   - Stockage : 480 Go NVMe (320 Go libres)
   - Réseau : 1 Gbps
4. **SCR-04** → Sélection **Minimal** (profil recommandé)
5. **SCR-05** → Briques pré-sélectionnées (non modifiables en Minimal) :
   - `ollama/llama3.1:8b`
   - `forgeai/embedding-minilm`
   - `forgeai/vllm-proxy`
6. **SCR-06** → Vérification OK
7. **SCR-07** → Sélection **Docker Compose**
8. **SCR-08** → Génération des fichiers
9. **SCR-09** → Déploiement (4 étapes : images, volumes, services, healthchecks)
10. **SCR-10** → Tests E2E (3 checks) → "Système opérationnel"

### 3. Wireframes ASCII (4 écrans critiques)

**SCR-01 — Accueil & Langue**
```
┌─ ForgeAI Toolkit ──────────────────────────────────────────────┐
│  Déployeur d'infrastructures IA agentiques                    │
│                                                                 │
│  Sélection de la langue                                         │
│  ┌─────────────────────┐  ┌─────────────────────┐             │
│  │  Français (FR)      │  │  English (EN)       │             │
│  │  ●                  │  │                     │             │
│  └─────────────────────┘  └─────────────────────┘             │
│                                                                 │
│  [ Continuer ]                                           [Quit]│
└─────────────────────────────────────────────────────────────────┘
```

**SCR-03 — Résultats Détection**
```
┌─ Résultats de la détection hardware ───────────────────────────┐
│  Détecté il y a 12 secondes                                     │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │ Composant      │ Valeur                    │ Statut       │ │
│  ├────────────────┼───────────────────────────┼──────────────┤ │
│  │ CPU            │ Intel Core i7-13700 (16c) │ OK           │ │
│  │ RAM            │ 31.2 / 32 Go              │ OK           │ │
│  │ GPU            │ NVIDIA RTX 3060 12 Go     │ OK (CUDA)    │ │
│  │ Stockage       │ 312 Go / 480 Go (NVMe)    │ OK           │ │
│  │ Réseau         │ 1000 Mbps                 │ OK           │ │
│  └───────────────────────────────────────────────────────────┘ │
│                                                                 │
│  Profil recommandé : Minimal                                    │
│  [ Re-détecter ]  [ Continuer ]                          [Quit]│
└─────────────────────────────────────────────────────────────────┘
```

**SCR-05 — Sélection Briques (Minimal)**
```
┌─ Sélection des briques (Profil: Minimal) ──────────────────────┐
│  3/3 briques requises • 0 optionnelle                           │
│                                                                 │
│  ┌────────────────────────────────────────────────────────────┐│
│  │ ✓ ollama/llama3.1:8b          │ 8.5 Go  │ Requis          ││
│  │ ✓ forgeai/embedding-minilm    │ 90 Mo   │ Requis          ││
│  │ ✓ forgeai/vllm-proxy          │ 120 Mo  │ Requis          ││
│  └────────────────────────────────────────────────────────────┘│
│                                                                 │
│  Filtre: [                    ]  Catégorie: [Toutes]            │
│  [ Retour ]                              [ Valider la sélection]│
└─────────────────────────────────────────────────────────────────┘
```

**SCR-09 — Déploiement + Preuve**
```
┌─ Déploiement en cours ─────────────────────────────────────────┐
│  Backend: docker-compose                                        │
│                                                                 │
│  ┌─ Progression ─────────────────────────────────────────────┐ │
│  │ [████████░░░░░░░░░░░░] 42%                                 │ │
│  │ Étape 4/7 : Healthchecks des services                      │ │
│  └───────────────────────────────────────────────────────────┘ │
│                                                                 │
│  Logs:                                                          │
│  • ollama-llama3.1:8b          [ OK ]  1m42s                    │
│  • embedding-minilm            [ OK ]  1m38s                    │
│  • vllm-proxy                  [ RUN ]                          │
│                                                                 │
│  [ Annuler ]                                                    │
└─────────────────────────────────────────────────────────────────┘
```

### 4. États d'erreur et de blocage

- **SCR-ERR-01** (Détection échouée) : Message clair + raison technique (ex: "Impossible de lire les informations GPU : driver NVIDIA non détecté"). Boutons : *Recommencer* / *Continuer sans GPU* / *Quitter*.
- **SCR-ERR-02** (Incompatibilité) : Dans SCR-06, ligne rouge avec icône `⚠`. La brique est grisée. Impossible de continuer tant qu'une incompatibilité bloquante existe (sauf action explicite "Forcer").
- **SCR-ERR-03** (Déploiement échoué) : Arrêt immédiat. Affichage de l'étape + message d'erreur + log tronqué. Boutons : *Voir logs complets*, *Réessayer*, *Générer les artefacts sans déployer*.
- **Règle stricte** : Aucun état "succès partiel" trompeur. L'écran SCR-10 n'est accessible que si tous les healthchecks passent.

### 5. Conventions

- **Navigation** : Tab / Shift+Tab, Flèches, Entrée, Echap = Retour, `q` = Quitter (confirmation).
- **i18n** : Sélection au démarrage (SCR-01). Le choix est conservé en mémoire pour la session. Tous les labels sont externalisés. Bascule possible via `Ctrl+L` (retour à SCR-01).
- **Thème** : Fond sombre (#1e1e2e), texte principal `#cdd6f4`, accents `#89b4fa`, erreur `#f38ba8`, succès `#a6e3a1`. Utilisation de `Textual` `Theme` + CSS.
- **Accessibilité** : Tous les widgets ont un `id` et `aria_label`. Focus visible (bordure). Pas de dépendance à la couleur seule. Messages d'erreur toujours textuels.
- **Contraintes Textual** : Utilisation de `DataTable`, `Select`, `ProgressBar`, `Log`, `Tree`, `Button`, `RadioSet`. Aucun écran ne dépasse 3-4 conteneurs verticaux principaux.
