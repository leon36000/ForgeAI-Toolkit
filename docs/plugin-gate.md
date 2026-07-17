# Gate de vérification des plugins (B-15)

`scripts/plugin_gate.py` vérifie une contribution externe (brique = plugin) AVANT acceptation :
une brique n'est intégrable que si elle est **vérifiable**.

## Champs requis (sinon refus)
- `id`, `name` : identité.
- `source_url` : dépôt (GitHub) — doit commencer par `https://` ; son **existence** est vérifiée
  par une requête HTTP (sauf `--offline`).
- `license` : licence déclarée (non vide).
- `healthcheck` : moyen de vérifier que la brique fonctionne (chaîne, ou objet `{"type": ...}`).

## Usage
```bash
python3 scripts/plugin_gate.py --plugin contribution.json            # vérif complète (réseau)
python3 scripts/plugin_gate.py --plugin contribution.json --offline  # sans vérif d'existence réseau
```
Sortie `PLUGIN-GATE : OK (<id> conforme)` + code 0 si acceptable ; sinon la liste des violations
(champ requis manquant, source_url invalide, source GitHub introuvable, healthcheck sans type) +
code 1.

La fonction `validate_plugin(plugin, existence_check=…)` accepte un vérificateur d'existence
INJECTABLE (réel en production, factice en test — aucune requête réseau dans les tests).
