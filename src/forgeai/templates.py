import json
from pathlib import Path


class TemplateError(Exception):
    """Erreur spécifique aux templates."""


def templates_dir() -> Path:
    return Path(__file__).resolve().parent / "data" / "templates"


def list_templates() -> list[str]:
    try:
        files = list(templates_dir().glob("*.json"))
    except FileNotFoundError:
        return []
    stems = sorted(f.stem for f in files if f.is_file())
    return stems


def load_template(name: str) -> dict:
    template_path = templates_dir() / f"{name}.json"
    if not template_path.is_file():
        raise TemplateError(f"Template '{name}' introuvable.")
    with open(template_path, encoding="utf-8") as f:
        return json.load(f)


def validate_template(template: dict, catalogue_entries: list[dict]) -> list[str]:
    catalogue_index = {entry["id"]: entry for entry in catalogue_entries}
    violations = []
    for brick in template.get("bricks", []):
        bid = brick.get("id")
        if bid is None:
            continue  # situation anormale, pas de règle prévue
        entry = catalogue_index.get(bid)
        if entry is None:
            violations.append(f"brique inconnue au catalogue : '{bid}'")
        else:
            desc_fr = entry.get("description_fr", "")
            desc_en = entry.get("description_en", "")
            if not desc_fr or not desc_en:
                violations.append(f"brique non bilingue : '{bid}'")
    return sorted(set(violations))


def resolve_template(template: dict, *, has_gpu: bool) -> list[dict]:
    bricks = template.get("bricks", [])
    resolved = []
    for brick in bricks:
        if brick.get("requires_gpu", False) and not has_gpu:
            continue
        resolved.append(brick)
    return resolved


def deployable_bricks(template: dict, *, has_gpu: bool) -> list[dict]:
    resolved = resolve_template(template, has_gpu=has_gpu)
    return [b for b in resolved if b.get("deployable", False)]
