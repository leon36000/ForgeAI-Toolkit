"""FAI-0009 (#115) — path traversal via le paramètre `stack`. `load_stack(stack_id)` construit
`stacks_dir()/f"{stack_id}.json"` sans normaliser : un `stack_id` avec `../` sort du dossier et
charge un `.json` arbitraire. Les routes /api/summary et /api/bricks passent `stack` non gardé
(contrairement à /api/stacks/<sid>).

Spécification : `load_stack` (point unique, protège tous les appelants) DOIT rejeter tout `stack_id`
contenant `/`, `\\`, `..` (ou vide). RED avant correctif : la traversée charge le fichier hors dossier.
"""
import json
import threading
import urllib.error
import urllib.request

import pytest

from forgeai.stacks import load_stack
from forgeai.web.server import build_server


def test_load_stack_rejette_la_traversee(tmp_path, monkeypatch):
    stacks = tmp_path / "stacks"
    stacks.mkdir()
    (stacks / "ok.json").write_text(json.dumps({"deploy": []}), encoding="utf-8")
    (tmp_path / "secret.json").write_text(json.dumps({"leaked": True}), encoding="utf-8")  # HORS stacks/
    monkeypatch.setattr("forgeai.stacks.stacks_dir", lambda: stacks)

    assert load_stack("ok") == {"deploy": []}  # cible légitime inchangée
    for hostile in ["../secret", "../../etc/passwd", "a/b", "..\\secret"]:
        with pytest.raises(FileNotFoundError):
            load_stack(hostile)


def test_api_summary_rejette_la_traversee(tmp_path, monkeypatch):
    """Boundary web : /api/summary?stack=<traversée> → 404, jamais le contenu hors dossier."""
    stacks = tmp_path / "stacks"
    stacks.mkdir()
    (tmp_path / "secret.json").write_text(json.dumps({"leaked": True}), encoding="utf-8")
    monkeypatch.setattr("forgeai.stacks.stacks_dir", lambda: stacks)

    srv = build_server("127.0.0.1", 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        req = f"{base}/api/summary?stack=..%2Fsecret"
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                status, body = r.status, r.read().decode()
        except urllib.error.HTTPError as exc:
            status, body = exc.code, exc.read().decode()
        assert status == 404, f"traversée acceptée (status {status})"
        assert "leaked" not in body
    finally:
        srv.shutdown()
        srv.server_close()
