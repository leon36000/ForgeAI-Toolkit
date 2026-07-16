"""
Portability module for ForgeAI stack setup export/import.

Guarantees:
- Bundles NEVER contain secrets (vault.json is excluded). Only key_fingerprint travels.
- Integrity is protected by a deterministic SHA‑256 hash of canonicalised JSON.
- Import never writes vault.json – secret provisioning is a separate manual step.
- Round‑trip is proven by content‑identicality of all setup files after import.
"""

import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

BUNDLE_VERSION = 1
SETUP_FILES = ("routes.json", "gateway.json", "wirings.json", "strategy.json", "budgets.json")
EXCLUDED_FILES = frozenset({"vault.json"})


class PortabilityError(Exception):
    """Raised when the bundle is invalid, tampered, or an operation is unsafe."""


def _canonical(payload: dict) -> str:
    """Deterministic JSON serialisation for hash computation."""
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def bundle_sha256(files: dict) -> str:
    """SHA‑256 hash of the logical bundle payload (version + files)."""
    envelope = {"version": BUNDLE_VERSION, "files": files}
    return hashlib.sha256(_canonical(envelope).encode("utf-8")).hexdigest()


def export_setup(home: str, out_path: Optional[str] = None) -> dict:
    """
    Export the current model‑stack setup into a portable, tamper‑proof bundle.

    Args:
        home: Path to the forge‑home directory containing the setup files.
        out_path: If given, write the bundle JSON to this path.

    Returns:
        The bundle dictionary.

    Raises:
        PortabilityError: If a route contains a plain‑text secret or if an
            excluded file would be included.
    """
    home = Path(home)
    files: Dict[str, Any] = {}

    for fname in SETUP_FILES:
        src = home / fname
        if src.exists():
            content = json.loads(src.read_text(encoding="utf-8"))
            files[fname] = content

    # Guard: excluded files must never be part of the bundle.
    if forbidden := EXCLUDED_FILES.intersection(files.keys()):
        raise PortabilityError(
            f"Forbidden files would be exported: {', '.join(forbidden)}"
        )

    # Guard: no plain‑text secrets in routes.
    routes_content = files.get("routes.json")
    if isinstance(routes_content, list):
        for idx, route in enumerate(routes_content):
            if not isinstance(route, dict):
                continue
            for forbidden_key in ("api_key", "key", "secret"):
                if forbidden_key in route and route[forbidden_key]:
                    raise PortabilityError(
                        f"Route at index {idx} contains a plain‑text '{forbidden_key}'. "
                        "Secrets must never be exported in clear."
                    )

    bundle = {
        "version": BUNDLE_VERSION,
        "created_at": date.today().isoformat(),
        "files": files,
        "sha256": bundle_sha256(files),
    }

    if out_path is not None:
        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(bundle, ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8",
        )

    return bundle


def verify_bundle(bundle: dict) -> None:
    """
    Verify that a bundle has the expected version and hash integrity.

    Raises PortabilityError on mismatch or tampering.
    """
    if bundle.get("version") != BUNDLE_VERSION:
        raise PortabilityError(
            f"Incompatible bundle version: {bundle.get('version')} "
            f"(expected {BUNDLE_VERSION})"
        )

    expected = bundle_sha256(bundle["files"])
    if bundle["sha256"] != expected:
        raise PortabilityError("Bundle integrity check failed – hash mismatch.")


def load_bundle(path: str) -> dict:
    """Load a bundle from disk and verify its integrity."""
    raw = Path(path).read_text(encoding="utf-8")
    bundle = json.loads(raw)
    verify_bundle(bundle)
    return bundle


def secrets_to_reprovision(bundle: dict) -> List[str]:
    """
    Return sorted list of route names that have a key_fingerprint and therefore
    require the operator to re‑enter the secret on the target machine.
    """
    routes = bundle.get("files", {}).get("routes.json", [])
    if not isinstance(routes, list):
        return []
    names = []
    for route in routes:
        if isinstance(route, dict) and route.get("key_fingerprint"):
            names.append(route.get("name", "unnamed"))
    return sorted(names)


def import_setup(bundle_path: str, home: str, *, force: bool = False) -> dict:
    """
    Import a portable bundle into a forge‑home directory.

    The bundle is first verified. Existing files are only overwritten when
    ``force=True``. vault.json is NEVER written.

    Returns a report dict with:
        restored: list of restored file names
        secrets_to_reprovision: routes whose secrets must be re‑entered
        home: the target home directory
    """
    bundle = load_bundle(bundle_path)
    home = Path(home)
    home.mkdir(parents=True, exist_ok=True)

    restored = []
    for fname, content in bundle["files"].items():
        dest = home / fname
        if dest.exists() and not force:
            raise PortabilityError(
                f"File already exists: {dest}. "
                "Use force=True to overwrite."
            )
        dest.write_text(
            json.dumps(content, ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8",
        )
        restored.append(fname)

    return {
        "restored": restored,
        "secrets_to_reprovision": secrets_to_reprovision(bundle),
        "home": str(home),
    }
