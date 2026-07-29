# RES-012B — Ressources rendues depuis le ServiceSpec (FAI-U-012)

## Cause racine
`_resources_block` codait `100m/128Mi → 1 CPU/1Gi` pour **tout** service, et `ServiceSpec` n'avait
aucun champ de ressources : le renderer ne pouvait rien lire d'autre que ses littéraux. Un runtime
d'inférence était plafonné comme un job d'init — **litellm en mourait**, OOMKill documenté et
contre-prouvé lors de K8S-022.

## Changement — le schéma décidé par l'ADR RES-012A
| Élément | Emplacement |
|---|---|
| Table des 4 classes (`llm`, `db`, `sidecar`, `utilitaire`), deux à deux distinctes | `core/models.py` |
| Validation unités + cohérence `limits ≥ requests`, 6 codes `ERR_RES_*` stables | `core/models.py`, `__post_init__` — fail-fast |
| Résolution `resources` > `resource_class` > défaut `utilitaire` | `_resoudre_ressources` |
| Lecture des valeurs résolues, **zéro magic number** | `renderers/k3s.py` |
| Classe déclarée par brique | `data/deploy-specs.json` (12 briques) |

Le renderer **ne valide rien** : la validation est unique et vit dans le modèle, donc elle couvre
tous les renderers présents et futurs. Un test structurel échoue si un littéral de ressource
réapparaît dans `k3s.py`.

## Le conflit ADR ↔ mesure, et comment il est tranché
L'ADR classe `litellm` en `sidecar` → `limits.memory: 512Mi`. Or **la mesure sur cluster réel donne
~1018 Mi au repos** (image épinglée, limite d'observation portée à 4Gi ; cf.
`reviews/RES-012B/evidence/mesure-litellm.txt`). La limite historique de 1Gi = 1024 Mi plaçait le
conteneur **exactement à sa limite** — l'OOMKill est entièrement expliqué. Appliquer la classe
`sidecar` telle quelle l'aurait tué **deux fois plus vite**.

Les ADR sont immuables : RES-012A n'est pas réécrit. Mais l'ADR §3.1 prévoit exactement ce cas —
« la dérogation couvre l'exception sans toucher à l'enum ». `litellm` reçoit donc une dérogation
**dérivée de la mesure** : `requests.memory: 1Gi` (garantir moins ferait placer le pod sur un nœud
incapable de le tenir), `limits.memory: 2Gi` (≈2× l'empreinte au repos : marge de trafic sans
sur-souscription), `cpu: 100m → 1000m` (empreinte CPU mesurée à 1m au repos).

## Régression introduite puis corrigée
La réécriture testait `svc.gpu_vendor == "nvidia"`, perdant le **défaut NVIDIA** d'un service
`gpu=True` sans vendor explicite — défaut que portait le paramètre `vendor` calculé en amont
(`(svc.gpu_vendor or "nvidia") if svc.gpu else None`). Un test préexistant l'a attrapée ; le
paramètre est restauré et son rôle commenté.

## Élargissements de périmètre — DÉCLARÉS
`core/models.py` et `data/deploy-specs.json` sont **hors `allowed_paths`** mais **prescrits par
l'ADR RES-012A** (§3.2, §5.3, §6), déjà approuvé 3/3 et mergé. Sans eux, le critère « rendre
requests/limits depuis ServiceSpec » est inatteignable. Ni l'un ni l'autre n'est dans le périmètre
interdit. `tests/test_k3s_hardening_fai0004.py` assertait les magic numbers que ce package
supprime : intention préservée, assertions recentrées sur les valeurs de classe.

## Rollback
`git revert` → retour aux littéraux (défaut FAI-U-012 connu, litellm OOMKillé) ; baseline verte.
