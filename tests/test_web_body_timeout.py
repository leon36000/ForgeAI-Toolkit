"""Regression tests for bounded HTTP request-body reads (RC1-AUDIT-WEB-590)."""

from __future__ import annotations

import socket
import threading
import time

import pytest

from forgeai.web.server import build_server


@pytest.fixture()
def live_server():
    server = build_server("127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


def _partial_post(server) -> tuple[socket.socket, float]:
    port = server.server_address[1]
    client = socket.create_connection(("127.0.0.1", port), timeout=6)
    request = (
        f"POST /api/nodes HTTP/1.0\r\n"
        f"Host: 127.0.0.1:{port}\r\n"
        "Content-Type: application/json\r\n"
        "Content-Length: 64\r\n"
        "\r\n"
        "{"
    ).encode("ascii")
    client.sendall(request)
    return client, time.monotonic()


def _read_response(client: socket.socket) -> bytes:
    chunks: list[bytes] = []
    while True:
        chunk = client.recv(4096)
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)


def test_partial_body_gets_408_instead_of_hanging_thread(live_server) -> None:
    client, started = _partial_post(live_server)
    try:
        response = _read_response(client)
    finally:
        client.close()

    elapsed = time.monotonic() - started
    assert response.startswith(b"HTTP/1.0 408 "), response
    assert elapsed < 5.5, f"le corps partiel a bloqué {elapsed:.2f}s"


def test_many_partial_bodies_are_released_within_one_bound(live_server) -> None:
    clients: list[socket.socket] = []
    started = time.monotonic()
    try:
        for _ in range(8):
            client, _ = _partial_post(live_server)
            clients.append(client)

        port = live_server.server_address[1]
        with socket.create_connection(("127.0.0.1", port), timeout=2) as healthy_client:
            healthy_client.sendall(
                f"GET /api/health HTTP/1.0\r\nHost: 127.0.0.1:{port}\r\n\r\n".encode("ascii")
            )
            healthy_response = _read_response(healthy_client)

        responses = [_read_response(client) for client in clients]
    finally:
        for client in clients:
            client.close()

    elapsed = time.monotonic() - started
    assert healthy_response.startswith(b"HTTP/1.0 200 "), healthy_response
    assert all(response.startswith(b"HTTP/1.0 408 ") for response in responses), responses
    assert elapsed < 5.5, f"les corps partiels ont retenu les handlers {elapsed:.2f}s"
