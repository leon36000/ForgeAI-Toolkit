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

## Rollback
`git revert` → retour au rendu sans validation (défaut FAI-U-011 connu) ; baseline verte.
