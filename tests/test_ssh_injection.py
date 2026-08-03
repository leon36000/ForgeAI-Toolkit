"""FAI-0008 (#114) — injection d'arguments SSH : `user`/`ip` non validés atteignent l'argv
de ssh-copy-id/ssh (CWE-88). Un token commençant par '-' (ex. '-oProxyCommand=<cmd>') est
interprété par ssh comme une OPTION → exécution de commande côté contrôleur.

Spécification : `add_node` (chemin CLI + web) DOIT rejeter toute cible SSH dont le `user` ou
l'`ip` n'est pas une valeur sûre (charset restreint, jamais un tiret en tête), AVANT tout appel
au bootstrapper. RED avant correctif : aucune validation → l'injection atteint l'argv.
"""

import pytest

from forgeai.network.node_add import add_node, NodeAddError


class _FakeBootstrapper:
    def __init__(self) -> None:
        self.install_calls: list = []
        self.verify_calls: list = []

    def install_key(self, ip, user, passwd, pubkey) -> None:
        self.install_calls.append((ip, user))

    def verify_key(self, ip, user, privkey) -> bool:
        self.verify_calls.append((ip, user))
        return True


class _Runner:
    def run(self, argv):
        return 0, "256 SHA256:abc fake (ED25519)"


def _add(ip, user, tmp_path, boot):
    pub = tmp_path / "k.pub"; priv = tmp_path / "k"
    pub.write_text("pub"); priv.write_text("priv")
    return add_node(ip, user, "pw", pubkey=pub, privkey=priv, bootstrapper=boot,
                    runner=_Runner(), registre_path=tmp_path / "r.jsonl")


@pytest.mark.parametrize("user", [
    "-oProxyCommand=touch /tmp/pwn",
    "-oPermitLocalCommand=yes",
    "root;rm -rf /",
    "-l",
    "admin\n",            # newline final : le `$` de regex l'acceptait (revue Grok) — doit être rejeté
    "admin\n-oProxyCommand=x",
    "admin evil",         # espace
])
def test_add_node_rejette_user_hostile(user, tmp_path):
    boot = _FakeBootstrapper()
    with pytest.raises(NodeAddError):
        _add("10.0.0.1", user, tmp_path, boot)
    assert boot.install_calls == [], "le bootstrapper NE doit PAS être appelé avec un user hostile"


@pytest.mark.parametrize("ip", [
    "-oProxyCommand=touch /tmp/pwn",
    "-D",
    "10.0.0.1 -oProxyCommand=x",
    "10.0.0.1\n",         # newline final : doit être rejeté (revue Grok)
    "10.0.0.1\n-oX",
])
def test_add_node_rejette_ip_hostile(ip, tmp_path):
    boot = _FakeBootstrapper()
    with pytest.raises(NodeAddError):
        _add(ip, "admin", tmp_path, boot)
    assert boot.install_calls == []


def test_add_node_accepte_cibles_valides(tmp_path):
    """Régression : IPv4, hostname et user POSIX normaux passent."""
    for ip, user in [("10.0.0.5", "admin"), ("node-1.lan", "ubuntu"), ("192.168.1.42", "forge_ai"),
                     ("srv.lan", "first.last")]:  # user à point (revue Qwen) — légitime, doit passer
        boot = _FakeBootstrapper()
        rec = _add(ip, user, tmp_path, boot)
        assert rec.ip == ip and rec.user == user
        assert boot.install_calls == [(ip, user)]


# --- Boundary web : /api/nodes rejette la cible hostile AVANT tout appel ssh (protection transitive) ---
import json as _json
import threading as _threading
import urllib.error as _urlerror
import urllib.request as _urlrequest

from forgeai.web.server import build_server


def _post_node(base, payload):
    req = _urlrequest.Request(f"{base}/api/nodes", data=_json.dumps(payload).encode(),
                              headers={"Content-Type": "application/json"}, method="POST")
    try:
        with _urlrequest.urlopen(req, timeout=10) as r:
            return r.status, _json.loads(r.read().decode())
    except _urlerror.HTTPError as exc:
        return exc.code, _json.loads(exc.read().decode())


def test_api_nodes_rejette_user_hostile(monkeypatch):
    """POST /api/nodes avec un user d'injection → 400, et le bootstrapper n'est JAMAIS appelé."""
    boot = _FakeBootstrapper()
    monkeypatch.setattr("forgeai.web.server._NODE_BOOTSTRAPPER", boot)
    srv = build_server("127.0.0.1", 0)
    _threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        code, body = _post_node(base, {"ip": "10.0.0.1", "user": "-oProxyCommand=touch /tmp/pwn",
                                       "password": "eph"})
        assert code == 400, body
        assert boot.install_calls == [], "aucune connexion ssh ne doit être tentée"
        assert "/tmp/pwn" not in _json.dumps(body), "la charge hostile ne doit pas être reflétée"
    finally:
        srv.shutdown(); srv.server_close()
