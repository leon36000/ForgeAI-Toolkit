"""WEB-034B — refus des identifiants sur transport non chiffré + TLS opt-in."""

import json
import socket
import ssl
import subprocess
import threading
import urllib.error
import urllib.request

import pytest

from forgeai.web.server import build_server, ForgeAIHandler


def _generate_tls_cert_key(tmp_path):
    """Génère un certificat auto-signé + clé (sans passphrase) via openssl."""
    cert = tmp_path / "cert.pem"
    key = tmp_path / "key.pem"
    subprocess.run(
        [
            "openssl", "req", "-x509", "-newkey", "rsa:2048",
            "-keyout", str(key), "-out", str(cert),
            "-days", "1", "-nodes", "-subj", "/CN=localhost",
        ],
        check=True,
        capture_output=True,
    )
    return cert, key


def _post(url, path, headers=None, body=None, context=None):
    data = json.dumps(body or {}).encode()
    req = urllib.request.Request(
        url.rstrip("/") + path, data=data, method="POST",
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    try:
        with urllib.request.urlopen(req, timeout=10, context=context) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()


def _get(url, path, headers=None):
    req = urllib.request.Request(url.rstrip("/") + path, method="GET", headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()


@pytest.fixture()
def live_no_tls():
    """Serveur loopback SANS TLS, port libre."""
    server = build_server("127.0.0.1", 0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_address[1]
    yield f"http://127.0.0.1:{port}", port, server
    server.shutdown()
    server.server_close()


@pytest.fixture()
def live_tls(monkeypatch, tmp_path):
    """Serveur loopback AVEC TLS (cert auto-signé), port libre."""
    cert, key = _generate_tls_cert_key(tmp_path)
    monkeypatch.setenv("FORGEAI_TLS_CERT", str(cert))
    monkeypatch.setenv("FORGEAI_TLS_KEY", str(key))
    server = build_server("127.0.0.1", 0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_address[1]
    yield f"https://127.0.0.1:{port}", port, server
    server.shutdown()
    server.server_close()


def test_identifiants_refuses_sur_reseau_clair(monkeypatch, live_no_tls):
    """CA1 : Authorization sur un client réseau sans TLS → 426 + message orientant vers TLS."""
    url, _port, _server = live_no_tls
    monkeypatch.setattr("forgeai.web.server._is_loopback_host", lambda ip: False)

    status, body = _post(url, "/api/deploy", headers={"Authorization": "Bearer x"})  # proof:allow
    assert status == 426, f"attendu 426, reçu {status}"
    assert "tls" in body.lower(), f"le message doit orienter vers TLS: {body}"


def test_sans_identifiants_pas_de_refus(monkeypatch, live_no_tls):
    """CA2 : sans Authorization, le trafic réseau n'est pas bloqué (/api/health)."""
    url, _port, _server = live_no_tls
    monkeypatch.setattr("forgeai.web.server._is_loopback_host", lambda ip: False)

    status, _ = _get(url, "/api/health")
    assert status == 200, f"le trafic sans identifiant ne doit pas être bloqué, reçu {status}"


def test_loopback_clair_autorise(live_no_tls):
    """CA2 : sur loopback réel, un POST avec Authorization ne déclenche JAMAIS 426 (UI locale)."""
    url, _port, _server = live_no_tls
    status, _ = _post(url, "/api/deploy", headers={"Authorization": "Bearer x"})  # proof:allow
    assert status != 426, "le loopback en clair doit rester autorisé"


def test_password_reseau_clair_refuse(monkeypatch, live_no_tls):
    """§2c : le mot de passe de POST /api/nodes est couvert TRANSITIVEMENT.

    Avec Authorization (cas réseau réel, le Bearer étant exigé hors loopback) → 426.
    Sans Authorization → 401 (jamais accepté) : dans les deux cas le mot de passe n'est
    jamais traité sur un transport réseau en clair.
    """
    url, _port, _server = live_no_tls
    monkeypatch.setattr("forgeai.web.server._is_loopback_host", lambda ip: False)
    corps = {"ip": "10.0.0.2", "user": "forge", "password": "MOTDEPASSE-TEST", "hostkey": "SHA256:x"}  # proof:allow

    status_avec, _ = _post(url, "/api/nodes", headers={"Authorization": "Bearer x"}, body=corps)  # proof:allow
    assert status_avec == 426, f"avec identifiant → 426, reçu {status_avec}"

    status_sans, _ = _post(url, "/api/nodes", body=corps)
    assert status_sans == 401, f"sans identifiant → 401 (jamais traité), reçu {status_sans}"


def test_is_secure_transport_false_hors_loopback_sans_tls(monkeypatch):
    """Unité : transport NON sûr pour un client réseau sur socket ordinaire.

    Le handler est construit sans __init__ (BaseHTTPRequestHandler.__init__ lance handle()
    et lirait la socket) : on n'exerce que le prédicat.
    """
    monkeypatch.setattr("forgeai.web.server._is_loopback_host", lambda ip: False)
    handler = ForgeAIHandler.__new__(ForgeAIHandler)
    handler.client_address = ("10.0.0.9", 12345)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        handler.connection = sock
        assert handler._is_secure_transport() is False
    finally:
        sock.close()


def test_is_secure_transport_true_en_loopback():
    """Unité : un client loopback est toujours considéré comme sûr (pas de réseau traversé)."""
    handler = ForgeAIHandler.__new__(ForgeAIHandler)
    handler.client_address = ("127.0.0.1", 12345)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        handler.connection = sock
        assert handler._is_secure_transport() is True
    finally:
        sock.close()


def test_tls_transport_accepte_identifiants(monkeypatch, live_tls):
    """CA3 : sur TLS, même avec un client réseau (loopback patché False), pas de 426."""
    url, _port, server = live_tls
    monkeypatch.setattr("forgeai.web.server._is_loopback_host", lambda ip: False)
    assert server.forgeai_tls is True, "le serveur TLS doit être marqué forgeai_tls"

    status, _ = _post(
        url, "/api/deploy",
        headers={"Authorization": "Bearer x"},  # proof:allow
        context=ssl._create_unverified_context(),
    )
    assert status != 426, "le TLS rend le transport sûr : pas de refus 426"
    assert status in (400, 401, 403), f"jeton bidon → refus d'auth attendu, reçu {status}"


def test_build_server_sans_tls_par_defaut(monkeypatch):
    """CA3 : sans FORGEAI_TLS_*, forgeai_tls est False (aucun TLS implicite)."""
    monkeypatch.delenv("FORGEAI_TLS_CERT", raising=False)
    monkeypatch.delenv("FORGEAI_TLS_KEY", raising=False)
    server = build_server("127.0.0.1", 0)
    try:
        assert server.forgeai_tls is False
    finally:
        server.server_close()


def test_garde_est_bien_la_source_du_426(monkeypatch, live_no_tls):
    """Détecteur : en neutralisant _require_secure_transport, le 426 disparaît — le refus
    provient donc bien de cette garde (et non d'un autre chemin)."""
    url, _port, _server = live_no_tls
    monkeypatch.setattr("forgeai.web.server._is_loopback_host", lambda ip: False)
    monkeypatch.setattr(ForgeAIHandler, "_require_secure_transport", lambda self: True)

    status, _ = _post(url, "/api/deploy", headers={"Authorization": "Bearer x"})  # proof:allow
    assert status != 426, "sans la garde, aucun 426 ne doit être émis"
