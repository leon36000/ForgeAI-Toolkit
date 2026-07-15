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

from forgeai.resources import catalogue_path, deploy_overlay_path

CATALOGUE = catalogue_path()
DEPLOY = deploy_overlay_path()


def test_catalogue_reel_integre_et_complet():
    assert verify_catalogue(CATALOGUE)
    bricks = load_catalogue(CATALOGUE)
    # Base : 1021 − 7 (retrait autorisé Command/Control Center + artefacts, registre
    # retrait_bespoke) = 1014. R-ALL peut ensuite AJOUTER des briques vérifiées
    # (dossier sourcé) ou en retirer sur preuve INTROUVABLE — donc borne, pas égalité.
    assert len(bricks) >= 940  # 1021 − Command/Control Center − INTROUVABLE bespoke (registre retrait_bespoke); décroît sur preuve
    # Aucune entrée vérifiée R-ALL ne doit être sans source (règle de rigueur).
    data = json.loads(CATALOGUE.read_text(encoding="utf-8"))
    for e in data["entries"]:
        if e.get("verified"):
            assert e.get("source_url", "").startswith("http"), e["name"]
    # Le compte des traductions en attente décroît à chaque lot appliqué (P2-F23) :
    # cohérence structurelle data-driven plutôt que valeur figée.
    data = json.loads(CATALOGUE.read_text(encoding="utf-8"))
    pending_flags = sum(1 for e in data["entries"] if e["en_pending"] or e["atlas_only"])
    pending_bricks = sum(1 for b in bricks if b.description_en is None)
    assert pending_bricks == pending_flags
    assert sum(1 for e in data["entries"] if e["en_pending"]) <= 742  # jamais de régression


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
