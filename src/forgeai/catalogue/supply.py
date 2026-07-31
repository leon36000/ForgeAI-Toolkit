"""Garde de chaîne d'approvisionnement — SUPPLY-018.

Refuse (fail-closed) le déploiement d'une brique non épinglée (image sans digest),
non vérifiée (``verified != True``), ou à licence hors allowlist SPDX.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


class SupplyChainError(Exception):
    """Brique refusée : non épinglée, non vérifiée, ou licence non autorisée."""


@lru_cache(maxsize=None)
def load_catalog_index(path: "Path | None" = None) -> dict[str, dict]:
    """Index ``{brick_id: {'verified': bool, 'license': str}}`` depuis le catalogue BRUT.

    ``load_catalogue`` renvoie des ``Brick`` sans les champs ``verified``/``license`` : la garde
    lit donc directement le JSON du catalogue (où ces champs existent) via ``resources.catalogue_path``.
    """
    if path is None:
        from forgeai.resources import catalogue_path  # import local : évite tout cycle
        path = catalogue_path()
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return {
        entry["id"]: {
            "verified": bool(entry.get("verified", False)),
            "license": entry.get("license", ""),
        }
        for entry in raw.get("entries", [])
        if entry.get("id")
    }


_LICENSE_ALLOWLIST = frozenset(
    {
        "MIT",
        "Apache-2.0",
        "BSD-2-Clause",
        "BSD-3-Clause",
        "ISC",
        "MPL-2.0",
        "GPL-2.0",
        "GPL-3.0",
        "LGPL-2.1",
        "LGPL-3.0",
        "AGPL-3.0",
    }
)


@dataclass(frozen=True)
class SupplyPolicy:
    """Politique de vérification pour une brique avant exécution.
    Fail-closed : toute vérification qui échoue lève ``SupplyChainError``."""

    license_allowlist: frozenset[str] = _LICENSE_ALLOWLIST
    require_digest: bool = True
    require_verified: bool = True


DEFAULT_POLICY = SupplyPolicy()


def verify_brick_before_exec(
    brick_id: str,
    image: str,
    catalog_index: dict[str, dict],
    policy: SupplyPolicy = DEFAULT_POLICY,
) -> None:
    """Lève ``SupplyChainError`` si la brique n'est pas déployable. Fail-closed.

    - **Épinglage UNIVERSEL** (``require_digest``) : TOUTE brique — plugin communautaire OU brique
      first-party du châssis — DOIT être épinglée par digest (``@sha256:``) ; un tag flottant → refus.
    - **Vérification + licence** : appliquées UNIQUEMENT aux plugins communautaires, c.-à-d. les briques
      présentes dans ``catalog_index``. Une brique first-party/châssis (absente du catalogue communautaire,
      ex. postgres, reranker) est de confiance dès lors qu'elle est épinglée — son intégrité vient de la
      revue du dépôt, pas du catalogue communautaire. Une brique CATALOGUÉE doit avoir ``verified`` vrai ;
      côté licence, seule une licence EXPLICITE hors ``license_allowlist`` est refusée — ``NOASSERTION``/vide
      (non assertée, fréquent sur les briques curées) est TOLÉRÉE, son risque étant couvert par ``verified``.
    """
    # 1. Épinglage : contrôle universel, y compris le châssis.
    if policy.require_digest and "@sha256:" not in image:
        raise SupplyChainError(
            f"Image de la brique '{brick_id}' n'est pas épinglée par digest (@sha256:)"
        )

    # 2. Vérification/licence : seulement pour les plugins communautaires (catalogués).
    entry = catalog_index.get(brick_id)
    if entry is None:
        return  # brique first-party/châssis : l'épinglage suffit

    if policy.require_verified and not entry.get("verified", False):
        raise SupplyChainError(f"Brique '{brick_id}' non vérifiée dans le catalogue")

    # Licence : rejette une licence EXPLICITE non autorisée (propriétaire, BUSL, CC, copyleft
    # hors liste…). « NOASSERTION » / vide = licence NON ASSERTÉE dans le catalogue communautaire
    # (fréquent sur les briques curées first-party, ex. litellm) : son risque est couvert par
    # l'exigence ``verified`` ci-dessus, on ne rejette donc pas sur ce seul motif.
    lic = entry.get("license", "")
    if lic and lic != "NOASSERTION" and lic not in policy.license_allowlist:
        raise SupplyChainError(
            f"Licence '{lic}' de la brique '{brick_id}' non autorisée"
        )
