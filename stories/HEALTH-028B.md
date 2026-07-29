# HEALTH-028B — Contrat de santé mappé vers Compose et K3s (FAI-U-028)

## Cause racine — la faille de vacuité
```python
if all(v == "healthy" for v in status.values()):   # deploy/compose.py:65
```
`all()` sur une collection **vide** renvoie `True`. Un plan sans aucun service sondé était donc
déclaré healthy **immédiatement**, sans la moindre preuve. Pas « healthy par erreur » : healthy
**par construction**. L'ADR HEALTH-028A l'interdit comme règle centrale — *« un déploiement de zéro
service sondé est UNKNOWN, jamais READY »*.

Et les sept champs du contrat étaient absents de `ServiceSpec`.

## Changement
| Élément | Effet |
|---|---|
| `ProbeType`, `HealthState` | 4 états dont **`TRANSPORT_READY` qui n'est PAS prêt** |
| 7 champs sur `ServiceSpec` + validation (5 codes `ERR_HEALTH_*`) | fail-fast à la construction |
| `agreger_verdicts` | **collection vide → `UNKNOWN`**, jamais READY |
| `evaluer_service` | distingue transport joignable / applicatif prouvé |
| `wait_healthy` + `HealthContractError` | **refuse** un `health_required` sans contrat exploitable |
| `_healthcheck_lines` (Compose) | `test: ["CMD", …]` — **argv, jamais chaîne shell** (injection) |
| `_probes_block` (K3s) | startup / readiness / liveness aux **rôles distincts** |

`startupProbe.failureThreshold` = 12 contre 3 pour liveness : **un démarrage lent n'est pas une
panne**. Confondre les deux fait redémarrer en boucle un service parfaitement sain.

## DEUX RÉGRESSIONS que ma réécriture avait introduites
Détectées par la **suite complète**, via trois tests **hors de mon périmètre autorisé** :

1. **Tout service sans `healthcheck_url` perdait ses sondes.** Redis n'en avait plus aucune :
   Kubernetes ne pourrait plus détecter qu'il est bloqué, et ne le redémarrerait jamais.
2. **La logique openbao avait disparu.** Le coffre démarre **scellé** (`/v1/sys/health` → 503).
   L'ancien code distinguait une liveness **tolérante** (`sealedcode=200` : le processus vit même
   scellé) d'une readiness **stricte**. Sans elle, **openbao redémarre en boucle avant son unseal**
   — le coffre de secrets ne démarre jamais.

Réparées en restructurant la chaîne de décision en **trois handlers distincts** (au lieu d'un seul
partagé), ce qui permet à openbao d'avoir liveness ≠ readiness sans affecter les autres services.
Un commentaire explicite protège désormais chaque branche : *« ne pas supprimer par
simplification »* — parce que c'est exactement ce que j'ai fait sans le vouloir.

**Ces deux comportements n'existaient que dans des tests.** Aucune spec ne les mentionnait. Sans la
suite complète, je livrais un package empêchant le coffre de secrets de démarrer, avec 9 tests
ciblés verts.

## Rollback
`git revert` → retour à la faille de vacuité (défaut FAI-U-028 connu) ; baseline verte.
