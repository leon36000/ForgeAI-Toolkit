from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_PATH = REPO_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from forgeai.hardware.drivers import VENDORS

GPU_DOC = REPO_ROOT / "Docs" / "reference" / "gpu-drivers-support.md"
ETAT_DOC = REPO_ROOT / "CANON" / "ETAT-SYSTEME.md"


def test_gpu_drivers_reference_doc_exists_and_traces_intel_issue():
    assert GPU_DOC.exists(), f"Missing reference doc: {GPU_DOC}"
    text = GPU_DOC.read_text(encoding="utf-8")
    lowered = text.lower()
    for vendor in VENDORS:
        assert vendor in lowered, f"Vendor {vendor!r} must be cited in {GPU_DOC}"
    assert "lab-033i" in lowered, f"Intel qualification issue LAB-033I must be cited in {GPU_DOC}"


def test_etat_systeme_refers_to_gpu_drivers_reference():
    assert ETAT_DOC.exists(), f"Missing canonical state doc: {ETAT_DOC}"
    text = ETAT_DOC.read_text(encoding="utf-8")
    assert "Docs/reference/gpu-drivers-support.md" in text


def test_etat_systeme_no_longer_claims_uniform_gpu_driver_coverage():
    assert ETAT_DOC.exists()
    text = ETAT_DOC.read_text(encoding="utf-8")
    forbidden = "cycle de vie des drivers GPU NVIDIA/AMD/Intel"
    assert forbidden not in text, f"Old unqualified GPU claim must be removed: {forbidden!r}"


def test_gpu_drivers_reference_covers_exact_code_vendors():
    assert GPU_DOC.exists()
    lowered = GPU_DOC.read_text(encoding="utf-8").lower()
    cited = {vendor for vendor in VENDORS if vendor in lowered}
    assert cited == set(VENDORS), (
        f"{GPU_DOC} must cite exactly the vendors from "
        f"forgeai.hardware.drivers.VENDORS: {set(VENDORS)!r}; "
        f"missing: {set(VENDORS) - cited!r}"
    )
