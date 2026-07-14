# Directives périmètre & rigueur — prompt maître Nathan, 14 juillet 2026

**Statut : CANON.** Complète `CANON/plan-integral.md`. Toute modification passe le circuit
de gouvernance (revue 3 modèles / 3 vendors + signature).

## 1. Confinement au workspace (Mission 1)
- **Interdiction absolue** de lire, référencer ou utiliser tout fichier hors du repo
  ForgeAI-Toolkit. La machine de l'auteur n'est **pas** une source du produit.
- Sources autorisées pour tout travail de contenu : **le web public (focus GitHub)** et
  les pièces jointes explicitement fournies par Nathan puis **versionnées au repo**
  (ex. `CANON/ANNEXE-ATLAS-SECTION4-BRIQUES-20260712.pdf`).
- Enforcement : story B-24 (hook bloquant l'accès filesystem hors workspace).
- **Le pourquoi** : ce Toolkit existe pour que son auteur puisse formater sa machine et
  tout redéployer avec l'outil — et épargner aux autres des mois de recherche. **Si le
  produit dépend d'un fichier qui n'est pas dans son repo/catalogue, il est cassé par
  définition.**

## 2. Règle R-ALL — recherche vérifiée sur l'intégralité du catalogue (Mission 3)
Née de quatre erreurs de classification évitées de justesse (retrait par correspondance
de nom annulé avant commit — registre `directive_perimetre`).
- **Aucune affirmation sur une brique sans preuve sourcée.** Rien n'est retiré, reclassé,
  décrit ou câblé par correspondance de nom, supposition ou mémoire de modèle.
- Chaque entrée du catalogue passe par un **dossier de recherche vérifié** : repo/source
  officielle confirmée (URL testée), licence, maintenance, popularité, méthode d'install
  officielle + version épinglable, description réelle FR/EN, rôle + points de branchement,
  flag `PUBLIC-INSTALLABLE` / `INTROUVABLE-APRÈS-RECHERCHE`. Champs `verified_at` +
  méthode; sha256 régénéré. Pipeline : fan-out par lots + contre-vérification croisée
  3 modèles (même circuit éprouvé que les 742 traductions).
- **Retrait** : uniquement `INTROUVABLE-APRÈS-RECHERCHE`, dossier à l'appui au registre.
  Exception unique (source directe Nathan, journalisée) : Forge Command Center et
  Control Center (toutes variantes) — bespoke confirmés, retirés.
- **Collision de noms** : toute entrée dont le nom existe chez plusieurs projets porte
  son qualificatif org/repo dans le nom affiché + un champ `disambiguation`. Gate
  catalogue : échec si deux entrées partagent un nom sans qualificatif (story B-26).

## 3. Règle de rigueur transversale (permanente)
**Toute affirmation factuelle dans un livrable, un dossier ou un rapport cite sa source
vérifiable. Une affirmation sans preuve est traitée comme un stub — bloquée par le même
gate.**

## 4. Phases du wizard (rappel de vision consolidé)
0 Détection matérielle → 1 Profil (Minimal/Standard/Complet/Personnalisé) → 2 Template
domaine → 2b Nœuds multi-machines (IP+user+mdp/clé, ed25519, Tailscale) → 3 Stratégie
modèle (Cerveau unique/Équipe/Hybride) → 4 Runtimes & moteurs (filtrés hardware) →
5 Modèles locaux (filtrés VRAM/backend) et cloud (nom + provenance + clé API + test réel)
→ **6 Phases par catégorie de briques** (Mémoire & RAG · Orchestration & agents · MCP &
outils · Guardrails & sécurité · Observabilité & éval · Harness & méthodologies — défaut ⭐
pré-sélectionné + alternatives, tout modulable) → 7 IDE/CLI livré branché (MCP + skills +
BMAD/prompt manager + hooks) → 8 Aperçu → Déploiement → Branchement auto via gateway
unique → 9 Vérification e2e réelle + rapport au registre.
