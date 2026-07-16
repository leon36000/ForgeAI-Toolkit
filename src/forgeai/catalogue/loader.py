"""Story P1-S03 — chargement du catalogue + vérification d'intégrité.

Le catalogue de connaissance (1021 entrées, catalogue/catalogue.json) est vérifié
contre son empreinte sha256 (gate hash-catalogue). La stack de déploiement Minimal
est un overlay curé (deploy-minimal.json) : briques exécutables avec images pinnées
par tag, ports et healthchecks — séparées de la connaissance, comme journalisé au
registre (les 1021 entrées décrivent l'écosystème; l'overlay décrit ce que P1 déploie).
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from forgeai.core.models import Brick


class CatalogueError(Exception):
    pass


def verify_catalogue(path: Path) -> str:
    """Vérifie l'empreinte sha256 du catalogue. Retourne le hash si intègre."""
    payload = path.read_text(encoding="utf-8")
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    recorded = path.with_suffix(".sha256").read_text(encoding="utf-8").strip()
    if digest != recorded:
        raise CatalogueError(
            f"Empreinte catalogue invalide : {digest} ≠ {recorded} (fichier altéré)")
    return digest


def load_catalogue(path: Path) -> list[Brick]:
    verify_catalogue(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    bricks = []
    for e in data["entries"]:
        bricks.append(Brick(
            id=e["id"],
            name_fr=e["name"],
            name_en=e["name"],
            category=e["category"],
            atlas_status=e["atlas_status"],
            description_fr=e["description_fr"],
            description_en=e["description_en"],
            source_url=e["source_url"],
        ))
    return bricks


def minimal_stack(deploy_path: Path) -> list[dict]:
    """Briques exécutables du profil Minimal (overlay curé, images pinnées)."""
    data = json.loads(deploy_path.read_text(encoding="utf-8"))
    services = data["services"]
    if not services:
        raise CatalogueError("Overlay de déploiement vide")
    for svc in services:
        missing = {"name", "image", "container_port"} - set(svc)
        if missing:
            raise CatalogueError(f"Service {svc.get('name', '?')} : champs manquants {missing}")
    return services


def parse_stars(popularity: str | None) -> int:
    """Extrait l'entier d'étoiles d'une chaîne de popularité."""
    if popularity is None:
        return 0
    match = re.search(r"★\s*(\d+)", popularity)
    if match is None:
        return 0
    return int(match.group(1))


def category_defaults(entries: list[dict]) -> dict[str, str]:
    """Retourne, pour chaque catégorie, le nom de l'entrée par défaut.

    L'entrée par défaut est celle ayant le plus d'étoiles ; en cas d'égalité,
    le départage se fait par ordre alphabétique croissant du nom.
    """
    defaults: dict[str, tuple[int, str]] = {}
    for entry in entries:
        category = entry["category"]
        name = entry["name"]
        stars = parse_stars(entry.get("popularity"))
        current = defaults.get(category)
        if current is None or stars > current[0] or (stars == current[0] and name < current[1]):
            defaults[category] = (stars, name)
    return {category: name for category, (_, name) in defaults.items()}
