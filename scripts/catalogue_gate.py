#!/usr/bin/env python3
"""Gate de désambiguïsation du catalogue de briques."""

import argparse
import json
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional


def load_entries(path: Path) -> List[Dict[str, Any]]:
    """Charge les entrées depuis un fichier JSON.

    Si le JSON est un objet avec une clé 'entries', retourne cette liste.
    Sinon, s'il s'agit directement d'une liste, la retourne.
    """
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    if isinstance(data, dict) and "entries" in data:
        return data["entries"]
    if isinstance(data, list):
        return data
    raise ValueError(f"Format de catalogue inattendu dans {path}")


def find_violations(entries: List[Dict[str, Any]]) -> List[str]:
    """Retourne la liste triée des violations constatées dans les entrées."""
    violations: List[str] = []

    # 1. Identifiants dupliqués
    id_counts: Dict[str, int] = {}
    for entry in entries:
        eid = entry.get("id")
        if eid and isinstance(eid, str):
            eid = eid.strip()
        if eid:  # non vide après strip
            id_counts[eid] = id_counts.get(eid, 0) + 1

    for eid, count in id_counts.items():
        if count > 1:
            violations.append(f"id dupliqué : '{eid}' ({count} entrées)")

    # 2. Entrées sans identifiant
    for entry in entries:
        eid = entry.get("id")
        if not eid or not isinstance(eid, str) or not eid.strip():
            name = entry.get("name", "?")
            violations.append(f"entrée sans id : '{name}'")

    # 3. Collisions de noms sans désambiguïsation
    name_groups: Dict[str, List[Dict[str, Any]]] = {}
    for entry in entries:
        name = entry.get("name", "")
        name_groups.setdefault(name, []).append(entry)

    for name, group in name_groups.items():
        if len(group) < 2:
            continue
        for entry in group:
            disamb = entry.get("disambiguation")
            if not disamb or not isinstance(disamb, str) or not disamb.strip():
                eid = entry.get("id", "?")
                violations.append(
                    f"nom en collision sans disambiguation : '{name}' (id {eid})"
                )

    return sorted(violations)


def default_catalogue_path() -> Path:
    """Retourne le chemin du catalogue packagé."""
    return (
        Path(__file__).resolve().parents[1]
        / "src"
        / "forgeai"
        / "data"
        / "catalogue.json"
    )


def default_schema_path() -> Path:
    """Retourne le chemin du schéma d'entrée packagé (source de vérité des champs)."""
    return default_catalogue_path().with_name("catalogue.schema.json")


def load_schema(path: Path) -> Dict[str, Any]:
    """Charge le JSON Schema d'une entrée de catalogue."""
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def _valeur_conforme_au_type(valeur: Any, type_declare: Any) -> bool:
    """Vérifie qu'une valeur Python est conforme à un type JSON Schema déclaré."""
    if isinstance(type_declare, list):
        return any(_valeur_conforme_au_type(valeur, t) for t in type_declare)
    if type_declare == "string":
        return isinstance(valeur, str)
    if type_declare == "boolean":
        return isinstance(valeur, bool)
    if type_declare == "integer":
        return isinstance(valeur, int) and not isinstance(valeur, bool)
    if type_declare == "number":
        return isinstance(valeur, (int, float)) and not isinstance(valeur, bool)
    if type_declare == "array":
        return isinstance(valeur, list)
    if type_declare == "object":
        return isinstance(valeur, dict)
    if type_declare == "null":
        return valeur is None
    return True


def schema_violations(entries: List[Dict[str, Any]], schema: Dict[str, Any]) -> List[str]:
    """Conformité au schéma : champs déclarés (si additionalProperties=false) et requis présents.
    Rend le champ 'disambiguation' (et tout autre) explicitement DÉCLARÉ au schéma.
    Valide aussi le type déclaré de chaque propriété déjà présente dans l'entrée."""
    props = set(schema.get("properties", {}))
    required = set(schema.get("required", []))
    allow_extra = schema.get("additionalProperties", True)
    properties = schema.get("properties", {})
    violations: List[str] = []
    for entry in entries:
        who = entry.get("id") or entry.get("name", "?")
        keys = set(entry)
        if allow_extra is False:
            for k in keys - props:
                violations.append(f"champ non déclaré au schéma : '{k}' (entrée '{who}')")
        for r in required - keys:
            violations.append(f"champ requis manquant : '{r}' (entrée '{who}')")
        # Validation des types pour les champs présents et déclarés
        for champ, valeur in entry.items():
            if champ not in properties:
                continue
            prop_schema = properties[champ]
            if not isinstance(prop_schema, dict):
                continue
            if "type" not in prop_schema:
                continue
            type_declare = prop_schema["type"]
            if not _valeur_conforme_au_type(valeur, type_declare):
                violations.append(
                    f"type invalide pour '{champ}' : attendu {type_declare!r}, reçu {type(valeur).__name__} (entrée '{who}')"
                )
    return sorted(violations)


def main(argv: Optional[List[str]] = None) -> int:
    """Point d'entrée CLI."""
    parser = argparse.ArgumentParser(description="Gate de désambiguïsation du catalogue")
    parser.add_argument(
        "--catalogue",
        type=str,
        default=str(default_catalogue_path()),
        help="Chemin vers le fichier catalogue.json",
    )
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    path = Path(args.catalogue)

    entries = load_entries(path)
    violations = find_violations(entries)
    schema = load_schema(default_schema_path())
    violations = sorted(violations + schema_violations(entries, schema))

    if violations:
        for v in violations:
            print(f"  {v}")
        print(
            f"CATALOGUE-GATE : ÉCHEC ({len(violations)} violations)",
            file=sys.stderr,
        )
        return 1

    print(f"CATALOGUE-GATE : OK ({len(entries)} entrées, zéro ambiguïté)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
