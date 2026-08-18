#!/usr/bin/env python3
"""Vérifie le contenu distribué des wheels et archives source ForgeAI."""

from __future__ import annotations

import argparse
import sys
import tarfile
import zipfile
from email.parser import BytesParser
from email.policy import default
from pathlib import Path
from typing import Iterable


NOM_ATTENDU = "forgeai-toolkit"
VERSION_ATTENDUE = "0.1.0"
REQUIRES_PYTHON_ATTENDU = ">=3.10"
CLASSIFIERS_PYTHON_ATTENDUS = {
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Programming Language :: Python :: 3.13",
}
COMPTES_MINIMAUX = {
    "locales": 2,
    "stacks": 6,
    "assets": 5,
    "smoke": 2,
}
NOMBRE_MINIMAL_JSON = 16


class ErreurVerification(Exception):
    """Signale un artefact de distribution non conforme."""


def _nom_membre_sur(nom: str) -> bool:
    """Retourne True si le nom d'un membre d'archive est sûr à exploiter.

    Défense en profondeur contre les archives malveillantes (règle
    pythonsecurity:S8707) : un nom est sûr s'il est non vide après
    normalisation des séparateurs « \\ » en « / », relatif (ne commence pas
    par « / ») et dépourvu de tout segment exactement égal à « .. »
    (remontée de répertoire).
    """
    normalise = nom.replace("\\", "/")
    if not normalise:
        return False
    if normalise.startswith("/"):
        return False
    return ".." not in normalise.split("/")


def _membres_wheel(chemin: Path) -> tuple[list[str], dict[str, bytes], bytes]:
    try:
        with zipfile.ZipFile(chemin) as archive:
            noms = [nom for nom in archive.namelist() if not nom.endswith("/")]
            metadata = [
                nom for nom in noms if nom.endswith(".dist-info/METADATA")
            ]
            if len(metadata) != 1:
                raise ErreurVerification(
                    f"{chemin}: METADATA wheel introuvable ou ambigu ; "
                    "le wheel doit contenir exactement un fichier *.dist-info/METADATA."
                )
            contenus = {nom: archive.read(nom) for nom in noms}
            return noms, contenus, contenus[metadata[0]]
    except zipfile.BadZipFile as erreur:
        raise ErreurVerification(
            f"{chemin}: wheel illisible ({erreur}). Reconstruisez-le avec python -m build."
        ) from erreur


def _membres_sdist(chemin: Path) -> tuple[list[str], dict[str, bytes], bytes]:
    try:
        with tarfile.open(chemin, "r:gz") as archive:
            membres = [membre for membre in archive.getmembers() if membre.isfile()]
            rejetes = sorted(
                {membre.name for membre in membres if not _nom_membre_sur(membre.name)}
            )
            if rejetes:
                raise ErreurVerification(
                    f"{chemin}: nom(s) de membre non sûr(s) dans le sdist : "
                    f"{', '.join(rejetes)}."
                )
            membres = [membre for membre in membres if _nom_membre_sur(membre.name)]
            noms = [membre.name for membre in membres]
            contenus: dict[str, bytes] = {}
            for membre in membres:
                flux = archive.extractfile(membre)
                if flux is not None:
                    contenus[membre.name] = flux.read()

            metadonnees = sorted(
                nom
                for nom in noms
                if nom.endswith("/PKG-INFO") and nom.count("/") == 1
            )
            if len(metadonnees) != 1:
                raise ErreurVerification(
                    f"{chemin}: PKG-INFO sdist introuvable ou ambigu ; "
                    "l'archive source doit contenir un PKG-INFO à sa racine."
                )
            return noms, contenus, contenus[metadonnees[0]]
    except (tarfile.TarError, OSError) as erreur:
        raise ErreurVerification(
            f"{chemin}: sdist illisible ({erreur}). Reconstruisez-le avec python -m build."
        ) from erreur


def _chemins_paquet(noms: Iterable[str]) -> set[str]:
    chemins: set[str] = set()
    for nom in noms:
        normalise = nom.replace("\\", "/")
        marqueur = "forgeai/"
        position = normalise.find(marqueur)
        if position >= 0:
            chemins.add(normalise[position:])
    return chemins


def _verifier_metadonnees(chemin: Path, contenu: bytes) -> None:
    try:
        metadonnees = BytesParser(policy=default).parsebytes(contenu)
    except Exception as erreur:
        raise ErreurVerification(
            f"{chemin}: métadonnées illisibles ({erreur})."
        ) from erreur

    if metadonnees.get("Name") != NOM_ATTENDU:
        raise ErreurVerification(
            f"{chemin}: nom de paquet attendu « {NOM_ATTENDU} », "
            f"trouvé « {metadonnees.get('Name', '')} »."
        )
    if metadonnees.get("Version") != VERSION_ATTENDUE:
        raise ErreurVerification(
            f"{chemin}: version attendue « {VERSION_ATTENDUE} », "
            f"trouvée « {metadonnees.get('Version', '')} »."
        )
    if metadonnees.get("Requires-Python") != REQUIRES_PYTHON_ATTENDU:
        raise ErreurVerification(
            f"{chemin}: Requires-Python attendu « {REQUIRES_PYTHON_ATTENDU} », "
            f"trouvé « {metadonnees.get('Requires-Python', '')} »."
        )

    classifiers = set(metadonnees.get_all("Classifier", []))
    manquants = sorted(CLASSIFIERS_PYTHON_ATTENDUS - classifiers)
    if manquants:
        raise ErreurVerification(
            f"{chemin}: classifiers Python manquants : {', '.join(manquants)}."
        )


def _compter(chemins: Iterable[str], prefixe: str, suffixe: str | None = None) -> int:
    return sum(
        1
        for chemin in chemins
        if chemin.startswith(prefixe) and (suffixe is None or chemin.endswith(suffixe))
    )


def _verifier_package_data(chemin: Path, chemins: set[str]) -> None:
    exigences = (
        ("locales", "forgeai/data/locales/", ".json"),
        ("stacks", "forgeai/data/stacks/", ".json"),
        ("assets", "forgeai/web/assets/", None),
        ("smoke", "forgeai/data/smoke/", ".md"),
    )
    for categorie, prefixe, suffixe in exigences:
        compte = _compter(chemins, prefixe, suffixe)
        minimum = COMPTES_MINIMAUX[categorie]
        if compte < minimum:
            raise ErreurVerification(
                f"{chemin}: package-data « {categorie}/ » incomplet : "
                f"{compte} fichier(s) trouvé(s), au moins {minimum} attendu(s)."
            )

    catalogue = "forgeai/data/catalogue.json"
    if catalogue not in chemins:
        raise ErreurVerification(
            f"{chemin}: catalogue absent : « {catalogue} » doit être distribué."
        )

    compte_json = sum(1 for chemin_paquet in chemins if chemin_paquet.endswith(".json"))
    if compte_json < NOMBRE_MINIMAL_JSON:
        raise ErreurVerification(
            f"{chemin}: package-data JSON incomplet : {compte_json} fichier(s) trouvé(s), "
            f"au moins {NOMBRE_MINIMAL_JSON} attendu(s)."
        )


def _contient_tests(noms: Iterable[str]) -> bool:
    return any(
        "tests" in nom.replace("\\", "/").lower().split("/")
        for nom in noms
    )


def _verifier_absences_interdites(
    chemin: Path,
    noms: Iterable[str],
    *,
    est_sdist: bool,
) -> None:
    repertoires_interdits = {"reviews", "registres", "governance", ".github"}
    if not est_sdist:
        repertoires_interdits.add("tests")

    noms_liste = list(noms)
    for nom in noms_liste:
        morceaux = [morceau.lower() for morceau in nom.replace("\\", "/").split("/")]
        if "__pycache__" in morceaux or nom.lower().endswith(".pyc"):
            raise ErreurVerification(
                f"{chemin}: fichier Python compilé interdit dans la distribution : {nom}."
            )
        interdit = next(
            (morceau for morceau in morceaux if morceau in repertoires_interdits),
            None,
        )
        if interdit is not None:
            raise ErreurVerification(
                f"{chemin}: fichier inattendu issu de « {interdit}/ » : {nom}."
            )

    if est_sdist and not _contient_tests(noms_liste):
        raise ErreurVerification(
            f"{chemin}: tests/ absent du sdist ; l'archive source doit permettre "
            "de tester le paquet distribué."
        )


def verifier_artefact(chemin: Path) -> None:
    """Vérifie un wheel ou un sdist et lève ErreurVerification au premier manquement."""
    if not chemin.is_file():
        raise ErreurVerification(f"{chemin}: artefact introuvable.")

    nom = chemin.name.lower()
    if nom.endswith(".whl"):
        membres, _contenus, metadonnees = _membres_wheel(chemin)
        est_sdist = False
    elif nom.endswith(".tar.gz") or nom.endswith(".tgz"):
        membres, _contenus, metadonnees = _membres_sdist(chemin)
        est_sdist = True
    else:
        raise ErreurVerification(
            f"{chemin}: format non pris en charge ; fournissez un .whl ou un .tar.gz."
        )

    _verifier_metadonnees(chemin, metadonnees)
    chemins = _chemins_paquet(membres)
    _verifier_package_data(chemin, chemins)
    _verifier_absences_interdites(chemin, membres, est_sdist=est_sdist)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Vérifie les métadonnées et le contenu d'artefacts ForgeAI distribués."
    )
    parser.add_argument(
        "artefacts",
        metavar="ARTEFACT",
        nargs="+",
        type=Path,
        help="wheel (.whl) ou archive source (.tar.gz) à vérifier",
    )
    arguments = parser.parse_args(argv)

    try:
        for artefact in arguments.artefacts:
            verifier_artefact(artefact)
            print(f"OK : {artefact}")
    except ErreurVerification as erreur:
        print(f"ERREUR : {erreur}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
