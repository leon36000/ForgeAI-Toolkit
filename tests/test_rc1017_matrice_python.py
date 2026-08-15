"""Tests anti-dérive de la matrice officielle de support Python."""

from __future__ import annotations

import re
import unittest
from pathlib import Path


RACINE = Path(__file__).resolve().parents[1]
CHEMIN_GATES = RACINE / ".github" / "workflows" / "gates.yml"
CHEMIN_SONAR = RACINE / ".github" / "workflows" / "sonarcloud.yml"
CHEMIN_PYPROJECT = RACINE / "pyproject.toml"
CHEMIN_LOCKFILE = RACINE / "requirements-ci.txt"
CHEMIN_POLITIQUE = RACINE / "docs" / "politique-versions-python.md"


def _contenu(chemin: Path) -> str:
    return chemin.read_text(encoding="utf-8")


def _versions_matrice() -> list[str]:
    contenu = _contenu(CHEMIN_GATES)
    correspondance = re.search(
        r"(?ms)^  tests:\n.*?^\s+python-version:\s*\[([^\]]+)\]",
        contenu,
    )
    if correspondance is None:
        raise AssertionError("La matrice Python du job tests est introuvable.")

    return re.findall(r'"(\d+\.\d+)"', correspondance.group(1))


def _versions_classifiers() -> list[str]:
    contenu = _contenu(CHEMIN_PYPROJECT)
    return re.findall(
        r'"Programming Language :: Python :: (\d+\.\d+)"',
        contenu,
    )


def _bloc_job_tests() -> str:
    contenu = _contenu(CHEMIN_GATES)
    correspondance = re.search(
        r"(?ms)^  tests:\n(.*?)(?=^  [a-z][a-z0-9-]*:\n|\Z)",
        contenu,
    )
    if correspondance is None:
        raise AssertionError("Le job tests est introuvable.")
    return correspondance.group(1)


class TestRC1017MatricePython(unittest.TestCase):
    """Garanties structurelles de la story RC1-017."""

    def test_versions_matrice_egales_aux_classifiers(self) -> None:
        """La CI et les métadonnées de distribution déclarent les mêmes versions."""
        self.assertEqual(_versions_matrice(), _versions_classifiers())

    def test_minimum_matrice_coherent_avec_requires_python(self) -> None:
        """La première version testée respecte la borne minimale distribuée."""
        contenu = _contenu(CHEMIN_PYPROJECT)
        correspondance = re.search(
            r'^requires-python\s*=\s*">=(\d+)\.(\d+)"',
            contenu,
            re.MULTILINE,
        )
        self.assertIsNotNone(correspondance)
        assert correspondance is not None
        minimum_declare = (
            int(correspondance.group(1)),
            int(correspondance.group(2)),
        )
        minimum_matrice = min(
            tuple(int(partie) for partie in version.split("."))
            for version in _versions_matrice()
        )
        self.assertEqual(minimum_matrice, minimum_declare)

    def test_lockfile_existe_et_epingle_chaque_dependance(self) -> None:
        """Chaque entrée versionnée du lockfile possède au moins une empreinte."""
        self.assertTrue(CHEMIN_LOCKFILE.is_file())
        lignes = _contenu(CHEMIN_LOCKFILE).splitlines()

        index = 0
        dependances_verifiees = 0
        while index < len(lignes):
            ligne = lignes[index]
            if re.match(r"^[A-Za-z0-9][A-Za-z0-9_.-]*==", ligne):
                bloc = [ligne]
                index += 1
                while index < len(lignes) and (
                    lignes[index].startswith((" ", "\t")) or not lignes[index].strip()
                ):
                    bloc.append(lignes[index])
                    index += 1
                self.assertIn(
                    "--hash=sha256:",
                    "\n".join(bloc),
                    f"Dépendance non protégée par empreinte : {ligne}",
                )
                dependances_verifiees += 1
                continue
            index += 1

        self.assertGreater(dependances_verifiees, 0)

    def test_job_matrice_installe_le_lockfile_avec_empreintes(self) -> None:
        """Le job de matrice impose la vérification des empreintes du lockfile."""
        bloc = _bloc_job_tests()
        self.assertRegex(
            bloc,
            r"pip install --require-hashes -r requirements-ci\.txt",
        )

    def test_aucune_liste_de_dependances_de_test_n_est_dupliquee(self) -> None:
        """Les workflows de gates et Sonar utilisent tous le lockfile unique."""
        expression_installation = re.compile(r"pip install[^\n]*", re.IGNORECASE)

        for chemin in (CHEMIN_GATES, CHEMIN_SONAR):
            installations = expression_installation.findall(_contenu(chemin))
            self.assertGreater(
                len(installations),
                0,
                f"Aucune installation de dépendance trouvée dans {chemin}.",
            )
            for installation in installations:
                self.assertIn(
                    "requirements-ci.txt",
                    installation,
                    f"Installation hors lockfile dans {chemin}: {installation}",
                )
                self.assertIn(
                    "--require-hashes",
                    installation,
                    f"Installation sans empreintes dans {chemin}: {installation}",
                )

    def test_politique_existe_et_cite_chaque_version(self) -> None:
        """La documentation de support cite toute version officiellement testée."""
        self.assertTrue(CHEMIN_POLITIQUE.is_file())
        politique = _contenu(CHEMIN_POLITIQUE)

        for version in _versions_matrice():
            self.assertIn(f"Python {version}", politique)


if __name__ == "__main__":
    unittest.main()
