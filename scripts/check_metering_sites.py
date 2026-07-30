#!/usr/bin/env python3
"""Point d'entrée CLI de la garde metering B-20b §7.4.

La logique (testée, couverte) vit dans ``forgeai.models.metering_guard`` ; ce
script n'est qu'un lanceur mince pour la CI (job ``metering-sites``)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from forgeai.models.metering_guard import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
