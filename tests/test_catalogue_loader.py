"""Tests S03 — catalogue : intégrité hash + chargement + overlay Minimal."""
import json
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from forgeai.catalogue.loader import (
    CatalogueError,
    load_catalogue,
    minimal_stack,
    verify_catalogue,
)

REPO = Path(__file__).resolve().parent.parent
CATALOGUE = REPO / "catalogue" / "catalogue.json"
DEPLOY = REPO / "catalogue" / "deploy-minimal.json"


def test_catalogue_reel_integre_et_complet():
    assert verify_catalogue(CATALOGUE)
    bricks = load_catalogue(CATALOGUE)
    assert len(bricks) == 1021
    pending = [b for b in bricks if b.description_en is None]
    assert len(pending) == 742 + 231  # traductions dues + entrées Atlas à enrichir


def test_alteration_detectee(tmp_path):
    altered = tmp_path / "catalogue.json"
    shutil.copy(CATALOGUE, altered)
    shutil.copy(CATALOGUE.with_suffix(".sha256"), tmp_path / "catalogue.sha256")
    data = json.loads(altered.read_text(encoding="utf-8"))
    data["entries"][0]["name"] = "FALSIFIÉ"
    altered.write_text(json.dumps(data, ensure_ascii=False, sort_keys=True, indent=1),
                       encoding="utf-8")
    with pytest.raises(CatalogueError, match="altéré"):
        verify_catalogue(altered)


def test_briques_connues_presentes():
    bricks = {b.id for b in load_catalogue(CATALOGUE)}
    assert "activepieces" in bricks
    assert any("ollama" in b for b in bricks)
    assert any("qdrant" in b for b in bricks)


def test_overlay_minimal_valide():
    services = minimal_stack(DEPLOY)
    names = {s["name"] for s in services}
    assert names == {"ollama", "vector-store"}
    assert all(":" in s["image"] for s in services)  # images taguées


def test_overlay_service_incomplet_rejete(tmp_path):
    bad = tmp_path / "deploy.json"
    bad.write_text('{"services": [{"name": "x"}]}', encoding="utf-8")
    with pytest.raises(CatalogueError, match="champs manquants"):
        minimal_stack(bad)
