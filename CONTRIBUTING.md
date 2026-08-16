# Contribuer à ForgeAI Toolkit

Ce document décrit la démarche pour proposer une contribution au projet ForgeAI Toolkit.

## 1. Préparation de l'environnement

Le projet repose sur la bibliothèque standard Python (`requires-python = ">=3.10"`). L'installation locale pour le développement s'effectue depuis la racine du dépôt :

```bash
git clone https://github.com/leon36000/ForgeAI-Toolkit.git
cd ForgeAI-Toolkit
pip install -e ".[dev]"
```

Pour vérifier les capacités et outils disponibles sur votre environnement :

```bash
python3 scripts/governance/capabilities.py
```

## 2. Démarche pour proposer une modification

1. **Créer une branche** dédiée à votre correctif ou fonctionnalité depuis la branche principale.
2. **Développer en TDD** : tout correctif ou ajout doit être accompagné d'un test automatisé (test rouge constatant le comportement initial, puis vert après modification).
3. **Respecter la règle §8bis (zéro stub, zéro faux)** : aucun corps vide, aucun `NotImplementedError`, aucun test sans assertion, aucune donnée inventée.
4. **Exécuter les gates locaux** avant de soumettre la pull request :
   ```bash
   pytest
   python3 scripts/no_stub_scan.py --all
   python3 scripts/registre.py verify evidence/registres/mission.jsonl
   ```
5. **Ouvrir une Pull Request** décrivant clairement le problème traité, la solution apportée et les commandes de test validées.

## 3. Pipeline de gouvernance et revue

Le pipeline complet d'intégration (orchestration, gates automatisés, revue aveugle scellée 3 vendors, gestion des registres) est documenté dans [AGENTS.md](AGENTS.md).

L'outillage externe de gouvernance (`civ_review.py`, bridge de modèles) est **optionnel** pour soumettre une contribution externe (cf. `scripts/governance/capabilities.py`). Il n'est pas requis pour ouvrir une PR : les revues scellées et les validations finales sont opérées lors de la phase d'intégration.
