#!/usr/bin/env python3
"""Réévaluation des défauts par catégorie avec preuve comparative."""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

from forgeai.catalogue.loader import category_defaults, parse_stars
from forgeai.core import registre
from forgeai.resources import catalogue_path


def current_defaults(entries: List[dict]) -> Dict[str, str]:
    """Retourne {category: name} des entrées marquées default=True."""
    mapping: Dict[str, str] = {}
    for entry in entries:
        if entry.get("default") is True:
            mapping[entry["category"]] = entry["name"]
    return mapping


def reevaluate_defaults(entries: List[dict]) -> List[dict]:
    """Compare le défaut courant au meilleur candidat pour chaque catégorie et retourne les changements."""
    best_per_cat = category_defaults(entries)
    current_per_cat = current_defaults(entries)

    changes: List[dict] = []
    all_cats = sorted(set(best_per_cat.keys()) | set(current_per_cat.keys()))

    for cat in all_cats:
        current_name = current_per_cat.get(cat)
        proposed_name = best_per_cat.get(cat)

        if current_name == proposed_name:
            continue

        # Stars du défaut courant
        current_stars = 0
        if current_name is not None:
            for e in entries:
                if e.get("category") == cat and e.get("name") == current_name:
                    current_stars = parse_stars(e.get("popularity", ""))
                    break

        # Stars du candidat proposé
        proposed_stars = 0
        if proposed_name is not None:
            for e in entries:
                if e.get("category") == cat and e.get("name") == proposed_name:
                    proposed_stars = parse_stars(e.get("popularity", ""))
                    break

        changes.append(
            {
                "category": cat,
                "current": current_name,
                "proposed": proposed_name,
                "current_stars": current_stars,
                "proposed_stars": proposed_stars,
            }
        )

    return changes


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Réévalue les défauts par catégorie")
    parser.add_argument(
        "--catalogue",
        type=Path,
        default=catalogue_path(),
        help="Chemin vers le catalogue JSON (par défaut celui packagé).",
    )
    parser.add_argument(
        "--registre",
        type=Path,
        default=Path("evidence/registres/mission.jsonl"),
        help="Chemin du registre (défaut evidence/registres/mission.jsonl).",
    )
    parser.add_argument(
        "--journal",
        action="store_true",
        help="Si présent, journalise les changements dans le registre.",
    )
    args = parser.parse_args(argv)

    # Chargement du catalogue
    catalogue_data = json.loads(args.catalogue.read_text(encoding="utf-8"))
    if isinstance(catalogue_data, list):
        entries = catalogue_data
    else:
        entries = catalogue_data["entries"]

    changes = reevaluate_defaults(entries)

    if not changes:
        n_categories = len({e["category"] for e in entries})
        print(f"REEVAL : aucun changement de defaut ({n_categories} categories optimales)")
        return 0

    for ch in changes:
        print(
            f"  {ch['category']} : {ch['current']}({ch['current_stars']}★) -> "
            f"{ch['proposed']}({ch['proposed_stars']}★)"
        )

    if args.journal:
        registre_path = args.registre
        for ch in changes:
            registre.append(Path(registre_path), "default_reeval", "recherche", ch)

    return 0


if __name__ == "__main__":
    sys.exit(main())
