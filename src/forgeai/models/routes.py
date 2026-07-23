"""Registre des routes modèle cloud (exigence DM-5, story B-09).

Provenances connues embarquées (direct fournisseur, OpenRouter, NIM, DeepInfra, autre).
Garanties (testées) :
  - la clé d'API n'est JAMAIS écrite en clair : scellée au coffre, référencée par empreinte ;
  - une route n'est ajoutée qu'après un test de connexion réel GREEN (sinon message clair) ;
  - le registre ne reçoit que l'empreinte (jamais la clé).
routes.json ne contient que des métadonnées + l'empreinte ; les secrets vivent au coffre.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from datetime import date
from pathlib import Path

from forgeai.models._locking import file_lock
from .probe import ProbeResult, Transport, UrllibTransport, probe_route
from .vault import Vault, fingerprint


# Provenances connues → URL de base compatible OpenAI. "direct"/"autre" exigent --base-url.
PROVENANCES: dict[str, str | None] = {
    "openrouter": "https://openrouter.ai/api/v1",
    "deepinfra": "https://api.deepinfra.com/v1/openai",
    "nim": "https://integrate.api.nvidia.com/v1",
    "direct": None,   # fournisseur direct : base_url fournie par l'utilisateur
    "autre": None,    # endpoint compatible OpenAI arbitraire
}


class RouteError(Exception):
    pass


@dataclass(frozen=True)
class CloudRoute:
    name: str
    provenance: str
    base_url: str
    model_id: str
    key_fingerprint: str
    created_at: str
    cache: bool = False
    cache_ttl_s: int | None = None
    cache_prefix: str | None = None

    def public_dict(self) -> dict:
        """Vue sérialisable — NE contient aucun secret (empreinte seulement)."""
        return asdict(self)


class RouteStore:
    """Persiste les routes (routes.json) et scelle les clés au coffre (vault.json)."""

    def __init__(self, home: Path) -> None:
        self.home = Path(home)
        self.routes_path = self.home / "routes.json"
        self.vault = Vault(self.home / "vault.json")

    def _load(self) -> list[dict]:
        if not self.routes_path.exists():
            return []
        return json.loads(self.routes_path.read_text(encoding="utf-8"))

    def _save(self, routes: list[dict]) -> None:
        self.home.mkdir(parents=True, exist_ok=True)
        self.routes_path.write_text(
            json.dumps(routes, ensure_ascii=False, indent=1), encoding="utf-8")

    def _route_from_dict(self, r: dict) -> CloudRoute:
        known = {f.name for f in CloudRoute.__dataclass_fields__.values()}
        return CloudRoute(**{k: v for k, v in r.items() if k in known})

    def resolve_base_url(self, provenance: str, base_url: str | None) -> str:
        if provenance not in PROVENANCES:
            raise RouteError(f"provenance inconnue '{provenance}' "
                             f"(connues : {', '.join(PROVENANCES)})")
        known = PROVENANCES[provenance]
        if known:
            return known
        if not base_url:
            raise RouteError(f"provenance '{provenance}' exige --base-url "
                             f"(endpoint compatible OpenAI)")
        return base_url

    def add_cloud(self, name: str, provenance: str, model_id: str, api_key: str,
                  passphrase: str, *, base_url: str | None = None,
                  transport: Transport | None = None) -> tuple[CloudRoute, ProbeResult]:
        """Ajoute une route APRÈS test réel. En cas d'échec : RouteError, rien n'est écrit."""
        if any(r["name"] == name for r in self._load()):
            raise RouteError(f"route '{name}' existe déjà")
        resolved = self.resolve_base_url(provenance, base_url)
        result = probe_route(resolved, model_id, api_key, transport or UrllibTransport())
        if not result.ok:
            # Aucune route cassée n'est ajoutée ; la clé n'a jamais touché le disque.
            raise RouteError(f"test de connexion {result.light} : {result.detail}")
        fp = self.vault.put(name, api_key, passphrase)  # clé scellée (chiffrée)
        route = CloudRoute(name=name, provenance=provenance, base_url=resolved,
                           model_id=model_id, key_fingerprint=fp,
                           created_at=date.today().isoformat())
        with file_lock(self.routes_path):
            routes = self._load()
            if any(r["name"] == name for r in routes):
                raise RouteError(f"route '{name}' existe déjà")
            routes.append(route.public_dict())
            self._save(routes)
        return route, result

    def list(self) -> list[CloudRoute]:
        return [self._route_from_dict(r) for r in self._load()]

    def get(self, name: str) -> CloudRoute:
        for r in self._load():
            if r["name"] == name:
                return self._route_from_dict(r)
        raise RouteError(f"route '{name}' introuvable")

    def configure_cache(self, name: str, enabled: bool, ttl_s: int | None = None,
                        prefix: str | None = None) -> CloudRoute:
        if ttl_s is not None and ttl_s < 0:
            raise RouteError("ttl_s doit être positif ou nul")
        routes = self._load()
        index = next((i for i, r in enumerate(routes) if r["name"] == name), None)
        if index is None:
            raise RouteError(f"route '{name}' introuvable")
        old_route = self._route_from_dict(routes[index])
        new_route = replace(old_route, cache=enabled, cache_ttl_s=ttl_s,
                            cache_prefix=prefix)
        routes[index] = new_route.public_dict()
        self._save(routes)
        return new_route
