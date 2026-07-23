"""FAI-0010 (#116) — RouteStore.add_cloud et Vault.put font un read-modify-write NON verrouillé
(_load -> mutate -> _save par réécriture complète). Deux ajouts concurrents lisent le même état,
puis la dernière écriture écrase l'autre : des routes ET des clés API scellées sont PERDUES.

Spécification : N ajouts concurrents de routes distinctes ⇒ les N routes sont persistées, et les N
clés sont retrouvables au coffre. RED avant correctif : lost-update (moins de N).
"""
import json
import multiprocessing as mp
import threading
from pathlib import Path

from forgeai.models.routes import RouteStore
from forgeai.models.vault import Vault

FAKE_KEY = "sk-fake-DO-NOT-LEAK"


class _GreenTransport:
    def post(self, url, headers, body, timeout):
        return 200, json.dumps({"choices": [{"message": {"content": "pong"}}]})


def _add_one(home_str: str, i: int, barrier) -> None:
    barrier.wait()
    store = RouteStore(Path(home_str))
    store.add_cloud(f"route-{i}", "openrouter", "z-ai/glm-4.6", FAKE_KEY, "pp-coffre",
                    transport=_GreenTransport())


def test_add_cloud_concurrent_ne_perd_aucune_route(tmp_path):
    """N process ajoutent des routes distinctes en parallèle ⇒ les N sont persistées."""
    home = tmp_path / "models"
    N = 8
    ctx = mp.get_context("fork")
    barrier = ctx.Barrier(N)
    procs = [ctx.Process(target=_add_one, args=(str(home), i, barrier)) for i in range(N)]
    for p in procs:
        p.start()
    for p in procs:
        p.join()

    store = RouteStore(home)
    noms = sorted(r.name for r in store.list())
    assert noms == sorted(f"route-{i}" for i in range(N)), f"routes perdues : {noms}"
    # chaque clé scellée est retrouvable (le coffre n'a pas non plus perdu d'entrée)
    for i in range(N):
        assert store.vault.get(f"route-{i}", "pp-coffre") == FAKE_KEY


def test_vault_put_concurrent_ne_perd_aucune_cle(tmp_path):
    """T threads scellent des secrets distincts en parallèle ⇒ tous retrouvables."""
    vault = Vault(tmp_path / "vault.json")
    T = 8
    barrier = threading.Barrier(T)

    def worker(i):
        barrier.wait()
        vault.put(f"k-{i}", f"secret-{i}", "pp")

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(T)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    for i in range(T):
        assert vault.get(f"k-{i}", "pp") == f"secret-{i}"
