"""Localisation portable des données embarquées dans le paquet (P3 portabilité).

Le catalogue et l'overlay de déploiement voyagent DANS le paquet `forgeai.data`,
afin que `pip install forgeai-toolkit` fonctionne sur n'importe quelle machine —
jamais un chemin relatif au dépôt de développement.
"""
from __future__ import annotations

from importlib.resources import as_file, files
from pathlib import Path


def data_path(name: str) -> Path:
    """Retourne le chemin d'un fichier de données du paquet (ex. 'catalogue.json').

    Fonctionne que le paquet soit installé (site-packages) ou en développement.
    """
    resource = files("forgeai.data") / name
    with as_file(resource) as path:
        return Path(path)


def catalogue_path() -> Path:
    return data_path("catalogue.json")


def deploy_overlay_path() -> Path:
    return data_path("deploy-minimal.json")
