# Revues ORCH-001

Ce dossier recevra les verdicts de revue aveugle scellée (§3).

Chaque fichier de verdict suit la convention:
```
reviews/ORCH-001/<modèle>.verdict.json
```

Les verdicts sont déposés via `~/proof-method/scripts/civ_review.py --story reviews/ORCH-001`.
Le dépouillement est effectué par `python3 scripts/revue.py tally reviews/ORCH-001`.

Trois vendors distincts ≠ vendor du codeur sont requis.
