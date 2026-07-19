import json
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from forgeai.catalogue.spheres import SPHERES, SPHERE_IDS
from forgeai.stacks import list_stacks, load_stack


def _catalogue_ids() -> set[str]:
    from forgeai.resources import catalogue_path

    entries = json.loads(catalogue_path().read_text(encoding="utf-8"))["entries"]
    return {entry["id"] for entry in entries}


def _fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=2) as resp:
        assert resp.status == 200, resp.status
        return json.loads(resp.read().decode("utf-8"))


def _wait_for_json(url: str, max_wait: float = 5.0) -> dict:
    deadline = time.monotonic() + max_wait
    last_exc: Exception | None = None
    while time.monotonic() < deadline:
        try:
            return _fetch_json(url)
        except (urllib.error.URLError, ConnectionRefusedError, TimeoutError) as exc:
            last_exc = exc
            time.sleep(0.05)
    raise last_exc or RuntimeError("serveur non joignable")


def test_defaut_de_sphere_est_deploye() -> None:
    failures: list[tuple[str, str, str]] = []
    for stack_id in list_stacks():
        stack = load_stack(stack_id)
        deploy = stack.get("deploy_by_sphere", {})
        for sphere, default in stack.get("default_by_sphere", {}).items():
            if default not in deploy.get(sphere, []):
                failures.append((stack_id, sphere, default))
    assert not failures, failures


def test_defaut_existe_au_catalogue() -> None:
    catalogue_ids = _catalogue_ids()
    failures: list[tuple[str, str, str]] = []
    for stack_id in list_stacks():
        stack = load_stack(stack_id)
        for sphere, default in stack.get("default_by_sphere", {}).items():
            if default not in catalogue_ids:
                failures.append((stack_id, sphere, default))
    assert not failures, failures


def test_sphere_voix_reelle() -> None:
    assert "VOIX" in SPHERE_IDS
    assert len(SPHERES) == 15
    voix = next(s for s in SPHERES if s.id == "VOIX")
    assert voix.num == 15


def test_api_bricks_voix() -> None:
    from forgeai.web.server import build_server

    server = build_server("127.0.0.1", 0)

    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        base = f"http://127.0.0.1:{port}"

        data = _wait_for_json(f"{base}/api/bricks?sphere=VOIX")
        total = data.get("total", len(data.get("bricks", [])))
        assert total >= 5, data

        data2 = _wait_for_json(
            f"{base}/api/bricks?sphere=VOIX&stack=support-conversationnel"
        )
        bricks = data2.get("bricks", [])
        assert any(b.get("installed") for b in bricks), data2
    finally:
        server.shutdown()


def test_etoiles_catalogue_sans_effet_deploiement() -> None:
    root = Path(__file__).resolve().parents[1]
    targets = (
        root / "src" / "forgeai" / "planner" / "assemble.py",
        root / "src" / "forgeai" / "cli.py",
    )
    for path in targets:
        assert path.exists(), f"{path.relative_to(root)} manquant"
        text = path.read_text(encoding="utf-8")
        assert "category_defaults" not in text, (
            f"{path.relative_to(root)} référence category_defaults"
        )

    loader = root / "src" / "forgeai" / "catalogue" / "loader.py"
    assert loader.exists(), "loader du catalogue manquant"
    assert "category_defaults" in loader.read_text(
        encoding="utf-8"
    ), "category_defaults devrait être défini dans le loader"
