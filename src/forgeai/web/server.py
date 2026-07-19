from __future__ import annotations

import importlib.resources
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from forgeai.catalogue.spheres import SPHERES, classify_sphere, spheres_index
from forgeai.core import registre
from forgeai.core.runner import SubprocessRunner, CommandRunner
from forgeai.deploy.compose import http_ok
from forgeai.hardware.detect import HardwareDetector
from forgeai.models.probe import Transport
from forgeai.models.routes import RouteError, RouteStore
from forgeai.network.keys import generate_keypair, KeyError_
from forgeai.network.node_add import add_node, Bootstrapper, NodeAddError, SshBootstrapper
from forgeai.network.nodes import cluster_status, ClusterError
from forgeai.preflight import available_backends, run_checks
from forgeai.resources import catalogue_path
from forgeai.stacks import deploy_ids, list_stacks, load_stack

try:
    from forgeai.catalogue.loader import parse_stars
except Exception:  # pragma: no cover
    import re

    def parse_stars(popularity: str | None) -> int:
        if popularity is None:
            return 0
        match = re.search(r"★\s*(\d+)", popularity)
        return int(match.group(1)) if match else 0


_MIME_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
}

_CHASSIS_CACHE: frozenset[str] | None = None
_NODE_RE = re.compile(r"^[a-z0-9]([a-z0-9.-]{0,62})$", re.ASCII)


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


def _catalogue_entries() -> list[dict]:
    return json.loads(catalogue_path().read_text(encoding="utf-8")).get("entries", [])


def _json_body(obj: object) -> bytes:
    return json.dumps(obj, ensure_ascii=False).encode("utf-8")


def chassis_ids() -> frozenset[str]:
    """Intersection des briques déployées par tous les stacks hors 'tout-en-un'."""
    global _CHASSIS_CACHE
    if _CHASSIS_CACHE is not None:
        return _CHASSIS_CACHE

    profiles = [sid for sid in list_stacks() if sid != "tout-en-un"]
    common: set[str] | None = None
    for sid in profiles:
        deployed = set(deploy_ids(load_stack(sid)))
        common = deployed if common is None else common & deployed

    _CHASSIS_CACHE = frozenset(common) if common is not None else frozenset()
    return _CHASSIS_CACHE


def bricks_payload(sphere_id: str, stack_id: str | None) -> dict | None:
    """Catalogue d'une sphère, enrichi de l'état par rapport à un stack optionnel."""
    valid_spheres = {s.id for s in SPHERES}
    if sphere_id not in valid_spheres:
        return None

    entries = _catalogue_entries()
    deployed: set[str] = set()
    sphere_defaults: dict[str, str] = {}

    if stack_id is not None:
        try:
            stack = load_stack(stack_id)
        except FileNotFoundError:
            return None
        deployed = set(deploy_ids(stack))
        sphere_defaults = stack.get("default_by_sphere", {})

    locked = chassis_ids()
    bricks = []
    for entry in entries:
        if classify_sphere(entry) != sphere_id:
            continue
        brick_id = entry["id"]
        installed = brick_id in deployed
        bricks.append(
            {
                "id": brick_id,
                "name": entry["name"],
                "description_fr": entry.get("description_fr", ""),
                "description_en": entry.get("description_en", ""),
                "stars": parse_stars(entry.get("popularity")),
                "license": entry.get("license", ""),
                "installed": installed,
                "locked": (brick_id in locked) and installed,
                "default": sphere_defaults.get(sphere_id) == brick_id,
            }
        )

    bricks.sort(key=lambda b: (not b["installed"], -b["stars"], b["id"]))
    return {
        "sphere": sphere_id,
        "stack": stack_id,
        "total": len(bricks),
        "bricks": bricks,
    }


def forgeai_home() -> Path:
    """Répertoire utilisateur ForgeAI (FORGEAI_HOME ou ~/.forgeai)."""
    return Path(os.environ.get("FORGEAI_HOME", Path.home() / ".forgeai"))


# Hooks pour les tests (valeurs par défaut si non posés).
_MODELS_HOME: Path | None = None
_PROBE_TRANSPORT: Transport | None = None
_REGISTRE_PATH: Path | None = None

_NODE_BOOTSTRAPPER: Bootstrapper | None = None
_NODE_KEYS_DIR: Path | None = None

# Hook déploiement : remplace la commande wizard par défaut dans les tests.
_DEPLOY_CMD: list[str] | None = None

_DEPLOY_STATE = {
    "proc": None,
    "lines": [],
    "done": False,
    "exit_code": None,
    "lock": threading.Lock(),
}


def _models_home() -> Path:
    return _MODELS_HOME if _MODELS_HOME is not None else forgeai_home() / "models"


def _probe_transport() -> Transport | None:
    return _PROBE_TRANSPORT


def _registre_path() -> Path:
    return _REGISTRE_PATH if _REGISTRE_PATH is not None else forgeai_home() / "Registres" / "mission.jsonl"


def _node_keys(runner: CommandRunner) -> tuple[Path, Path]:
    """Retourne la paire de clés active, la génère si elle est absente."""
    key_dir = _NODE_KEYS_DIR if _NODE_KEYS_DIR is not None else forgeai_home() / "keys"
    private = key_dir / "forgeai_ed25519"
    public = private.with_suffix(".pub")
    if not private.exists() or not public.exists():
        generate_keypair(key_dir, runner)
    return public, private


def _available_backends() -> list[str]:
    return available_backends(
        run_checks(SubprocessRunner(), HardwareDetector(SubprocessRunner()), http_ok)
    )


def _summary_payload(stack_id: str) -> dict:
    stack = load_stack(stack_id)
    profile = HardwareDetector(SubprocessRunner()).full_report()
    nodes: list[str] = []
    try:
        nodes = [n["name"] for n in cluster_status(SubprocessRunner())]
    except ClusterError:
        pass
    return {
        "stack": {
            "id": stack.get("id", stack_id),
            "name": stack.get("name", stack_id),
            "n_deploy": len(deploy_ids(stack)),
        },
        "hardware": {
            "cpu_model": getattr(profile, "cpu_model", ""),
            "gpus": len(getattr(profile, "gpus", [])),
            "ram_gb": getattr(profile, "ram_gb", 0),
        },
        "backends": _available_backends(),
        "chassis": len(chassis_ids()),
        "nodes": nodes,
    }


class ForgeAIHandler(BaseHTTPRequestHandler):
    server_version = "ForgeAI/0.1"

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, code: int, obj: object) -> None:
        self._send(code, _json_body(obj), "application/json; charset=utf-8")

    def _read_json_body(self, max_length: int = 65536) -> dict | None:
        length_hdr = self.headers.get("Content-Length")
        if length_hdr is None:
            self._send_json(413, {"error": "Content-Length requis"})
            return None

        try:
            length = int(length_hdr)
        except ValueError:
            self._send_json(400, {"error": "Content-Length invalide"})
            return None

        if length < 0 or length > max_length:
            self._send_json(413, {"error": "corps trop grand"})
            return None

        try:
            body = self.rfile.read(length)
            data = json.loads(body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._send_json(400, {"error": "JSON invalide"})
            return None

        if not isinstance(data, dict):
            self._send_json(400, {"error": "JSON invalide"})
            return None

        return data

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

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

        if path == "/api/models":
            store = RouteStore(_models_home())
            self._send_json(200, [r.public_dict() for r in store.list()])
            return

        if path == "/api/stacks":
            stack_ids = list_stacks()
            ordered = [sid for sid in stack_ids if sid != "tout-en-un"]
            if "tout-en-un" in stack_ids:
                ordered.append("tout-en-un")
            summaries = []
            for sid in ordered:
                stack = load_stack(sid)
                summaries.append(
                    {
                        "id": stack.get("id", sid),
                        "name": stack.get("name", sid),
                        "description_fr": stack.get("description_fr", ""),
                        "description_en": stack.get("description_en", ""),
                        "n_deploy": len(deploy_ids(stack)),
                        "defaults": stack.get("default_by_sphere", {}),
                        "surface": stack.get("surface"),
                    }
                )
            self._send_json(200, summaries)
            return

        if path.startswith("/api/stacks/"):
            sid = path[len("/api/stacks/") :]
            if not sid or "/" in sid:
                self._send_json(404, {"error": "stack not found"})
                return
            try:
                stack = load_stack(sid)
                self._send_json(200, stack)
            except FileNotFoundError:
                self._send_json(404, {"error": "stack not found"})
            return

        if path == "/api/spheres":
            entries = _catalogue_entries()
            index = spheres_index(entries)
            spheres = [
                {
                    "id": sphere.id,
                    "num": sphere.num,
                    "name_fr": sphere.name_fr,
                    "name_en": sphere.name_en,
                    "count": len(index.get(sphere.id, [])),
                }
                for sphere in sorted(SPHERES, key=lambda s: s.num)
            ]
            self._send_json(200, spheres)
            return

        if path == "/api/bricks":
            query = urllib.parse.parse_qs(parsed.query)
            sphere_list = query.get("sphere")
            if not sphere_list:
                self._send_json(400, {"error": "sphere requis"})
                return
            sphere_id = sphere_list[0]
            stack_id = query.get("stack", [None])[0]
            payload = bricks_payload(sphere_id, stack_id)
            if payload is None:
                self._send_json(404, {"error": "not found"})
                return
            self._send_json(200, payload)
            return

        if path == "/api/summary":
            query = urllib.parse.parse_qs(parsed.query)
            stack_list = query.get("stack")
            if not stack_list:
                self._send_json(400, {"error": "stack requis"})
                return
            stack_id = stack_list[0]
            try:
                self._send_json(200, _summary_payload(stack_id))
            except FileNotFoundError:
                self._send_json(404, {"error": "stack not found"})
            return

        if path == "/api/deploy/events":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()

            if _DEPLOY_STATE["proc"] is None:
                payload = json.dumps({"exit_code": None}, ensure_ascii=False)
                try:
                    self.wfile.write(f"event: end\ndata: {payload}\n\n".encode("utf-8"))
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    pass
                return

            idx = 0
            while True:
                with _DEPLOY_STATE["lock"]:
                    lines = _DEPLOY_STATE["lines"]
                    done = _DEPLOY_STATE["done"]
                    exit_code = _DEPLOY_STATE["exit_code"]
                    while idx < len(lines):
                        try:
                            self.wfile.write(f"data: {lines[idx]}\n\n".encode("utf-8"))
                            self.wfile.flush()
                        except (BrokenPipeError, ConnectionResetError):
                            return
                        idx += 1
                    if done:
                        payload = json.dumps({"exit_code": exit_code}, ensure_ascii=False)
                        try:
                            self.wfile.write(f"event: end\ndata: {payload}\n\n".encode("utf-8"))
                            self.wfile.flush()
                        except (BrokenPipeError, ConnectionResetError):
                            pass
                        return
                time.sleep(0.2)

        if path == "/api/nodes/status":
            runner = SubprocessRunner()
            try:
                nodes = cluster_status(runner)
                self._send_json(200, {"nodes": nodes})
            except ClusterError as exc:
                self._send_json(200, {"nodes": [], "detail": str(exc)})
            return

        basename = path.rsplit("/", 1)[-1]
        data = _asset_bytes(basename)
        if data is not None:
            self._send(200, data, _mime(basename))
            return

        payload = json.dumps({"error": "not found", "path": path}, ensure_ascii=False).encode("utf-8")
        self._send(404, payload, "application/json; charset=utf-8")

    def do_POST(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/api/nodes":
            data = self._read_json_body()
            if data is None:
                return

            required = ["ip", "user", "password"]
            missing = [field for field in required if field not in data]
            if missing:
                self._send_json(400, {"error": "champs manquants", "missing": missing})
                return

            ip = data["ip"]
            user = data["user"]
            password = data["password"]  # proof:allow (identifiant ; valeur jamais journalisee)

            try:
                runner = SubprocessRunner()
                pubkey, privkey = _node_keys(runner)
                bootstrapper = _NODE_BOOTSTRAPPER if _NODE_BOOTSTRAPPER is not None else SshBootstrapper()
                record = add_node(
                    ip,
                    user,
                    password,
                    pubkey=pubkey,
                    privkey=privkey,
                    bootstrapper=bootstrapper,
                    runner=runner,
                    registre_path=_registre_path(),
                )
            except NodeAddError as exc:
                self._send_json(400, {"error": str(exc)})
                return
            except KeyError_:
                self._send_json(500, {"error": "erreur de gestion des clés"})
                return
            except FileNotFoundError as exc:
                # outil requis absent (ex. sshpass, ssh-keygen) — réponse propre,
                # jamais de crash silencieux du handler (preuve navigateur B-02d)
                self._send_json(500, {"error": f"outil requis absent : {exc.filename or exc}"})
                return
            except Exception:
                # aucune valeur soumise n'est reflétée
                self._send_json(500, {"error": "erreur interne lors de l'ajout du nœud"})
                return

            self._send_json(
                201,
                {
                    "node": {
                        "ip": record.ip,
                        "user": record.user,
                        "key_fingerprint": record.key_fingerprint,
                    }
                },
            )
            return

        if path == "/api/deploy":
            data = self._read_json_body()
            if data is None:
                return

            required = ["stack", "backend", "confirm"]
            missing = [field for field in required if field not in data]
            if missing:
                self._send_json(400, {"error": "champs manquants", "missing": missing})
                return

            stack_id = data["stack"]
            backend = data["backend"]
            confirm = data["confirm"]

            if confirm != "FORCER":
                self._send_json(400, {"error": "confirmation 'FORCER' requise"})
                return

            if backend not in {"compose", "k3s"}:
                self._send_json(400, {"error": "backend invalide"})
                return

            node = data.get("node", "local")
            if node not in ("local", "auto") and not _NODE_RE.match(node):
                self._send_json(400, {"error": "node invalide"})
                return

            try:
                load_stack(stack_id)
            except FileNotFoundError:
                self._send_json(404, {"error": "stack not found"})
                return

            with _DEPLOY_STATE["lock"]:
                proc = _DEPLOY_STATE["proc"]
                if proc is not None and proc.poll() is None:
                    self._send_json(409, {"error": "déploiement déjà en cours"})
                    return

                _DEPLOY_STATE["lines"].clear()
                _DEPLOY_STATE["done"] = False
                _DEPLOY_STATE["exit_code"] = None

                cmd = _DEPLOY_CMD
                if cmd is None:
                    cmd = [
                        sys.executable,
                        "-m",
                        "forgeai",
                        "wizard",
                        "--ci",
                        "--workdir",
                        str(forgeai_home() / "deploy"),
                        "--backend",
                        backend,
                        "--node",
                        node,
                        "--stack",
                        stack_id,
                    ]
                    if data.get("dry_run"):
                        cmd.append("--dry-run")

                new_proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )
                _DEPLOY_STATE["proc"] = new_proc

            def _reader() -> None:
                try:
                    for line in new_proc.stdout:
                        with _DEPLOY_STATE["lock"]:
                            _DEPLOY_STATE["lines"].append(line.rstrip("\r\n"))
                    new_proc.wait()
                    with _DEPLOY_STATE["lock"]:
                        _DEPLOY_STATE["exit_code"] = new_proc.returncode
                        _DEPLOY_STATE["done"] = True
                except Exception:
                    with _DEPLOY_STATE["lock"]:
                        if new_proc.returncode is None:
                            try:
                                new_proc.kill()
                                new_proc.wait()
                            except Exception:
                                pass
                        _DEPLOY_STATE["exit_code"] = new_proc.returncode if new_proc.returncode is not None else -1
                        _DEPLOY_STATE["done"] = True

            threading.Thread(target=_reader, daemon=True).start()
            self._send_json(202, {"started": True})
            return

        if path != "/api/models":
            self._send_json(404, {"error": "not found"})
            return

        data = self._read_json_body()
        if data is None:
            return

        required = ["name", "provenance", "model_id", "api_key", "passphrase"]
        missing = [field for field in required if field not in data]
        if missing:
            self._send_json(400, {"error": "champs manquants", "missing": missing})
            return

        name = data["name"]
        provenance = data["provenance"]
        model_id = data["model_id"]
        api_key = data["api_key"]  # proof:allow (identifiant ; la valeur n'est jamais journalisee)
        passphrase = data["passphrase"]
        base_url = data.get("base_url")

        try:
            store = RouteStore(_models_home())
            route, result = store.add_cloud(
                name,
                provenance,
                model_id,
                api_key,
                passphrase,
                base_url=base_url,
                transport=_probe_transport(),
            )
        except RouteError as exc:
            self._send_json(400, {"error": str(exc)})
            return

        # Journalisation best-effort : la route EST créée (clé scellée) même si le
        # registre échoue, mais l'échec est SIGNALÉ au client (objection revue B-02c —
        # jamais avalé en silence).
        registre_journalise = True
        try:
            reg_path = _registre_path()
            reg_path.parent.mkdir(parents=True, exist_ok=True)
            registre.append(
                reg_path,
                "route_cloud_ajoutee",
                "web",
                {
                    "name": route.name,
                    "provenance": route.provenance,
                    "model_id": route.model_id,
                    "key_fingerprint": route.key_fingerprint,
                },
            )
        except Exception:
            registre_journalise = False

        self._send_json(
            201,
            {
                "route": route.public_dict(),
                "probe": {"light": result.light, "detail": result.detail},
                "registre_journalise": registre_journalise,
            },
        )

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
