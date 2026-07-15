"""Stratégie modèle : Cerveau unique / Équipe / Hybride (exigence DM-5b, story B-10).

Le choix de stratégie DÉTERMINE le nombre de slots de la phase Modèles (un slot = un rôle
à pourvoir par une route/un modèle). La stratégie est écrite au canon du projet. Tout
changement ultérieur produit un DIFF de reconfiguration explicite (slots ajoutés/retirés) —
jamais appliqué silencieusement (le CLI exige --confirm).
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

# Rôles de slots par défaut pour chaque stratégie. « Équipe » reflète une répartition
# multi-modèles (orchestration + spécialistes) ; « Hybride » mêle principal et spécialistes.
_DEFAULT_SLOTS: dict[str, tuple[str, ...]] = {
    "cerveau-unique": ("generaliste",),
    "equipe": ("orchestrateur", "code", "raisonnement", "embeddings"),
    "hybride": ("principal", "specialiste-local", "specialiste-cloud"),
}
STRATEGIES = tuple(_DEFAULT_SLOTS)


class StrategyError(Exception):
    pass


@dataclass(frozen=True)
class StrategySpec:
    strategy: str
    slots: tuple[str, ...]

    @property
    def slot_count(self) -> int:
        return len(self.slots)


def resolve_spec(strategy: str, custom_roles: list[str] | None = None) -> StrategySpec:
    if strategy not in _DEFAULT_SLOTS:
        raise StrategyError(f"stratégie inconnue '{strategy}' (choix : {', '.join(STRATEGIES)})")
    if custom_roles:
        slots = tuple(dict.fromkeys(r.strip() for r in custom_roles if r.strip()))
        if not slots:
            raise StrategyError("liste de rôles vide")
        if strategy == "cerveau-unique" and len(slots) != 1:
            raise StrategyError("cerveau-unique n'admet qu'un seul slot")
    else:
        slots = _DEFAULT_SLOTS[strategy]
    return StrategySpec(strategy=strategy, slots=slots)


@dataclass(frozen=True)
class ReconfigDiff:
    added: tuple[str, ...] = ()
    removed: tuple[str, ...] = ()
    kept: tuple[str, ...] = ()

    @property
    def is_change(self) -> bool:
        return bool(self.added or self.removed)

    def render(self) -> str:
        lines = []
        for s in self.added:
            lines.append(f"  + slot ajouté   : {s}")
        for s in self.removed:
            lines.append(f"  - slot retiré   : {s} (route associée à retirer)")
        for s in self.kept:
            lines.append(f"    slot conservé : {s}")
        return "\n".join(lines)


def diff_specs(old: StrategySpec, new: StrategySpec) -> ReconfigDiff:
    old_set, new_set = set(old.slots), set(new.slots)
    return ReconfigDiff(
        added=tuple(s for s in new.slots if s not in old_set),
        removed=tuple(s for s in old.slots if s not in new_set),
        kept=tuple(s for s in new.slots if s in old_set),
    )


class StrategyStore:
    """Persiste la stratégie au canon du projet (strategy.json)."""

    def __init__(self, home: Path) -> None:
        self.home = Path(home)
        self.path = self.home / "strategy.json"

    def get(self) -> StrategySpec | None:
        if not self.path.exists():
            return None
        d = json.loads(self.path.read_text(encoding="utf-8"))
        return StrategySpec(strategy=d["strategy"], slots=tuple(d["slots"]))

    def save(self, spec: StrategySpec) -> None:
        self.home.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(asdict(spec) | {"slots": list(spec.slots)},
                                        ensure_ascii=False, indent=1), encoding="utf-8")

    def plan_change(self, new: StrategySpec) -> ReconfigDiff:
        """Diff entre la stratégie courante et la nouvelle (sans écrire). Aucune courante
        = tous les slots sont des ajouts (première configuration)."""
        current = self.get()
        if current is None:
            return ReconfigDiff(added=new.slots)
        return diff_specs(current, new)
