# RC1-021 — incrément 2b : mutation ciblée des gardes

Issue : #451
Dépendance : incrément 2a (#582), qui fournit les seuils de couverture de branches par catégorie.

## Contrat livré

Le job `mutation-targeted` exécute `scripts/mutation_gate.py` sur une copie temporaire du
paquet. Trois mutations représentatives du rate limiter sont injectées :

- inversion de l’exemption loopback ;
- armement du lockout seulement après `auth_max` au lieu de l'atteindre ;
- autorisation de `rate_max == 0`, qui réintroduirait la division par zéro.

Le job échoue dès qu'un mutant survit. Le rapport JSON conserve pour chaque mutant le site, le
contrat observable, le code retour pytest et la disposition. Une disposition `FAIL: mutant
survivant` est donc bloquante, jamais une dette silencieuse.

## Corrections et preuves

La campagne `mutmut` initiale sur la cible existante a produit 195 mutants tués et 6 survivants
équivalents dans la lecture des variables d'environnement. Ces survivants équivalents sont
documentés par le test explicite des variables absentes; le code final conserve en plus un
fallback `None` explicite et typé afin que le gate mypy reste strict. La campagne ciblée
versionnée tue ensuite les trois mutants de garde (`3/3`, zéro survivant).

La commande pytest interne de la campagne porte une justification `noqa: S603` directement
sur la ligne d'appel multilignes : c'est la forme reconnue par Ruff 0.14.5, version du gate CI.
La commande, ses arguments et sa copie de travail sont entièrement construits par le script;
aucune entrée shell utilisateur n'est interpolée.

## Bornes

Cet incrément ne prétend pas couvrir tout le dépôt ni produire un score global de mutation. Les
mutants sont intentionnellement peu nombreux et attachés à des contrats de sécurité/rejet
observables ; l'extension à d'autres catégories se fera par incréments séparés.
