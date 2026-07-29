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

## Phase couverture (imposée par le quality gate SonarCloud)

La PR a été refusée par SonarCloud à **79,9 % de couverture sur le code nouveau** (seuil 80 %).
Le refus ne portait pas sur un défaut de comportement mais sur un trou de preuve : **40 des
196 lignes ajoutées n'étaient exercées par aucun test**, dont `_etats_docker` **en entier** —
la fonction qui lit l'état réel des services dans Docker, c'est-à-dire la pièce sur laquelle
repose toute la sortie « healthy » vue par l'utilisateur.

Ce trou avait une cause structurelle, pas un oubli : les lignes non couvertes appartenaient
à des cibles difficiles à atteindre — une **closure** (`_default_probe`, interne à
`wait_healthy`) et un **fragment pré-indenté** (`_probes_block`, calibré pour s'insérer dans
le manifeste). Aucune n'est atteignable autrement qu'en passant par le point d'entrée public.
Les tests correspondants ont donc été écrits via `wait_healthy` et `render_k3s`, conformément
au principe déjà acquis en RAG-005 : un test qui fabrique son entrée valide un chemin que la
production n'emprunte jamais.

**Résultat mesuré : 79,6 % -> 97,4 % (191/196).** 41 tests ajoutés (fichier 3 -> 44).
Suite complète : code de sortie pytest **0**, zéro FAILED.

Les 5 lignes restantes sont assumées : `compose.py:129` (retour `{}` sur returncode non nul),
`235-236` (service probeable sans sonde exécutable) et `k3s.py:295-296` (fallback tcpSocket,
vérifié à la main mais atteint par un autre chemin par le test). Aucun test n'a été fabriqué
pour flatter le compteur — l'invariant no-fake l'interdit et le seuil est franchi de 17 points.

### Erreurs de méthode commises pendant cette phase (journalisées)

Quatre de mes propres gardes ont rendu un verdict faux, toutes pour la même raison :
**vérifier une chaîne de caractères au lieu de la propriété réelle.**

| Garde | Croyait vérifier | Ratait |
|---|---|---|
| `ast.parse()` | le fichier compile | mot-clé dupliqué (il faut `compile()`) |
| `"import x" in src` | l'import existe | matchait un **commentaire** |
| `ast.walk` sur les imports | le nom est disponible | trouvait un import **local à une autre fonction** |
| absence de `ast.Assert` | test sans assertion | `pytest.raises(match=…)` est une assertion plus forte |

De plus, le `except Exception: return {}` de `_etats_docker` (contrat volontaire : un
diagnostic qui plante ne diagnostique rien) a masqué successivement un `TypeError` de
signature de mock puis un `NameError` de classe helper absente, en affichant les deux fois
le même `{}` trompeur — ce qui m'a fait suspecter trois fois un défaut inexistant du produit.
Diagnostic obtenu en reproduisant l'appel **hors pytest**, ce qui laisse l'exception remonter.

## Revue scellée — tour 7 (diff intégral : code + 41 tests)

APPROVE **3/3**, vendors distincts `deepseek` / `google` / `xai`. Codeur = MiniMax (`minimax`),
absent du panel — jamais d'auto-review. Tally calculé par script, aucun LLM n'écrit un score.

**Objection mineure de Gemini — FONDÉE, corrigée.** Deux tests construisaient leur faux plan
avec l'attribut `id` alors que `_etats_docker` lit `plan.plan_id`. L'`AttributeError` partait
dans le `except Exception`, qui rendait `{}` : les tests passaient **sans jamais atteindre le
parsing qu'ils prétendaient vérifier**. Ils auraient continué à passer avec un parsing cassé.

Preuve exécutée de l'écart :
    mock {id}      -> AttributeError 'P' object has no attribute 'plan_id' => {} sans parser
    mock {plan_id} -> parse réellement le JSON tronqué, rend {} pour la BONNE raison
Corrigé (`id` -> `plan_id`), 44 tests toujours verts.

C'est la **troisième** fois dans ce package que le `except Exception` de `_etats_docker` masque
une cause (TypeError de signature, NameError de helper, et ici AttributeError du mock) — et la
première où c'est la revue qui l'attrape, pas moi. Un reviewer aveugle lisant le seul pack a vu
ce que dix corrections successives m'avaient laissé sous les yeux.
