# Cycle de recherche — réévaluation des défauts ⭐ (B-21)

`scripts/reeval_defaults.py` réévalue la brique par défaut (⭐) de chaque catégorie et propose un
changement dès qu'une brique mieux notée (★) existe — **avec preuve comparative**, jamais en aveugle.

## Règle
Pour chaque catégorie, le meilleur candidat = ★ max (départage : plus petit nom), via
`category_defaults` (B-01). Si ce candidat diffère du défaut courant (`default=true`), un changement
est proposé : `{category, current, proposed, current_stars, proposed_stars}`.

## Usage
```bash
python3 scripts/reeval_defaults.py            # rapport (aucune écriture)
python3 scripts/reeval_defaults.py --journal  # journalise chaque changement (registre 'default_reeval')
```
Sortie `REEVAL : aucun changement de defaut (<n> categories optimales)` si le catalogue est déjà
optimal ; sinon la liste `<cat> : <current>(<cs>★) -> <proposed>(<ps>★)`. Toujours code 0
(recommandation, jamais bloquant) ; chaque changement de défaut est journalisé avec sa preuve.
