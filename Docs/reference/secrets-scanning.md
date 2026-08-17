# Scan de secrets : GitGuardian vs Gitleaks (RC1-015, #445)

Deux détecteurs de secrets tournent en CI sur ce dépôt, avec des périmètres et des garanties
différents. Ni l'un ni l'autre ne remplace le second.

## Portée avant/après RC1-015

Avant #445, `.gitguardian.yaml` excluait globalement `**/*.md` du scan GitGuardian —
`stories/`, `Docs/`, `CANON/`, `evidence/reviews/**` (prompts, rapports de revue, verdicts
narrés en Markdown) n'étaient donc **jamais** analysés par ce détecteur, même si une valeur
sensible y apparaissait. Gitleaks (gate CI `gitleaks`, toujours actif indépendamment de
`.gitguardian.yaml`) réduisait déjà ce risque, mais **une couverture par un détecteur n'est pas
une preuve d'équivalence avec un autre** : ensembles de règles, heuristiques d'entropie et
politiques de validation en ligne diffèrent.

Depuis RC1-015, `.gitguardian.yaml` n'exclut plus aucun Markdown globalement. Seuls des chemins
non-Markdown préexistants restent exclus (`tests/fixtures/**`,
`src/forgeai/data/catalogue.json`, `LICENSE`, `.gitignore`) — voir
[`scripts/governance/check_gitguardian_scope.py`](../../scripts/governance/check_gitguardian_scope.py),
qui vérifie mécaniquement qu'aucune exclusion Markdown globale n'est réintroduite.

## Différences de portée mesurées

| | GitGuardian (`ggshield`) | Gitleaks |
|---|---|---|
| Détecteurs | Spécifiques par fournisseur (AWS, GitHub, Slack, OpenAI, …) + génériques | Règles regex génériques + quelques détecteurs spécifiques |
| Validation en ligne | Oui pour certains détecteurs (ex. `AWS Keys` : interroge l'API AWS, retourne `Validity: Invalid/Valid/Unknown`) | Non — détection structurelle uniquement |
| Config d'exclusion | `.gitguardian.yaml` (`secret.ignored_paths`, globs) | Pas de config dédiée dans ce dépôt (aucun `.gitleaks.toml`) — scanne tout par défaut |
| Mode local sans compte | `ggshield secret scan path` fonctionne pour la détection par motifs sans authentification (vérifié RC1-015 : `ggshield 1.53.0`) ; la remontée d'incidents vers le tableau de bord GitGuardian, elle, nécessite un compte | `gitleaks detect` entièrement local, aucune authentification |

## Preuve empirique (RC1-015)

Vérification réelle (pas seulement une lecture de la config), CLI `ggshield` installée dans un
venv scratch isolé (jamais dans l'environnement du produit — `dependencies=[]` reste stdlib pur) :

- **Scan comparatif** : `ggshield secret scan path --recursive` sur l'arbre complet, avec puis
  sans l'exclusion `**/*.md`. Résultat : 1961 fichiers scannés (exclusion retirée) contre 1710
  (exclusion présente) — 251 fichiers `.md` de plus couverts — **zéro nouvel incident** ; les 4
  incidents détectés sont identiques dans les deux scans, tous dans des fichiers `tests/*.py`
  déjà couverts avant #445 et déjà `known: true` (préexistants, sans rapport avec le Markdown).
- **Preuve positive de couverture** (pas seulement une absence de faux positifs) : un identifiant
  de clé d'accès AWS de forme plausible mais aléatoire, placé dans un fichier `.md` temporaire
  hors de tout chemin exclu, est correctement détecté (`AWS Keys`, `Validity: Invalid` — la clé
  inventée est bien vérifiée comme inactive auprès de l'API AWS, pas seulement reconnue par sa
  forme). Ce test prouve que les documents ordinaires sont désormais réellement analysés, pas
  seulement que la config a changé.
- Grep manuel ciblé (préfixes de clés connus : `sk-`, `ghp_`, `AKIA`, blocs `PRIVATE KEY`, JWT,
  affectations `password=`/`token=`/`api_key=` à haute entropie) <!-- proof:allow : exemple prose --> sur l'intégralité du corpus
  Markdown : les seules occurrences trouvées sont des valeurs de test explicitement fausses
  (identifiants nommés `FAKE_KEY` ou similaires, annotés `# proof:allow` ou `DO-NOT-LEAK` —
  littéraux non reproduits ici pour ne pas réintroduire dans ce document ce qui a justement été
  retiré ailleurs) situées dans
  `evidence/reviews/DATA-002/`, `evidence/reviews/DATA-003/` (packs de revue scellés historiques
  — leurs octets sont dans la préimage d'un `prompt_sha256`, jamais modifiés, voir RC1-011/#441)
  et `stories/ERR-041A.md` (corrigée dans cette même story : le littéral factice retiré de la
  prose, la fixture réelle vit uniquement dans `tests/test_redaction.py` où elle est déjà
  scannée).

## Limite assumée

Cette vérification utilise `ggshield` en mode CLI **non authentifié** (détection par motifs
locale uniquement). Le gate CI GitGuardian (`GitGuardian Security Checks`, intégration GitHub
App) peut disposer de détecteurs ou d'un accès au tableau de bord (secrets déjà connus/ignorés
côté GitGuardian) non strictement identiques à cette CLI locale. Cette preuve locale constitue
une évidence forte, pas une garantie byte-à-byte de parité avec le gate CI — pour la comparaison
PRÉCISE « CLI locale non authentifiée » vs « gate CI GitGuardian réel sur une PR », c'est ce
dernier qui fait foi. Ceci ne constitue PAS une affirmation de préséance de GitGuardian sur
`gitleaks` en général : les deux détecteurs restent complémentaires, aucun des deux ne remplace
l'autre (voir la section précédente) — `gitleaks` reste par ailleurs le filet de dernier recours
pour tout contournement du cliquet structurel de `.gitguardian.yaml`
(`scripts/governance/check_gitguardian_scope.py`), un risque distinct de celui traité ici.
