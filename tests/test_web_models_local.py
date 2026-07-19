"""P0.3 — registre des modèles locaux : 113 entrées vérifiées HF, servies SANS filtrage matériel.

Directive permanente : la config locale ne restreint JAMAIS le choix — tout modèle est
déployable vers n'importe quel nœud du réseau."""
import json
import threading
import urllib.request

import pytest

from forgeai.web.server import build_server


@pytest.fixture()
def base_url():
    srv = build_server("127.0.0.1", 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()
    srv.server_close()


def _get(base, path):
    with urllib.request.urlopen(base + path, timeout=10) as r:
        return r.status, json.loads(r.read().decode("utf-8"))


def test_registre_complet_et_integre(base_url):
    status, d = _get(base_url, "/api/models/local")
    assert status == 200
    assert d["total"] == len(d["modeles"]) == 113
    for m in d["modeles"]:
        assert m["hf_id"] and m["source_url"].startswith("https://huggingface.co")
        assert m["tier"] in ("petit", "moyen", "gros")
        assert m["famille"] and m["verif"], m["hf_id"]


def test_citations_utilisateur_presentes(base_url):
    """GLM 5.2, Qwen 3.6 27B et Gemma 4 (cites par l'utilisateur) sont VERIFIES reels."""
    _, d = _get(base_url, "/api/models/local")
    ids = {m["hf_id"] for m in d["modeles"]}
    assert "zai-org/GLM-5.2" in ids
    assert "Qwen/Qwen3.6-27B" in ids
    assert any(i.startswith("google/gemma-4") for i in ids)


def test_aucun_filtrage_materiel(base_url):
    """Les 3 tiers sont TOUS servis quel que soit le materiel local (gros inclus)."""
    _, d = _get(base_url, "/api/models/local")
    tiers = {m["tier"] for m in d["modeles"]}
    assert tiers == {"petit", "moyen", "gros"}
    assert sum(1 for m in d["modeles"] if m["tier"] == "gros") >= 20
