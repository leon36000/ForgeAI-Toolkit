"""Tests de la garde de chaîne d'approvisionnement (SUPPLY-018)."""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from forgeai.catalogue.supply import (
    verify_brick_before_exec,
    SupplyChainError,
    _LICENSE_ALLOWLIST,
)


# ---------------------------------------------------------------------------
# G1-G6 : vérification isolée, index construit à la main
# ---------------------------------------------------------------------------
class TestVerifyBrickUnit:
    def test_missing_digest_raises(self):
        idx = {"ollama": {"verified": True, "license": "MIT"}}  # proof:allow
        with pytest.raises(SupplyChainError, match="épinglée"):
            verify_brick_before_exec("ollama", "ollama/ollama:latest", idx)

    def test_not_verified_raises(self):
        idx = {"ollama": {"verified": False, "license": "MIT"}}  # proof:allow
        with pytest.raises(SupplyChainError, match="non vérifiée"):
            verify_brick_before_exec("ollama", "ollama/ollama@sha256:abc123", idx)

    @pytest.mark.parametrize(
        "bad_license", ["service propriétaire", "proprietary", "BUSL-1.1", "CC-BY-4.0"]
    )
    def test_explicit_disallowed_license_raises(self, bad_license):
        # Licence EXPLICITE hors allowlist → refus, même vérifiée.
        idx = {"ollama": {"verified": True, "license": bad_license}}  # proof:allow
        with pytest.raises(SupplyChainError, match="non autorisée"):
            verify_brick_before_exec("ollama", "ollama/ollama@sha256:abc123", idx)

    @pytest.mark.parametrize("lic", ["NOASSERTION", ""])
    def test_unasserted_license_on_verified_passes(self, lic):
        # Licence NON assertée sur une brique curée (verified) : tolérée (risque couvert par verified).
        idx = {"ollama": {"verified": True, "license": lic}}  # proof:allow
        verify_brick_before_exec("ollama", "ollama/ollama@sha256:abc123", idx)  # ne lève pas

    def test_uncatalogued_but_pinned_passes(self):
        # Brique first-party/châssis (absente du catalogue communautaire) : épinglée = confiance.
        verify_brick_before_exec("postgres", "postgres:15-alpine@sha256:abc", {})  # ne lève pas

    def test_uncatalogued_unpinned_raises(self):
        # L'épinglage reste UNIVERSEL : une brique non cataloguée ET non épinglée est refusée.
        with pytest.raises(SupplyChainError, match="épinglée"):
            verify_brick_before_exec("postgres", "postgres:15-alpine", {})

    def test_happy_path(self):
        idx = {"ollama": {"verified": True, "license": "MIT"}}  # proof:allow
        verify_brick_before_exec("ollama", "ollama/ollama@sha256:abc123", idx)  # ne lève pas

    @pytest.mark.parametrize("allowed", sorted(_LICENSE_ALLOWLIST))
    def test_every_allowed_license_passes(self, allowed):
        idx = {"b": {"verified": True, "license": allowed}}  # proof:allow
        verify_brick_before_exec("b", "b@sha256:abc", idx)

    @pytest.mark.parametrize("bad", ["proprietary", "GPL-4.0", "AGPL-4.0"])
    def test_disallowed_licenses_fail(self, bad):
        idx = {"b": {"verified": True, "license": bad}}  # proof:allow
        with pytest.raises(SupplyChainError):
            verify_brick_before_exec("b", "b@sha256:abc", idx)


# ---------------------------------------------------------------------------
# load_catalog_index : lit le catalogue BRUT (verified/license absents de Brick)
# ---------------------------------------------------------------------------
def test_load_catalog_index_reads_raw(tmp_path):
    from forgeai.catalogue.supply import load_catalog_index
    cat = tmp_path / "catalogue.json"
    cat.write_text(json.dumps({"version": 1, "entries": [
        {"id": "ollama", "verified": True, "license": "MIT"},   # proof:allow
        {"id": "x", "verified": False, "license": "NOASSERTION"},
    ]}), encoding="utf-8")
    idx = load_catalog_index(cat)
    assert idx["ollama"] == {"verified": True, "license": "MIT"}  # proof:allow
    assert idx["x"]["verified"] is False


# ---------------------------------------------------------------------------
# G7 — Intégration : la garde est réellement SUR le chemin d'assemble_plan.
#      On mocke minimal_stack et load_catalog_index LÀ OÙ assemble_plan les
#      référence (forgeai.planner.assemble), pas dans leur module d'origine.
# ---------------------------------------------------------------------------
def _svc(brick_id, image):
    return {"brick_id": brick_id, "name": brick_id, "image": image,
            "container_port": 11434, "volume": None, "healthcheck_path": None,
            "gpu_capable": False, "resource_class": "utilitaire"}


def _overlay(tmp_path):
    p = tmp_path / "deploy-minimal.json"
    p.write_text(json.dumps({"models": {"llm": "m-llm", "embed": "m-embed"}}), encoding="utf-8")
    return p


@patch("forgeai.planner.assemble.load_catalog_index")
@patch("forgeai.planner.assemble.minimal_stack")
def test_assemble_rejects_unpinned_brick(mock_minimal, mock_index, tmp_path):
    mock_minimal.return_value = [_svc("ollama", "ollama/ollama:latest")]  # pas de digest
    mock_index.return_value = {"ollama": {"verified": True, "license": "MIT"}}  # proof:allow
    from forgeai.planner.assemble import assemble_plan
    with pytest.raises(SupplyChainError, match="épinglée"):
        assemble_plan("minimal", _overlay(tmp_path), is_free=lambda p: True)


@patch("forgeai.planner.assemble.load_catalog_index")
@patch("forgeai.planner.assemble.minimal_stack")
def test_assemble_accepts_uncatalogued_pinned_chassis(mock_minimal, mock_index, tmp_path):
    # Brique de châssis (non cataloguée) mais épinglée → plan produit (pas de refus).
    mock_minimal.return_value = [_svc("postgres", "postgres:15-alpine@sha256:abc")]
    mock_index.return_value = {}  # postgres absent du catalogue communautaire
    from forgeai.planner.assemble import assemble_plan
    from forgeai.core.models import DeploymentPlan
    plan = assemble_plan("minimal", _overlay(tmp_path), is_free=lambda p: True)
    assert isinstance(plan, DeploymentPlan)


@patch("forgeai.planner.assemble.load_catalog_index")
@patch("forgeai.planner.assemble.minimal_stack")
def test_assemble_accepts_conforming_brick(mock_minimal, mock_index, tmp_path):
    mock_minimal.return_value = [_svc("ollama", "ollama/ollama:latest@sha256:abc123")]
    mock_index.return_value = {"ollama": {"verified": True, "license": "MIT"}}  # proof:allow
    from forgeai.planner.assemble import assemble_plan
    from forgeai.core.models import DeploymentPlan
    plan = assemble_plan("minimal", _overlay(tmp_path), is_free=lambda p: True)
    assert isinstance(plan, DeploymentPlan)
    assert any(s.name == "ollama" for s in plan.services)
