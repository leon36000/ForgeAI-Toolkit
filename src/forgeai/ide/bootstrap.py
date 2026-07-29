from dataclasses import dataclass
from . import IDEError, IdeConfig
import json

MCP_CAPABLE = ("claude-code", "cline", "cursor", "opencode")

@dataclass(frozen=True)
class McpServer:
    name: str
    url: str
    transport: str = "http"

    def __post_init__(self):
        if self.transport not in ("http", "sse"):
            raise IDEError(f"transport MCP invalide: {self.transport} (attendu http ou sse)")

@dataclass(frozen=True)
class HookSpec:
    event: str
    command: str
    matcher: str = "*"

    def __post_init__(self):
        if not self.event:
            raise IDEError("HookSpec: 'event' vide")
        if not self.command:
            raise IDEError("HookSpec: 'command' vide")
        if not self.matcher:
            raise IDEError("HookSpec: 'matcher' vide")

def _normalize_hook(item):
    if isinstance(item, HookSpec):
        return item
    if isinstance(item, str):
        if not item:
            raise IDEError("hook str vide")
        return HookSpec(event=item, command=item, matcher="*")
    raise IDEError(f"type de hook invalide: {type(item).__name__}")

def generate_mcp_config(ide: str, servers: list[McpServer]) -> IdeConfig:
    if ide not in MCP_CAPABLE:
        raise IDEError(f"IDE '{ide}' ne supporte pas la configuration MCP")
    if not servers:
        raise IDEError("aucun serveur MCP fourni")

    if ide in ("claude-code", "cline"):
        servers_dict = {
            s.name: {"type": s.transport, "url": s.url}
            for s in servers
        }
        content = {"mcpServers": servers_dict}
        path = ".mcp.json" if ide == "claude-code" else "cline_mcp_settings.json"
    elif ide == "cursor":
        servers_dict = {s.name: {"url": s.url} for s in servers}
        content = {"mcpServers": servers_dict}
        path = ".cursor/mcp.json"
    elif ide == "opencode":
        servers_dict = {
            s.name: {"type": "remote", "url": s.url, "enabled": True}
            for s in servers
        }
        content = {"mcp": servers_dict}
        path = "opencode.json"
    else:
        # safety, already checked
        raise IDEError(f"IDE '{ide}' non supporté")

    content_str = json.dumps(content, ensure_ascii=False, indent=1)
    return IdeConfig(ide=ide, path=path, content=content_str, fmt="json")

def generate_governance_config(skills: list[str], hooks: list[str | HookSpec], *, ide: str = "claude-code") -> IdeConfig:
    if ide != "claude-code":
        raise IDEError("governance skills+hooks n'est supportée que pour claude-code")
    # Build permissions.allow from skills
    permissions = {"allow": skills}
    # Build hooks: each hook becomes a key with a list of one matcher rule
    hooks_dict: dict[str, list[dict]] = {}
    for item in hooks:
        spec = _normalize_hook(item)
        rule = {
            "matcher": spec.matcher,
            "hooks": [{"type": "command", "command": spec.command}],
        }
        hooks_dict.setdefault(spec.event, []).append(rule)
    content = {"permissions": permissions, "hooks": hooks_dict}
    content_str = json.dumps(content, ensure_ascii=False, indent=1)
    return IdeConfig(ide="claude-code", path=".claude/settings.json", content=content_str, fmt="json")

def verify_bootstrap(*configs: IdeConfig) -> list[str]:
    problems = []

    MCP_PATHS = {".mcp.json", "cline_mcp_settings.json", ".cursor/mcp.json", "opencode.json"}
    GOVERNANCE_PATH = ".claude/settings.json"

    for cfg in configs:
        # Check JSON validity
        try:
            data = json.loads(cfg.content)
        except (json.JSONDecodeError, ValueError) as e:
            problems.append(f"JSON invalide dans {cfg.path}: {e}")
            continue  # can't do deeper checks

        # Check MCP configs
        if cfg.path in MCP_PATHS:
            has_servers = False
            if cfg.path in (".mcp.json", "cline_mcp_settings.json", ".cursor/mcp.json"):
                mcp_servers = data.get("mcpServers", {})
                if mcp_servers:
                    has_servers = True
            elif cfg.path == "opencode.json":
                mcp_dict = data.get("mcp", {})
                if mcp_dict:
                    has_servers = True
            if not has_servers:
                problems.append(f"Configuration MCP {cfg.path} sans serveur défini")
        # Check governance config
        elif cfg.path == GOVERNANCE_PATH:
            if not ("permissions" in data and "hooks" in data):
                problems.append(
                    f"Configuration de gouvernance {cfg.path} sans clé 'permissions' ou 'hooks'"
                )

    return sorted(problems)
