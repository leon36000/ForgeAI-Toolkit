# K8S-027 — journal de la revue scellée

## Tour 3 : **APPROVE 3/3, zéro objection**
Vendors distincts `deepseek / google / tencent`, sceau `5df277409565`. Vendor du codeur
(**MiniMax**) exclu du trio. Le cycle a convergé.

## Trois tours — chacun déjà APPROVE, chacun ayant amélioré le package
| tour | sceau | objections | issue |
|---|---|---|---|
| 1 | `d4d21dddf2ab` | 1 (Gemini) | budget faussé en silence → corrigé |
| 2 | `e968acf6e2db` | 3 | **1 vrai bug** + 2 lacunes de couverture → corrigés |
| 3 | `5df277409565` | **0** | convergence |

**Un APPROVE n'autorise jamais à ignorer une objection.** J'aurais pu merger trois fois ; le
package est meilleur parce que je ne l'ai pas fait.

## Tour 1 — une objection « théorique » corrigée quand même
`_budget_du_plan` sous-comptait le budget en silence via deux `continue` défensifs. L'état était
**inatteignable** via `ServiceSpec` (validation fail-fast de RES-012B). Corrigée malgré tout : ce
budget devient un `ResourceQuota`, et une branche défensive qui fausse un budget en silence
convertit un état impossible en **quota faux** au lieu d'une **erreur visible**. Le code aurait
reproduit le mal qu'il combat.

## Tour 2 — trois objections triées par des tests rouges écrits AVANT correction
| objection | test | verdict |
|---|---|---|
| **Tencent** — `AttributeError` quand `res.get(cat, {})` rencontre `None` | **ROUGE** | **vrai défaut** |
| **DeepSeek** — `ERR_QUOTA_MEMOIRE_DEPASSEE` jamais atteint | vert | correct mais **non protégé** |
| **Tencent** — valeurs de `requests.*` non assertées | vert | somme correcte, **assertion manquante** |

Le test rouge tranche ce que la lecture seule ne peut pas : **une objection sur trois** portait sur
un vrai bug. Sans ces tests, les trois auraient été traitées à l'identique — ou toutes écartées
comme « théoriques ».

## Fait notable sur la composition du trio
**Tencent-Hy3 a trouvé le seul vrai bug** que ni Gemini ni DeepSeek n'avaient vu. Or il n'a été
recruté que parce que **Grok était tombé en HTTP 500** au package précédent. Sans cette panne de
route, ce bug partait sur `main`. La diversité du trio produit des trouvailles ; ce n'est pas une
formalité de procédure.
