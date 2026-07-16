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
