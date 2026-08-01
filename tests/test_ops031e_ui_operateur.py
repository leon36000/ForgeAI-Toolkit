from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
HTML = ROOT / "src/forgeai/web/assets/index.html"
APPJS = ROOT / "src/forgeai/web/assets/app.js"
FR = ROOT / "src/forgeai/data/locales/fr.json"
EN = ROOT / "src/forgeai/data/locales/en.json"


def read(path: Path) -> str:
    content = path.read_text(encoding="utf-8")
    assert content
    return content


def locale_web_keys(path: Path) -> set[str]:
    payload = json.loads(read(path))
    assert isinstance(payload, dict)
    table = payload.get("web", payload)
    assert isinstance(table, dict)
    return set(table)


def test_g1_operations_panel_is_outside_step_rail() -> None:
    html = read(HTML)
    match = re.search(r'<section\b[^>]*\bid="operations"[^>]*>', html)
    assert match is not None
    opening_tag = match.group(0)
    assert "data-step-panel" not in opening_tag


def test_g2_operations_toggle_is_in_header_controls_not_step_rail() -> None:
    html = read(HTML)
    controls_start = html.index('<div class="controls">')
    header_end = html.index("</header>", controls_start)
    toggle_position = html.index('id="ops-toggle"')
    rail_start = html.index('<nav id="step-rail"')
    rail_end = html.index("</nav>", rail_start)

    assert controls_start < toggle_position < header_end
    assert not rail_start < toggle_position < rail_end


def test_g3_status_and_existing_event_stream_are_used_without_new_routes() -> None:
    appjs = read(APPJS)

    assert "'/api/status'" in appjs
    assert "/api/deploy/events" in appjs
    assert "/api/diagnostic" not in appjs
    assert "/api/logs" not in appjs


def test_g4_status_handles_unauthorized_explicitly() -> None:
    appjs = read(APPJS)
    status_position = appjs.index("'/api/status'")
    nearby_code = appjs[max(0, status_position - 1000):status_position + 1500]

    assert "401" in nearby_code
    assert "ops_auth_requise" in nearby_code
    assert "response.status === 401" in nearby_code


def test_g5_diagnostic_is_cli_only_without_browser_export() -> None:
    html = read(HTML)
    appjs = read(APPJS)
    combined = f"{html}\n{appjs}".lower()

    assert "forgeai diagnostic --out diagnostic.json" in f"{html}\n{appjs}"
    assert "download" not in combined
    assert "blob:" not in combined


def test_g6_operations_i18n_keys_have_fr_en_parity() -> None:
    fr_ops_keys = {key for key in locale_web_keys(FR) if key.startswith("ops_")}
    en_ops_keys = {key for key in locale_web_keys(EN) if key.startswith("ops_")}

    assert fr_ops_keys
    assert en_ops_keys
    assert fr_ops_keys == en_ops_keys


def test_g7_log_stream_does_not_clobber_the_status_panel() -> None:
    """Le bouton « journaux » ne doit PAS confier `#ops-status` à `streamDeployLog`.

    Détecteur de l'objection de revue : le handler `end` du flux écrit
    `status.textContent = t('deploy_done_ok')`. Si `#ops-status` lui était passé comme élément de
    statut, la fin d'un déploiement ÉCRASERAIT l'agrégat /api/status affiché à l'opérateur —
    un écran de santé qui se fait remplacer par autre chose est pire qu'un écran vide.
    """
    appjs = read(APPJS)
    handler_start = appjs.index("loadLogs.addEventListener")
    handler = appjs[handler_start:handler_start + 600]
    # On découpe jusqu'à la FIN D'INSTRUCTION `);` : couper au premier `)` s'arrêterait sur celui
    # de `getElementById(...)` et masquerait un second argument — le test passerait alors quelle
    # que soit la réalité (vérifié : la mutation survivait avec ce découpage naïf).
    appel = handler[handler.index("streamDeployLog("):]
    appel = appel[:appel.index(");") + 2]

    assert "ops-log" in appel, "le flux doit bien alimenter le journal du panneau"
    assert "ops-status" not in appel, (
        "`#ops-status` ne doit jamais servir d'élément de statut au flux : la fin de déploiement "
        f"y écraserait l'agrégat de santé (appel trouvé : {appel})"
    )
