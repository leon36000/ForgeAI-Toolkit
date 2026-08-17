from __future__ import annotations

import io
import tarfile
import zipfile
from pathlib import Path

import pytest

from verifier_artefact_distribue import ErreurVerification, verifier_artefact


METADATA = """Metadata-Version: 2.1
Name: forgeai-toolkit
Version: 0.1.0
Requires-Python: >=3.10
Classifier: Programming Language :: Python :: 3.10
Classifier: Programming Language :: Python :: 3.11
Classifier: Programming Language :: Python :: 3.12
Classifier: Programming Language :: Python :: 3.13

"""


def fichiers_paquet(sans: str | None = None) -> dict[str, bytes]:
    fichiers = {
        "forgeai/data/catalogue.json": b"{}",
        "forgeai/data/locales/fr.json": b"{}",
        "forgeai/data/locales/en.json": b"{}",
        "forgeai/data/stacks/a.json": b"{}",
        "forgeai/data/stacks/b.json": b"{}",
        "forgeai/data/stacks/c.json": b"{}",
        "forgeai/data/stacks/d.json": b"{}",
        "forgeai/data/stacks/e.json": b"{}",
        "forgeai/data/stacks/f.json": b"{}",
        "forgeai/data/smoke/a.md": b"# a\n",
        "forgeai/data/smoke/b.md": b"# b\n",
        "forgeai/web/assets/app.js": b"",
        "forgeai/web/assets/adoption.js": b"",
        "forgeai/web/assets/engine_filter.js": b"",
        "forgeai/web/assets/style.css": b"",
        "forgeai/web/assets/logo.svg": b"",
    }
    for index in range(7):
        fichiers[f"forgeai/data/extra-{index}.json"] = b"{}"
    if sans is not None:
        del fichiers[sans]
    return fichiers


def ecrire_wheel(chemin: Path, fichiers: dict[str, bytes]) -> None:
    with zipfile.ZipFile(chemin, "w") as archive:
        archive.writestr("forgeai_toolkit-0.1.0.dist-info/METADATA", METADATA)
        for nom, contenu in fichiers.items():
            archive.writestr(nom, contenu)


def ecrire_sdist(
    chemin: Path,
    fichiers: dict[str, bytes],
    *,
    inclure_tests: bool = True,
    fichiers_racine: dict[str, bytes] | None = None,
) -> None:
    racine = "forgeai_toolkit-0.1.0"
    with tarfile.open(chemin, "w:gz") as archive:
        metadata = METADATA.encode("utf-8")
        info = tarfile.TarInfo(f"{racine}/PKG-INFO")
        info.size = len(metadata)
        archive.addfile(info, io.BytesIO(metadata))

        if inclure_tests:
            contenu_test = b"def test_paquet_distribue() -> None:\n    assert True\n"
            info = tarfile.TarInfo(f"{racine}/tests/test_adoption.py")
            info.size = len(contenu_test)
            archive.addfile(info, io.BytesIO(contenu_test))

        for nom, contenu in (fichiers_racine or {}).items():
            info = tarfile.TarInfo(f"{racine}/{nom}")
            info.size = len(contenu)
            archive.addfile(info, io.BytesIO(contenu))

        for nom, contenu in fichiers.items():
            info = tarfile.TarInfo(f"{racine}/src/{nom}")
            info.size = len(contenu)
            archive.addfile(info, io.BytesIO(contenu))


def test_verifie_un_wheel_factice_complet(tmp_path: Path) -> None:
    wheel = tmp_path / "forgeai_toolkit-0.1.0-py3-none-any.whl"
    ecrire_wheel(wheel, fichiers_paquet())

    verifier_artefact(wheel)


def test_verifie_un_sdist_factice_complet_avec_tests(tmp_path: Path) -> None:
    sdist = tmp_path / "forgeai_toolkit-0.1.0.tar.gz"
    ecrire_sdist(sdist, fichiers_paquet())

    verifier_artefact(sdist)


def test_detecte_un_package_data_retiré_volontairement(tmp_path: Path) -> None:
    wheel = tmp_path / "forgeai_toolkit-0.1.0-py3-none-any.whl"
    ecrire_wheel(wheel, fichiers_paquet(sans="forgeai/data/locales/en.json"))

    with pytest.raises(ErreurVerification, match="locales/.*incomplet"):
        verifier_artefact(wheel)


def test_detecte_un_fichier_de_tests_inattendu(tmp_path: Path) -> None:
    wheel = tmp_path / "forgeai_toolkit-0.1.0-py3-none-any.whl"
    fichiers = fichiers_paquet()
    fichiers["tests/test_interdit.py"] = b"assert True\n"
    ecrire_wheel(wheel, fichiers)

    with pytest.raises(ErreurVerification, match="tests/"):
        verifier_artefact(wheel)


def test_rejette_un_sdist_sans_tests(tmp_path: Path) -> None:
    sdist = tmp_path / "forgeai_toolkit-0.1.0.tar.gz"
    ecrire_sdist(sdist, fichiers_paquet(), inclure_tests=False)

    with pytest.raises(ErreurVerification, match="tests/ absent"):
        verifier_artefact(sdist)


def test_rejette_un_sdist_contenant_reviews(tmp_path: Path) -> None:
    sdist = tmp_path / "forgeai_toolkit-0.1.0.tar.gz"
    ecrire_sdist(
        sdist,
        fichiers_paquet(),
        fichiers_racine={"reviews/decision.md": b"# interdit\n"},
    )

    with pytest.raises(ErreurVerification, match="reviews/"):
        verifier_artefact(sdist)
