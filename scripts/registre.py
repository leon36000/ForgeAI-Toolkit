#!/usr/bin/env python3
"""Interface CLI/CI du registre hash-chaîné — implémentation : forgeai.core.registre."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from forgeai.core.registre import (  # noqa: E402,F401 — ré-export pour les tests
    GENESIS,
    _entry_hash,
    _read_entries,
    append,
    main,
    verify,
)

if __name__ == "__main__":
    main()
