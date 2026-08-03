import json
import threading
import urllib.error
import urllib.request

import pytest

from forgeai.network.node_add import NodeAddError
from forgeai.web import server as server_module


def request_json(url, method="GET", data=None):
    headers = {}
    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        response_body = exc.read().decode("utf-8")
        try:
            return exc.code, json.loads(response_body)
        except json.JSONDecodeError:
            return exc.code, response_body


@pytest.fixture
def tmp_env(monkeypatch, tmp_path):
    keys_dir = tmp_path / "keys"
    keys_dir.mkdir()
    (keys_dir / "forgeai_ed25519").write_text("fake-private-key")
    (keys_dir / "forgeai_ed25519.pub").write_text(
        "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIDIhz2GK fake"
    )
    models_dir = tmp_path / "models"
    models_dir.mkdir()

    monkeypatch.setattr(server_module, "_NODE_KEYS_DIR", keys_dir)
    monkeypatch.setattr(server_module, "_REGISTRE_PATH", tmp_path / "r.jsonl")
    monkeypatch.setattr(server_module, "_MODELS_HOME", models_dir)
    return tmp_path


@pytest.fixture
def fake_bootstrapper(monkeypatch, tmp_env):
    import forgeai.network.node_add as node_add_module

    class FakeBootstrapper:
        def __init__(self):
            self.calls = []

        def install_key(self, ip, user, passwd, pubkey):
            self.calls.append(("install", ip, user, passwd, str(pubkey)))

        def verify_key(self, ip, user, privkey):
            self.calls.append(("verify", ip, user, str(privkey)))
            return True

    bs = FakeBootstrapper()
    monkeypatch.setattr(server_module, "_NODE_BOOTSTRAPPER", bs)
    monkeypatch.setattr(
        node_add_module, "key_fingerprint", lambda pubkey, runner: "SHA256:FAKEFP"
    )
    return bs


@pytest.fixture
def base_url(tmp_env):
    server = server_module.build_server("127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    yield f"http://{host}:{port}"
    server.shutdown()
    server.server_close()


def test_add_node_ok(base_url, tmp_env, fake_bootstrapper):
    password = "mdp-Distinctif-9"  # proof:allow (litteral de test : sert a PROUVER la non-persistance)
    payload = {"ip": "192.168.1.31", "user": "forge", "password": password,
               "hostkey": "SHA256:FAKEFP"}  # SSH-021 : empreinte requise
    status, body = request_json(f"{base_url}/api/nodes", method="POST", data=payload)

    assert status == 201
    node = body["node"]
    assert node["ip"] == "192.168.1.31"
    assert node["user"] == "forge"
    assert node["key_fingerprint"] == "SHA256:FAKEFP"
    assert "password" not in body

    assert any(call[0] == "install" for call in fake_bootstrapper.calls)
    assert any(call[0] == "verify" for call in fake_bootstrapper.calls)

    for path in tmp_env.rglob("*"):
        if path.is_file():
            content = path.read_text(errors="ignore")
            assert password not in content, f"password found in {path}"

    reg_path = tmp_env / "r.jsonl"
    assert reg_path.exists()
    events = [json.loads(line) for line in reg_path.read_text(encoding="utf-8").splitlines()]
    node_events = [e for e in events if e.get("type") == "node_added"]
    assert len(node_events) == 1
    data = node_events[0]["payload"]
    assert data["ip"] == "192.168.1.31"
    assert data["user"] == "forge"
    assert data["key_fingerprint"] == "SHA256:FAKEFP"
    assert password not in str(data)


def test_add_node_echec_bootstrap(base_url, tmp_env, monkeypatch):
    class FailingBootstrapper:
        def install_key(self, ip, user, passwd, pubkey):
            raise NodeAddError("auth refusee")

        def verify_key(self, ip, user, privkey):
            return False

    monkeypatch.setattr(server_module, "_NODE_BOOTSTRAPPER", FailingBootstrapper())

    status, body = request_json(
        f"{base_url}/api/nodes",
        method="POST",
        data={"ip": "192.168.1.31", "user": "forge", "password": "x",
              "hostkey": "SHA256:FAKEFP"},  # SSH-021 : empreinte requise pour atteindre le bootstrapper
    )

    assert status == 400
    assert "auth refusee" in body["error"]

    reg_path = tmp_env / "r.jsonl"
    assert not reg_path.exists() or reg_path.read_text() == ""


def test_add_node_champs_manquants(base_url):
    distinctive_ip = "1.2.3.4"
    distinctive_user = "utilisateur_distinctif_42"
    status, body = request_json(
        f"{base_url}/api/nodes",
        method="POST",
        data={"ip": distinctive_ip, "user": distinctive_user},
    )

    assert status == 400
    assert body["error"] == "champs manquants"
    assert "password" in body["missing"]
    assert distinctive_ip not in str(body)
    assert distinctive_user not in str(body)
    assert "password" not in str(body.get("password", ""))


def test_nodes_status_graceful(base_url, monkeypatch):
    def boom(runner):
        raise server_module.ClusterError("pas de cluster")

    monkeypatch.setattr(server_module, "cluster_status", boom)

    status, body = request_json(f"{base_url}/api/nodes/status")

    assert status == 200
    assert body["nodes"] == []
    assert "pas de cluster" in body["detail"]


def test_non_regression(base_url):
    status, body = request_json(f"{base_url}/api/models")
    assert status == 200
    assert isinstance(body, list)

    status, body = request_json(f"{base_url}/api/stacks")
    assert status == 200
    assert isinstance(body, list)

    status, body = request_json(f"{base_url}/api/nope", method="POST", data={})
    assert status == 404
