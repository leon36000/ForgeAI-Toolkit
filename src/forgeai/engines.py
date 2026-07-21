"""Story S4 — compatibilité moteur↔vendor : le « au choix » FILTRÉ par vendor.

Source de vérité unique : `data/moteurs-inference.json` (champ `gpu_vendors` par moteur). Permet
de proposer/valider uniquement les moteurs compatibles avec le vendor GPU du nœud cible (ex.
tensorrt-llm est nvidia-only → jamais sur un nœud AMD). Fonctions pures, sans I/O réseau.
"""
from __future__ import annotations

import json
from importlib.resources import files


def _moteurs() -> list[dict]:
    raw = (files("forgeai.data") / "moteurs-inference.json").read_text(encoding="utf-8")
    return json.loads(raw)["moteurs"]


def engine_vendors(engine_id: str) -> tuple[str, ...]:
    """Vendors GPU supportés par un moteur (tuple vide si moteur inconnu)."""
    for m in _moteurs():
        if m.get("id") == engine_id:
            return tuple(m.get("gpu_vendors", ()))
    return ()


def engine_supports_vendor(engine_id: str, vendor: str) -> bool:
    """Le moteur supporte-t-il ce vendor ? (False si moteur inconnu ou vendor absent)."""
    return vendor in engine_vendors(engine_id)


def compatible_engines(vendor: str) -> list[str]:
    """Liste des moteurs compatibles avec un vendor (la liste de choix FILTRÉE de l'UI)."""
    return [m["id"] for m in _moteurs() if vendor in m.get("gpu_vendors", ())]


def incompatible_selections(selections: list[dict]) -> list[str]:
    """Signale les couples moteur↔vendor incompatibles d'une sélection [{engine, vendor?}, ...].
    Une entrée sans `vendor` (vendor du nœud inconnu) est IGNORÉE — on ne peut pas la valider,
    donc pas de faux rejet. Retourne une liste triée de 'engine@vendor'."""
    bad = []
    for e in selections:
        vendor = e.get("vendor")
        if vendor and not engine_supports_vendor(e.get("engine", ""), vendor):
            bad.append(f"{e.get('engine', '')}@{vendor}")
    return sorted(bad)
