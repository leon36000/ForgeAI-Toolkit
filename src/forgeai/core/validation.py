"""Validateurs partagés (source unique — évite la duplication CLI ↔ web ↔ …)."""
import os
import re
from pathlib import Path

from forgeai.i18n import t

# Nom de nœud / hôte : label RFC1123 en minuscules (a-z0-9, tirets/points internes, 1-63 car.).
# Source UNIQUE réutilisée par cli.py et web/server.py (FAI-0016 : dé-duplication).
NODE_NAME_RE = re.compile(r"^[a-z0-9]([a-z0-9.-]{0,62})$", re.ASCII)


class ValidationError(ValueError):
    """Erreur de validation d'un chemin ou d'un nom."""


def valider_nom_simple(name: str) -> None:
    """Lève ValidationError si le nom est vide, vaut '.', contient '/', os.sep ou '..'."""
    if (
        not name
        or name == "."
        or "/" in name
        or os.sep in name
        or ".." in name
    ):
        raise ValidationError(t("core.validation.valider_nom_simple.nom_invalide", name=name))


def resolve_within(
    path: str | os.PathLike[str],
    root: str | os.PathLike[str],
    *,
    base: str | os.PathLike[str] | None = None,
) -> Path:
    """Résout `path` et vérifie qu'il est contenu dans `root` (realpath des deux côtés)."""
    path_str = os.fspath(path)
    root_str = os.fspath(root)

    if not os.path.isabs(path_str):
        if base is not None:
            base_str = os.fspath(base)
            resolved = os.path.join(base_str, path_str)
        else:
            resolved = path_str
    else:
        resolved = path_str

    cible_reelle = os.path.realpath(resolved)
    racine_reelle = os.path.realpath(root_str)

    cible_norm = os.path.normcase(cible_reelle)
    racine_norm = os.path.normcase(racine_reelle)

    try:
        common = os.path.commonpath([racine_norm, cible_norm])
    except ValueError as exc:
        raise ValidationError(
            t("core.validation.resolve_within.chemin_hors_racine",
              cible=cible_reelle, racine=racine_reelle)
        ) from exc

    if common != racine_norm:
        raise ValidationError(
            t("core.validation.resolve_within.chemin_hors_racine",
              cible=cible_reelle, racine=racine_reelle)
        )

    return Path(cible_reelle)
