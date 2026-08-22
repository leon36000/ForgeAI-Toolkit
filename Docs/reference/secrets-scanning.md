# Référence — périmètre des scans de secrets

ForgeAI Toolkit utilise deux contrôles distincts. Ils ne reposent pas sur les mêmes
détecteurs et ne constituent donc pas deux implémentations interchangeables du même scan.

## GitGuardian

`.gitguardian.yaml` ne contient plus d’exclusion globale des fichiers Markdown. Les fichiers
`README.md`, `Docs/**/*.md`, `stories/**/*.md` et `evidence/reviews/**/*.md` restent donc dans le
périmètre normal de GitGuardian.

Les seules exclusions conservées sont bornées et intentionnelles :

| Motif | Justification |
| --- | --- |
| `tests/fixtures/**` | fixtures synthétiques de tests, non distribuées comme documents opérateur |
| `src/forgeai/data/catalogue.json` | catalogue public généré, contrôlé par ses propres empreintes |
| `LICENSE` | texte juridique sans configuration opérateur |
| `.gitignore` | règles de contrôle de version, sans contenu de secret attendu |

Une modification de cette liste doit rester explicitement bornée et être accompagnée d’une
justification. Le test `tests/test_gitguardian_config.py` vérifie la liste exacte et empêche le
retour d’une exclusion Markdown globale.

## Gitleaks

Le job CI `gitleaks` reste indépendant de GitGuardian et s’exécute sur un checkout avec historique
complet (`fetch-depth: 0`). Il fournit le contrôle bloquant du dépôt et de l’historique selon ses
propres règles. Un résultat Gitleaks vert ne prouve pas que GitGuardian aurait produit le même
résultat, et inversement.

## Vérification active GitGuardian

La détection GitGuardian qui utilise l’API fournisseur doit être lancée dans un environnement
opérateur de confiance, jamais avec un token committé ou injecté dans une PR non fiable :

```bash
ggshield --config-path .gitguardian.yaml secret scan path --format json /tmp/forgeai-secret-probe/Docs/ordinary.md
ggshield --config-path .gitguardian.yaml secret scan path --recursive --yes .
ggshield --config-path .gitguardian.yaml secret scan repo .
```

Pour la preuve positive, créer le fichier Markdown temporaire et sa valeur factice à l’exécution
dans `/tmp`, puis conserver uniquement le verdict synthétique. Ne jamais publier la valeur,
`--show-secrets`, la sortie JSON brute ou le token d’authentification dans le dépôt.
