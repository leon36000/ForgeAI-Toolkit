from dataclasses import dataclass
from . import IDEError, IdeConfig
from forgeai.i18n import t
import json

MCP_CAPABLE = ("claude-code", "cline", "cursor", "opencode")

@dataclass(frozen=True)
class McpServer:
    name: str
    url: str
    transport: str = "http"

    def __post_init__(self):
        if self.transport not in ("http", "sse"):
            raise IDEError(t("ide.bootstrap.mcp_server.transport_invalide", transport=self.transport))

@dataclass(frozen=True)
class HookSpec:
    """Spécification d'un hook claude-code (event + commande + matcher optionnel).

    Invariants durcis (gelés par ``__post_init__`` ET revérifiés à l'usage dans
    ``_normalize_hook`` — un appelant peut muter une instance frozen via
    ``object.__setattr__``, ce qui contourne ``__post_init__`` ; c'est pourquoi
    la validation est *aussi* re-effectuée à chaque consommation) :

    - les trois champs doivent être des ``str`` (ni ``int``, ni ``list``, etc.) ;
    - aucun champ ne doit être vide ni whitespace-only (un event/command/matcher
      « mort » ne doit jamais atteindre le JSON).
    """

    event: str
    command: str
    matcher: str = "*"

    def __post_init__(self):
        # O2 : validation à la construction — type strict + non-vide après strip.
        # O3 : le message d'erreur inclut le type reçu pour faciliter le diagnostic.
        if not isinstance(self.event, str):
            raise IDEError(
                t("ide.bootstrap.hook_spec.event_type_invalide", type_recu=type(self.event).__name__)
            )
        if not isinstance(self.command, str):
            raise IDEError(
                t("ide.bootstrap.hook_spec.command_type_invalide", type_recu=type(self.command).__name__)
            )
        if not isinstance(self.matcher, str):
            raise IDEError(
                t("ide.bootstrap.hook_spec.matcher_type_invalide", type_recu=type(self.matcher).__name__)
            )
        if not self.event.strip():
            raise IDEError(t("ide.bootstrap.hook_spec.event_vide"))
        if not self.command.strip():
            raise IDEError(t("ide.bootstrap.hook_spec.command_vide"))
        if not self.matcher.strip():
            raise IDEError(t("ide.bootstrap.hook_spec.matcher_vide"))


def _normalize_hook(item):
    """Normalise un élément de ``hooks`` en ``HookSpec``, avec re-validation défensive.

    Pourquoi re-valider ici alors que ``HookSpec.__post_init__`` valide déjà ?
    Parce qu'une dataclass ``frozen`` n'est gelée que par son ``__setattr__``
    généré ; ``object.__setattr__(instance, ...)`` contourne cette protection.
    Un appelant peut donc muter un ``HookSpec`` après construction ; la
    validation de construction seule ne couvre pas ce chemin. On revérifie donc
    les trois invariants (type str + strip non vide) à chaque consommation.
    """
    # Cas str : on construit un HookSpec canonique (event == command, matcher "*").
    if isinstance(item, str):
        if not item or not item.strip():
            # O4 : durcissement VOLONTAIRE — chaîne vide / whitespace-only rejetée.
            raise IDEError(t("ide.bootstrap.normalize_hook.str_vide"))
        return HookSpec(event=item, command=item, matcher="*")

    # Cas HookSpec : on revérifie les trois champs (le contournement
    # object.__setattr__ rend __post_init__ insuffisant).
    if isinstance(item, HookSpec):
        if not isinstance(item.event, str) or not item.event.strip():
            raise IDEError(
                t("ide.bootstrap.normalize_hook.event_invalide_usage", type_recu=type(item.event).__name__)
            )
        if not isinstance(item.command, str) or not item.command.strip():
            raise IDEError(
                t("ide.bootstrap.normalize_hook.command_invalide_usage", type_recu=type(item.command).__name__)
            )
        if not isinstance(item.matcher, str) or not item.matcher.strip():
            raise IDEError(
                t("ide.bootstrap.normalize_hook.matcher_invalide_usage", type_recu=type(item.matcher).__name__)
            )
        return item

    raise IDEError(t("ide.bootstrap.normalize_hook.type_invalide", type_recu=type(item).__name__))

def generate_mcp_config(ide: str, servers: list[McpServer]) -> IdeConfig:
    if ide not in MCP_CAPABLE:
        raise IDEError(t("ide.bootstrap.generate_mcp_config.ide_non_mcp_capable", ide=ide))
    if not servers:
        raise IDEError(t("ide.bootstrap.generate_mcp_config.aucun_serveur"))

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
        raise IDEError(t("ide.bootstrap.generate_mcp_config.ide_non_supporte", ide=ide))

    content_str = json.dumps(content, ensure_ascii=False, indent=1)
    return IdeConfig(ide=ide, path=path, content=content_str, fmt="json")

def generate_governance_config(skills: list[str], hooks: list[str | HookSpec], *, ide: str = "claude-code") -> IdeConfig:
    """Construit ``.claude/settings.json`` (claude-code uniquement).

    Chaque entrée de ``skills`` devient un élément de ``permissions.allow``.
    Chaque entrée de ``hooks`` (str ou ``HookSpec``) devient une règle
    ``{matcher, hooks:[{type: command, command}]}`` groupée par ``event``.

    **Divergences assumées par rapport à l'historique (durcissement volontaire,
    pas un bug)** :

    - Une chaîne vide ou whitespace-only dans ``hooks`` (``[""]``, ``[" "]``)
      lève ``IDEError`` au lieu d'être sérialisée comme une clé/event mort
      dans le JSON (O4).
    - Un ``HookSpec`` dont un champ n'est pas ``str`` ou est vide/whitespace
      est rejeté — à la construction (``__post_init__``) ET à l'usage dans
      ``_normalize_hook`` (un HookSpec peut être muté via
      ``object.__setattr__`` après construction, ce qui contourne le
      ``__post_init__`` d'une dataclass frozen).
    - Les règles strictement identiques (même ``matcher`` ET même liste de
      commandes) pour un même ``event`` sont dédupliquées ; deux ``HookSpec``
      distincts sur le même event restent agrégés.
    """
    if ide != "claude-code":
        raise IDEError(t("ide.bootstrap.generate_governance_config.ide_non_supporte"))
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
        bucket = hooks_dict.setdefault(spec.event, [])
        # Égalité structurelle des dicts : même matcher + même contenu == même règle.
        # Préserve l'historique (["A","A"] -> 1 règle) tout en agrégeant les DISTINCTES.
        if rule not in bucket:
            bucket.append(rule)
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
