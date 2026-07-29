# PLACE-011 — Placement validé contre l'inventaire réel avant rendu (FAI-U-011)

## Cause racine
Aucun inventaire n'était consulté au rendu. Un workload NVIDIA épinglé sur un nœud CPU-only
produisait un manifeste **syntaxiquement parfait**, envoyé à `kubectl`, qui échouait au scheduling :
le pod restait `Pending`, sans message causal. **L'utilisateur découvrait l'incompatibilité en
production.**

## Changement — un contrat d'inventaire et une validation en amont
| Élément | Rôle |
|---|---|
| `NodeInventaire(hostname, gpu_vendor, vram_mib)` | contrat minimal décrivant ce qu'un nœud peut réellement honorer |
| `PlacementError` | refus AVANT rendu, jamais un manifeste voué à l'échec |
| `valider_placement(svc, inventaire, node_demande)` | valide un nœud imposé, ou sélectionne le premier nœud qualifié en mode auto |
| `ServiceSpec.vram_min_mib` | VRAM minimale exigée, confrontée à l'inventaire |

Le renderer appelle la validation dans sa boucle de services. **Sans inventaire fourni, rien ne
change** : la validation est une capacité ajoutée, pas une rupture.

## Comportement prouvé (exécution réelle, `reviews/PLACE-011/evidence/COMPORTEMENT.txt`)
| demande | verdict |
|---|---|
| NVIDIA sur nœud CPU-only | `ERR_PLACE_CPU_ONLY` |
| AMD sur nœud NVIDIA | `ERR_PLACE_VENDOR_INCOMPATIBLE` — un GPU n'est pas un GPU générique |
| 12288 Mio exigés, nœud à 8192 | `ERR_PLACE_VRAM_INSUFFISANTE` — **les deux chiffres** dans le message |
| Intel, mode auto | `ERR_PLACE_AUCUN_NOEUD_QUALIFIE` — avec la raison de rejet de **chaque** nœud examiné |
| nœud absent de l'inventaire | `ERR_PLACE_NOEUD_INCONNU` — avec la liste des hostnames connus |
| AMD, mode auto | → `n-amd`, le seul qualifié |
| sans inventaire | → inchangé (rétro-compatibilité) |
| service CPU | → jamais contraint par le vendor d'un nœud |

Chaque message est **causal** : ce qui a été demandé, ce qui a été trouvé, pourquoi c'est
incompatible — lisible sans consulter l'inventaire.

## Piège de crew rencontré
Le modèle a rendu un contrat dont la **docstring d'ouverture n'était jamais fermée** (une seule
`"""` dans tout le fichier). Tout le code suivant devenait une chaîne, et l'erreur de syntaxe se
manifestait 90 lignes plus loin, dans une docstring saine de `ServiceSpec` — j'ai d'abord soupçonné
mon indentation à tort. Diagnostic par comptage (nombre impair de `"""`), réparation, et surtout :
un `ast.parse()` **avant écriture** a été ajouté à la procédure d'intégration, pour que du code
non compilable ne corrompe plus un fichier sain.

## Objections de la revue scellée — toutes traitées (tour 1 : APPROVE 3/3)
**Convergence à trois, sur le même point.** Gemini, Grok et DeepSeek ont relevé
INDÉPENDAMMENT que `NodeInventaire` levait `ERR_PLACE_VENDOR_INCONNU` pour un hostname vide et une
VRAM négative — deux cas étrangers au vendor. Ironie utile : ce package existe pour produire des
erreurs causales, et son propre contrat en portait une trompeuse. Trois codes distincts désormais :
`ERR_PLACE_HOSTNAME_INVALIDE`, `ERR_PLACE_VRAM_INVALIDE`, `ERR_PLACE_VENDOR_INCONNU`.

**DeepSeek** : un tuple vide passait pour une absence d'inventaire. `None` = « je ne sais pas » ;
`()` = « je sais, et il n'y a rien ». Le correctif du contrat ne suffisait pas — mon propre câblage
du renderer testait `if inventaire:` et court-circuitait la validation avant de l'appeler ; corrigé
en `is not None`. Sans le test rouge, je l'aurais manqué.

**Grok** : `ERR_PLACE_NOEUD_INCONNU` était démontré dans les preuves d'exécution mais aucun test ne
le couvrait. Le test ajouté passe du premier coup — la fonctionnalité était là, mais **un
comportement prouvé une fois n'est pas un comportement protégé**. Même famille d'erreur que le
test-sur-chemin-inventé de RAG-005, vue par l'autre bout : là un test sans comportement, ici un
comportement sans test.

## Rollback
`git revert` → retour au rendu sans validation (défaut FAI-U-011 connu) ; baseline verte.
