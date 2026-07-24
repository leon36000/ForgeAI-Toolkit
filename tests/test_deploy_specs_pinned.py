from __future__ import annotations

import json
import re
from importlib import resources
from pathlib import Path

import pytest

_FILES = (
    "deploy-specs.json",
    "deploy-minimal.json",
    "deploy-hardened.json",
)

_DIGEST_RE = re.compile(r".+@sha256:[0-9a-f]{64}")


def _data_dir() -> Path:
    """Retourne le répertoire `src/forgeai/data/`, via importlib.resources ou pathlib."""
    try:
        return Path(str(resources.files("forgeai") / "data"))
    except Exception:
        repo_root = Path(__file__).resolve().parent.parent
        return repo_root / "src" / "forgeai" / "data"


def _iter_images(obj, service_name: str | None = None):
    """Itère sur les couples (nom_service, image) trouvés dans la structure JSON."""
    if isinstance(obj, dict):
        if "image" in obj and isinstance(obj["image"], str):
            name = service_name or obj.get("name") or obj.get("service") or "<anonymous>"
            yield name, obj["image"]
        for key, value in obj.items():
            next_name = service_name
            if next_name is None and isinstance(value, dict):
                next_name = key
            elif key in ("name", "service") and isinstance(value, str):
                next_name = value
            yield from _iter_images(value, next_name)
    elif isinstance(obj, list):
        for item in obj:
            yield from _iter_images(item, service_name)


def test_deploy_images_are_pinned_by_digest() -> None:
    data_dir = _data_dir()
    unpinned: list[str] = []

    for filename in _FILES:
        path = data_dir / filename
        if not path.exists():
            if filename == "deploy-specs.json":
                pytest.fail(f"Fichier requis absent : {path}")
            continue

        data = json.loads(path.read_text(encoding="utf-8"))
        for service, image in _iter_images(data):
            if "@sha256:" not in image or _DIGEST_RE.fullmatch(image) is None:
                unpinned.append(f"{filename}:{service} -> {image}")

    assert not unpinned, "Images non épinglées par digest :\n" + "\n".join(unpinned)
