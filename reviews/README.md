# reviews/ — verdicts de revue aveugle scellés (§3.1 du plan maître)

Un fichier par reviewer et par étape : `reviews/<étape>/<modèle>.verdict.json`

```json
{
  "verdict": "APPROVE | REJECT",
  "objections": [
    {"severite": "critique | majeure | mineure", "description": "...", "preuve": "..."}
  ],
  "date": "YYYY-MM-DD",
  "heure": "HH:MM:SSZ"
}
```

Règles :
- Déposé sur branche isolée, **sans accès aux verdicts des autres** reviewers.
- Révélation uniquement quand tous les verdicts sont déposés (tally par script, jamais par LLM).
- Un verdict déposé après révélation est invalide (vérification par timestamps de commit).
- Seuil : ≥7/9 APPROVE et zéro objection critique non résolue; sinon round Delphi (max 2).
