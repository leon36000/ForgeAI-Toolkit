# RC1-013 incrément 2a — inventaire codes de sortie + variables d'environnement (#443)

Suite de l'incrément 1 (PR #556, mergée). Critères restants ciblés par cet incrément :
- [ ] inventaire codes-retour/variables (seules commandes+options sont couvertes actuellement).

Les autres critères (FR/EN → #555, exemples auto-vérifiés → incrément 2b distinct, exemptions
inutiles → aucun mécanisme d'exemption n'existe) restent hors périmètre de 2a.

## Reconnaissance déjà faite (fournie en contexte, ne pas refaire)

Un inventaire EXHAUSTIF des codes de sortie numériques significatifs (≠0, ≠1) de
`src/forgeai/cli.py` a déjà été produit par lecture complète du fichier (1724 lignes) + traçage
de chaque `return <N>` jusqu'à sa condition de déclenchement — fourni intégralement dans
`stories/RC1-013-increment2a-rapport-codes-sortie.md` (à créer depuis le texte ci-dessous, ANNEXE
DE CETTE STORY, ne JAMAIS re-dériver ces valeurs par une nouvelle lecture).

4 variables d'environnement déjà identifiées par lecture directe :
- `FORGEAI_LANG` (ligne ~1369, `_run()`) : override de la langue par défaut de la CLI entière
  (`--lang`), retombe sur `"fr"` si absente ou invalide.
- `FORGEAI_DEBUG` (ligne ~1717, `main()`) : si définie (non vide), les exceptions non prévues par
  un handler sont RE-LEVÉES avec traceback complet au lieu d'être capturées proprement (message +
  `return 1`).
- `args.password_env` (mécanisme, PAS une variable fixe) : `node add --password-env NOM_VAR` —
  le NOM de la variable à lire est un paramètre CLI, documenté via l'option elle-même, pas comme
  variable d'environnement fixe nommée.
- Idem `_read_secret(env_var, ...)` (fonction interne partagée, appelée avec un `env_var`
  paramétrable selon la commande) — même traitement que ci-dessus.

## Décision de conception (pourquoi pas un inventaire 100% automatique par AST)

L'inventaire commandes/options existant (`gate_docs.py::_inventaire_cli`) fonctionne par AST
simple car `add_parser`/`add_argument` sont des appels DIRECTS et STRUCTURELS, faciles à
reconnaître syntaxiquement. Les codes de sortie, eux, nécessitent de comprendre la SÉMANTIQUE de
CHAQUE branche conditionnelle (quelle exception, quelle condition métier) — un vrai analyseur de
flux de contrôle serait disproportionné et fragile (faux sens probables). Approche retenue,
cohérente avec le pattern déjà établi dans ce dépôt pour d'autres données structurées écrites à
la main et gouvernées (`governance/ruff-classification.json`,
`governance/branch-coverage-categories.json`) : un **registre JSON écrit à la main** (source de
vérité humaine, review-visible) + un **gate de cohérence mécanique** (vérifie que chaque entrée du
registre correspond toujours à la RÉALITÉ du code — pas un inventaire par AST, mais une DÉTECTION
DE DÉRIVE déterministe).

## Livrable attendu

1. **`Docs/exit-codes.json`** (nouveau, écrit à la main depuis l'annexe de reconnaissance) —
   schéma : `{"_schema": "exit-codes-v1", "codes_globaux": {"0": "succès", "1": "échec générique
   (exception non prévue)", "130": "interrompu (SIGINT/Ctrl-C)"}, "codes_par_commande": {
   "<commande>": [{"code": <int>, "ligne": <int>, "signification": "<texte court>"}]}}`. Une
   entrée par code significatif trouvé dans l'annexe (13 codes numériques distincts couvrant les
   21 commandes — certaines commandes/sous-verbes n'en ont aucun, uniquement 0/1, à ne PAS lister
   dans `codes_par_commande` pour elles).
2. **`scripts/gate_exit_codes.py`** (nouveau, même style que `scripts/gate_docs.py` fourni en
   contexte comme modèle) : charge `Docs/exit-codes.json`, pour CHAQUE entrée de
   `codes_par_commande`, lit `src/forgeai/cli.py` à la `ligne` indiquée (1-indexé) et vérifie
   qu'elle contient bien la sous-chaîne `return <code>` littérale — sinon anomalie bloquante
   (« le registre affirme le code X à la ligne Y, mais cette ligne ne contient plus `return X` —
   registre périmé, corriger `Docs/exit-codes.json` ou re-vérifier le code »). Mode `--report`
   (comme `gate_docs.py`) qui affiche juste le nombre d'entrées vérifiées sans échouer sur du
   contenu manquant dans la doc (séparé du mode par défaut, qui EST bloquant sur la vérification
   ligne↔code). `main(argv)` retourne un entier, jamais de `sys.exit` direct dans la logique
   testable.
3. **`.github/workflows/gates.yml`** : nouveau job bloquant `exit-codes` (même structure que le
   job `docs` existant, fourni en contexte) invoquant `python3 scripts/gate_exit_codes.py`.
4. **`Docs/reference/cli.md`** (fourni en contexte intégral) : ajouter DEUX nouvelles sections
   après l'introduction et AVANT la première commande (`## Codes de sortie` et `## Variables
   d'environnement`), contenu dérivé fidèlement de l'annexe de reconnaissance — codes globaux
   (0/1/130) + un tableau ou une liste par commande pour les 13 codes spécifiques trouvés (grouper
   par commande, citer le code et sa signification en une phrase claire) ; les 2 variables
   d'environnement globales (`FORGEAI_LANG`, `FORGEAI_DEBUG`) avec leur effet exact. Ne PAS
   toucher au reste du fichier (856 lignes existantes, sections par commande déjà rédigées).
5. **Tests** (`tests/test_gate_exit_codes.py`, nouveau, TDD, style `tests/test_...gate...`
   existant fourni en contexte comme modèle si trouvé) : cas nominal (registre cohérent avec le
   code, `main()` retourne 0), cas de dérive (ligne modifiée pour ne plus contenir le bon
   `return N`, `main()` retourne 1 avec message clair), fichier registre absent/invalide,
   `--report` n'échoue jamais sur une dérive (juste affiche), test structurel vérifiant que le
   nouveau job CI existe dans `gates.yml` et qu'il est dans `needs:` de l'agrégateur `tests`
   (même motif que `tests/test_rc1580_tests_aggregate.py`, fourni en contexte).

## Contraintes

- `Docs/exit-codes.json` est un fichier de DONNÉES écrit à la main — le contenu EXACT (codes,
  lignes, significations) doit venir de l'annexe de reconnaissance fournie, jamais deviné ou
  réinventé.
- Ne pas modifier `scripts/gate_docs.py` ni `Docs/BASELINE-CLI-DOC.json` (hors périmètre de cet
  incrément, déjà fonctionnels).
- Zéro nouvelle dépendance tierce.
