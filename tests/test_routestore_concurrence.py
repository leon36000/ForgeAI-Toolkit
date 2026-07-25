"""FAI-0010 (#116) — RouteStore.add_cloud et Vault.put font un read-modify-write NON verrouillé
(_load -> mutate -> _save par réécriture complète). Deux ajouts concurrents lisent le même état,
puis la dernière écriture écrase l'autre : des routes ET des clés API scellées sont PERDUES.

Spécification : N ajouts concurrents de routes distinctes ⇒ les N routes sont persistées, et les N
clés sont retrouvables au coffre. RED avant correctif : lost-update (moins de N).
"""
import json
import multiprocessing as mp
import os
import signal
import threading
from pathlib import Path

from forgeai.models._locking import file_lock
from forgeai.models.routes import RouteError, RouteStore
from forgeai.models.vault import Vault, fingerprint

FAKE_KEY = "sk-fake-DO-NOT-LEAK"


class _GreenTransport:
    def post(self, url, headers, body, timeout):
        return 200, json.dumps({"choices": [{"message": {"content": "pong"}}]})


def _add_one(home_str: str, i: int, barrier) -> None:
    barrier.wait()
    store = RouteStore(Path(home_str))
    store.add_cloud(f"route-{i}", "openrouter", "z-ai/glm-4.6", FAKE_KEY, "pp-coffre",
                    transport=_GreenTransport())


def _configure_pause_before_replace(home_str: str, ready) -> None:
    """Processus victime : attend indéfiniment juste avant le rename atomique."""
    target = Path(home_str) / "routes.json"
    real_replace = os.replace

    def paused_replace(src, dst):
        if os.fspath(dst) == os.fspath(target):
            ready.set()
            threading.Event().wait()
        return real_replace(src, dst)

    os.replace = paused_replace
    RouteStore(Path(home_str)).configure_cache("route", True, 60, "cache")


def _add_cloud_pause_before_routes_replace(home_str: str, ready) -> None:
    """Processus victime : coffre remplacé, puis attente avant le replace des routes."""
    target = Path(home_str) / "routes.json"
    real_replace = os.replace

    def paused_replace(src, dst):
        if os.fspath(dst) == os.fspath(target):
            ready.set()
            threading.Event().wait()
        return real_replace(src, dst)

    os.replace = paused_replace
    RouteStore(Path(home_str)).add_cloud(
        "orpheline",
        "openrouter",
        "m",
        FAKE_KEY,
        "pp-coffre",
        transport=_GreenTransport(),
    )


def _add_cloud_pause_before_journal_unlink(home_str: str, ready) -> None:
    """Processus victime : les deux fichiers sont commités, le journal est encore présent."""
    target = Path(home_str) / ".models-transaction.json"
    real_unlink = os.unlink

    def paused_unlink(path, *args, **kwargs):
        if os.fspath(path) == os.fspath(target):
            ready.set()
            threading.Event().wait()
        return real_unlink(path, *args, **kwargs)

    os.unlink = paused_unlink
    RouteStore(Path(home_str)).add_cloud(
        "orpheline",
        "openrouter",
        "m",
        FAKE_KEY,
        "pp-coffre",
        transport=_GreenTransport(),
    )


def _add_cloud_wait_then_pause_before_journal_unlink(
    home_str: str, start, ready
) -> None:
    """Attend le signal parent; le processus est forké avant les threads du test."""
    if not start.wait(timeout=10):
        raise RuntimeError("signal de départ absent")
    _add_cloud_pause_before_journal_unlink(home_str, ready)


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


def test_configure_cache_100_ecritures_concurrentes_sont_toutes_persistees(tmp_path):
    """100 RMW concurrents sur des routes distinctes ne perdent aucune configuration."""
    home = tmp_path / "models"
    home.mkdir()
    route_count = 100
    routes = [
        {
            "name": f"route-{i}",
            "provenance": "openrouter",
            "base_url": "https://openrouter.ai/api/v1",
            "model_id": "m",
            "key_fingerprint": f"sha256:{i:016x}",
            "created_at": "2026-07-25",
        }
        for i in range(route_count)
    ]
    (home / "routes.json").write_text(json.dumps(routes), encoding="utf-8")
    barrier = threading.Barrier(route_count)
    errors: list[Exception] = []
    errors_lock = threading.Lock()
    reader_stop = threading.Event()
    reader_started = threading.Event()

    def reader() -> None:
        reader_started.set()
        while not reader_stop.is_set():
            try:
                persisted = json.loads((home / "routes.json").read_text())
                assert isinstance(persisted, list)
            except Exception as exc:
                with errors_lock:
                    errors.append(exc)
                return

    reader_thread = threading.Thread(target=reader)
    reader_thread.start()
    assert reader_started.wait(timeout=2)

    def worker(i: int) -> None:
        barrier.wait()
        try:
            RouteStore(home).configure_cache(
                f"route-{i}", True, ttl_s=i, prefix=f"prefix-{i}"
            )
        except Exception as exc:  # la liste rend les erreurs de thread observables
            with errors_lock:
                errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(route_count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
        assert not thread.is_alive(), "configure_cache est resté bloqué"
    reader_stop.set()
    reader_thread.join(timeout=5)

    assert errors == []
    persisted = {route.name: route for route in RouteStore(home).list()}
    assert len(persisted) == route_count
    for i in range(route_count):
        route = persisted[f"route-{i}"]
        assert (route.cache, route.cache_ttl_s, route.cache_prefix) == (
            True,
            i,
            f"prefix-{i}",
        )


def test_add_cloud_et_configure_cache_partagent_la_meme_transaction(
    tmp_path, monkeypatch
):
    """Un add bloqué ne peut pas écraser une configuration concurrente déjà persistée."""
    home = tmp_path / "models"
    home.mkdir()
    (home / "routes.json").write_text(
        json.dumps(
            [
                {
                    "name": "existante",
                    "provenance": "openrouter",
                    "base_url": "https://openrouter.ai/api/v1",
                    "model_id": "m",
                    "key_fingerprint": "sha256:0000000000000000",
                    "created_at": "2026-07-25",
                }
            ]
        ),
        encoding="utf-8",
    )
    add_store = RouteStore(home)
    config_store = RouteStore(home)
    add_save_entered = threading.Event()
    release_add_save = threading.Event()
    config_save_entered = threading.Event()
    errors: list[Exception] = []
    errors_lock = threading.Lock()
    original_add_save = add_store._save
    original_config_save = config_store._save

    def blocked_add_save(routes: list[dict]) -> None:
        add_save_entered.set()
        if not release_add_save.wait(timeout=5):
            raise RuntimeError("timeout de synchronisation add_cloud")
        original_add_save(routes)

    def observed_config_save(routes: list[dict]) -> None:
        config_save_entered.set()
        original_config_save(routes)

    monkeypatch.setattr(add_store, "_save", blocked_add_save)
    monkeypatch.setattr(config_store, "_save", observed_config_save)

    def add_worker() -> None:
        try:
            add_store.add_cloud(
                "nouvelle",
                "openrouter",
                "m",
                FAKE_KEY,
                "pp-coffre",
                transport=_GreenTransport(),
            )
        except Exception as exc:
            with errors_lock:
                errors.append(exc)

    def configure_worker() -> None:
        try:
            config_store.configure_cache("existante", True, 60, "cache")
        except Exception as exc:
            with errors_lock:
                errors.append(exc)

    add_thread = threading.Thread(target=add_worker)
    add_thread.start()
    assert add_save_entered.wait(timeout=5), "add_cloud n'a pas atteint son commit"
    config_thread = threading.Thread(target=configure_worker)
    config_thread.start()
    config_save_entered.wait(timeout=0.5)
    release_add_save.set()
    add_thread.join(timeout=10)
    config_thread.join(timeout=10)

    assert not add_thread.is_alive()
    assert not config_thread.is_alive()
    assert errors == []
    persisted = {route.name: route for route in RouteStore(home).list()}
    assert sorted(persisted) == ["existante", "nouvelle"]
    assert (
        persisted["existante"].cache,
        persisted["existante"].cache_ttl_s,
        persisted["existante"].cache_prefix,
    ) == (True, 60, "cache")


def test_sigkill_avant_replace_conserve_ancien_routes_json(tmp_path):
    """Un kill après fsync du tmp mais avant replace laisse l'ancien JSON complet."""
    home = tmp_path / "models"
    home.mkdir()
    path = home / "routes.json"
    path.write_text(
        json.dumps(
            [
                {
                    "name": "route",
                    "provenance": "openrouter",
                    "base_url": "https://openrouter.ai/api/v1",
                    "model_id": "m",
                    "key_fingerprint": "sha256:0000000000000000",
                    "created_at": "2026-07-25",
                }
            ]
        ),
        encoding="utf-8",
    )
    before = path.read_bytes()
    ctx = mp.get_context("fork")
    ready = ctx.Event()
    process = ctx.Process(
        target=_configure_pause_before_replace, args=(str(home), ready)
    )
    process.start()
    assert ready.wait(timeout=5), "le processus n'a pas atteint os.replace"

    os.kill(process.pid, signal.SIGKILL)
    process.join(timeout=5)

    assert process.exitcode == -signal.SIGKILL
    assert path.read_bytes() == before
    assert RouteStore(home).get("route").cache is False


def test_sigkill_entre_vault_et_routes_recupere_sans_cle_orpheline(tmp_path):
    """Une nouvelle session rollback la transaction interrompue entre les deux fichiers."""
    home = tmp_path / "models"
    ctx = mp.get_context("fork")
    ready = ctx.Event()
    process = ctx.Process(
        target=_add_cloud_pause_before_routes_replace, args=(str(home), ready)
    )
    process.start()
    assert ready.wait(timeout=10), "le processus n'a pas atteint le replace routes"

    os.kill(process.pid, signal.SIGKILL)
    process.join(timeout=5)

    assert process.exitcode == -signal.SIGKILL
    recovered = RouteStore(home)
    assert recovered.list() == []
    assert recovered.vault.names() == []


def test_sigkill_add_cloud_restaure_exactement_etat_preexistant(tmp_path):
    """Le journal ne doit pas être contaminé par la mutation du nouvel état."""
    home = tmp_path / "models"
    home.mkdir()
    existing_secret = "secret-existant"
    Vault(home / "vault.json").put("existante", existing_secret, "pp")
    (home / "routes.json").write_text(
        json.dumps(
            [
                {
                    "name": "existante",
                    "provenance": "openrouter",
                    "base_url": "https://openrouter.ai/api/v1",
                    "model_id": "m",
                    "key_fingerprint": fingerprint(existing_secret),
                    "created_at": "2026-07-25",
                }
            ]
        ),
        encoding="utf-8",
    )
    observer = RouteStore(home)
    ctx = mp.get_context("fork")
    ready = ctx.Event()
    process = ctx.Process(
        target=_add_cloud_pause_before_routes_replace, args=(str(home), ready)
    )
    process.start()
    assert ready.wait(timeout=10), "le processus n'a pas atteint le replace routes"

    os.kill(process.pid, signal.SIGKILL)
    process.join(timeout=5)

    assert process.exitcode == -signal.SIGKILL
    assert [route.name for route in observer.list()] == ["existante"]
    assert observer.vault.names() == ["existante"]
    assert observer.vault.get("existante", "pp") == existing_secret


def test_vault_put_apres_crash_recupere_avant_nouvelle_ecriture(tmp_path):
    """Une écriture Vault acquittée après crash ne doit jamais être effacée ensuite."""
    home = tmp_path / "models"
    ctx = mp.get_context("fork")
    ready = ctx.Event()
    process = ctx.Process(
        target=_add_cloud_pause_before_routes_replace, args=(str(home), ready)
    )
    process.start()
    assert ready.wait(timeout=10), "le processus n'a pas atteint le replace routes"

    os.kill(process.pid, signal.SIGKILL)
    process.join(timeout=5)

    assert process.exitcode == -signal.SIGKILL
    vault = Vault(home / "vault.json")
    vault.put("apres-crash", "secret-durable", "pp")
    assert vault.names() == ["apres-crash"]

    recovered = RouteStore(home)
    assert recovered.list() == []
    assert recovered.vault.names() == ["apres-crash"]
    assert recovered.vault.get("apres-crash", "pp") == "secret-durable"


def test_sigkill_apres_routes_replace_est_recupere_avant_precheck_add(tmp_path):
    """Le precheck d'une instance existante récupère avant de juger un doublon."""
    home = tmp_path / "models"
    observer = RouteStore(home)
    ctx = mp.get_context("fork")
    ready = ctx.Event()
    process = ctx.Process(
        target=_add_cloud_pause_before_journal_unlink, args=(str(home), ready)
    )
    process.start()
    assert ready.wait(timeout=10), "le processus n'a pas atteint l'unlink du journal"

    os.kill(process.pid, signal.SIGKILL)
    process.join(timeout=5)

    assert process.exitcode == -signal.SIGKILL
    route, result = observer.add_cloud(
        "orpheline",
        "openrouter",
        "m",
        "nouveau-secret",
        "pp",
        transport=_GreenTransport(),
    )
    assert result.ok
    assert route.key_fingerprint == fingerprint("nouveau-secret")
    assert observer.vault.get("orpheline", "pp") == "nouveau-secret"


def test_precheck_add_est_atomique_avec_la_recuperation(tmp_path, monkeypatch):
    """Aucun writer ne peut commiter entre recovery et lecture du precheck."""
    home = tmp_path / "models"
    observer = RouteStore(home)
    load_entered = threading.Event()
    release_load = threading.Event()
    observer_done = threading.Event()
    results = []
    errors: list[Exception] = []
    real_load = observer._load
    first_load = True

    def blocked_first_load():
        nonlocal first_load
        if first_load:
            first_load = False
            load_entered.set()
            if not release_load.wait(timeout=10):
                raise RuntimeError("precheck non libéré")
        return real_load()

    monkeypatch.setattr(observer, "_load", blocked_first_load)
    ctx = mp.get_context("fork")
    writer_start = ctx.Event()
    writer_ready = ctx.Event()
    writer = ctx.Process(
        target=_add_cloud_wait_then_pause_before_journal_unlink,
        args=(str(home), writer_start, writer_ready),
    )
    writer.start()

    def observer_worker() -> None:
        try:
            results.append(
                observer.add_cloud(
                    "collision",
                    "openrouter",
                    "m",
                    "secret-observer",
                    "pp",
                    transport=_GreenTransport(),
                )
            )
        except Exception as exc:
            errors.append(exc)
        finally:
            observer_done.set()

    observer_thread = threading.Thread(target=observer_worker)
    observer_thread.start()
    assert load_entered.wait(timeout=5), "le precheck observer n'a pas commencé"

    writer_start.set()
    writer_interleaved_during_precheck = writer_ready.wait(timeout=0.5)
    release_load.set()

    writer_reached_commit = (
        writer_interleaved_during_precheck or writer_ready.wait(timeout=5)
    )
    if writer_reached_commit:
        os.kill(writer.pid, signal.SIGKILL)
    writer.join(timeout=5)
    observer_thread.join(timeout=10)

    assert not writer_interleaved_during_precheck, (
        "un writer a commité pendant le precheck"
    )
    assert observer_done.is_set()
    assert errors == []
    assert len(results) == 1


def test_deux_configure_cache_meme_route_restent_linearisables(tmp_path):
    """Deux configurations concurrentes donnent un état final complet de l'une des deux."""
    home = tmp_path / "models"
    home.mkdir()
    (home / "routes.json").write_text(
        json.dumps(
            [
                {
                    "name": "route",
                    "provenance": "openrouter",
                    "base_url": "https://openrouter.ai/api/v1",
                    "model_id": "m",
                    "key_fingerprint": "sha256:0000000000000000",
                    "created_at": "2026-07-25",
                }
            ]
        ),
        encoding="utf-8",
    )
    barrier = threading.Barrier(2)
    results: list[tuple[int | None, str | None]] = []
    errors: list[Exception] = []
    result_lock = threading.Lock()

    def worker(ttl: int, prefix: str) -> None:
        barrier.wait()
        try:
            route = RouteStore(home).configure_cache(
                "route", True, ttl_s=ttl, prefix=prefix
            )
            with result_lock:
                results.append((route.cache_ttl_s, route.cache_prefix))
        except Exception as exc:
            with result_lock:
                errors.append(exc)

    threads = [
        threading.Thread(target=worker, args=(10, "a")),
        threading.Thread(target=worker, args=(20, "b")),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert errors == []
    assert sorted(results) == [(10, "a"), (20, "b")]
    final = RouteStore(home).get("route")
    assert (final.cache_ttl_s, final.cache_prefix) in {(10, "a"), (20, "b")}


def test_deux_add_cloud_meme_nom_refusent_le_perdant_sans_desaligner_vault(
    tmp_path,
):
    """Le perdant reçoit RouteError; la clé du coffre correspond à la route gagnante."""
    home = tmp_path / "models"
    barrier = threading.Barrier(2)
    successes: list[tuple[str, str]] = []
    errors: list[Exception] = []
    result_lock = threading.Lock()

    class BarrierTransport(_GreenTransport):
        def post(self, url, headers, body, timeout):
            barrier.wait()
            return super().post(url, headers, body, timeout)

    def worker(secret: str) -> None:
        try:
            route, _ = RouteStore(home).add_cloud(
                "collision",
                "openrouter",
                "m",
                secret,
                "pp",
                transport=BarrierTransport(),
            )
            with result_lock:
                successes.append((secret, route.key_fingerprint))
        except Exception as exc:
            with result_lock:
                errors.append(exc)

    threads = [
        threading.Thread(target=worker, args=("secret-a",)),
        threading.Thread(target=worker, args=("secret-b",)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert len(successes) == 1
    assert len(errors) == 1
    assert isinstance(errors[0], RouteError)
    assert "existe déjà" in str(errors[0])
    persisted_route = RouteStore(home).get("collision")
    persisted_secret = RouteStore(home).vault.get("collision", "pp")
    assert persisted_route.key_fingerprint == fingerprint(persisted_secret)
    assert successes == [(persisted_secret, persisted_route.key_fingerprint)]


def test_probe_reseau_reste_hors_verrou_transaction(tmp_path):
    """Un contender acquiert le lock pendant le probe réseau lui-même."""
    home = tmp_path / "models"
    store = RouteStore(home)
    probe_completed = threading.Event()
    lock_acquired_during_probe = threading.Event()

    class ObservedTransport(_GreenTransport):
        def post(self, url, headers, body, timeout):
            def contender() -> None:
                with file_lock(store.transaction_lock_path):
                    lock_acquired_during_probe.set()

            contender_thread = threading.Thread(target=contender)
            contender_thread.start()
            assert lock_acquired_during_probe.wait(timeout=2), (
                "le verrou transactionnel couvre le probe réseau"
            )
            contender_thread.join(timeout=2)
            result = super().post(url, headers, body, timeout)
            probe_completed.set()
            return result

    store.add_cloud(
        "route",
        "openrouter",
        "m",
        "secret",
        "pp",
        transport=ObservedTransport(),
    )

    assert probe_completed.is_set()
    assert lock_acquired_during_probe.is_set()
