# REG-029B — Ancrer les checkpoints et détecter rollback/troncature

Issue #276. Dépendances livrées : REG-029A (complétude), TRUST-019B (HMAC Tier 1).

> **Révision 2** après revue d'architecture **NO-GO**. La révision 1 plaçait l'ancre dans un
> fichier versionné `Registres/CHECKPOINTS.jsonl`. **C'était faux et je le documente plutôt que de
> le masquer** : une PR peut tronquer le registre *et* réécrire l'ancre dans le même diff, et le
> gate reste vert. Ma justification (« réécrire l'ancre exige de réécrire l'historique de `main` »)
> était démentie par l'ADR elle-même, qui admet le contournement « **(a) passer par le même
> processus de PR** » (`ADR-TRUST-019A…:130-135`). L'ancre faisant autorité est donc `origin/main`,
> jamais un fichier de l'arbre en cours de revue.

## 1. État mesuré (lu, pas supposé)

**`verify()` n'inspecte jamais `seq`.** `src/forgeai/core/registre.py:174` : `seq` n'est lu que
pour formater les messages d'erreur.

**La troncature de queue laisse la chaîne parfaitement valide** — la boucle s'arrête plus tôt et
renvoie `None` (succès). Un registre **vide** est valide (`tests/test_registre.py:52`). Le test
existant qui « détecte une entrée supprimée » supprime la **genèse**, pas la fin.

**Trois chemins de défaillance ouverte mesurés** — c'est le défaut le plus grave possible pour un
gate, car il est silencieux :
1. `registre.py:83-88` — `_read_entries` renvoie `[]` si le fichier n'existe pas → `verify` renvoie
   `None` → `main()` imprime `OK … 0 entrées` et **sort 0**.
2. `gates.yml:55` utilise le glob shell `Registres/*.jsonl` : un fichier **supprimé** n'apparaît
   pas dans `argv`, donc n'est examiné par personne. `Registres/` vidé ⇒ toujours exit 0.
3. `registre_completude.py:90-91` — `charger` avale `FileNotFoundError` → `[]` → 0 anomalie.

**L'ADR l'avait prévu et délégué ici.** `CANON/adr/ADR-TRUST-019A-…md` : ligne 81 (rollback par
suppression de la fin → « **NON** localement ») ; lignes 89-93 (« une garantie *anti-rollback*
exige une **ancre externe** … le hash-chain seul ne l'offre jamais intrinsèquement ») ; ligne 125
(« **Ancrage externe périodique via l'historique Git/GitHub — RETENUE** ») ; lignes 220-222
(« Déléguer à un package d'implémentation séparé (`TRUST-019B`/`REG-029B`) »). Le §2.3 dénonce
nommément le gate actuel : `verify` « retourne succès sur une chaîne entièrement réécrite de façon
cohérente », donnant « un faux sentiment de sécurité ».

**Le registre** : 384 entrées à la mesure, `seq` 1→384 sans trou, `key_id` absent partout
(Tier 0 intégral), 33 fichiers sous `Registres/`.

## 2. Décision de conception, et ce qui a été réfuté

### L'ancre doit être hors de portée du diff en cours de revue
Un attaquant qui soumet une PR contrôle **tout l'arbre** de cette PR. Toute ancre vivant dans cet
arbre est modifiable dans le même commit que la fraude. La seule référence qu'une PR ne peut pas
réécrire est l'état **déjà mergé** : `origin/main` (ou la `merge-base`). C'est exactement le
Tier 2 de l'ADR (ligne 180).

### Réfutation 1 — « `actions/checkout` est en profondeur 1, l'historique est absent »
**Fait exact, conclusion inverse de la révision 1.** La réponse n'est pas de renoncer à l'ancre
git, c'est de **rendre l'historique disponible et d'échouer s'il ne l'est pas**. Le dépôt sait
déjà le faire : `scope-guard.yml:22-24` et `gates.yml:86-89` utilisent `fetch-depth: 0`.
Référence non résolvable ⇒ **échec dur nommant le remède**, jamais un SKIP.

### Réfutation 2 — « le contrôle de `seq` apporte l'anti-rollback »
**Faux, et la révision 1 le laissait croire.** `append` dérive `seq = len(entries)+1` sous verrou
exclusif (`registre.py:129-134`) : un écrivain légitime ne peut produire ni trou ni doublon, et le
chaînage `prev_hash` fige déjà tout le préfixe. Tronquer 384→383 puis appender un 384 forgé laisse
`seq` parfaitement contigu. Le contrôle de `seq` est conservé — il attrape l'**édition manuelle**
et une divergence du **second écrivain** du format (`src/forgeai/ide/guard_fs.py:359-388`) — mais
sa portée est énoncée honnêtement : cohérence, pas anti-rollback.

### Réfutation 3 — « émettre l'ancre dans un format ad hoc sous `Registres/` »
**Casserait le gate existant dès le premier jour.** `gates.yml:55` passe `Registres/*.jsonl` à
`verify`, qui exige `prev_hash == GENESIS` sur la première entrée (`registre.py:172-176`) : un
enregistrement `{registre, seq, hash}` sans `prev_hash` rend le job **rouge sur toutes les PR**.
Les checkpoints sont donc émis **via `registre.append()`**, `type="checkpoint"` — l'ancre est ainsi
couverte gratuitement par `verify`, et `anomalies()` ignore un type inconnu
(`registre_completude.py:53`), donc zéro anomalie de complétude nouvelle.

**Tier 0 obligatoire, jamais HMAC** : `gates.yml:55` appelle `verify` **sans `--key`**, et
`registre.py:190-191` renvoie une erreur pour toute entrée portant `key_id` sans clé fournie.
L'authenticité de l'ancre relève du Tier 2 git, pas d'un secret — ce qui retire toute question de
donnée confidentielle de cette story.

### Réfutation 4 — « un checkpoint versionné suffit, même sans git »
**Réfutée par la seconde revue d'architecture, et c'est l'attaque la plus courte trouvée.**
Tronquer le registre à **exactement `N` = `seq` du dernier checkpoint émis** : l'entrée `N` porte
toujours le hash ancré, le compte satisfait `N ≥ N`, `prev_hash` chaîne, `seq` reste contigu →
**gate vert**, et tout ce qui suivait le checkpoint (attestations `story_complete`,
`revue_scellee`) disparaît sans trace. La protection d'un checkpoint est donc bornée par sa
**latence d'émission**, pas par le hash-chain. C'est la raison décisive pour laquelle la référence
faisant autorité est `origin/main`, toujours au sommet : la fenêtre non protégée tombe à zéro.

### Invariant d'itération : la POPULATION, jamais les preuves
Les deux revues d'architecture se contredisaient ici, et aucune n'avait entièrement raison.
N'itérer que sur les **preuves** (ancres) laisse un registre neuf non protégé, et un ensemble
d'ancres **vide** produit zéro itération donc un succès silencieux. N'itérer que sur le **disque**
rend une **suppression** invisible, puisqu'un fichier absent n'est plus énuméré. La règle est donc
l'**UNION** : `sorted(set(reference) | set(courant))`.
- présent des deux côtés → `prefixe_conserve` ;
- présent en référence, absent du disque → **anomalie dure « supprimé »** ;
- présent sur le disque, absent de la référence → **nouveau légitime**, aucune anomalie.

L'énumération se fait **en Python** (`sorted(Path("Registres").glob("*.jsonl"))`), jamais par glob
shell : mesuré, `gates.yml:55` tourne sans `nullglob`, donc si `Registres/` disparaissait bash
passerait le littéral `Registres/*.jsonl`, `path.exists()` serait faux, et le gate **verdirait sur
un répertoire supprimé**. Le Python couvre d'un coup les chemins à espaces, Windows et la
suppression du répertoire.

### Décision
Un seul primitif, appliqué à deux usages :

**`prefixe_conserve(reference, courant)`** → `None` si et seulement si `courant[i]["hash"] ==
reference[i]["hash"]` pour tout `i < len(reference)` **et** `len(courant) >= len(reference)` ;
sinon le message de la première divergence. Appliqué à chaque registre contre `origin/main`, il
détecte troncature, rollback **et** réécriture totale cohérente — y compris de l'ancre elle-même.

Le contrôle est **piloté par la référence**, jamais par le glob : un registre connu d'`origin/main`
et devenu absent est un ROUGE, alors qu'un registre absent de la référence est un **nouveau
légitime** (aucune ancre exigée — sans cette règle, la PR REG-029B, qui crée son propre
`PATCH-REG-029B.jsonl`, échouerait à son propre gate).

`Registres/CHECKPOINTS.jsonl` n'est **pas** l'ancre : c'est une redondance vérifiable hors ligne
(audit d'un tarball sans git), documentée comme telle et jamais présentée comme une garantie.

### Base de référence de complétude — bornée par construction
REG-029A a mesuré une dette héritée (29 anomalies de schéma + 1 d'attestation). Un gate rouge au
premier jour ne servirait qu'à être désactivé ; mais une base de référence exprimée en **nombre**
serait un affaiblissement déguisé. Quatre propriétés cumulatives la rendent difficile à contourner :

1. **Identités, jamais un compte** : `(fichier, seq, type, champ)` — `seq` est stable, le registre
   étant append-only.
2. **Bornée par construction** : la base fige `(seq_max, hash)` par registre. Toute anomalie à
   `seq > seq_max` est **nouvelle par construction et ne peut jamais être baselinée**. C'est la
   propriété qui rend « il suffit d'élargir la base » impossible pour tout ce qui sera écrit
   désormais — et ce couple `(seq_max, hash)` **est** le checkpoint : un seul primitif, deux usages.
3. **Non croissante** : comparée à `git show origin/main:<base>`, toute identité **ajoutée** est un
   échec (en retirer est autorisé).
4. **Sans entrée périmée** : une identité qui ne correspond plus à une anomalie réelle doit être
   retirée, sinon échec — sans quoi la base devient une couverture générale.

### Ce que cette story ne promet pas
- L'ancre git n'est opposable à un compte **administrateur** que si `enforce_admins: true` est
  activé sur `main` (ADR §8.2). C'est une action de **configuration hors code** : sans elle, le
  gate promet plus que la configuration ne tient. Frontière T3 — Nathan seul.
- **L'ADR socle est encore `PROPOSED`** (`ADR-TRUST-019A…:3-4`). Signalé à Nathan ; la conception
  s'y conforme mais ne peut pas la ratifier.

## 3. TDAD — ce que chaque test rend impossible

- **G1 troncature de queue** — registre coupé après la référence : `verify()` renvoie **succès**,
  `prefixe_conserve` échoue. Test rouge exigé par l'ADR (lignes 235-237).
- **G2 réécriture totale cohérente** — chaîne entièrement reconstruite : `verify()` succès,
  ancrage échec (le `hash` au rang ancré diffère).
- **G3 avance légitime acceptée** — appender après la référence reste valide, sinon le contrôle
  interdirait le fonctionnement normal.
- **G4 registre connu devenu ABSENT ⇒ ROUGE** — nomme le fail-open mesuré : le glob ne voit pas un
  fichier supprimé. Le contrôle itère sur la **référence**.
- **G5 registre absent de la référence = nouveau légitime** — sinon la story échoue à son propre gate.
- **G6 `seq` : trou, doublon, recul détectés** — avec, dans le test, l'énoncé explicite que ce
  contrôle **n'apporte pas** l'anti-rollback (portée honnête).
- **G7 référence non résolvable ⇒ ÉCHEC DUR nommant le remède** (`fetch-depth: 0`), jamais un SKIP.
- **G8 ligne d'ancre illisible ⇒ échec dur**, jamais un `continue` silencieux.
- **G9 la base de référence est bornée** — une anomalie à `seq > seq_max` ne peut pas être
  baselinée, même si on l'ajoute au fichier.
- **G10 la base ne peut pas croître** — une identité ajoutée par rapport à `origin/main` = échec.
- **G11 le gate CI appelle réellement les contrôles** — assertion sur la chaîne de commande lue
  dans `.github/workflows/gates.yml`. Sans lui, on livrerait un mécanisme défini et jamais invoqué
  (aucun test ne lit ce fichier aujourd'hui).
- **G12 le checkpoint n'écrit jamais dans le registre vérifié** (lecture seule).

Mutations à prouver : neutraliser la comparaison de `hash` → G1+G2 rougissent ; neutraliser
l'itération par la référence → G4 rougit ; neutraliser la borne `seq_max` → G9 rougit.

## 4. Critères d'acceptation

- **CA1** `verify` et `forgeai.core.registre.main()` **inchangés** ; suite complète verte
  (mesurée, pas un nombre annoncé), **à l'exception documentée de `tests/test_proc.py`** : 5
  échecs **antérieurs à cette story**, prouvés identiques sur `origin/main` sans mes changements,
  causés par un chemin de venv contenant un espace et une interpolation non citée dans le test.
  Corriger ce défaut de portabilité est traité **hors de ce périmètre** ; le dire ici plutôt que
  d'annoncer une suite « verte » est la seule formulation honnête.
- **CA2** contrôle de `seq` (continuité, monotonie stricte, unicité) **appelé par le gate**, pas
  seulement défini — et sa portée réelle énoncée.
- **CA3** `prefixe_conserve` détecte troncature, rollback et réécriture totale ; chaque cas a un
  test qui échoue si le contrôle est retiré.
- **CA4** **strict par défaut** : la référence est obligatoire, l'échappatoire est un drapeau
  explicite réservé au bootstrap, jamais utilisé en CI. Aucun chemin où une donnée absente produit
  un succès.
- **CA5** base de référence = identités + borne `(seq_max, hash)` + non-croissance vérifiée contre
  `origin/main` + zéro entrée périmée.
- **CA6** logique **pure** dans `src/forgeai/core/registre_ancrage.py` (stdlib seule, aucun
  subprocess, aucun réseau — `git` est absent chez un utilisateur `pip install`) ; accès git confiné
  à `scripts/registre.py`, argv fixe, jamais de shell.
- **CA7** un **seul** argparse dans `scripts/registre.py` (`append`/`verify`/`completude`/
  `checkpoint`/`ancrage`). Le dispatch hors argparse de REG-029A est **corrigé, pas étendu** : il
  n'était pas découvrable par `--help`, ne composait pas, et n'était couvert par aucun test
  (`--cov=src/forgeai` ne mesure pas `scripts/`). `python3 scripts/registre.py completude <f>`
  reste valide.
- **CA8** `fetch-depth: 0` sur le job `registres` — modification de workflow **annoncée
  explicitement** dans le périmètre, pas glissée.
- **CA9** couverture ≥ 85 % sur le module neuf (**mesurée : 91 %**) ; aucun champ obligatoire ajouté au format d'entrée (le second
  écrivain `guard_fs.py:359-388` réplique le format et divergerait en silence).

## 5. Preuve mesurée sur le dépôt réel

Trois attaques rejouées sur `Registres/` (390 entrées, 33 registres), état restauré ensuite :

| Attaque | `verify` (intégrité) | `ancrage` (nouveau) |
|---|---|---|
| Troncature de queue, 35 entrées supprimées | `0 anomalie`, **rc=0** | `troncature detectee : courant 355, reference 390`, **rc=1** |
| Suppression totale de `PATCH-WEB-001.jsonl` | `0 anomalie`, **rc=0** | `registre supprime, 10 entrees perdues`, **rc=1** |
| Référence git introuvable | — | échec nommant le remède `fetch-depth: 0`, **rc=1** |

`verify` renvoie **succès** dans les deux premiers cas : c'est exactement le faux sentiment de
sécurité dénoncé par l'ADR §2.3, et la démonstration que le contrôle ajoute quelque chose.

Cliquet de complétude, mesuré : dette héritée (31 identités bornées) → **rc=0** ; une entrée
`revue_scellee` incomplète ajoutée au-delà de la borne → `31 couvertes, 2 nouvelles`, **rc=1**.

**Mutations vérifiées** : neutraliser la comparaison de `hash` → G14 rougit ; remplacer l'union
par une itération sur le seul disque → G14b rougit.

## 6. Défauts trouvés en cours de route, et ce qu'ils ont changé

- **Deux revues d'architecture successives ont invalidé ma conception initiale.** La v1 plaçait
  l'ancre dans un fichier versionné ; une PR pouvait tronquer le registre *et* réécrire l'ancre
  dans le même diff. La v2 a montré une attaque encore plus courte : tronquer à exactement le
  `seq` du dernier checkpoint laisse tout cohérent. D'où la référence `origin/main`, toujours au
  sommet, dont la fenêtre non protégée est nulle.
- **Mes tests étaient tous verts alors que la CLI plantait sur quatre appels** (`str` au lieu de
  `Path`, `verify` traité comme un itérable). Les gates CI n'appellent pas les fonctions pures :
  ils appellent `scripts/registre.py`. D'où les tests G13→G17, qui exercent le point d'entrée réel.
- **La réécriture de la CLI a cassé deux contrats non écrits** : `--payload-json` (un test hérité
  l'invoque littéralement ; `--payload` ne marchait que par abréviation argparse) et la ligne de
  sortie « chaîne intègre » (assertionnée par `test_guard_fs.py`). Restaurés à la lettre : une
  réécriture doit conserver la sortie **observable**, pas seulement le code de retour.
- **Ma fixture de test dépendait de la machine** : elle créait un dépôt git réel, donc les hooks
  git globaux du développeur s'exécutaient dedans et le test échouait — pour lui seul. Isolée par
  `core.hooksPath` neutralisé, conformément à l'exigence d'universalité du projet.

## 7. Revue scellée — tour R1 : REJECT 0/3, et ce qu'il a trouvé

Le trio a rejeté la première livraison à l'unanimité. Les trois objections critiques étaient
**fondées** ; la deuxième était un défaut de sécurité réel, pas une préférence de style.

1. **Couverture 72 % < 85 % (CA9).** Le chiffre était imprimé dans mon propre pack et je ne l'avais
   pas lu. Corrigé à **91 %** par des tests qui NOMMENT chacun la garde qu'ils protègent
   (G18→G22 : ancre incomplète, types faussement valides — `bool` est une sous-classe de `int` —,
   entrée sans `hash`, `seq` non entier, base malformée). Aucun test n'a été ajouté pour faire
   monter un nombre.
2. **`--base-ref-git` absent du gate ⇒ non-croissance silencieusement ignorée.** Le gate ne passait
   que `--base`, donc `reference_base` valait `None` et **la base pouvait être élargie dans la PR
   elle-même** — exactement le contournement que le cliquet devait fermer. C'est le même défaut
   que celui que je traquais, un niveau plus bas : un mécanisme câblé, mais amputé de la propriété
   qui lui donne son sens. Corrigé, et **G23** le prouve de bout en bout en élargissant réellement
   la base contre une référence git.
3. **CA1 littéral non satisfait** (`test_proc.py`). CA1 est désormais formulé honnêtement plutôt
   que satisfait en apparence.

La résolution du cas « base absente de la référence » distingue trois situations, car les
confondre recrée le fail-open : référence illisible ⇒ **échec dur** ; référence lisible mais base
absente ⇒ **légitime et ANNONCÉ** (c'est la PR qui introduit la base) ; base présente ⇒ contrôle
appliqué. Un contrôle inapplicable et muet est indiscernable d'un contrôle réussi.

## 8. Tour R2 — APPROVE 3/3, sceau `02518c90857a`, 0 objection bloquante

Une objection **mineure** relevée : le step `Complétude` utilise le glob shell `Registres/*.jsonl`
alors que §2 exige l'énumération en Python. L'objection est **fondée en classe** — l'incohérence
est réelle — mais **mesurée sur le cas qu'elle vise**, le répertoire supprimé est déjà
fail-closed deux fois dans le même job :

| Étape du job `registres` | `Registres/` supprimé |
|---|---|
| `verify` (glob shell, **inchangé** par CA1) | `OK Registres/*.jsonl: 0 entrées` — **rc=0**, le fail-open documenté au §1 |
| `ancrage` (énumération Python) | **rc=1**, 34 lignes `registre supprime` |
| `completude` (glob shell) | **rc=1**, base illisible → échec dur |

L'énumération Python de `ancrage` est donc bien ce qui porte la garantie sur la **population**,
exactement comme §2 l'affirme ; le glob du step `completude` n'est pas porteur, puisqu'il échoue
de toute façon par sa base. Le fail-open de `verify` subsiste — il est **antérieur**, couvert par
`ancrage` dans le même job, et le corriger toucherait `verify`, ce que CA1 interdit.

Cette section documente une **mesure**, pas une modification : le code scellé par le trio est
inchangé.
