# Politique de support des versions Python

## Matrice officielle

ForgeAI Toolkit supporte officiellement Python 3.10, 3.11, 3.12 et 3.13. La CI exécute la
suite complète sur chacune de ces versions, sous Ubuntu.

| Version | Plateforme de test | Rôle |
|---|---|---|
| Python 3.10 | Ubuntu | Version supportée, non de référence |
| Python 3.11 | Ubuntu | Version supportée, non de référence |
| Python 3.12 | Ubuntu, macOS et Windows pour le sous-ensemble portable | Version de référence |
| Python 3.13 | Ubuntu | Version supportée, non de référence |

Python 3.12 est la version de référence. C'est exclusivement sur cette version que les seuils de
couverture du projet sont appliqués : 85 % pour le paquet `src/forgeai` et 95 % pour
`src/forgeai/core/registre.py`. Les autres versions exécutent néanmoins toute la suite de tests ;
elles ne sont jamais dispensées silencieusement.

Un sous-ensemble de tests explicitement portables est aussi exécuté sur macOS et Windows avec
Python 3.12.

## Ajout d'une version

Toute nouvelle version Python est ajoutée d'abord à la matrice CI. Si elle révèle une
incompatibilité, le résultat est un échec CI visible : elle ne peut pas être retirée, exclue ou
neutralisée silencieusement pour faire passer la vérification.

Après validation, son classifier officiel est ajouté dans `pyproject.toml` et la documentation
est mise à jour dans la même pull request.

## Retrait d'une version

Une version Python ne peut être retirée qu'après sa date de fin de vie amont. Le retrait fait
l'objet d'une pull request dédiée qui modifie simultanément :

1. la matrice Python de `.github/workflows/gates.yml` ;
2. les classifiers Python de `pyproject.toml` ;
3. `requires-python` dans `pyproject.toml`.

Ces trois déclarations constituent un contrat unique et ne doivent jamais diverger.

## Mise à jour du lockfile CI

Les dépendances de test directes sont déclarées dans `requirements-ci.in`. Le fichier
`requirements-ci.txt` est le lockfile universel généré avec empreintes SHA-256.

La génération utilise `uv pip compile --universal --python-version 3.10` : Python 3.10 est la
borne basse de résolution et `--universal` génère les branches conditionnelles par marker pour
toutes les versions de la matrice officielle.

Le workflow `ci-deps-update.yml` le régénère chaque semaine et peut aussi être lancé
manuellement avec `workflow_dispatch`. Lorsqu'une modification est détectée, il ouvre une pull
request ; il ne pousse jamais directement sur `main`. Toute modification du lockfile est donc
revue avant intégration.

## Hermétisme des tests

Les jobs de test n'installent aucune dépendance par nom de paquet et ne téléchargent aucune
dépendance hors du lockfile. Ils installent uniquement
`requirements-ci.txt` avec `pip install --no-cache-dir --require-hashes`.

Toute nouvelle dépendance de test doit d'abord être ajoutée à `requirements-ci.in`, puis le
lockfile universel doit être régénéré par la procédure contrôlée. Le produit runtime reste, lui,
sans dépendance externe.
