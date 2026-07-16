# Gate de désambiguïsation du catalogue (B-26)

`scripts/catalogue_gate.py` empêche l'ambiguïté dans `src/forgeai/data/catalogue.json`
(948 briques). Il est **bloquant en CI** (job `catalogue` de `.github/workflows/gates.yml`).

## Invariants garantis
1. **`id` unique et présent** : deux entrées ne peuvent pas partager le même `id`, et toute
   entrée doit en porter un (non vide).
2. **Noms en collision qualifiés** : si deux entrées portent le même `name`, chacune DOIT
   porter un champ `disambiguation` non vide (le qualificatif org/repo qui les distingue).

Aujourd'hui le catalogue respecte ces invariants (id unique, zéro collision de nom — les ~14
cas ambigus rencontrés lors du R-ALL ont été qualifiés, ex. `av/harbor`). Le gate empêche toute
**régression** lors d'ajouts futurs.

## Utilisation
```bash
python3 scripts/catalogue_gate.py                 # catalogue packagé par défaut
python3 scripts/catalogue_gate.py --catalogue X   # un autre fichier
```
Sortie `CATALOGUE-GATE : OK (<n> entrées, zéro ambiguïté)` + code 0 si conforme ; sinon la liste
des violations + code 1.

## Résoudre une violation
- **id dupliqué / absent** : donner un `id` unique à chaque entrée.
- **collision de nom** : ajouter un `disambiguation` non vide à chaque entrée partageant le nom
  (décrire l'org/repo/portée qui la distingue), ou qualifier le `name` lui-même (`org/nom`).

Régénérer ensuite `catalogue.sha256` si le contenu change.
