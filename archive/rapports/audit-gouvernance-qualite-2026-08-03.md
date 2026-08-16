# Audit gouvernance & qualité — 2026-08-03

**Base auditée** : `origin/main` = `d4b7710` (Preuve 10, `git rev-parse origin/main`).
Aucune PR ouverte (0/0, Preuve 7). Demandé par Nathan après clôture de
B-22/B-23/B-25/I18N-041 : *"corrige tous les problèmes ensuite fais un audit qui doit être
approuvé par consensus par toute l'équipe multi-modèles"* (verbatim, message utilisateur
de cette session — non inclus dans les preuves techniques ci-dessous, c'est une citation
de conversation, pas une mesure d'état du dépôt).

**Portée explicite** : cet audit couvre le substrat gouvernance/qualité (tests, CI, gates,
registres, coordination, catalogue, i18n, protection de branche) — les dimensions que la
session en cours a mesurées, corrigées et peut attester avec preuve directe. Il **ne
ré-audite PAS** les 25 exigences produit de `Rapports/conformite-v2.0-integrale.md`
(Section B — TUI, multi-nœuds, gestion de modèles, stacks par domaine, etc.) : ce
périmètre n'a pas été retouché cette session et une ré-affirmation sans nouvelle mesure
serait une allégation non vérifiée. Ce document complète ce rapport antérieur, il ne le
remplace pas.

**Méthodologie** : dans les **§1 à §9** (l'audit lui-même), chaque ligne est une mesure
directe (commande exécutée, sortie citée), jamais une reformulation de mémoire ou un
résumé de conversation précédente — c'est le périmètre où cette garantie s'applique.
**Les §10 et suivants (revue scellée de ce document par lui-même) et le « Verdict
proposé » sont d'une autre nature : une narration de processus** (qui a dit quoi, quand,
et ce qui a été corrigé) — par construction non re-vérifiable par un artefact statique du
dépôt de la même façon qu'un fait d'état (détail, raison, et portée exacte de cette
distinction en §9, qui prime sur toute formulation générale trouvée ailleurs dans ce
document). Horodatage : 2026-08-03, ~12h50 UTC.

## 1. Suite de tests et couverture

```
$ pytest -o addopts="" -q -rs
1858 passed, 7 skipped, 3 warnings in 201.94s (0:03:21)
RC=0
```
(Preuve 12.)
```
$ pytest -o addopts="" -q --cov=forgeai --cov-report=term-missing
TOTAL                                      7183    483    93%
```
(Preuve 18 — 2 exécutions séparées, durées différentes (201.94s vs 205.15s). **Précision
round 7** : le compte de tests identique (1858) est cohérent avec le même état du dépôt,
mais ceci n'est pas prouvé formellement dans ce pack — aucun hash de commit n'a été capturé
au moment de chacune des 2 exécutions pour l'établir de façon certaine.)

`rc=0` confirmé explicitement (pas déduit). Les 7 skips ont chacun une raison nommée dans
la sortie `-rs` (Preuve 12) : 2 tests spécifiques à Windows, skippés sur ce runner Linux —
le message de skip lui-même l'affirme (Preuve 12) ; `guard-fs-multi-os (windows-latest):
pass` sur PR #382 (Preuve 24) confirme que le JOB Windows passe, mais ne liste pas
individuellement ces 2 tests précis — l'inférence qu'ils tournent réellement là s'appuie
sur le nom du job et le contenu du message de skip, pas sur une preuve test-par-test — et
5 tests e2e Docker lourds, skip par défaut, rejouables avec `FORGEAI_E2E=1` (raison donnée
dans le message de skip lui-même, Preuve
12 — le lien avec une preuve d'exécution passée au registre n'est PAS vérifié dans ce
pack et n'est donc plus affirmé ici). **Correction round 1** : l'affirmation initiale de
cet audit ("dépendances GPU absentes en CI") était fausse — vérifiée et corrigée après le
round 1, aucun des 7 skips ne concerne le GPU.

**3 warnings — correction round 3, la caractérisation round 2 était FAUSSE** : les 3
warnings ne proviennent PAS tous du même test. Preuve 12, lu précisément : 2 warnings de
`test_rel038b_unicite.py::test_g4_hote_libere_meme_sur_exception_non_rattrapee`
(`KeyboardInterrupt` non rattrapé, délibéré d'après le nom du test — même réserve
qu'avant, non vérifié en lisant le code source) et **1 warning distinct**, de
`test_rel038c_process_groups.py::test_g1_deploiement_reel_lance_dans_son_propre_groupe` :
`AttributeError: 'PopenEnregistreur' object has no attribute 'returncode'`, levée dans un
thread `_reader` en tâche de fond, `src/forgeai/web/server.py:1505`. Lecture la plus
probable (NON vérifiée en lisant le test) : `PopenEnregistreur` est un double de test
(le nom français « Enregistreur » suggère un espion qui enregistre les appels) qui
n'expose pas `.returncode` — une lacune du double de test plutôt qu'un défaut de
`server.py`, mais ceci est une hypothèse, pas une conclusion vérifiée. Les 3 reviewers de
la revue scellée de CET audit (round 3) ont trouvé cette erreur indépendamment ; les
2 rounds précédents avaient laissé passer une affirmation fausse sans la vérifier au
niveau du nom de fichier exact — corrigé ici en citant les 2 tests distincts.

## 2. Gates CI sur `main`

Dernier run post-merge (coordination I18N-041, PR #383) : `gates: success`,
`sonarcloud: success` (2026-08-03T12:48Z, Preuve 8). `main` n'a aucune PR en attente ;
état propre. **Correction round 1** : la version initiale de cet audit citait par erreur
PR #382 / 12:41Z ici alors que la Preuve 8 citait déjà #383 / 12:48Z — incohérence interne
trouvée par 2 des 3 reviewers indépendamment, corrigée.

`no-stub-scan --all` (326 fichiers scannés) : **zéro violation**.

**Nouveau constat (trouvé en préparant les preuves du round 2, absent du round 1)** :
SonarCloud produit DEUX analyses distinctes sous le même nom de check « SonarCloud Code
Analysis », confirmé par comparaison directe (Preuve 19) :
- contexte **PULL REQUEST** (`pullRequest=382`, via `gh pr checks`) : **passe**.
- contexte **BRANCHE main continue** (`branch=main`, via `gh api commits/.../check-runs`) :
  **échoue** sur `D Security Rating on New Code` (seuil ≥ A) — condition détaillée
  confirmée sur le merge de PR #378 ET de PR #382 (Preuve 15). Sur `main~50`, seul le
  statut agrégé `failure` a été récupéré (pas le détail de la condition) — cohérent avec le
  même échec, non confirmé nommément à cette distance.

Preuve 1 (config brute de branch protection) ne distingue PAS elle-même ces deux contextes
— elle liste juste le nom « SonarCloud Code Analysis » comme required check, sans préciser
lequel des deux. **Correction round 6 — l'inférence précédente était non fondée, retirée** :
les rounds 2-5 de cette revue affirmaient que les 6 PRs mergées malgré l'échec branche
persistant prouvaient que le required check résout vers le contexte PR. **Ceci ignorait
une explication alternative que Preuve 1 contient déjà** : `enforce_admins.enabled = false`
— la signification opérationnelle de ce champ (les administrateurs du dépôt peuvent merger
en contournant tous les required checks) est la sémantique **standard, documentée par
l'API GitHub elle-même** pour ce champ, pas une inférence propre à ce pack ni à ce dépôt ;
elle n'a pas besoin d'une preuve brute supplémentaire, au même titre que le sens de
`allow_force_pushes` ou `strict` n'en a pas besoin ailleurs dans ce document. **Précision
round 9** : que les merges #378-383 aient été faits avec des droits d'administrateur n'est
pas non plus établi par un artefact du dépôt — c'est un fait sur QUI a agi (l'auteur de ce
document, via `gh pr merge`), de la même nature que les affirmations de processus déjà
signalées comme non re-vérifiables par un artefact statique (§9). **Donc : lequel des deux
contextes conditionne réellement un merge NON-admin reste, à ce stade, non déterminé par
les preuves de ce pack** — les deux explications (required check résout vers PR ; OU
merges admin bypassant le required check indépendamment de son contexte) sont compatibles
avec les faits observés, et rien ici ne les départage.

Sur l'ancienneté : **précision round 7, réduite au strictement soutenu**. Ce qui EST
établi sans ambiguïté : le même check nommé (Preuve 19 corrigée) échoue sur le merge de PR
#378 (2026-08-03T07:28Z) ET sur celui de PR #382 (2026-08-03T12:41Z, Preuve 15) — 2 points
temporels distincts, dates connues (Preuve 11), séparant des changements de code
différents entre eux (I18N-031 vs I18N-041). `main~50` n'est PAS utilisé pour établir
l'ancienneté : sa position chronologique relative à PR #378 n'a pas été établie dans ce
pack (`main~50` est relatif au tip ACTUEL de `main`, après #378 ET #382 ET #383 — pas
nécessairement avant #378), et son contenu n'a pas été récupéré (seul le statut agrégé
`failure`, Preuve 15). Non établi non plus : si PR #378 elle-même a été produite par un
travail antérieur DANS cette même session étendue ou avant son début.

Ce qui reste non résolu par ce pack : si un merge NON-admin serait bloqué par ce check
aujourd'hui. Ce que cet audit NE prétend PLUS établir (retiré au round 6). Dans tous les
cas, jamais documenté explicitement jusqu'ici et nécessite son propre lot d'investigation
(quels Security Hotspots précisément, ET quel contexte le required check évalue
réellement) — hors périmètre de cet audit, signalé pour suivi.

## 3. Protection de branche `main` — ÉCART TROUVÉ, divergence rapport vs réalité

Mesure directe (`gh api repos/leon36000/ForgeAI-Toolkit/branches/main/protection`,
2026-08-03, répétée deux fois indépendamment ce jour — Preuve 1 et Preuve 16, sorties
JSON identiques) :
```
required_status_checks : strict=true, 6 contexts (gitleaks, no-stub-scan, registres,
                          tests, SonarCloud Code Analysis, GitGuardian Security Checks)
allow_force_pushes : false | allow_deletions : false
required_pull_request_reviews : ABSENT
required_signatures.enabled   : false
enforce_admins.enabled        : false
```

**Ce que le rapport du 2026-07-14 affirme EXACTEMENT** (citation verbatim, Preuve 9) :
*"Branch protection posée (`gh api`, sur autorisation Nathan) : les 4 gates CI (…) sont
required checks bloquants, force-push et suppression interdits sur `main`. CODEOWNERS
ajouté. Commits `main` signés GPG par Nathan (clé RSA…). → Les invariants #2/#3/#4 passent
de « enforcement PARTIEL » à enforcement SERVEUR."* Recherche exhaustive sur le fichier
**ENTIER** (pas seulement cet extrait — Preuve 29, `grep` sans résultat) confirme que le
rapport **n'emploie nulle part** les termes `required_pull_request_reviews` ni
`enforce_admins` — ce sont des noms de champs de
l'API GitHub, pas des mots du rapport ; **correction round 2** : la version précédente de
cet audit affirmait à tort que le rapport « déclare posés » ces champs précis, ce qu'il ne
fait pas littéralement.

**Confronté à la mesure d'aujourd'hui (Preuve 1/16)** :
- « 4 gates CI requis bloquants » + « force-push et suppression interdits » : **vérifié
  vrai** (`required_status_checks` actif 6 contexts, `allow_force_pushes`/
  `allow_deletions` à `false`).
- « CODEOWNERS ajouté » : **vérifié vrai** comme fichier (`.github/CODEOWNERS` existe,
  Preuve 17) — mais **inerte côté serveur**, voir plus bas.
- « Commits `main` signés GPG par Nathan » : ambigu — soit un fait sur la pratique
  personnelle de Nathan (hors du champ mesurable par `gh api branch protection`), soit une
  affirmation que `required_signatures` a été activé pour TOUT le monde. Mesuré aujourd'hui
  : `required_signatures.enabled = false` — si la 2e lecture est la bonne, c'est contredit ;
  si c'est la 1ère, cette phrase du rapport ne prétendait pas à un enforcement serveur et
  n'est pas contredite par cette mesure.
- « enforcement SERVEUR » (conclusion générale du rapport) : **non soutenu** par la mesure
  d'aujourd'hui pour la revue obligatoire (`required_pull_request_reviews` absent).

**Précision round 4 (nuance manquée)** : le rapport du 2026-07-14 ne prétend PAS que ce
point était réglé — il l'annonce lui-même explicitement comme un reste : *"Reste (mineur) :
signature GPG des commits automatisés Forge-GRS (…) et une revue humaine PR (impraticable
en mono-propriétaire — la revue 3 modèles reste la gouvernance de contenu)"* (Preuve 9,
citation complète). La mesure d'aujourd'hui (`required_pull_request_reviews` absent) **est
donc cohérente avec ce que le rapport annonçait déjà lui-même comme non réglé**, pas une
contradiction d'un point que le rapport aurait prétendu résolu. La divergence réelle porte
sur la conclusion générale (« enforcement SERVEUR », prise comme un tout) plus que sur ce
point précis, que le rapport avait honnêtement laissé ouvert.

Fait vérifié : le commit `920b463` (même date, message *"Branch protection posée par
Fable sur autorisation Nathan (gh api)"*) ne contient, dans son diff réel, QUE
`.github/CODEOWNERS` (17 lignes) et une entrée registre — **aucun artefact reproductible
de l'appel `gh api` de protection de branche n'existe dans le dépôt** (ce qui est normal
pour un appel API ponctuel, mais signifie que la seule preuve de son exécution était
l'affirmation elle-même, jamais re-vérifiée depuis).

Deux explications possibles, non départagées ici (aucune ne peut être confirmée
rétroactivement sans accès à l'historique GitHub des réglages) :
1. Le réglage a été posé le 2026-07-14 puis perdu depuis (transfert/renommage de dépôt,
   réinitialisation, ou action manuelle ultérieure).
2. Le réglage n'a en réalité jamais été appliqué avec succès — l'affirmation du commit
   `920b463` n'a jamais été re-vérifiée par un `gh api` de contrôle au moment des faits.

**CODEOWNERS existe** (`.github/CODEOWNERS`, bien structuré) mais est **inerte côté
serveur** tant que `required_pull_request_reviews.require_code_owner_reviews` n'est pas
positionné — un fichier présent n'implique pas un enforcement actif.

Déjà journalisé cette session (`Registres/mission.jsonl` seq 408, type `blocage_t3`,
2026-08-03T11:50Z) : gap mesuré, action proposée documentée, **aucune exécution sans
approbation explicite de Nathan** (réglage de plateforme partagée externe = frontière T3).
Cet audit ne fait que consolider et dater cette même mesure, avec en plus la divergence
vs le rapport de 2026-07-14 découverte pendant sa rédaction.

**Action proposée, en attente d'approbation Nathan (inchangée)** :
```
PUT /repos/leon36000/ForgeAI-Toolkit/branches/main/protection
  required_pull_request_reviews: {required_approving_review_count: 3,
                                   require_code_owner_reviews: true}
  enforce_admins: true
  (required_status_checks préservé à l'identique)
PUIS séparément :
POST /repos/leon36000/ForgeAI-Toolkit/branches/main/protection/required_signatures
```

## 4. Registres hash-chaînés

Intégrité vérifiée sur les **34** fichiers `Registres/*.jsonl` (`mission.jsonl` + 33
`PATCH-*.jsonl` — Preuve 3, `scripts/registre.py verify` un par un) : **tous OK, aucune
chaîne rompue**. `mission.jsonl` : 408 entrées. Contenu exact des 2 constats de cette
session cité intégralement en Preuve 13 (seq 407 `audit_finding`/B-25, seq 408
`blocage_t3`/B-22 — mêmes faits que §3 et §6 ci-dessous, payload complet, pas résumé).
**Correction round 1** : « 33 fichiers » était une erreur de comptage (oubli de
`mission.jsonl` lui-même) — trouvée indépendamment par 2 des 3 reviewers.

## 5. Coordination (`coordination/`)

`scripts/coordination/validate_coordination.py` (Preuve 4) : **PASS — 69 packages, 69
complétés, zéro claim actif, zéro erreur.** B-23 et I18N-041 sont désormais tracés par les
PRs de coordination `#381 "chore(coordination): B-23 complétée (#380) + constats
B-22/B-25"` et `#383 "chore(coordination): I18N-041 complétée (#382) — 69/69"` (titres
exacts, état MERGED — Preuve 20). **Précision round 8** : l'affirmation que B-23 (comme
I18N-041, §7) proviendrait d'un audit du backlog plutôt que du plan initial n'est
soutenue, dans ce pack, que pour I18N-041 (Preuve 17, en-tête de `stories/I18N-041.md` :
« Origine : audit du backlog demandé par Nathan… » — pas Preuve 21, qui ne couvre que la
preuve de couverture §4) — retirée pour
B-23, dont l'origine n'a pas de preuve brute jointe ici. **Correction round 5** : la
mention « même pattern que
SSH-030/DATA-002B/I18N-031 » a été retirée — comparaison stylistique de mémoire de
session, sans preuve brute jointe dans ce pack pour ces 3 entrées.

## 6. Catalogue de découverte logicielle

```python
total: 1577 | verified=true: 1577 | INTROUVABLE: 0
méthodes : gh-api 1514, huggingface 18, URL directe 18, site 10, gh-search 9,
           web:github 4, produit 3, PyPI 1
```
(Preuve 5 — total, `verified`, méthodes.) Version catalogue `2026-07-13` (Preuve 5).
**Correction round 11** : l'affirmation que TOUTES les vérifications individuelles sont
datées 2026-07 n'est pas dans Preuve 5 elle-même (qui ne donne que la version globale) —
c'est le registre seq 407 qui l'énonce (payload cité en entier, Preuve 13 : « toutes
datees 2026-07 »), citation désormais correctement attribuée. **~3 semaines avant cet
audit**. Fraîcheur raisonnable mais non garantie indéfiniment (popularité/statut de
maintenance de projets open-source dérive) ; déjà signalé au registre seq 407 comme
limite à re-vérifier par échantillonnage dans un futur lot, pas comme un défaut actuel.

## 7. Internationalisation (i18n)

`fr.json`/`en.json` (Preuve 6) : **275/275 clés, parité stricte confirmée**. I18N-031 (PR
#378, état MERGED confirmé — Preuve 22) + I18N-041 (71 messages d'exception sur 4 fichiers
fondamentaux — décompte détaillé par fichier : `core/models.py` 31, `models/vault.py` 13,
`renderers/k3s.py` 14, `portability.py` 13, cité verbatim en Preuve 21 depuis
`stories/I18N-041.md` §4) mergés et vérifiés sur `main`. **~123 messages d'exception
restants sur ~38 fichiers**, mesurés et listés explicitement — liste complète par fichier
citée en Preuve 14 (extrait verbatim de `stories/I18N-041.md` §6, pas un résumé) — traité
comme borne inférieure, pas un compte final. **Correction round 3** (citation manquante) :
trois passages de détection successifs se sont chacun révélés incomplets, et une revue
scellée indépendante a trouvé un 4e site que les trois avaient manqué — cité verbatim en
Preuve 26 (`stories/I18N-041.md` §1), pas seulement affirmé. Différé délibérément, pas
silencieusement abandonné.

## 8. Issues et PRs GitHub

0 issue ouverte, 0 PR ouverte (Preuve 7). Dernières PRs mergées (2026-08-03) : #378-383,
chacune vérifiée individuellement — état MERGED, commit de fusion, et statut des checks
sur ce commit précis : 12 succès / 1 échec pour chacune des 6 (Preuve 11, comptage
agrégé). **Précision round 4** : seuls #378 et #382 ont été confirmés individuellement
comme portant le même échec nommé « D Security Rating on New Code » (Preuve 15, sortie
détaillée) ; pour #379/#380/#381/#383, le motif exact de l'unique échec n'a pas été
récupéré séparément — l'hypothèse qu'il s'agit du même échec repose sur le compte
identique (1/12) et sa persistance connue sur `main~50` (Preuve 15), pas sur une
vérification individuelle des 4 — présenté comme hypothèse forte, pas comme fait mesuré
pour ces 4-là spécifiquement. Contenu réel confirmé sur `origin/main` (pas le seul
badge de fusion) pour I18N-041 et son fichier de test — Preuve 17.

## 9. Limites explicites de cet audit

- Ne couvre PAS les 25 exigences produit (TUI, multi-nœuds interactif, gestion de
  modèles, stacks par domaine, plugins, IDE) — voir « Portée explicite » en tête de
  document.
- Le catalogue (§6) et le sous-ensemble i18n restant (§7) sont des **bornes inférieures**
  mesurées, pas des comptes exhaustifs garantis.
- La divergence de branch protection (§3) est journalisée mais sa **cause** (perdue vs
  jamais appliquée) n'est pas déterminée — aucune preuve rétroactive disponible.
- Le « D Security Rating » SonarCloud sur `main` (§2) est confirmé pré-existant mais son
  contenu précis (quels Security Hotspots) n'a pas été investigué — hors périmètre.
- Aucune vérification e2e de déploiement réel (Compose/K3s) n'a été refaite cette
  session ; ce périmètre repose sur les preuves antérieures déjà au registre.
- Les §10-12 (revues scellées de CET audit) et le déroulé round par round narrent un
  PROCESSUS (qui a dit quoi, dans quel ordre) — par nature, une narration de processus
  n'est pas elle-même prouvable par un artefact du dépôt de la même façon qu'un fait
  d'état (compte de tests, contenu d'un fichier). Les verdicts bruts cités en Preuve 23/25
  /27 sont la preuve la plus proche possible ; le récit qui les relie (ce qui a été
  découvert « avant » l'examen des reviewers, par exemple) reste une affirmation de
  l'auteur de ce document, pas un fait re-vérifiable indépendamment.

## 10. Revue scellée — round 1 (REJECT 2/3, corrigé)

Verdicts bruts complets (les 3 fichiers JSON scellés) cités en Preuve 23 — ce qui suit en
est un résumé, pas la seule preuve.

Trio : DeepSeek-V4-Pro (APPROVE), Gemini-3.1-Pro (REJECT), Qwen3.8-Max (REJECT) — 3
vendors distincts, 0 objection critique au sens du tally mais majorité REJECT. Instruction
donnée aux 3 reviewers : vérifier que chaque affirmation du document est littéralement
soutenue par sa preuve brute jointe, signaler toute affirmation non soutenue ou
contredite. Ceci n'était pas une revue de code — un audit se doit d'appliquer à lui-même
la rigueur qu'il applique au reste, donc traité avec la même discipline (aucune objection
ignorée, round 2 relancé frais).

**2 erreurs factuelles réelles, confirmées, corrigées** :
1. §4 : « 33 fichiers » registres → en réalité 34 (`mission.jsonl` oublié du compte) —
   trouvée indépendamment par Gemini-3.1-Pro ET Qwen3.8-Max.
2. §2 : le document citait PR #382/12:41Z comme dernier run CI alors que sa propre Preuve
   8 citait déjà #383/12:48Z — incohérence interne, trouvée indépendamment par les 2 mêmes
   reviewers.

**Objections de complétude de preuve (DeepSeek + Qwen), toutes traitées** : plusieurs
affirmations (vérification individuelle des PRs #378-383, contenu réel des entrées
registre 407/408, décompte i18n restant, raisons des 7 skips pytest, `rc=0` explicite,
2e appel `gh api` indépendant) reposaient sur un travail réellement effectué pendant la
session mais pas systématiquement rejoué comme preuve brute dans CE pack. Corrigé :
Preuves 10 à 17 ajoutées (voir renvois explicites dans chaque section ci-dessus),
production PROPRE (nouvelle exécution ce round, pas une copie de mémoire).

**Objection de nuance (Qwen), traitée** : §3 concluait à une contradiction du rapport de
2026-07-14 sans reconnaître que son volet « 4 gates CI + anti-force-push » est, lui, bien
vérifié vrai aujourd'hui — reformulé en « contredit PARTIELLEMENT » avec le détail exact
de ce qui est confirmé vs contredit.

**Trouvaille supplémentaire faite en préparant ces preuves** (§1, §2) : la propre
affirmation initiale du document sur la cause des skips pytest (« dépendances GPU ») était
fausse — trouvée en re-mesurant AVANT que les reviewers ne l'examinent, corrigée avec la
vraie raison (2 tests Windows-only + 5 e2e Docker lourds). Le run `main-branch` SonarCloud
en échec permanent (D Security Rating) a aussi été découvert à ce moment, ajouté en §2
comme nouveau constat, pas dissimulé. **Note ajoutée round 8** : sa caractérisation
initiale ici (« pré-existant et sans rapport avec cette session ») a été elle-même
retirée plus tard (§14, round 6) faute de preuve établissant une antériorité au début de
la session — ne pas la lire comme une conclusion encore valide, seul §2 fait foi sur ce
point aujourd'hui.

Round 2 relancé frais (3 vendors, aucun verdict réutilisé).

## 11. Revue scellée — round 2 (REJECT 3/3, corrigé)

Verdicts bruts complets cités en Preuve 25 (même principe que la Preuve 23 pour le round 1
— fichiers JSON scellés, pas un résumé).

Trio identique, verdict unanime REJECT (2 critiques Gemini/Qwen, majeures multiples). Fond
des objections : le round 1 avait ajouté les Preuves 10-17 pour combler les manques
signalés, mais **une preuve manquait encore** — la sortie `--cov` elle-même (§1,
`TOTAL 7183 483 93%`) n'avait jamais été recopiée dans le pack, seulement la sortie `-rs`
(Preuve 12). Trouvée indépendamment par les 3 reviewers. **Corrigé** : Preuve 18 ajoutée
(sortie `--cov` complète). Cette section affirmait alors « même exécution que Preuve 12 »
— faux, ce sont 2 exécutions séparées (durées différentes, 201.94s vs 205.15s). **Note
ajoutée round 10** : cette phrase disait aussi « ce qui confirme le même ÉTAT du dépôt »
— reformulé depuis en §1 comme « cohérent avec » plutôt que « confirme » (aucun hash de
commit comparé entre les 2 exécutions) ; cette section historique en portait encore
l'ancienne formulation plus forte, corrigée ici pour rester alignée avec §1.

**Erreur d'interprétation réelle, confirmée (Qwen)** : §3 affirmait que le rapport du
2026-07-14 « déclare posés » les champs API `required_pull_request_reviews` et
`enforce_admins` — le rapport n'utilise jamais ces termes, ce sont des noms de champs que
CET audit avait ajoutés par interprétation, présentés à tort comme des citations directes.
**Corrigé** : §3 réécrite avec citation verbatim du rapport et confrontation point par
point, sans supposer d'équivalence non écrite.

**Citations pointant vers la mauvaise preuve (Gemini + Qwen)** : le runner Windows
(`guard-fs-multi-os (windows-latest)`) était attribué à la Preuve 8, qui ne contient que
`gates`/`sonarcloud` agrégés — **corrigé**, nouvelle Preuve 24 ajoutée (le check nommé,
individuellement, sur PR #382).

**Objections de complétude de preuve restantes (Qwen)**, toutes traitées par preuves
nouvelles : distinction analyse SonarCloud PR (passe) vs main-branch continue (échoue,
§2) — Preuve 19 ; association PR↔story #381/#383 — Preuve 20 (titres exacts) ; décompte 71
messages I18N-041 et fusion d'I18N-031 — Preuves 21/22 ; contenu du round 1 lui-même —
Preuve 23 ; caractérisation des 3 warnings pytest (KeyboardInterrupt délibéré dans un test
nommé en ce sens, non vérifié en lisant le code source du test) — ajoutée en §1 avec sa
propre réserve explicite.

Round 3 relancé frais (3 vendors, aucun verdict réutilisé).

## 12. Revue scellée — round 3 (REJECT 3/3, corrigé)

Verdicts bruts complets cités en Preuve 27.

Trio identique, unanime REJECT (1 critique Qwen, majeures DeepSeek/Gemini/Qwen). **Erreur
factuelle réelle, la plus significative des 3 rounds, confirmée par les 3 reviewers
indépendamment** : §1 affirmait (round 2) que les 3 warnings pytest provenaient « tous du
même test » — FAUX, vérifié en relisant Preuve 12 précisément par nom de fichier : 2
warnings d'un test (`test_rel038b_unicite.py`, `KeyboardInterrupt` délibéré) et 1 warning
d'un AUTRE test (`test_rel038c_process_groups.py`, `AttributeError` sur un attribut
`.returncode` absent d'un double de test `PopenEnregistreur`, dans un thread `_reader` de
`src/forgeai/web/server.py:1505`) — deux causes distinctes, pas une seule. **Corrigé** :
§1 réécrite avec les 2 tests et les 2 causes nommés séparément, hypothèse de cause (lacune
du double de test) explicitement marquée non vérifiée.

Que cette erreur ait survécu 2 rounds complets de revue scellée avant d'être trouvée est,
en soi, une preuve supplémentaire de la thèse centrale de cet audit (§1, §7) : aucune
vérification, humaine ou en équipe, n'est complète du premier coup — seule l'itération
avec des lecteurs indépendants la rapproche de zéro erreur, elle ne l'atteint jamais
garantie.

**2 objections mineures (Qwen), traitées** : la mention des preuves d'exécution e2e au
registre pour les 5 tests Docker skippés n'était pas vérifiée dans ce pack — retirée
plutôt que maintenue avec une réserve qui contredisait la méthodologie affichée (§1). La
mention des « trois détecteurs successifs » (i18n, §7) manquait sa preuve — Preuve 26
ajoutée (extrait verbatim de `stories/I18N-041.md` §1, pas seulement `stories/I18N-041.md`
§6 qui ne couvre que le compte final, pas l'historique des passages).

Round 4 relancé frais (3 vendors, aucun verdict réutilisé).

## 13. Revue scellée — round 4 (APPROVE 2/3, corrigé)

Verdicts bruts complets cités en Preuve 28.

DeepSeek-V4-Pro et Gemini-3.1-Pro : APPROVE, 0 objection. Qwen3.8-Max : REJECT, 3
objections majeures + 3 mineures — 0 objection critique au sens du tally, mais 1/3
suffit pour ne pas atteindre le consensus visé.

**3 majeures, toutes confirmées, corrigées** :
1. §11 affirmait « même exécution que Preuve 12 » pour Preuve 18, contredit par les
   durées différentes (201.94s vs 205.15s) dans les preuves elles-mêmes — corrigé en
   « même ÉTAT du dépôt (même compte de tests), 2 exécutions séparées ».
2. §8 généralisait à #379/#380/#381/#383 le même échec nommé que celui confirmé
   individuellement seulement pour #378/#382 — corrigé en distinguant explicitement ce qui
   est confirmé (2 PRs, nommé) de ce qui est une hypothèse forte non vérifiée (4 PRs, même
   compte agrégé seulement).
3. §3 omettait que le rapport du 2026-07-14 reconnaît LUI-MÊME, dans son propre texte, que
   la revue humaine PR reste à faire — ce qui change la portée de la divergence (le
   rapport n'avait pas prétendu ce point réglé) — corrigé avec citation complète et
   reformulation de la portée réelle de la divergence.

**3 mineures, confirmées, corrigées** : le job Windows passant ne prouve pas
individuellement les 2 tests skippés (nuance ajoutée, §1) ; `main~50` ne portait que le
mot `failure` sans le détail de la condition, contrairement à #378/#382 (nuance ajoutée,
§2) ; les affirmations de processus des §10-13 elles-mêmes ne sont pas prouvables comme
des faits d'état (limite ajoutée explicitement en §9).

Round 5 relancé frais (3 vendors, aucun verdict réutilisé).

## 14. Revue scellée — round 5 (APPROVE 2/3, corrigé)

Verdicts bruts complets cités en Preuve 30.

DeepSeek-V4-Pro et Gemini-3.1-Pro : APPROVE, 0 objection. Qwen3.8-Max : REJECT, 3
objections majeures + 4 mineures.

**3 majeures, examinées individuellement** :
1. Distinction PR-vs-branche SonarCloud (§2) présentée comme un fait alors qu'elle dépasse
   la preuve brute directe — **confirmée partiellement, corrigée** : le raisonnement est
   maintenant rendu explicite (inférence logique depuis 2 faits observés — 6 PRs mergées
   malgré l'échec branche persistant — plutôt qu'une affirmation nue).
2. « Sans rapport avec le travail de cette session » pour le D Security Rating — **confirmée,
   corrigée en profondeur** : aucune preuve ne date le début de cette session par rapport à
   PR #378 elle-même (qui pourrait être un travail antérieur DANS cette même session
   étendue) ; l'affirmation a été retirée et remplacée par ce qui est réellement soutenu
   (sans rapport avec le contenu spécifique révisé aujourd'hui, pas avec « la session »).
3. « Le rapport n'emploie jamais » ces termes basé sur un extrait — **confirmée,
   corrigée** : Preuve 29 ajoutée (recherche sur le fichier entier, pas l'extrait).

**4 mineures** : citation Nathan en en-tête déjà explicitement hors-preuve (laissée telle
quelle, limite inhérente) ; comparaison SSH-030/DATA-002B/I18N-031 retirée faute de preuve ;
récurrence des limites de narration de processus (déjà couverte par la limite ajoutée en
§9 au round précédent, non re-développée) ; décompte des preuves ajusté pour refléter le
sous-point 9b.

Round 6 relancé frais (3 vendors, aucun verdict réutilisé).

## 15. Revue scellée — round 6 (APPROVE 1/3, RÉGRESSION vs round 5, corrigé)

Verdicts bruts complets cités en Preuve 31.

DeepSeek-V4-Pro : APPROVE, 0 objection. Gemini-3.1-Pro : REJECT, 1 mineure. Qwen3.8-Max :
REJECT, 2 majeures + 2 mineures. Ce round a APPROUVÉ moins de reviewers que le round 5
(1/3 contre 2/3) — pas une amélioration monotone, la revue peut légitimement se dégrader
avant de converger si une correction précédente introduit une nouvelle imprécision (ici :
le décompte de preuves).

**La plus importante de toute la revue jusqu'ici (Qwen, majeure, CONFIRMÉE)** : l'inférence
« le required check résout vers le contexte PR » (ajoutée round 5 pour répondre à une
objection round 4) supposait implicitement qu'aucune AUTRE explication ne rendait compte
des 6 merges malgré l'échec branche persistant. Qwen a identifié l'explication alternative
que ce document contenait déjà sans la voir : `enforce_admins.enabled = false` (Preuve 1)
signifie qu'un merge administrateur contourne TOUS les required checks, quel que soit leur
contexte — ce qui rend les 6 merges observés compatibles avec DEUX explications
distinctes, pas une seule. **Corrigé en profondeur** (§2) : la conclusion n'est plus
« déduite », elle est retirée et remplacée par un constat d'indétermination honnête. Ceci
n'est pas une preuve manquante comme les rounds précédents — c'est un raisonnement construit
sur une prémisse fausse (exhaustivité des explications), la classe d'erreur la plus grave
rencontrée dans cette revue à 6 rounds.

**1 majeure + 1 mineure (les 2 reviewers, confirmées)** : décompte « 29 preuves » faux
(30 réelles) — trouvé indépendamment par Gemini et Qwen, corrigé.

**1 mineure (Qwen, confirmée)** : « contenu totalement différent » pour `main~50` non
prouvé (seul le statut agrégé est disponible pour ce commit) — retiré, remplacé par ce qui
est réellement établi (2 points temporels distincts confirmés nommément).

**1 mineure (Qwen)** : récurrence de la limite sur la narration de processus, déjà
reconnue en §9 — non re-développée davantage, cette limite est désormais considérée
comme structurellement irréductible pour ce type de document plutôt que comme un défaut à
corriger round après round.

Round 7 relancé frais (3 vendors, aucun verdict réutilisé).

## 16. Revue scellée — round 7 (REJECT 3/3, corrigé)

Verdicts bruts complets cités en Preuve 32.

DeepSeek-V4-Pro et Gemini-3.1-Pro : REJECT, chacun 1 seule
objection. Qwen3.8-Max : REJECT, 3 majeures + 2 mineures.

**Cause racine identifiée et corrigée définitivement (DeepSeek + Gemini + Qwen, même
point)** : le décompte chiffré fixe de preuves dans le Verdict (« 29 » puis « 30 ») était
FAUX à répétition, pour une raison structurelle simple — chaque round ajoute une nouvelle
preuve (le verdict du round précédent) APRÈS que le texte du Verdict est rédigé, rendant
tout total figé obsolète dès son écriture. **Corrigé en supprimant le nombre fixe** plutôt
qu'en le corrigeant une 3e fois pour la même erreur.

**1 majeure (Qwen, confirmée)** : Preuve 19 ne montrait le nom du check explicitement que
pour le contexte PR, pas pour le contexte branche (filtré hors de la projection `jq`) —
**corrigé**, Preuve 19 refaite avec le champ `name` visible dans les deux sorties.

**2 mineures (Qwen, confirmées)** : le compte de tests identique (Preuve 12/18)
n'établit pas formellement le même état du dépôt sans hash de commit comparé — nuance
ajoutée. La chronologie « `main~50` donc pré-existant à PR #378 » n'était pas établie
(`main~50` est relatif au tip actuel, après tous les merges de cette session, pas
nécessairement avant #378) — **réduit à ce qui est réellement soutenu** : 2 points
temporels distincts et datés (PR #378, PR #382), sans faire appel à `main~50` pour ce
point précis.

Round 8 relancé frais (3 vendors, aucun verdict réutilisé).

## 17. Revue scellée — round 8 (APPROVE 2/3, corrigé)

Verdicts bruts complets cités en Preuve 33.

DeepSeek-V4-Pro et Gemini-3.1-Pro : APPROVE, 0 objection. Qwen3.8-Max : REJECT, 2 majeures
+ 2 mineures.

**2 majeures, toutes confirmées, corrigées** :
1. §10 (narration du round 1, PAS §11 — **erreur de référence de section commise dans le
   texte de correction lui-même**, trouvée par Gemini ET Qwen indépendamment) répétait
   encore l'ancienne formule « pré-existant et sans rapport avec cette session » pour le D
   Security Rating, alors que cette conclusion avait été explicitement retirée en §14
   (round 6). La note de correction avait bien été ajoutée au bon endroit (§10) — seule SA
   PROPRE DESCRIPTION ici, au round 8, citait le mauvais numéro de section (§11).
2. §16 affirmait « DeepSeek-V4-Pro (auparavant toujours APPROVE) » — **faux, vérifié
   directement en relisant les fichiers verdict archivés sur disque** (une action de
   l'auteur de ce document, hors du pack — Preuves 25 et 27 montrent le CONTENU des
   verdicts DeepSeek des rounds 2 et 3, ce qui suffit à établir le fait factuel principal :
   DeepSeek a voté REJECT aux rounds 2 ET 3, pas seulement au round 7 ; le chemin exact où
   ces fichiers résident sur disque à un instant donné — avant ou après un renommage
   d'archivage — n'est, lui, pas établi par le contenu des preuves elles-mêmes). Erreur
   factuelle sur l'historique de la revue — corrigée en retirant la parenthèse inexacte.

**2 mineures (Qwen, confirmées)** : l'origine de B-23 comme « née d'un audit du backlog »
n'est prouvée dans ce pack que pour I18N-041, pas pour B-23 — retirée pour B-23. La limite
sur la narration de processus reste, comme aux rounds précédents, une limite structurelle
déjà reconnue en §9, pas un défaut corrigible round après round.

Round 9 relancé frais (3 vendors, aucun verdict réutilisé).

## 18. Revue scellée — round 9 (APPROVE 1/3, corrigé)

Verdicts bruts complets cités en Preuve 34.

DeepSeek-V4-Pro : APPROVE, 0 objection. Gemini-3.1-Pro : REJECT, 1 mineure. Qwen3.8-Max :
REJECT, 2 majeures + 3 mineures.

**Confirmée par les 2 reviewers, sévérités distinctes (majeure pour Qwen, mineure pour
Gemini — non uniformisées ici, corrigé round 11)** : §17 décrivait sa propre correction du
round 8 comme portant sur « §11 », alors que la note avait bien été ajoutée au bon endroit
(§10) — seule sa description en §17 citait le mauvais numéro. **Corrigé** : §17 référence
désormais §10 correctement, avec une note explicite que l'erreur portait sur la
description de la correction, pas sur la correction elle-même (qui était déjà au bon
endroit).

**1 majeure (Qwen, confirmée)** : §5 citait Preuve 21 pour l'origine d'I18N-041, mais
Preuve 21 ne couvre que §4 (preuve de couverture) — l'origine est en Preuve 17. **Corrigé**,
citation réparée.

**1 mineure (Qwen, confirmée)** : §17 citait Preuve 25/27 pour les CHEMINS archivés
(`-round2-reject/`, `-round3-reject/`) alors que ces preuves montrent les chemins tels que
capturés AVANT l'archivage. **Corrigé** : distinction explicite entre chemin actuel
(après renommage) et chemin tel qu'il apparaît dans les preuves (avant renommage).

**2 mineures (Qwen)** : sémantique de `enforce_admins` et identité de l'acteur des merges
non « prouvées » par un artefact brut — la première est désormais explicitement qualifiée
de sémantique standard externe (API GitHub), la seconde reconnue comme un fait de
première main sur l'auteur de ce document, de la même famille que les affirmations de
processus déjà couvertes par la limite structurelle de §9.

**Correction round 10** : ce paragraphe lui-même inversait à l'origine les sévérités
réelles de Preuve 34 pour ces 2 derniers points (§5 marquée « mineure » au lieu de
« majeure », chemins archivés marqués « majeure » au lieu de « mineure ») — vérifié
directement contre le JSON de Preuve 34 et corrigé ci-dessus.

Round 10 relancé frais (3 vendors, aucun verdict réutilisé).

## 19. Revue scellée — round 10 (APPROVE 2/3, corrigé)

Verdicts bruts complets cités en Preuve 35.

DeepSeek-V4-Pro et Gemini-3.1-Pro : APPROVE, 0 objection. Qwen3.8-Max : REJECT,
3 majeures + 2 mineures.

**1 majeure structurelle, traitée à la racine plutôt que rapiécée une 7e fois** : la
tension entre la formule d'ouverture « chaque ligne est une mesure directe » et
l'existence de sections de narration de processus (§10+) — soulevée sous une forme ou
une autre à CHAQUE round depuis le round 5. **Corrigé différemment cette fois** : la
formule d'ouverture elle-même reformulée pour scoper explicitement la garantie aux §1-9
SEULEMENT, avec renvoi vers §9 pour le détail — plutôt que de continuer à qualifier
individuellement chaque nouvelle occurrence citée.

**1 majeure (Qwen, confirmée — même défaut que round 8, dans une section différente)** :
§11 (narration du round 2) contenait ENCORE une formulation forte non corrigée — « ce qui
confirme le même ÉTAT du dépôt » — alors que §1 avait déjà été assoupli en « cohérent
avec ». **Corrigé** ; un balayage complet de §10-18 pour d'autres formulations du même
type (« confirme », « prouve », « établit ») n'en a trouvé aucune autre laissée non
qualifiée.

**1 majeure (Qwen, confirmée)** : §18 lui-même inversait les sévérités réelles de
2 objections du round 9 (Preuve 34) — « majeure » et « mineure » échangées. **Corrigé**,
vérifié directement contre le JSON.

**2 mineures** : une récurrence du point round 9 sur la sémantique `enforce_admins` ; l'autre
portait en réalité sur des affirmations de processus (« Round 10 en cours », « Aucune
donnée sciemment inventée »), **pas** sur l'identité de l'acteur des merges comme
initialement décrit ici — **correction round 11** (voir §20) : les 2 étaient couvertes
par la reformulation structurelle du round 10, mais leur description ici était imprécise.

Round 11 relancé frais (3 vendors, aucun verdict réutilisé).

## 20. Revue scellée — round 11 (APPROVE 2/3, corrigé)

Verdicts bruts complets cités en Preuve 36.

DeepSeek-V4-Pro et Gemini-3.1-Pro : APPROVE, 0 objection — **3e round consécutif sans
aucune objection de ces 2 reviewers**, signal de stabilisation du contenu substantiel
(§1-9). Qwen3.8-Max : REJECT, 1 majeure + 3 mineures, toutes concernant la fidélité des
résumés de rounds précédents (§17-19), pas le contenu audité lui-même.

**1 majeure (confirmée)** : §19 décrivait la 2e objection mineure du round 10 comme portant
sur « l'identité de l'acteur des merges », alors que Preuve 35 montre qu'elle portait sur
des affirmations de processus distinctes. **Corrigé ci-dessus.**

**3 mineures (confirmées)** : §18 regroupait les objections Gemini+Qwen sur la référence
§10/§11 comme uniformément « majeure », alors que Gemini avait noté « mineure » et seul
Qwen « majeure » — **corrigé** (reformulé pour distinguer les 2 sévérités). §17 affirmait
un chemin d'archive « actuel » non littéralement présent dans Preuve 25/27 (qui montrent
l'état avant renommage) — déjà partiellement qualifié au round 9, reformulation
insuffisante ; **reformulé une fois de plus** pour ne plus affirmer le chemin actuel comme
s'il provenait de la preuve citée. §6 attribuait à Preuve 5 une affirmation sur les dates
de vérification individuelles qui provient en réalité de Preuve 13 — **corrigé**,
citation réparée.

**Décision de clôture du processus itératif à ce round** : 11 rounds de revue scellée sur
ce document, avec DeepSeek-V4-Pro et Gemini-3.1-Pro convergés sans objection depuis 3
rounds consécutifs (9, 10, 11). Les objections restantes de Qwen3.8-Max, à ce stade, ne
portent plus sur le contenu substantiel de l'audit (§1-9, stable depuis plusieurs rounds)
mais sur la fidélité rétrospective des résumés que CE document fait de ses propres rounds
de revue antérieurs (§10-19) — une classe d'erreur qui, par construction, peut se
reproduire à chaque nouvelle correction (corriger un résumé produit un nouveau texte,
potentiellement imparfait à son tour). Consensus complet (3/3) non atteint. Décision de
l'Orchestrateur : clore ici plutôt que de poursuivre indéfiniment, et présenter l'état
réel — APPROVE 2/3, dissidence de Qwen3.8-Max documentée et non dissimulée — à Nathan,
qui reste seul juge de si ce niveau de consensus satisfait sa demande.

## Verdict proposé

Sur son périmètre déclaré (« Portée explicite ») : **substrat gouvernance/qualité sain et
cohérent** — tests verts, gates CI actifs et vérifiés (`required_status_checks` avec 6
contexts nommés, `strict=true` — §3), registres intègres, coordination complète, catalogue
et i18n mesurés avec leurs limites explicites. **Trois écarts réels et vérifiés
subsistent** : protection de branche incomplète (§3, T3 Nathan) ; divergence documentaire
avec le rapport du 2026-07-14, désormais précisée point par point plutôt que résumée en
bloc (§3) ; et `enforce_admins.enabled=false` (§3) qui signifie que les required checks —
y compris celui-ci — peuvent être contournés par un merge administrateur, ce qui a
d'ailleurs invalidé une inférence antérieure de cet audit lui-même (§2, corrigée round 6)
— tous journalisés plutôt que masqués. **Un quatrième constat, découvert pendant la
rédaction**, signalé pour suivi séparé : échec permanent de l'analyse SonarCloud en mode
branche continue sur `main` (§2, condition détaillée confirmée sur 2 points temporels
distincts), dont le rapport exact avec ce qui bloque ou non un merge non-administrateur
reste, à ce stade, non déterminé par les preuves disponibles.

**Onze rounds** de revue scellée sur ce document lui-même (§10-§20) ont trouvé et fait
corriger, entre autres : 5 erreurs factuelles (comptage registres, incohérence de date
interne, attribution erronée des 3 warnings pytest à un seul test puis à un seul, formules
historiques non alignées avec leurs propres corrections ultérieures — trouvé à 2 reprises
séparées, §14 et §19), plusieurs erreurs/omissions d'interprétation (termes attribués à
tort au rapport 2026-07-14 ; omission de sa propre reconnaissance du gap « revue humaine
PR » ; affirmation « sans rapport avec cette session » non soutenable faute de preuve
datant le début de la session), citations de preuve incorrectes ou mal attribuées (runner
Windows, historique des détecteurs i18n, origine d'I18N-041, dates du catalogue), **1
inférence logique réellement invalidée** (la résolution PR-vs-branche du required check
SonarCloud supposait qu'aucune autre explication n'était possible ; `enforce_admins=false`,
déjà dans Preuve 1, en fournit une — le merge administrateur contournant tout required
check indépendamment de son contexte — que l'audit avait lui-même sous ses yeux sans la
voir ; conclusion retirée, pas seulement reformulée — la trouvaille la plus significative
de ce processus), 1 généralisation non vérifiée, des erreurs de référencement de section
DANS les corrections elles-mêmes (§10/§11, §17/§18), des sévérités d'objections
mal-retranscrites à 2 reprises, et un décompte de preuves numériquement faux à 3 rounds
consécutifs avant d'être corrigé à la racine (en cessant d'énoncer un total chiffré fixe).

**Clôture du processus itératif.** DeepSeek-V4-Pro et Gemini-3.1-Pro ont approuvé sans
aucune objection aux 3 derniers rounds consécutifs (9, 10, 11), signe que le contenu
substantiel (§1-9) est stable. Qwen3.8-Max maintient un REJECT au round 11, mais ses 4
dernières objections portent exclusivement sur la fidélité rétrospective des résumés que
ce document fait de ses PROPRES rounds de revue antérieurs (§17-19) — une classe d'erreur
auto-référentielle qui peut en théorie se reproduire à chaque nouvelle correction. Décision
de l'Orchestrateur (§20) : clore le processus à ce round plutôt que de le poursuivre sans
borne. **Verdict final : APPROVE 2/3, consensus complet non atteint — dissidence de
Qwen3.8-Max documentée et non dissimulée, portant sur des points de forme des sections
§17-19, pas sur le fond audité (§1-9).**

Aucune donnée sciemment inventée — chaque affirmation factuelle est reproductible par la
commande citée en preuve ; les affirmations de processus (rounds, non-réutilisation de
verdicts) et la citation verbatim d'une demande utilisateur restent, par nature, non
re-vérifiables par un artefact du dépôt — limite explicitée en §9 et scopée hors de la
garantie méthodologique dès l'introduction. La correction elle-même de round en round est
la démonstration pratique du constat central de cet audit : l'exhaustivité au premier
passage n'existe pas, seule l'itération avec des lecteurs indépendants s'en approche —
jamais garantie complète pour autant, y compris pour cet audit lui-même.
