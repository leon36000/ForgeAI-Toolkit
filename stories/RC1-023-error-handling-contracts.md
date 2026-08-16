# RC1-023 — Contractualiser les handlers d'erreur à haut risque (lot 1/N)

Issue : #452 (campagne RC1, vague 2, orchestrée par #481). Priorité P2_HIGH, reliability.
Dépend de #430 (DONE).

## Problème (issue #452)

Le scan AST a relevé des captures larges et des handlers silencieux dans `src/forgeai/`.
Plusieurs sont intentionnels et ne doivent pas être convertis automatiquement en bugs — mais
chaque site à haut risque doit posséder un contrat observable (disposition explicite, pas
d'exception avalée sans trace).

## Mesure (reconnaissance, cette story)

182 blocs `except` réels dans `src/forgeai/` à l'ouverture de cette story (comptage AST
indépendant). Répartition initiale par comportement du corps du handler : 87 `return_default`,
42 `re_raise` (déjà conformes — la cause est propagée, pas « avalée »), 29 `autre`, 18 `pass`,
6 `continue`.

**Mise à jour round 24-27 (#452, objections GPT-5.6-Terra-Pro)** — la mesure ci-dessus est celle
d'AVANT cette story ; elle ne reflète plus le dépôt après ses propres correctifs. Le motif
« repli ultime du print diagnostic best-effort » (# proof:allow, rounds 1-8) introduit 6 sites
`except Exception: pass` — DÉJÀ contractualisés au round 11 — chacun imbriqué dans un except
externe `except Exception:` (corps = un `try`, donc `autre`) qui, lui, n'est PAS contractualisé
(même catégorie que les 29 `autre` existants, différée aux lots suivants). Round 27 (correctif
`str_exc_sur`, `src/forgeai/core/safe_repr.py`) ajoute 1 site `return_default` de plus (le repli
défensif de `str_exc_sur` elle-même si `exc.__str__()` lève). Total et répartition courants (195,
vérifiés par `python3 scripts/governance/validate_error_contracts.py --root .` —
`coverage.total_except_sites_src_forgeai` fait foi, recalculé automatiquement par
`_compter_except_handlers_reels` depuis le round 17) : 88 `return_default` (87 + 1), 42 `re_raise`,
35 `autre` (29 + 6), 24 `pass` (18 + 6, les 6 nouveaux déjà couverts par le lot 1 ci-dessous),
6 `continue`. 88+42+35+24+6 = 195.

**Note de vérification round 29 (#452, objection GPT-5.6-Terra-Pro répétée à l'identique 2 fois)**
— objection : plusieurs contrats des replis ultimes (# proof:allow) pointeraient sur la ligne du
corps `pass` plutôt que sur la ligne du handler `except` lui-même (ex. `detect.py:61` serait le
`pass`, l'`except` serait à `60`). **Vérifié FAUX, trois méthodes indépendantes, à chaque
relance :**
1. Lecture directe du fichier (`sed -n '55,63p' src/forgeai/hardware/detect.py`) : ligne 61 =
   `except Exception:  # proof:allow …`, ligne 62 = `pass`.
2. `ast.parse` direct : `ExceptHandler.lineno == 61` (pas 60, pas 62).
3. Appel direct de `_verifier_site_ast()` (la fonction du validateur elle-même) sur les 3 entrées
   nommément citées (`detect.py:61`, `detect.py:95`, `server.py:615`) : aucune erreur, dans les
   trois cas.
Le hunk du diff cumulatif (`@@ -42,8 +44,22 @@`, comptage ligne par ligne depuis l'en-tête)
confirme la même chose : la ligne `+44` est `except (...) as exc:`, en comptant les 17 lignes `+`
suivantes on arrive à `+61` = `except Exception:  # proof:allow`, `+62` = `pass`. Pas d'ambiguïté
de format de diff — juste une lecture à corriger côté revue. Aucune correction de code nécessaire
: `governance/error-handling-contracts.json` est exact, confirmé par le gate lui-même (l'AST fait
foi, pas une relecture manuelle du diff).

## Scope de ce lot (1/N — campagne à la RC1-010/#440)

**Les 24 sites `pass`/`continue`** — les handlers les plus silencieux, cœur du problème décrit
par l'issue — **+ 1 site adjacent** découvert en traitant l'un d'eux (`web/server.py:1517`, même
fonction que le site `1523` déjà dans le lot, cause racine du même échec de thread). Triage réel
site par site (lecture du code, pas de classification automatique) :
- **16 JUSTIFIED** : comportement déjà correct et documenté (idiomes de nettoyage POSIX,
  boucles de parsing défensif à faible risque, motifs de scrutation, dégradation déjà
  contractualisée). Aucun changement de code.
- **9 FIXED** : dégradation silencieuse réelle sur des chemins sécurité/persistance/déploiement/
  rollback (ex. constat d'audit L07-002 : deux `except Exception: pass` avalaient des échecs de
  persistance de l'état de déploiement sans aucune trace). Correctif MINIMAL : rendre la
  dégradation visible (stderr ou ligne d'avertissement dans le flux de déploiement, selon le
  contexte), **aucun changement de comportement fonctionnel préexistant pour la hiérarchie
  `Exception`** — portée précisée round 37 (voir « Risque résiduel accepté » ci-dessous) : un
  `__str__` pathologique qui lève explicitement un `BaseException` non-`Exception` reste un écart
  résiduel étroit, accepté et documenté, pas silencieusement recouvert par cette formulation.

Les 158 sites restants (`autre`, `return_default`, contrats docstring légers sur `re_raise`)
sont hors scope de ce lot — `governance/error-handling-contracts.json::coverage.note` documente
le plan des lots suivants.

## Livrables

1. `governance/error-handling-contracts.json` — inventaire machine de 31 sites (25 initiaux +
   6 ajoutés au round 11, voir note ci-dessous ; site, exception attendue, comportement,
   journalisation, propriétaire, justification, test compensatoire ou raison d'absence, échéance
   de révision à 180 jours, disposition).
2. `scripts/governance/validate_error_contracts.py` — validateur stdlib : schéma complet
   (id/site/coverage/review_horizon durcis au round 10, objections GPT-5.6-Terra-Pro),
   plancher de couverture (`coverage.floor`), dates de révision, XOR test/raison, FIXED exige un
   test réel, **dérive AST** (le site existe toujours à la ligne indiquée, le type d'exception
   n'a pas changé) — sur les 31 sites inventoriés uniquement, pas sur les 163 autres (couverture
   volontairement progressive, pas un remplacement mécanique de tous les `except`). Round 11
   (objection GPT-5.6-Terra-Pro) : `coverage.total_except_sites_src_forgeai` recalculé en AST pur
   (194, pas 182) après découverte d'un écart de méthode grep/AST non lié à cette story
   (`src/forgeai/ide/guard_fs.py` embarque un script généré comme littéral de chaîne — grep
   matchait 11 "except" texte à l'intérieur, l'AST correctement non).
3. `governance/ERROR-HANDLING-CONTRACTS.md` — rapport généré (`--render`).
4. `.github/workflows/error-handling-contracts.yml` — gate CI (validation + détection de
   mutation : un site déplacé doit faire échouer le gate).
5. 9 correctifs minimaux (sites FIXED) + 9 tests d'injection de faute prouvant (a) le nouveau
   signal apparaît, (b) le comportement observable préexistant est inchangé pour toute `Exception`
   levée par `__str__()` — la frontière `BaseException` non-`Exception` est un risque résiduel
   étroit distinct, accepté et documenté (voir « Risque résiduel accepté » ci-dessous), pas une
   omission de cette preuve.
6. ~~`manifests/roles.yaml` — 2 entrées ajoutées (`kimi-k3`, `gemini-3.7-flash`)~~ : livrable
   initial (roster codeur périmé découvert en construisant le reçu D9 de cette story, vendors
   vérifiés à la source via `/v1/model/info`, signalé sur #481) — **superseded, retiré du diff
   final**. Au rebase de cette branche sur origin/main courant, le roster avait déjà mûri
   (roulement RC1-010/ROSTER-MAJ-PR511) : les entrées équivalentes `kimi_k3`/`gemini_flash`
   (mêmes `provider_id` `Kimi-K3`/`Gemini-3.7-Flash`, vendors moonshot/google identiques,
   convention de nommage à underscore alignée sur le reste du fichier) existaient déjà, mieux
   intégrées. Mes ajouts hyphenés (`kimi-k3`/`gemini-3.7-flash`) auraient été des doublons —
   retirés en résolvant le conflit de rebase plutôt que réappliqués. Aucune action de suivi :
   le besoin original est déjà couvert par le roster actuel.

## Risque résiduel accepté (rounds 19-23, #452) — compensating_test et exécution réelle

`validate_error_contracts.py` vérifie qu'un `compensating_test` référencé par un contrat `FIXED`
désigne une fonction/méthode réellement **collectable** par pytest (convention de nommage round
14, non-`__init__` round 15, absence de skip inconditionnel — décorateur fonction round 19,
`pytestmark` de module round 20, décorateur classe round 21, `skipif` à condition littéralement
constante round 22). Ce que le gate NE vérifie PAS, et ne vérifiera PAS dans ce lot : qu'une
condition `skipif` **non littérale mais constante-repliable** (`skipif(1 == 1, ...)`,
`skipif(not False, ...)`, etc.) désactive réellement le test à l'exécution — round 23, objection
GPT-5.6-Terra-Pro, re-signale précisément le cas déjà documenté et testé (contre-preuve
`test_compensating_test_skipif_expression_non_litterale_reste_valide`) comme délibérément hors
scope.

**Pourquoi c'est une frontière délibérée, pas un oubli** : détecter categoriquement TOUTE
condition constante-repliable exige soit (a) une évaluation partielle de code Python arbitraire
(replier `1 == 1`, `not False`, `(1+1)==2`, un nombre non borné de formes équivalentes — la même
classe de problème que `pytest.skip()` en corps de fonction, déjà hors scope depuis le round 19),
soit (b) exécuter réellement pytest et lire l'issue (SKIPPED vs PASSED) plutôt que d'analyser
l'AST statiquement. Vérifié empiriquement avant cette décision : `pytest --collect-only` ne
distingue PAS un test skip-marqué d'un test normal (le skip est évalué au SETUP, pas à la
collecte) — seule une exécution réelle (`pytest -q <nodeid>`, sortie `code retour 0` que le test
soit PASSED **ou** SKIPPED, distinction uniquement dans le texte de sortie) donnerait un signal
fiable. Ce changement d'architecture — d'un gate rapide/déterministe/sans effet de bord vers une
vérification qui exécute du code de test arbitraire (coût par invocation, risque de fragilité
d'un test par ailleurs sans rapport, isolation vis-à-vis d'une éventuelle exécution pytest
englobante) — est un choix de conception qui mérite sa propre story dédiée avec ses propres
compromis explicites (fréquence d'exécution, timeout, cache, ordonnancement CI), pas un correctif
réactif de plus dans ce lot.

**Portée réelle du risque résiduel** : aucun `compensating_test` du dépôt réel n'utilise
aujourd'hui une condition `skipif` non littérale du type visé (`@posix_only` utilise une
`ast.Compare` sur `os.name`, qui n'est PAS une condition triviale/déguisée — elle dépend
réellement de la plateforme, cas légitime et volontairement toléré). Le risque est donc
actuellement théorique sur ce dépôt, contrairement au round 19 (`@posix_only`, `pytestmark`) où
le mécanisme sous-jacent existait déjà réellement dans le code — round 22/23 sont les premiers de
cette série où l'objection reste au niveau du gate lui-même, pas d'une donnée réelle affectée.

**Suivi** : signalé sur #452/#481 pour une story dédiée si ce risque devient réel en pratique
(nouveau `compensating_test` utilisant une condition constante déguisée non détectée) — pas
ignoré en silence, disposition équivalente à `SPLIT_TO_NEW_ISSUE` au niveau du gate plutôt que
d'un site individuel.

## Risque résiduel accepté (rounds 27-37, #452) — str_exc_sur() et le critère « aucun changement de comportement » des sites FIXED

`src/forgeai/core/safe_repr.py::str_exc_sur()` (round 27) rend sûre l'interpolation `f"...:
{exc}"` utilisée par les sites FIXED de cette story (`_persist_deploy_state`, `_load_deploy_state`,
`_reader`) — mais UNIQUEMENT si `exc.__str__()` lève une `Exception` normale. Round 28 avait
élargi à `except BaseException` pour couvrir aussi un `__str__` qui lève explicitement
`SystemExit`/`KeyboardInterrupt` ; round 30 est revenu sur ce choix (un `except BaseException`
avale AUSSI un Ctrl-C authentique arrivant PENDANT l'appel à `str(exc)`, sans rapport avec
`exc.__str__()` elle-même — Python ne peut pas distinguer les deux cas). Round 36 (objection
GPT-5.6-Terra-Pro) pointe la conséquence directe pour CETTE story spécifiquement : ce compromis
signifie que `str_exc_sur()` peut encore, dans le cas pathologique étroit (`__str__` qui lève
explicitement un `BaseException`), interrompre le fallback/nettoyage d'un site FIXED avant sa
fin — un changement de comportement observable dans ce cas précis, par rapport au bloc
`except ...: pass` d'avant cette story qui n'appelait jamais `str(exc)` du tout.

**Analyse de la portée réelle (round 36)** : vérifié empiriquement que `_reader` s'exécute
exclusivement sur un thread daemon en arrière-plan (`threading.Thread(target=_reader,
daemon=True).start()`) — Python ne délivre JAMAIS `KeyboardInterrupt` à un thread non-principal
via le mécanisme normal de signal (confirmé par test direct : un `SIGINT` envoyé au process
n'atteint que le thread principal, jamais un thread secondaire). Pour ce site précis (le plus
sévère des trois, cf. round 27 — `done` resterait bloqué à `False` sans lui), la préoccupation
« Ctrl-C asynchrone avalé » de round 30 ne s'applique donc PAS en pratique. Il ne reste que le cas
« `__str__` personnalisé lève explicitement `BaseException` » — un `exc` dans ce contexte provient
exclusivement d'exceptions standard liées au sous-processus/E-S (`OSError` et consorts), dont le
`__str__` de la stdlib est stable et testé ; le risque résiduel réel est donc doublement
pathologique (thread + type d'exception), pas seulement théorique une fois.

**Décision** : ne PAS ajouter de garde supplémentaire (ex. `except BaseException: pass` local à
chaque site) — chaque garde de ce type est ELLE-MÊME un nouveau site `except`/`pass` à
contractualiser (même famille body_kind que ce lot 1 priorise), rouvrant la même classe de travail
pour une couverture marginale sur un risque déjà doublement pathologique. Le compromis round 30
(signal-safe par défaut) reste la position finale de ce lot ; le risque résiduel exact — étroit,
documenté dans le docstring de `str_exc_sur()`, et maintenant analysé au niveau story — est accepté
plutôt que rouvert indéfiniment.

**Suivi** : signalé sur #452/#481, disposition équivalente à `SPLIT_TO_NEW_ISSUE` — si ce risque
devient réel en pratique (jamais observé à ce jour), la correction appropriée serait un helper
dédié `str_exc_sur_best_effort_total()` (BaseException, réservé aux contextes déjà vérifiés
signal-safe comme les threads daemon) plutôt qu'une garde ad hoc par site.

**Round 37 (objection GPT-5.6-Terra-Pro, REJECT majeure, 2/3 APPROVE)** : round 36 documentait
correctement ce risque résiduel dans CETTE section, mais laissait intacte, plus bas, la formulation
des « Critères de validation » et des livrables qui affirmait sans nuance « aucun changement de
comportement observable sur les 9 sites FIXED » — une contradiction interne du document (l'analyse
ci-dessus admet explicitement un changement de comportement dans le cas pathologique
`BaseException`, la case à cocher le niait). Un reviewer indépendant lisant le pack complet retombe
nécessairement sur cette contradiction, quelle que soit la qualité de l'analyse : documenter un
risque résiduel à un endroit du document sans corriger l'affirmation contraire ailleurs ne le
résout pas. **Aucun changement de code** — le compromis `except Exception` (round 30) reste la
position finale, toujours pour les mêmes raisons de sécurité signal. Seule la formulation des trois
endroits qui promettaient « zéro changement de comportement » sans réserve a été corrigée pour
scoper précisément à la hiérarchie `Exception` (livrable 9-FIXED, livrable 5, case AC) — la preuve
par tests d'injection de faute reste exacte et inchangée pour ce périmètre corrigé.

## Critères de validation

- [x] `pytest` — suite complète verte (2224 tests collectés, 0 échec ; régression confirmée sur
      les fichiers modifiés ET sur l'ensemble du dépôt).
- [x] `python3 scripts/no_stub_scan.py --all` — 0 violation.
- [x] `python3 scripts/governance/validate_error_contracts.py --root . --render` — OK.
- [x] Mutation locale (site déplacé) → gate détecte "site introuvable" (vérifié en local avant
      CI).
- [x] Aucun changement de comportement observable sur les 9 sites FIXED pour toute `Exception`
      levée par `exc.__str__()` (prouvé par les tests d'injection de faute : valeur de retour /
      absence d'exception propagée inchangée). Portée EXCLUT explicitement un `__str__` qui lève
      un `BaseException` non-`Exception` (`SystemExit`/`KeyboardInterrupt` explicites) — risque
      résiduel étroit, analysé et accepté round 36-37, pas couvert par cette preuve (voir
      « Risque résiduel accepté (rounds 27-36…) » ci-dessus). Round 37 (objection GPT-5.6-Terra-Pro,
      REJECT majeure) : la formulation précédente de cette case ne portait pas cette exclusion
      explicitement et contredisait donc la section d'analyse — corrigé ici, aucun changement de
      code (le compromis round 30/36 reste inchangé, seule la formulation de l'AC était fausse).
- [x] Revue aveugle scellée 3 vendors distincts, APPROVE 3/3 — round 39 (Qwen3.7-Max/alibaba,
      GPT-5.6-Terra-Pro/openai, Muse-Spark-1.2/meta), 0 objection,
      `prompt_sha256=1f00937992ff7e34f79b0a2d3a6e7350a2b2e54f4c40ce4ec060655a46bab666`.

## Post-round-39 — cliquet mypy progressif (#449, gate apparu en cours de story via rebase)

`scripts/mypy_gate.py` (fusionné sur `main` pendant le traitement de cette story, #449) borne le
nombre d'erreurs mypy par fichier « en dette » contre `Docs/BASELINE-MYPY.json` — toute
augmentation est un échec bloquant, jamais résolu en relevant simplement la borne. Rebase de
cette branche a exposé une régression réelle sur `src/forgeai/web/server.py` (106 → 121 erreurs) :
chaque nouveau site FIXED de ce lot qui journalise désormais un avertissement (`with
_DEPLOY_STATE["lock"]: _DEPLOY_STATE["lines"].append(...)`) ajoutait des occurrences de la MÊME
classe d'erreur `union-attr` déjà tolérée ailleurs dans le fichier — `_DEPLOY_STATE` est un dict
littéral sans annotation explicite, donc mypy infère `None | list[Any] | bool | LockType` pour
CHAQUE accès à CHAQUE clé, peu importe laquelle.

**Rejeté** : suppression via `# type: ignore[union-attr]` aux nouveaux sites — `mypy_gate.py`
scelle spécifiquement contre ce contournement (`occurrences_type_ignore`/`type_ignore_lignes`
dans la base JSON, correctif post-revue round 12 #449) ; le baseline actuel pour ce fichier est
`type_ignore: None` (zéro toléré), donc tout ajout aurait été détecté comme une neutralisation,
pas une correction.

**Corrigé** : annotation `_DEPLOY_STATE: dict[str, Any]` (import `typing.Any` ajouté) — un
changement d'UNE ligne, zéro changement de comportement runtime (annotation pure), qui élimine
la classe d'erreur entière plutôt que de la suppresser site par site. Effet mesuré :
`src/forgeai/web/server.py` passe de 121 à **19** erreurs (mieux que la borne baselinée de 106,
amélioration nette de 87 erreurs pré-existantes non liées à cette story) ; total dépôt 149 → 47
(borne 134). `Docs/BASELINE-MYPY.json` volontairement NON modifié — la borne de 106 reste
correcte comme PLAFOND, l'inutile de l'abaisser formellement n'est pas dans le scope de cette
story (dette mypy hors #452, resserrer le cliquet est une décision distincte pour #449/#456).
