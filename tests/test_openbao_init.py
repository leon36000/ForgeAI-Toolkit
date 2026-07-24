"""Tests exhaustifs pour ensure_openbao_ready avec FakeTransport, KeyStore, SecretStore."""

from __future__ import annotations

import http.server
import json
import threading

import pytest
from forgeai.secrets.openbao_init import (
    OpenBaoInitError,
    ensure_openbao_ready,
    http_transport,
)

# ---------------------------------------------------------------------------
# Stores mémorisant read/write en mémoire
# ---------------------------------------------------------------------------

class InMemoryStore:
    """Store en mémoire avec lecture/écriture atomique simulée."""
    def __init__(self, initial: dict | None = None) -> None:
        self._data: dict | None = initial

    def read(self) -> dict | None:
        return self._data

    def write(self, data: dict) -> None:
        self._data = data


class BrokenWriteStore(InMemoryStore):
    """Store dont l'écriture est silencieusement ignorée (pour test de read-back)."""
    def write(self, data: dict) -> None:
        # Écriture volontairement NON persistée : on la mémorise à part pour l'inspection,
        # mais read() renverra toujours l'état initial -> déclenche l'échec de read-back.
        self.dropped = dict(data)


# ---------------------------------------------------------------------------
# FakeTransport simulant la machine à états openbao
# ---------------------------------------------------------------------------

class FakeTransport:
    """Transport factice respectant la même interface que http_transport.

    Il lève OpenBaoInitError pour toute réponse HTTP >= 400, comme le vrai transport.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str | None, dict | None]] = []
        # État interne du coffre
        self._initialized: bool = False
        self._sealed: bool = False
        self._root_token: str | None = None
        self._unseal_key: str | None = None
        self._mounts: set[str] = set()
        self._policies: dict[str, str] = {}                 # name -> HCL
        self._tokens: dict[str, list[str]] = {}             # token -> policies

    # ------------------------------------------------------------------
    # Callable transport.request(method, path, *, token=None, payload=None)
    # ------------------------------------------------------------------
    def request(
        self,
        method: str,
        path: str,
        *,
        token: str | None = None,
        payload: dict | None = None,
    ) -> tuple[int, dict]:
        self.calls.append((method, path, token, payload))
        status, body = self._handle(method, path, token, payload)
        if status >= 400:
            raise OpenBaoInitError(f"openbao {method} {path} -> HTTP {status}")
        return status, body

    def __call__(self, method, path, *, token=None, payload=None):
        # Permet de passer l'objet directement comme `request` (callable).
        return self.request(method, path, token=token, payload=payload)

    # ------------------------------------------------------------------
    # Moteur de simulation
    # ------------------------------------------------------------------
    def _handle(
        self,
        method: str,
        path: str,
        token: str | None,
        payload: dict | None,
    ) -> tuple[int, dict]:
        # ── Seal status ──────────────────────────────────────────
        if path == "/v1/sys/seal-status":
            return 200, {"initialized": self._initialized, "sealed": self._sealed}

        # ── Init ─────────────────────────────────────────────────
        if path == "/v1/sys/init":
            if self._initialized:
                return 400, {"errors": ["already initialized"]}
            self._initialized = True
            self._sealed = True
            self._unseal_key = "fake-unseal-key-abc123"
            self._root_token = "fake-root-token-xyz789"
            return 200, {
                "keys": [self._unseal_key],
                "root_token": self._root_token,
            }

        # ── Unseal ───────────────────────────────────────────────
        if path == "/v1/sys/unseal":
            if payload and payload.get("key") == self._unseal_key:
                self._sealed = False
                return 200, {"sealed": False}
            return 400, {"errors": ["incorrect unseal key"]}

        # ── Mounts ───────────────────────────────────────────────
        if method == "GET" and path == "/v1/sys/mounts":
            data = {}
            for mnt in self._mounts:
                data[mnt] = {"type": "kv", "options": {"version": "2"}}
            return 200, {"data": data}

        if method == "POST" and path == "/v1/sys/mounts/secret":
            if "secret/" in self._mounts:
                return 400, {"errors": ["path already in use"]}
            self._mounts.add("secret/")
            return 204, {}

        # ── Policy ACL ───────────────────────────────────────────
        if method == "PUT" and path == "/v1/sys/policies/acl/forgeai-app":
            self._policies["forgeai-app"] = payload.get("policy", "") if payload else ""
            return 204, {}

        # ── Token management ─────────────────────────────────────
        if method == "GET" and path == "/v1/auth/token/lookup-self":
            if token and token in self._tokens:
                return 200, {"data": {"policies": self._tokens[token]}}
            return 403, {"errors": ["bad token"]}

        if method == "POST" and path == "/v1/auth/token/create":
            if token != self._root_token:
                return 403, {"errors": ["permission denied"]}
            policies = payload.get("policies", []) if payload else []
            new_token = f"token-{len(self._tokens)+1:04d}"
            self._tokens[new_token] = policies
            return 200, {"auth": {"client_token": new_token}}

        if method == "POST" and path == "/v1/auth/token/revoke":
            revoke_target = (payload or {}).get("token") if payload else token
            if revoke_target and revoke_target in self._tokens:
                del self._tokens[revoke_target]
            return 204, {}

        return 404, {"errors": []}  # inconnu


# ======================================================================
# Tests
# ======================================================================

CONTAINS_SECRET_MSG = (
    "le message d'erreur ne doit contenir ni root_token ni unseal_key"
)


def _assert_no_secrets_in_message(error: BaseException, root: str, key: str) -> None:
    msg = str(error)
    assert root not in msg, CONTAINS_SECRET_MSG
    assert key not in msg, CONTAINS_SECRET_MSG


class TestFreshInit:
    """1. fresh init – premier démarrage, tout est vierge."""

    def test_fresh_init_creates_everything(self) -> None:
        transport = FakeTransport()
        key_store = InMemoryStore()
        secret_store = InMemoryStore()

        token = ensure_openbao_ready(transport.request, key_store, secret_store)

        # Le token retourné n'est pas vide ni le root
        assert token
        assert token != transport._root_token

        # Vérification des appels
        methods_paths = [(m, p) for m, p, _, _ in transport.calls]

        assert ("PUT", "/v1/sys/init") in methods_paths
        assert ("PUT", "/v1/sys/unseal") in methods_paths
        assert ("GET", "/v1/sys/mounts") in methods_paths
        assert ("POST", "/v1/sys/mounts/secret") in methods_paths
        assert ("PUT", "/v1/sys/policies/acl/forgeai-app") in methods_paths
        assert ("POST", "/v1/auth/token/create") in methods_paths

        # key_store contient bien les secrets initiaux
        stored = key_store.read()
        assert stored is not None
        assert stored["unseal_key"] == transport._unseal_key
        assert stored["root_token"] == transport._root_token

        # secret_store contient le token applicatif
        assert secret_store.read() == {"token": token}


class TestAlreadyInitializedSealed:
    """2. Déjà initialisé, scellé, mais les clés sont dans le store."""

    def test_unseals_and_creates_token(self) -> None:
        transport = FakeTransport()
        # Pré-état : initialisé + scellé, clés connues
        transport._initialized = True
        transport._sealed = True
        transport._unseal_key = "my-key"
        transport._root_token = "my-root"

        key_store = InMemoryStore({"unseal_key": "my-key", "root_token": "my-root"})
        secret_store = InMemoryStore()

        token = ensure_openbao_ready(transport.request, key_store, secret_store)

        # init ne doit PAS avoir été appelé
        methods_paths = [(m, p) for m, p, _, _ in transport.calls]
        assert ("PUT", "/v1/sys/init") not in methods_paths
        # unseal a été appelé
        assert ("PUT", "/v1/sys/unseal") in methods_paths
        # token a été créé
        assert ("POST", "/v1/auth/token/create") in methods_paths
        assert token and token != "my-root"


class TestAlreadyUnsealedAndReady:
    """3. Déjà unscellé, KV monté, token valide présent (idempotence)."""

    def test_reuses_existing_token(self) -> None:
        transport = FakeTransport()
        transport._initialized = True
        transport._sealed = False
        transport._mounts.add("secret/")                     # KV déjà monté
        transport._policies["forgeai-app"] = "..."           # policy existante
        # Token valide déjà enregistré
        existing_token = "existing-valid-token"
        transport._tokens[existing_token] = ["forgeai-app"]
        transport._root_token = "my-root"

        key_store = InMemoryStore({
            "unseal_key": "my-key",
            "root_token": "my-root",
        })
        secret_store = InMemoryStore({"token": existing_token})

        token = ensure_openbao_ready(transport.request, key_store, secret_store)

        assert token == existing_token

        methods_paths = [(m, p) for m, p, _, _ in transport.calls]
        # Pas d'init, pas d'unseal
        assert ("PUT", "/v1/sys/init") not in methods_paths
        assert ("PUT", "/v1/sys/unseal") not in methods_paths
        # Le lookup-self a été fait
        assert ("GET", "/v1/auth/token/lookup-self") in methods_paths
        # Aucune création de token supplémentaire
        create_calls = [c for c in transport.calls if c[1] == "/v1/auth/token/create"]
        assert len(create_calls) == 0


class TestFailFastNoKeys:
    """4. Coffre initialisé mais key_store vide -> erreur."""

    def test_raises_when_keys_missing(self) -> None:
        transport = FakeTransport()
        transport._initialized = True
        transport._sealed = True
        key_store = InMemoryStore()          # vide
        secret_store = InMemoryStore()

        with pytest.raises(OpenBaoInitError) as exc_info:
            ensure_openbao_ready(transport.request, key_store, secret_store)

        assert "clés absentes" in str(exc_info.value) or "key" in str(exc_info.value).lower()


class TestInvalidTokenInStore:
    """5. Token présent dans le secret_store mais invalide (lookup-self 403)."""

    def test_recreates_token_and_revokes_old(self) -> None:
        transport = FakeTransport()
        transport._initialized = True
        transport._sealed = False
        transport._root_token = "my-root"
        transport._mounts.add("secret/")
        transport._policies["forgeai-app"] = "..."

        key_store = InMemoryStore({
            "unseal_key": "my-key",
            "root_token": "my-root",
        })
        old_token = "dead-token"
        secret_store = InMemoryStore({"token": old_token})

        token = ensure_openbao_ready(transport.request, key_store, secret_store)

        # Nouveau token a été créé
        assert token and token != old_token
        # Appels : lookup-self sur l'ancien a dû échouer (403), création, puis révocation ancien
        calls_details = [(m, p, t, pl) for m, p, t, pl in transport.calls]

        lookup_calls = [c for c in calls_details if c[1] == "/v1/auth/token/lookup-self"]
        assert any(c[2] == old_token for c in lookup_calls)

        create_calls = [c for c in calls_details if c[1] == "/v1/auth/token/create"]
        assert len(create_calls) == 1
        revoke_calls = [c for c in calls_details if c[1] == "/v1/auth/token/revoke"]
        assert any(
            (c[3] or {}).get("token") == old_token for c in revoke_calls
        )

        # Le nouveau token est stocké
        assert secret_store.read() == {"token": token}


class TestReadBackInitFails:
    """6. L'initialisation réussit mais le read-back échoue (store cassé)."""

    def test_detects_readback_failure(self) -> None:
        transport = FakeTransport()
        key_store = BrokenWriteStore()   # n'écrit jamais -> read() renverra le None initial
        secret_store = InMemoryStore()

        with pytest.raises(OpenBaoInitError) as exc_info:
            ensure_openbao_ready(transport.request, key_store, secret_store)

        assert "read-back" in str(exc_info.value).lower()
        _assert_no_secrets_in_message(
            exc_info.value,
            transport._root_token or "",
            transport._unseal_key or "",
        )


class TestKVMountAlreadyPresent:
    """7. Le montage secret/ existe déjà -> pas de POST supplémentaire."""

    def test_skips_mount_when_already_present(self) -> None:
        transport = FakeTransport()
        transport._initialized = True
        transport._sealed = False
        transport._root_token = "my-root"
        transport._mounts.add("secret/")                    # déjà présent

        key_store = InMemoryStore({
            "unseal_key": "my-key",
            "root_token": "my-root",
        })
        secret_store = InMemoryStore()

        token = ensure_openbao_ready(transport.request, key_store, secret_store)

        # Aucun appel POST /v1/sys/mounts/secret
        mount_calls = [
            c for c in transport.calls
            if c[0] == "POST" and c[1] == "/v1/sys/mounts/secret"
        ]
        assert len(mount_calls) == 0
        assert token is not None


class TestSecretSafety:
    """8. Les messages d'erreur ne contiennent jamais de secrets."""

    def test_error_message_contains_no_secrets(self) -> None:
        transport = FakeTransport()
        transport._initialized = False

        key_store = InMemoryStore()
        secret_store = InMemoryStore()

        # Simulation d'une erreur en brisant le retour d'init
        original_handle = transport._handle

        def broken_handle(m, p, t, pl):
            if p == "/v1/sys/init":
                return 500, {"errors": ["internal error"]}
            return original_handle(m, p, t, pl)

        transport._handle = broken_handle  # type: ignore[assignment]

        with pytest.raises(OpenBaoInitError) as exc_info:
            ensure_openbao_ready(transport.request, key_store, secret_store)

        # Les secrets ne sont normalement même pas générés ici, mais on vérifie quand même
        _assert_no_secrets_in_message(exc_info.value, "fake-root", "fake-unseal")

    def test_unseal_failure_no_leak(self) -> None:
        transport = FakeTransport()
        transport._initialized = True
        transport._sealed = True
        transport._unseal_key = "real-key"
        transport._root_token = "real-root"

        key_store = InMemoryStore({
            "unseal_key": "real-key",
            "root_token": "real-root",
        })
        secret_store = InMemoryStore()

        # On corrompt la clé en mémoire pour provoquer un échec d'unseal
        _original_handle = transport._handle

        def bad_unseal(m, p, t, pl):
            if p == "/v1/sys/unseal":
                return 400, {"errors": ["incorrect unseal key"]}
            return _original_handle(m, p, t, pl)

        transport._handle = bad_unseal  # type: ignore[assignment]

        with pytest.raises(OpenBaoInitError) as exc_info:
            ensure_openbao_ready(transport.request, key_store, secret_store)

        # Vérifier qu'aucun secret n'est divulgué
        _assert_no_secrets_in_message(exc_info.value, "real-root", "real-key")

    def test_lookup_failure_no_leak(self) -> None:
        transport = FakeTransport()
        transport._initialized = True
        transport._sealed = False
        transport._root_token = "root-secret"
        transport._mounts.add("secret/")
        transport._policies["forgeai-app"] = "..."

        key_store = InMemoryStore({
            "unseal_key": "unseal-secret",
            "root_token": "root-secret",
        })
        secret_store = InMemoryStore({"token": "my-token"})

        # Faire échouer le lookup avec une erreur 500 qui déclenche une exception
        _original_handle = transport._handle

        def broken_lookup(m, p, t, pl):
            if p == "/v1/auth/token/lookup-self":
                return 500, {"errors": ["internal"]}
            return _original_handle(m, p, t, pl)

        transport._handle = broken_lookup  # type: ignore[assignment]

        try:
            ensure_openbao_ready(transport.request, key_store, secret_store)
        except OpenBaoInitError as exc:
            _assert_no_secrets_in_message(exc, "root-secret", "unseal-secret")
            # Mais ici la fonction ne devrait pas lever car elle rattrape l'erreur
            # et crée un nouveau token. Vérifions plutôt le comportement : elle va
            # tenter de créer un token (réussira) et retourner le token. Aucune
            # exception ne devrait fuiter les secrets.
            pytest.fail("Une exception inattendue a été levée")
        else:
            # Pas d'exception -> c'est bon, l'erreur a été absorbée sans fuite
            pass


# ---------------------------------------------------------------------------
# Extension de FakeTransport pour les cas d'erreur
# ---------------------------------------------------------------------------

class IncompleteInitTransport(FakeTransport):
    """Transport dont /v1/sys/init renvoie un corps incomplet (ni keys ni root_token)."""
    def __call__(self, method, path, *, token=None, payload=None):
        if method == "PUT" and "/v1/sys/init" in path:
            return (200, {})         # pas de 'keys', pas de 'root_token'
        return super().__call__(method, path, token=token, payload=payload)


class NoClientTokenTransport(FakeTransport):
    """Transport dont /v1/auth/token/create renvoie auth sans client_token."""
    def __call__(self, method, path, *, token=None, payload=None):
        if method == "POST" and "/v1/auth/token/create" in path:
            return (200, {"auth": {}})   # pas de client_token dans auth
        return super().__call__(method, path, token=token, payload=payload)


class MountAlreadyUsedTransport(FakeTransport):
    """Transport : secret/ absent du GET mounts, mais POST mounts échoue en 400."""
    def __call__(self, method, path, *, token=None, payload=None):
        if method == "GET" and path == "/v1/sys/mounts":
            # Aucun mount 'secret/' recensé
            return (200, {"data": {}})
        if method == "POST" and path == "/v1/sys/mounts/secret":
            # Simule un 400 'path already in use'
            raise OpenBaoInitError("openbao POST /v1/sys/mounts/secret -> HTTP 400")
        return super().__call__(method, path, token=token, payload=payload)


# ---------------------------------------------------------------------------
# Tests de http_transport contre un vrai serveur HTTP éphémère
# ---------------------------------------------------------------------------

class _TestHandler(http.server.BaseHTTPRequestHandler):
    """Handler minimal pour les tests de http_transport."""
    def do_GET(self):
        self._handle()
    def do_POST(self):
        self._handle()

    def _handle(self):
        # echo des en-têtes et du corps utiles pour les assertions
        content_length = int(self.headers.get("Content-Length", 0))
        body_data = self.rfile.read(content_length) if content_length else b""
        try:
            payload = json.loads(body_data) if body_data else None
        except Exception:
            payload = None

        if self.path == "/boom":
            self.send_error(500, "Internal Server Error")
        elif self.path == "/empty":
            self.send_response(200)
            self.end_headers()
        elif self.path == "/badjson":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b"not json")
        else:
            # par défaut renvoie un JSON avec l'en-tête X-Vault-Token reçu
            response = {
                "ok": True,
                "path": self.path,
                "token_header": self.headers.get("X-Vault-Token", None),
                "body": payload,
            }
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(response).encode("utf-8"))

    def log_message(self, fmt, *args):  # noqa: A002
        # Silence les logs du serveur HTTP de test (pas de bruit dans la sortie pytest).
        _ = (fmt, args)


def _start_http_server(handler_class=_TestHandler) -> tuple[http.server.HTTPServer, str]:
    """Démarre un serveur HTTP sur un port aléatoire et retourne (serveur, base_url)."""
    server = http.server.HTTPServer(("127.0.0.1", 0), handler_class)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    base_url = f"http://{host}:{port}"
    return server, base_url


def test_http_transport_success():
    """Test du chemin nominal avec GET, POST + en-tête token."""
    server, base_url = _start_http_server()
    try:
        t = http_transport(base_url)
        # GET simple
        status, body = t("GET", "/v1/sys/seal-status")
        assert status == 200
        assert body["ok"] is True
        assert body["path"] == "/v1/sys/seal-status"
        assert body["token_header"] is None

        # POST avec payload et token
        payload = {"test": True}
        status, body = t("POST", "/v1/auth/token/create", token="test-token", payload=payload)
        assert status == 200
        assert body["ok"] is True
        assert body["path"] == "/v1/auth/token/create"
        assert body["token_header"] == "test-token"
        assert body["body"] == payload
    finally:
        server.shutdown()
        server.server_close()


def test_http_transport_httperror():
    """Une réponse >=400 doit lever OpenBaoInitError sans fuiter le token."""
    server, base_url = _start_http_server()
    try:
        t = http_transport(base_url)
        with pytest.raises(OpenBaoInitError, match=r"HTTP 500") as excinfo:
            t("GET", "/boom", token="secret-token-123")
        # Vérifier que le token n'apparaît pas dans le message
        assert "secret-token-123" not in str(excinfo.value)
    finally:
        server.shutdown()
        server.server_close()


def test_http_transport_urlerror():
    """Connexion à un port fermé doit lever OpenBaoInitError."""
    t = http_transport("http://127.0.0.1:1", timeout=0.5)
    with pytest.raises(OpenBaoInitError, match=r"injoignable"):
        t("GET", "/anything")


def test_http_transport_empty_body():
    """Corps de réponse vide → (200, {})."""
    server, base_url = _start_http_server()
    try:
        t = http_transport(base_url)
        status, body = t("GET", "/empty")
        assert status == 200
        assert body == {}
    finally:
        server.shutdown()
        server.server_close()


def test_http_transport_bad_json_body():
    """Corps JSON malformé → OpenBaoInitError."""
    server, base_url = _start_http_server()
    try:
        t = http_transport(base_url)
        with pytest.raises(OpenBaoInitError, match=r"réponse illisible"):
            t("GET", "/badjson")
    finally:
        server.shutdown()
        server.server_close()


# ---------------------------------------------------------------------------
# Tests des branches d'erreur de ensure_openbao_ready
# ---------------------------------------------------------------------------

def test_init_response_incomplete():
    """init renvoie un corps sans keys ni root_token → OpenBaoInitError."""
    # Le transport simule un état non initialisé (seal-status: initialized=False, sealed=False)
    transport = IncompleteInitTransport()
    transport._initialized = False
    transport._sealed = False
    store = InMemoryStore()
    with pytest.raises(OpenBaoInitError, match=r"réponse incomplète"):
        ensure_openbao_ready(transport, store, store)


def test_create_token_no_client_token():
    """token/create renvoie auth sans client_token → OpenBaoInitError."""
    transport = NoClientTokenTransport()
    # Initialiser les stores avec root_token/unseal_key pour éviter une erreur prématurée
    keys_store = InMemoryStore({"unseal_key": "fake-key", "root_token": "root"})
    secrets_store = InMemoryStore()  # pas de token préexistant
    with pytest.raises(OpenBaoInitError, match=r"pas de client_token"):
        ensure_openbao_ready(transport, keys_store, secrets_store)


def test_mount_already_in_use_ignored():
    """Quand le mount secret/ est déjà utilisé, le 400 est ignoré et le flux continue."""
    transport = MountAlreadyUsedTransport()
    keys_store = InMemoryStore({"unseal_key": "fake-key", "root_token": "root"})
    secrets_store = InMemoryStore()
    # La fonction doit terminer sans erreur et retourner un token
    token = ensure_openbao_ready(transport, keys_store, secrets_store)
    # Le FakeTransport par défaut renvoie un token factice pour token/create
    assert isinstance(token, str)
    assert len(token) > 0
