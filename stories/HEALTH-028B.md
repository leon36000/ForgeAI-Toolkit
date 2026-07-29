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

## REJECT 3/3 au tour 1 — cinq défauts, tous réels
Les trois vendors ont convergé sur un défaut que mes 9 tests ne pouvaient pas voir :
**`evaluer_service` et `agreger_verdicts` étaient définies, testées… et jamais appelées par
`wait_healthy`**, qui reconstruisait sa logique à la main. La règle anti-vacuité que ce package
existe pour instaurer **ne protégeait donc rien en production**.

C'est exactement le piège consigné le matin même après RAG-005 — *tester une fonction que le chemin
de production n'emprunte pas*. Reproduit six heures plus tard. La mémoire ne suffit pas : seul un
test traversant le vrai point d'entrée protège. J'en ai écrit un explicite, qui vérifie que
`wait_healthy` **appelle** `agreger_verdicts`, pas qu'elle existe.

| défaut | source | gravité |
|---|---|---|
| `wait_healthy` n'appelle ni `evaluer_service` ni `agreger_verdicts` | 3 vendors | la garde ne protégeait rien |
| `ProbeType.NONE` accepté comme sonde valide (`is not None` = vrai) | DeepSeek, Gemini, Tencent | contrat violé sans détection |
| service `EXEC` requis **absent des verdicts** | Gemini, Tencent | déploiement prêt **en l'ignorant** |
| guillemet dans un argument **corrompt le YAML** | Gemini | manifeste cassé par une config |
| services sondables sans `health_required` jamais évalués | **trouvé en corrigeant** | agrégat `UNKNOWN` malgré une preuve disponible |

## Un sixième point : ne pas casser ce que le produit consomme
Ma réécriture changeait le vocabulaire de sortie (`"healthy"` → `"functionally_ready"`). Or
**`cli.py` compare à `"healthy"` en dur** — et `cli.py` est hors périmètre. J'ai donc préservé le
contrat public via `_etiquette_publique`, en gardant `HealthState` en interne : c'est lui qui porte
la garde anti-vacuité, le vocabulaire public n'a jamais eu besoin de changer.

Point sémantique tranché au passage : pendant une **boucle d'attente**, une sonde qui échoue
signifie « pas encore », pas « échec ». Les violations de contrat étant rejetées AVANT la boucle,
tout `FAILED` restant est un « pas encore prouvé » → étiquette `waiting`, l'état interne exact
restant rendu dans le champ `détail`. Conforme à l'ADR, qui réserve `FAILED` à *« une preuve
d'échec ou un contrat violé »*.

## Tour 2 — une omission de ma part, relevée par Gemini
J'avais corrigé l'échappement dans `renderers/compose.py` (`json.dumps`) mais **pas dans
`renderers/k3s.py`**. Corriger un symptôme et laisser le jumeau intact.

**Mesuré avant de corriger** — le défaut est plus grave que signalé : ce ne sont pas seulement des
corruptions, ce sont des **altérations silencieuses**.

| argument | résultat sans échappement |
|---|---|
| `a: b` | devient un **dictionnaire** `{'a': 'b'}` |
| `[x]` | devient une **liste** `['x']` |
| ` #c` | devient **`None`** |
| `{a}` | devient `{'a': None}` |
| `*ref` | **corrompt le document** (ComposerError) |

Dans quatre cas sur cinq, **la sonde exécuterait autre chose que demandé, sans la moindre erreur**.
Une altération silencieuse est pire qu'un échec bruyant : le déploiement se déclare sain en
exécutant une commande qui n'a jamais été écrite. `json.dumps` sur les deux renderers ferme la
classe entière du problème.

## Tour 3 — un défaut BLOQUANT que j'aurais livré
**Objection critique de Gemini, reproduite** : tout plan contenant un service à sonde INTERNE
(`EXEC`/`TCP`, ou `HTTP` sans `healthcheck_url`) échouait **systématiquement par timeout**. Le
produit devenait inutilisable dès qu'un postgres ou un redis était présent — mesuré :

```
BLOQUÉ : Déploiement non READY (verdict=unknown) après 3.0s. États: {'postgres': 'waiting'}
```

Ma correction du tour 2 en était la cause : j'avais fait entrer les services sondables dans les
verdicts, mais un service à sonde interne reste éternellement `UNKNOWN` — donc jamais `READY`.

**Le contournement que je n'ai pas fait.** Exclure ces services du verdict aurait rendu les tests
verts immédiatement — en abandonnant la garantie : un postgres `health_required=True` serait passé
**sans aucune preuve**, précisément le défaut que ce package supprime.

**La preuve existait, ailleurs.** Docker exécute lui-même le `healthcheck` : `wait_healthy` la LIT
désormais (`docker compose ps`). C'est la seule preuve fonctionnelle disponible pour ces services,
et c'est exactement ce que le critère 1 demande — *« postgres/redis ne sont pas prêts sur simple
port ouvert si une probe fonctionnelle existe »*.

| état Docker | verdict |
|---|---|
| `healthy` | sonde réussie |
| `unhealthy` / `exited` / `dead` | sonde échouée, service nommé dans l'échec |
| `starting` / `unknown` | pas encore de preuve — on attend |

`_etats_docker` **ne lève jamais** : docker absent, JSON invalide, timeout → dictionnaire vide,
traité comme une absence d'information. Un diagnostic qui plante ne diagnostique rien.

**Deux autres objections du même tour**, toutes deux justes : le chemin HTTP n'était pas échappé
dans K3s (même classe que les arguments EXEC, sur un autre champ) ; et la validation rejetait
`--password ""`, un argv légitime — seul un **tuple** vide est un contrat absent.

## Rollback
`git revert` → retour à la faille de vacuité (défaut FAI-U-028 connu) ; baseline verte.
