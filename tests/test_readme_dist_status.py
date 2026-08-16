"""Tests de conformité et de statut de distribution du README.md (Issue #442 / RC1-012).

Rappel TDD : sur l'ancien README, le test `test_readme_installation_regression_guard`
échouait car la commande nue 'pip install forgeai-toolkit' était présentée comme
méthode d'installation par défaut alors que le paquet n'est pas publié sur PyPI.
De même, `test_readme_public_docs_indexed` et `test_readme_rc1_v1_status_and_links`
échouaient sur l'ancien README faute d'indexation de CONTRIBUTING.md/SECURITY.md
et de distinction formelle RC1 (#428) vs v1.0 (#429).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _resolve_state_path(data: dict, path_str: str):
    """Résout un chemin à points dans le JSON d'état (racine ou sous 'deterministe')."""
    keys = path_str.split(".")
    # 1. Essai depuis la racine
    cur = data
    found = True
    for k in keys:
        if isinstance(cur, dict) and k in cur:
            cur = cur[k]
        else:
            found = False
            break
    if found:
        return cur

    # 2. Essai sous deterministe si présent
    if "deterministe" in data and isinstance(data["deterministe"], dict):
        cur = data["deterministe"]
        for k in keys:
            if isinstance(cur, dict) and k in cur:
                cur = cur[k]
            else:
                raise KeyError(f"Clé non trouvée dans STATE-CURRENT.json: {path_str}")
        return cur

    raise KeyError(f"Clé non trouvée dans STATE-CURRENT.json: {path_str}")


def test_readme_installation_regression_guard():
    """Vérifie que le README ne promeut pas 'pip install forgeai-toolkit' nu depuis PyPI.

    Le chemin principal documenté doit être l'installation locale depuis un clone
    (ex: `pip install -e .` ou `pip install .`).
    """
    readme_path = REPO_ROOT / "README.md"
    assert readme_path.exists(), "Le fichier README.md doit exister à la racine du dépôt"
    content = readme_path.read_text(encoding="utf-8")

    # Guard 1: Interdiction absolue de la commande nue 'pip install forgeai-toolkit'
    # sans qualification, qui échouerait car le paquet n'est pas publié sur PyPI.
    bare_pypi_pattern = re.compile(r"^\s*pip install forgeai-toolkit\s*$", re.MULTILINE)
    assert not bare_pypi_pattern.search(
        content
    ), "Le README ne doit pas contenir la commande nue 'pip install forgeai-toolkit' (non publié sur PyPI)"

    # Guard 2: Présence documentée du chemin local valide
    local_install_pattern = re.compile(r"pip install -e \.", re.MULTILINE)
    assert local_install_pattern.search(
        content
    ), "Le README doit présenter l'installation locale 'pip install -e .' comme parcours principal"


def test_readme_safe_commands_executable():
    """Exécute réellement les commandes sûres documentées pour garantir leur véracité."""
    # 1. Script d'état des capacités
    cap_cmd = [sys.executable, "scripts/governance/capabilities.py"]
    res_cap = subprocess.run(
        cap_cmd,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert res_cap.returncode == 0, (
        f"La commande '{' '.join(cap_cmd)}' doit réussir. "
        f"Sortie stderr: {res_cap.stderr}"
    )

    # 2. Scanner d'absence de stubs
    stub_cmd = [sys.executable, "scripts/no_stub_scan.py", "--all"]
    res_stub = subprocess.run(
        stub_cmd,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert res_stub.returncode == 0, (
        f"La commande '{' '.join(stub_cmd)}' doit réussir. "
        f"Sortie stderr: {res_stub.stderr}"
    )

    # 3. Test d'importabilité du CLI avec PYTHONPATH=src
    import_env = {**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")}
    import_cmd = [sys.executable, "-c", "import forgeai.cli"]
    res_import = subprocess.run(
        import_cmd,
        cwd=REPO_ROOT,
        env=import_env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert res_import.returncode == 0, (
        f"L'import du module forgeai.cli doit réussir avec PYTHONPATH=src. "
        f"Sortie stderr: {res_import.stderr}"
    )


def test_readme_rc1_v1_status_and_links():
    """Vérifie que les statuts RC1 et v1.0 sont distingués et liés aux issues canoniques #428 et #429."""
    readme_path = REPO_ROOT / "README.md"
    content = readme_path.read_text(encoding="utf-8")

    assert "RC1" in content, "Le statut RC1 doit être explicité dans le README"
    assert "v1.0" in content or "v1" in content, "Le statut v1.0 doit être explicité dans le README"

    # Vérification de la présence des références aux issues de gouvernance #428 et #429
    assert (
        "#428" in content or "issues/428" in content
    ), "Le README doit pointer vers l'issue RC1 (#428)"
    assert (
        "#429" in content or "issues/429" in content
    ), "Le README doit pointer vers l'issue v1.0 (#429)"


def test_readme_state_markers_consistency():
    """Vérifie que les marqueurs <!-- state:... --> sont valides et synchronisés avec STATE-CURRENT.json."""
    state_file = REPO_ROOT / "governance" / "STATE-CURRENT.json"
    assert state_file.exists(), "Le fichier governance/STATE-CURRENT.json doit exister"

    with state_file.open("r", encoding="utf-8") as f:
        state_data = json.load(f)

    readme_path = REPO_ROOT / "README.md"
    content = readme_path.read_text(encoding="utf-8")

    marker_pattern = re.compile(r"<!--\s*state:([a-zA-Z0-9_\.]+)\s*-->(.*?)<!--\s*/state\s*-->")
    matches = marker_pattern.findall(content)

    assert len(matches) > 0, "Le README doit contenir au moins un marqueur <!-- state:... -->"

    for path_str, displayed_value in matches:
        expected_raw_value = _resolve_state_path(state_data, path_str)
        expected_str = str(expected_raw_value).strip()
        actual_str = displayed_value.strip()

        assert actual_str == expected_str, (
            f"Désynchronisation du marqueur state:{path_str} : "
            f"affiché '{actual_str}', attendu '{expected_str}' selon STATE-CURRENT.json"
        )


def test_readme_public_docs_indexed():
    """Vérifie que CONTRIBUTING.md et SECURITY.md existent et sont référencés dans le README."""
    contributing_file = REPO_ROOT / "CONTRIBUTING.md"
    security_file = REPO_ROOT / "SECURITY.md"
    readme_path = REPO_ROOT / "README.md"

    assert contributing_file.is_file(), "Le fichier CONTRIBUTING.md doit exister à la racine"
    assert security_file.is_file(), "Le fichier SECURITY.md doit exister à la racine"

    content = readme_path.read_text(encoding="utf-8")
    assert "CONTRIBUTING.md" in content, "Le README doit contenir un lien vers CONTRIBUTING.md"
    assert "SECURITY.md" in content, "Le README doit contenir un lien vers SECURITY.md"
    assert "LICENSE" in content, "Le README doit contenir un lien vers LICENSE"
