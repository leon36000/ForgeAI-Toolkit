# AUDIT-SUPPLY #585 — Appliquer les types JSON Schema au catalogue avant chargement

## Constat vérifié (ne pas re-dériver)

`src/forgeai/data/catalogue.schema.json` déclare des `type` JSON Schema par propriété (ex.
`"verified": {"type": "boolean"}`, `"default": {"type": ["boolean", "null"]}`, la plupart des
autres champs en `"string"`), avec `additionalProperties: false` et une liste `required`.

`scripts/catalogue_gate.py::schema_violations(entries, schema)` (lignes 92-107) ne vérifie
QUE : (1) les champs présents mais non déclarés au schéma (si `additionalProperties=false`),
(2) les champs requis absents. Elle **ignore intégralement** la clé `type` de chaque propriété.
Une entrée `{"verified": "false", ...(tous les autres champs requis présents)...}` passe donc le
gate CI actuel (`.github/workflows/gates.yml` job `catalogue`) sans être détectée, alors que sa
valeur `verified` est une chaîne au lieu d'un booléen.

Vérifié empiriquement AVANT cette story : le vrai catalogue (`src/forgeai/data/catalogue.json`,
1576 entrées) est déjà 100% conforme en types — aucune anomalie actuelle, donc la nouvelle
validation ne doit produire AUCUNE nouvelle violation sur les données réelles.

Le champ `verified` n'est lu par aucun module runtime du produit
(`src/forgeai/catalogue/loader.py` ne le référence pas) ; il est consommé par les outils de
gouvernance `scripts/rall.py`/`scripts/rall_verify_urls.py` via `entry.get("verified")` en
contexte booléen implicite Python — une chaîne non vide comme `"false"` y est truthy, donc
silencieusement traitée comme « vérifiée ». Cette story corrige la frontière supply-chain (le
gate), pas ces scripts de gouvernance (hors périmètre, non modifiés).

## Livrable attendu

1. **`scripts/catalogue_gate.py`** : étendre `schema_violations()` pour valider aussi le `type`
   déclaré de chaque propriété DÉJÀ PRÉSENTE dans l'entrée (ne pas dupliquer la détection de champ
   manquant, déjà couverte par la vérification `required` existante — un champ requis absent ne
   doit pas produire une deuxième violation de type en plus de la violation "requis manquant").
   Mapping JSON Schema → Python à couvrir, dans une fonction dédiée réutilisable (ex.
   `_valeur_conforme_au_type(valeur, type_declare) -> bool`) :
   - `"string"` → `isinstance(valeur, str)`
   - `"boolean"` → `isinstance(valeur, bool)` (Python : un `int` n'est PAS accepté comme
     `boolean`, même si `bool` hérite techniquement de `int` — `isinstance(1, bool)` est déjà
     `False` nativement, aucun garde supplémentaire requis).
   - `"integer"` → `isinstance(valeur, int) and not isinstance(valeur, bool)` (exclure les
     booléens, qui sont des `int` en Python).
   - `"number"` → `isinstance(valeur, (int, float)) and not isinstance(valeur, bool)`.
   - `"array"` → `isinstance(valeur, list)`.
   - `"object"` → `isinstance(valeur, dict)`.
   - `"null"` → `valeur is None`.
   - Type déclaré comme **liste** de types (ex. `["boolean", "null"]`, cas du champ `default`) :
     conforme si la valeur satisfait AU MOINS UN des types listés.
   - Propriété du schéma sans clé `type` (ex. schéma minimal dans les tests existants) : ne rien
     valider pour cette propriété (comportement actuel préservé, pas de régression).
   Message de violation pour un type incohérent, même format que les 2 existants :
   `f"type invalide pour '{champ}' : attendu {type_declare!r}, reçu {type(valeur).__name__} (entrée '{qui}')"`.
2. **`tests/test_catalogue_gate.py`** (fourni en contexte intégral, NE PAS modifier les tests déjà
   présents, uniquement AJOUTER) :
   - Test négatif ciblé sur le cas exact de l'issue #585 : `{"verified": "false", ...}` (chaîne au
     lieu de booléen) → `schema_violations` retourne une violation mentionnant `verified` et
     `type invalide`.
   - Test négatif pour un champ `string` recevant un entier.
   - Test positif : le type `["boolean", "null"]` (champ `default`) accepte `True`, `False` ET
     `None` sans violation.
   - Test qu'un champ requis ABSENT ne produit PAS de double violation (une seule ligne "requis
     manquant", pas de ligne "type invalide" en plus pour ce même champ absent).
   - Test que `test_catalogue_reel_conforme_au_schema` (déjà existant, ne pas dupliquer) continue
     de passer — c'est la preuve de non-régression sur les 1576 entrées réelles, aucun nouveau
     test requis pour ça, juste vérifier qu'il reste vert après le changement.
3. Rejouer `python3 scripts/catalogue_gate.py` en CLI réel (pas seulement les tests) pour prouver
   que le gate CI (`job: catalogue` de `.github/workflows/gates.yml`, déjà existant, aucune
   modification requise de ce fichier) reste vert sur le vrai catalogue.

## Contraintes

- Ne PAS modifier `scripts/rall.py`, `scripts/rall_verify_urls.py`, `.github/workflows/gates.yml`,
  ni `src/forgeai/data/catalogue.schema.json`, ni `src/forgeai/data/catalogue.json` — hors
  périmètre de cette story (frontière = le gate mécanique uniquement).
- Zéro nouvelle dépendance tierce (stdlib pur, cohérent avec le fichier existant).
- `schema_violations()` garde sa signature actuelle `(entries, schema) -> List[str]`.

## Preuve d'exécution (round 1 de revue scellée, 3 objections mineures : sortie CLI absente du diff)

Sortie brute de `python3 scripts/catalogue_gate.py` sur le vrai catalogue (1576 entrées), après
application du correctif ci-dessus :

```text
CATALOGUE-GATE : OK (1576 entrées, zéro ambiguïté)
```

Code de sortie : `0`. Confirme la non-régression sur les données réelles (aucune des 1576
entrées n'a de type incohérent avec `src/forgeai/data/catalogue.schema.json`).
