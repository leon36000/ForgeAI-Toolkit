from __future__ import annotations

import importlib.resources
import json
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from forgeai.core.runner import SubprocessRunner
from forgeai.hardware.detect import HardwareDetector


_MIME_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
}


def _mime(name: str) -> str:
    lower = name.lower()
    for ext, ctype in _MIME_TYPES.items():
        if lower.endswith(ext):
            return ctype
    return "application/octet-stream"


def _asset_bytes(name: str) -> bytes | None:
    """Retourne le contenu d'un asset embarqué, ou None si interdit/absent."""
    if "/" in name or "\\" in name or ".." in name:
        return None
    try:
        resource = importlib.resources.files("forgeai.web") / "assets" / name
        return resource.read_bytes()
    except (FileNotFoundError, ModuleNotFoundError):
        return None


def hardware_json() -> str:
    return HardwareDetector(SubprocessRunner()).full_report().to_json()


class ForgeAIHandler(BaseHTTPRequestHandler):
    server_version = "ForgeAI/0.1"

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        path = urllib.parse.urlparse(self.path).path

        if path in ("/", "/index.html"):
            data = _asset_bytes("index.html")
            if data is None:
                self._send(500, b"index.html missing", "text/plain; charset=utf-8")
            else:
                self._send(200, data, "text/html; charset=utf-8")
            return

        if path == "/api/detect":
            try:
                body = hardware_json().encode("utf-8")
                self._send(200, body, "application/json; charset=utf-8")
            except Exception as exc:  # noqa: BLE001
                payload = json.dumps({"error": str(exc)}, ensure_ascii=False).encode("utf-8")
                self._send(500, payload, "application/json; charset=utf-8")
            return

        if path == "/api/health":
            self._send(
                200,
                json.dumps({"status": "ok"}, ensure_ascii=False).encode("utf-8"),
                "application/json; charset=utf-8",
            )
            return

        basename = path.rsplit("/", 1)[-1]
        data = _asset_bytes(basename)
        if data is not None:
            self._send(200, data, _mime(basename))
            return

        payload = json.dumps({"error": "not found", "path": path}, ensure_ascii=False).encode("utf-8")
        self._send(404, payload, "application/json; charset=utf-8")

    def log_message(self, *args) -> None:  # noqa: ARG002
        return


def build_server(host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), ForgeAIHandler)


def serve(
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = True,
) -> None:
    server = build_server(host, port)
    url = f"http://{host}:{server.server_address[1]}"
    print(url)
    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
        server.server_close()


def web_command(args) -> int:
    serve(
        getattr(args, "host", "127.0.0.1"),
        getattr(args, "port", 8765),
        open_browser=not getattr(args, "no_browser", False),
    )
    return 0
