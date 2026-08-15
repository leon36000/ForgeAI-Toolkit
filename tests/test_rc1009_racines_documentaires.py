"""Garantit que seule la racine documentaire canonique Docs/ est suivie."""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path


RACINE = Path(__file__).resolve().parents[1]


def _chemins_suivis_par_git() -> list[str]:
    resultat = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=RACINE,
        check=True,
        capture_output=True,
        text=False,
    )
    return [
        chemin.decode("utf-8")
        for chemin in resultat.stdout.split(b"\0")
        if chemin
    ]


class TestRC1009RacinesDocumentaires(unittest.TestCase):
    """Contrat de consolidation des racines documentaires."""

    def test_aucun_chemin_suivi_ne_commence_par_docs_minuscule(self) -> None:
        """Docs/ est la seule racine de documentation active suivie par Git."""
        chemins_docs_minuscules = [
            chemin
            for chemin in _chemins_suivis_par_git()
            if chemin.startswith("docs/")
        ]

        self.assertEqual(
            chemins_docs_minuscules,
            [],
            "Des fichiers suivis subsistent sous docs/ minuscule : "
            + ", ".join(chemins_docs_minuscules),
        )


if __name__ == "__main__":
    unittest.main()
