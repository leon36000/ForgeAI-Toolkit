"""Branchement automatique brique → gateway UNIQUE (exigence DM-6, story B-11).

Invariant : AUCUNE brique ne pointe vers un modèle. Toute brique consommant un modèle est
câblée vers le gateway unique (endpoint compatible OpenAI) ; le gateway seul détient les
clés fournisseur (au coffre, story B-09) et route par nom de modèle. Une brique reçoit :
  - OPENAI_API_BASE = URL du gateway (jamais une URL fournisseur) ;
  - OPENAI_API_KEY  = jeton INTERNE du gateway (jamais une clé fournisseur) ;
  - OPENAI_MODEL    = modèle résolu depuis le rôle de la brique.
Le câblage est vérifié (assert_via_gateway) puis PROUVÉ par un appel traversant réel.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from .probe import ProbeResult, Transport, probe_route
from .routes import PROVENANCES, RouteError, RouteStore

# Hôtes fournisseurs connus : une brique qui pointe là = violation de l'invariant.
_PROVIDER_HOSTS = {
    urlparse(u).hostname for u in PROVENANCES.values() if u
} | {
    "api.openai.com", "api.anthropic.com", "api.mistral.ai", "generativelanguage.googleapis.com",
    "api.deepseek.com", "api.moonshot.ai", "api.x.ai", "z.ai", "api.minimax.io",
}


class GatewayError(Exception):
    pass


@dataclass(frozen=True)
class GatewayConfig:
    """Le gateway unique. `key_env` nomme la variable portant son jeton interne (jamais inline)."""
    base_url: str
    key_env: str = "FORGEAI_GATEWAY_KEY"

    def __post_init__(self) -> None:
        host = urlparse(self.base_url).hostname
        if host in _PROVIDER_HOSTS:
            raise GatewayError(
                f"l'URL du gateway ({self.base_url}) est un hôte fournisseur — "
                f"le gateway doit être un endpoint neutre unique")


@dataclass(frozen=True)
class BrickWiring:
    """Câblage effectif d'une brique — ne contient JAMAIS d'URL/clé fournisseur."""
    brick_id: str
    role: str
    env: dict[str, str] = field(default_factory=dict)


def wire_brick(brick_id: str, role: str, model_id: str, gateway: GatewayConfig) -> BrickWiring:
    """Câble une brique vers le gateway. Le modèle vient du rôle ; la clé est celle DU GATEWAY."""
    env = {
        "OPENAI_API_BASE": gateway.base_url,
        "OPENAI_BASE_URL": gateway.base_url,  # alias reconnu par les SDK récents
        "OPENAI_API_KEY": f"${{{gateway.key_env}}}",  # référence env, jamais la valeur
        "OPENAI_MODEL": model_id,
    }
    return BrickWiring(brick_id=brick_id, role=role, env=env)


def wire_all(assignments: list[tuple[str, str]], role_mapping: dict[str, str],
             store: RouteStore, gateway: GatewayConfig) -> list[BrickWiring]:
    """Câble chaque (brick_id, rôle). role_mapping: rôle → nom de route (RouteStore)."""
    wirings = []
    for brick_id, role in assignments:
        route_name = role_mapping.get(role)
        if not route_name:
            raise GatewayError(f"rôle '{role}' (brique {brick_id}) sans route associée")
        try:
            route = store.get(route_name)
        except RouteError as exc:
            raise GatewayError(f"route '{route_name}' pour le rôle '{role}' introuvable : {exc}")
        wirings.append(wire_brick(brick_id, role, route.model_id, gateway))
    return wirings


def assert_via_gateway(wirings: list[BrickWiring], gateway: GatewayConfig) -> list[str]:
    """Enforcement de l'invariant. Retourne la liste des violations (vide = conforme)."""
    violations = []
    for w in wirings:
        base = w.env.get("OPENAI_API_BASE") or w.env.get("OPENAI_BASE_URL") or ""
        if base != gateway.base_url:
            violations.append(f"{w.brick_id}: pointe vers '{base}' ≠ gateway unique")
        host = urlparse(base).hostname
        if host in _PROVIDER_HOSTS:
            violations.append(f"{w.brick_id}: pointe vers un hôte fournisseur '{host}'")
        key = w.env.get("OPENAI_API_KEY", "")
        if not key.startswith("${"):
            violations.append(f"{w.brick_id}: OPENAI_API_KEY n'est pas une référence env "
                              f"(clé en clair interdite)")
    return violations


def prove_traversal(wiring: BrickWiring, gateway_key: str,
                    transport: Transport | None = None) -> ProbeResult:
    """PREUVE de branchement : la brique appelle réellement le gateway et obtient une réponse
    non vide (pas une simple présence de config). Utilise le jeton interne du gateway."""
    base = wiring.env["OPENAI_API_BASE"]
    model = wiring.env["OPENAI_MODEL"]
    return probe_route(base, model, gateway_key, transport)


class GatewayStore:
    """Persiste la config gateway (gateway.json) et les câblages de briques (wirings.json).
    Réutilise le RouteStore (même home) pour résoudre rôle → route → modèle."""

    def __init__(self, home: Path) -> None:
        self.home = Path(home)
        self.gateway_path = self.home / "gateway.json"
        self.wirings_path = self.home / "wirings.json"
        self.routes = RouteStore(self.home)

    def set_gateway(self, config: GatewayConfig) -> None:
        self.home.mkdir(parents=True, exist_ok=True)
        self.gateway_path.write_text(json.dumps(asdict(config), ensure_ascii=False, indent=1),
                                     encoding="utf-8")

    def get_gateway(self) -> GatewayConfig:
        if not self.gateway_path.exists():
            raise GatewayError("gateway non configuré (forgeai gateway set-url)")
        return GatewayConfig(**json.loads(self.gateway_path.read_text(encoding="utf-8")))

    def _load_wirings(self) -> list[BrickWiring]:
        if not self.wirings_path.exists():
            return []
        return [BrickWiring(**w) for w in json.loads(self.wirings_path.read_text(encoding="utf-8"))]

    def wire(self, brick_id: str, role: str, route_name: str) -> BrickWiring:
        gateway = self.get_gateway()
        try:
            route = self.routes.get(route_name)
        except RouteError as exc:
            raise GatewayError(f"route '{route_name}' introuvable : {exc}")
        wiring = wire_brick(brick_id, role, route.model_id, gateway)
        wirings = [w for w in self._load_wirings() if w.brick_id != brick_id]
        wirings.append(wiring)
        self.wirings_path.write_text(
            json.dumps([asdict(w) for w in wirings], ensure_ascii=False, indent=1),
            encoding="utf-8")
        return wiring

    def wirings(self) -> list[BrickWiring]:
        return self._load_wirings()

    def verify(self) -> list[str]:
        """Enforcement sur les câblages persistés (invariant DM-6)."""
        return assert_via_gateway(self._load_wirings(), self.get_gateway())
