#!/usr/bin/env python3
"""Interface CLI/CI du registre hash-chaîné — implémentation : forgeai.core.registre."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from forgeai.core.registre_completude import anomalies, charger  # noqa: E402
from forgeai.core.registre import (  # noqa: E402,F401 — ré-export pour les tests
    GENESIS,
    _entry_hash,
    _read_entries,
    append,
    main,
    verify,
)

def _main_completude(argv: list[str]) -> int:
    """REG-029A : rapporte les anomalies de COMPLÉTUDE (distinctes de l'intégrité vérifiée par
    `verify`). Cette commande RAPPORTE — elle ne réécrit jamais le registre, qui est append-only
    et haché. Aucun gate CI ne s'y branche ici : c'est l'objet de REG-029B."""
    parser = argparse.ArgumentParser(
        prog=f"{Path(sys.argv[0]).name} completude",
        description="Rapporte les anomalies de complétude d'un registre JSONL.",
    )
    parser.add_argument("fichier", help="chemin du registre JSONL à contrôler")
    arguments = parser.parse_args(argv)

    rapport = anomalies(charger(arguments.fichier))
    for anomalie in rapport:
        print(f"[{anomalie['type']}] seq={anomalie['seq']} story={anomalie['story']}: {anomalie['raison']}")
    print(f"— {len(rapport)} anomalie(s) de complétude")
    return min(len(rapport), 1)


if __name__ == "__main__":
    if sys.argv[1:2] == ["completude"]:
        raise SystemExit(_main_completude(sys.argv[2:]))
    main()
