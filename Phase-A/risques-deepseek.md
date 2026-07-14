<!-- Livrable Phase A — §1 plan maître
membre: deepseek (DeepSeek-V4-Pro via forge-model-bridge, provider_id=deepseek)
date: 2026-07-14 | statut: DONE | claim: UNVERIFIED (revue aveugle à venir au plan-freeze)
-->
# REGISTRE DES RISQUES – FORGEAI TOOLKIT (PHASE A)

## 1. REGISTRE DES RISQUES

| ID | Catégorie | Description | Prob. | Impact | Mitigation | Signal précoce |
|---|---|---|---|---|---|---|
| R-01 | Technique | Détection multi-vendor échoue sur matériel non-standard (ARM SBC, GPU hétéroclites) → profil Minimal déployé sur stack incompatible | H | H | Ajouter fallback générique « détection forcée » + tests croisés sur 3 vendors/5 boards | Rapport de détection vide ou warnings > 30% capteurs |
| R-02 | Processus | Orchestration 9 LLM dans Claude Code produit des boucles de régression croisée (LLM A corrige LLM B qui corrige A) sans sortie | M | H | Timer hard limit par étape + gate de cohérence logique (vérification delta entre itérations) | Messages identiques répétés > 3 cycles |
| R-03 | Sécurité | Bootstrap SSH ed25519 sur multi-nœuds Tailscale propage une clé compromise stockée en clair dans un registre | H | H | Chiffrement des clés via vault intégré + rotation automatique post-déploiement | Clé non chiffrée détectée dans log de registre |
| R-04 | Coût | Revue aveugle 3/3 vendors avec 3 reviewers/vendor → 9 threads parallèles, licence Claude Code facture exponentielle | M | M | Budget fixe par phase + alerte à 80% consommation + bascule partielle sur API moins chère | Dépassement > 15% budget estimé en 2 jours |
| R-05 | Technique | Rendus Docker Compose et K3s divergent (différences réseaux, volumes) → déploiement cassé sur un backend | M | H | Tests d'intégration croisée : déployer même configuration sur les deux backends et comparer | Test d'intégration échoue pour < 80% des services |
| R-06 | Processus | Consensus 7/9 bloqué : 3 reviewers refusent systématiquement pour des raisons stylistiques (langue, syntaxe) | H | M | Règles de notation objectives (checklist pondérée) + arbitre tournant si blocage > 2 rounds | Taux d'approbation < 30% après 3 rounds |
| R-07 | Sécurité | Gates CI déterministes bloquantes : une gate mal configurée (regex trop large, timeout trop court) bloque TOUTE livraison | M | H | Gates redondantes non-bloquantes en parallèle + bypass manuel validé par T3 humain | Accumulation de 5+ gates en rouge sans explication claire |
| R-08 | Technique | Registres hash-chaînés fragiles : corruption silencieuse d'un bloc (erreur mémoire, I/O) → chaîne entière invalidée | B | H | Checksum CRC32+SHA256 double + réplication sur 2 nœuds physiques distincts | Divergence de hash entre deux réplicas |
| R-09 | Coût | T3 humain pour 3 opérations (paiements/secrets/suppressions) crée un goulot d'étranglement : temps d'attente > 48h | M | M | Équipe de secours T3 + escalade automatique après 12h + procédure dégradée (logs d'audit seuls) | File d'attente T3 > 5 tickets non traités |
| R-10 | Processus | Catalogue 340+ briques bilingue FR/EN : incohérence de traduction (terme technique différent entre langues) → erreur de sélection | H | M | Glossaire technique commun + revue croisée par locuteur natif chaque langue | Occurrences de traductions contradictoires > 3 par version |
| R-11 | Technique | Wizard TUI détecte du matériel mais ne gère pas les mises à jour dynamiques (branchement à chaud GPU) → profil figé | B | M | Hook de re-détection déclenché par udev (Linux) ou événement système | Événement matériel non capturé dans log TUI |
| R-12 | Sécurité | Gates « no-stub » peuvent être contournées via un stub fonctionnel mais malveillant (code obfusqué) | M | H | Analyse statique + heuristique de détection d'obfuscation + limite de taille de stub | Stub avec entropie anormale (Shannon > 7.5) |
| R-13 | Processus | Tests TDD sans couverture des chemins d'erreur matériels (panne disque, réseau instable) → faux positifs tests unitaires | H | M | Tests d'injection de fautes (disque full, perte paquets) + profils de charge | Aucun test d'erreur I/O dans suite TDD |
| R-14 | Coût | Phase P1 (machine nue → RAG fonctionnel) sous-estime le temps de réglage du RAG : 340 briques à indexer + embedding | H | H | Benchmark de performance RAG dès J1 + réduction du périmètre à 50 briques P1 si dérive > 30% | Temps d'indexation > 200% estimation initiale |
| R-15 | Technique | Multi-nœuds Tailscale : latence inter-nœuds non testée → RAG fonctionnel mais trop lent pour usage réel | M | M | Seuil de latence max (500ms) + bascule locale si dépassé | Temps de réponse RAG > 2s pour requête simple |
| R-16 | Sécurité | Registre hash-chaîné accessible en lecture à tous les nœuds Tailscale → fuite de métadonnées de déploiement | M | H | ACL réseau : registre accessible uniquement depuis nœud contrôleur + tunnel chiffré dédié | Tentative de connexion au registre depuis nœud non autorisé |
| R-17 | Processus | Revue aveugle 3/3 vendors : conflit d'intérêt si deux reviewers du même vendor évaluent le même artefact | M | M | Vérification d'unicité vendor par artefact + rotation garantie | Même vendor assigné à 2+ reviewers sur même ticket |
| R-18 | Technique | BMAD non testé avec 9 LLM simultanés → deadlock ou consommation mémoire excessive | H | H | Simulation de charge avec agents factices + limite mémoire par processus (256MB) | Utilisation mémoire > 80% avant fin de phase |
| R-19 | Coût | Licences tierces (Claude Code, API LLM, stockage registre) peuvent subir inflation de prix en cours de phase | B | M | Contrats à prix fixe pour 6 mois + fonds de réserve 20% du budget total | Avis de modification de prix fournisseur |
| R-20 | Technique | Wizard TUI en mode texte : affichage incorrect sur terminaux non-standards (tmux, Windows Terminal) → utilisateur aveugle | M | M | Tests sur 5 émulateurs + mode fallback ASCII pur | Rapport utilisateur d'affichage déformé |

## 2. REVUE CRITIQUE DU PLAN

**Faiblesse 1 – Dérive multi-agents non contenue** : L'orchestration de 9 LLM dans Claude Code sans mécanisme de convergence explicite (vote pondéré, fusion de résultats) génèrera du bruit. Deux réponses correctes mais contradictoires peuvent bloquer le consensus indéfiniment. Le timer hard limit (R-02) est une bouée, pas une solution.

**Faiblesse 2 – Gates déterministes aveugles** : Les gates CI sont dites « bloquantes » mais aucune mention de règles de priorisation. Une gate sur un test cosmétique (style de commentaire) peut bloquer une gate de sécurité critique. Sans hiérarchie, le pipeline est fragile.

**Faiblesse 3 – Consensus aveugle sans métriques de divergence** : « 7/9 » ne mesure pas l'accord sémantique. Trois reviewers peuvent voter « oui » pour des raisons opposées (un valide la sémantique, un autre le style). Le score brut masque des désaccords réels.

**Faiblesse 4 – Coût exponentiel masqué par absence de budget unitaire** : Chaque round de revue (9 threads × 3 rounds) coûte > 0,10$ en API calls. Si la phase P1 nécessite 200 itérations (typique), le coût atteint 2000$ sans garde-fou. Aucune limite par itération n'est spécifiée.

**Faiblesse 5 – Dépendance Tailscale non-sécable** : Aucun plan de repli si Tailscale est indisponible (panne DNS, limitation de débit). L'ensemble du déploiement multi-nœuds devient inaccessible. Le plan devrait inclure un mode dégradé local (single node sans orchestration).

**Faiblesse 6 – BMAD sans modèle de charge** : 9 LLM simultanés sur un même contexte peuvent saturer la mémoire du conteneur Claude Code. Aucune métrique de scaling vertical/horizontal n'est prévue. En dessous de 8GB RAM, le système peut planter.

**Faiblesse 7 – Registres hash-chaînés : performance non testée** : L'ajout de hash-chaînes (double checksum + réplication) sur chaque action ralentit le pipeline. Pour 340 briques × 100 actions, le temps d'écriture peut dépasser 10 minutes. Aucun benchmark de latence n'est documenté.

## 3. TOP 3 RISQUES TUEURS DE MISSION

**R-01 prioritaire : Échec de détection hardware → profil inadapté → RAG non fonctionnel**
- *Contingence* : Dans les 24h suivant échec de détection, activer le mode « détection forcée » : questionnaire manuel utilisateur (8 questions max) pour définir profil. Si toujours échec, déployer profil minimal standard (CPU only, 4GB RAM, pas de GPU). Délai max : 48h.

**R-05 prioritaire : Divergence Docker Compose / K3s → déploiement cassé**
- *Contingence* : Maintenir un shell de compatibilité qui transforme automatiquement les configurations Docker Compose en K3s (ou vice-versa) via un adaptateur YAML. Tester cette transformation en continu. Si divergence détectée, basculer exclusivement sur le backend fonctionnel le temps de corriger l'adaptateur.

**R-14 prioritaire : Sous-estimation du temps RAG → P1 non livrée dans les temps**
- *Contingence* : Dès J3, mesurer le temps d'indexation réel des 340 briques. Si > 200% de l'estimation, réduire le périmètre P1 à 50 briques prioritaires (critères : pertinence doc, fréquence usage). Livrer la version réduite dans les délais, puis compléter en P2. Communiquer transparentement sur le rétrécissement.

**Conclusion** : Le plan est solide mais repose sur des hypothèses de performance (détection, orchestration, indexation) non testées. Les gates CI et le consensus gagneraient à être enrichis de métriques qualitatives (cohérence, sémantique) pour éviter le blocage. Le coût réel pourrait être 3-5× le budget si les itérations multi-agents s'emballent.
