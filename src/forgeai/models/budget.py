"""Gestion de l'économie de tokens : budget alloué par agent."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict


class BudgetError(Exception):
    """Erreur liée à la gestion d'un budget de tokens."""
    pass


@dataclass(frozen=True)
class BudgetState:
    """État courant du budget d'un agent.

    Attributes:
        agent: Identifiant de l'agent.
        quota_tokens: Nombre de tokens alloués pour la période.
        used_tokens: Nombre de tokens déjà consommés.
        alert_ratio: Seuil (entre 0 et 1) déclenchant une alerte.
    """

    agent: str
    quota_tokens: int
    used_tokens: int
    alert_ratio: float

    @property
    def ratio(self) -> float:
        """Ratio de consommation (used / quota), ou 0.0 si le quota est nul."""
        if self.quota_tokens == 0:
            return 0.0
        return self.used_tokens / self.quota_tokens

    @property
    def etat(self) -> str:
        """État du budget : 'OK', 'ALERTE' ou 'COUPURE'."""
        if self.used_tokens >= self.quota_tokens:
            return "COUPURE"
        if self.ratio >= self.alert_ratio:
            return "ALERTE"
        return "OK"


class BudgetTracker:
    """Persistance et suivi des budgets de tokens par agent.

    Les données sont stockées dans ``<home>/budgets.json`` sous la forme
    ``{agent: {"quota_tokens": int, "used_tokens": int, "alert_ratio": float}}``.
    """

    _FILENAME = "budgets.json"

    def __init__(self, home: Path) -> None:
        self._home = Path(home)
        self._home.mkdir(parents=True, exist_ok=True)
        self._path = self._home / self._FILENAME
        self._data: Dict[str, Dict[str, Any]] = self._load()

    def _load(self) -> Dict[str, Dict[str, Any]]:
        if not self._path.exists():
            return {}
        with self._path.open("r", encoding="utf-8") as fh:
            try:
                data = json.load(fh)
            except json.JSONDecodeError:
                raise BudgetError("budgets.json corrompu")
        if not isinstance(data, dict):
            raise BudgetError("Fichier de budgets corrompu.")
        return data

    def _save(self) -> None:
        with self._path.open("w", encoding="utf-8") as fh:
            json.dump(self._data, fh, indent=2, ensure_ascii=False)

    def set_budget(self, agent: str, quota_tokens: int, alert_ratio: float = 0.8) -> None:
        """Crée ou réinitialise le budget d'un agent.

        Args:
            agent: Identifiant de l'agent.
            quota_tokens: Quota de tokens alloué (doit être >= 0).
            alert_ratio: Seuil d'alerte (strictement entre 0 et 1 inclus).

        Raises:
            BudgetError: Si les paramètres sont invalides.
        """
        if quota_tokens < 0:
            raise BudgetError("Le quota de tokens doit être positif ou nul.")
        if not (0 < alert_ratio <= 1):
            raise BudgetError("alert_ratio doit être dans l'intervalle ]0, 1]")

        self._data[agent] = {
            "quota_tokens": int(quota_tokens),
            "used_tokens": 0,
            "alert_ratio": float(alert_ratio),
        }
        self._save()

    def record(self, agent: str, tokens: int) -> str:
        """Enregistre une consommation de tokens pour un agent.

        Args:
            agent: Identifiant de l'agent.
            tokens: Nombre de tokens consommés (doit être >= 0).

        Returns:
            L'état résultant du budget : 'OK', 'ALERTE' ou 'COUPURE'.

        Raises:
            BudgetError: Si l'agent est inconnu ou si tokens est négatif.
        """
        if agent not in self._data:
            raise BudgetError(f"Agent inconnu : {agent}")
        if tokens < 0:
            raise BudgetError("La consommation de tokens ne peut pas être négative.")

        self._data[agent]["used_tokens"] += int(tokens)
        self._save()
        return self.status(agent).etat

    def status(self, agent: str) -> BudgetState:
        """Retourne l'état courant du budget d'un agent.

        Raises:
            BudgetError: Si l'agent est inconnu.
        """
        if agent not in self._data:
            raise BudgetError(f"Agent inconnu : {agent}")

        entry = self._data[agent]
        return BudgetState(
            agent=agent,
            quota_tokens=entry["quota_tokens"],
            used_tokens=entry["used_tokens"],
            alert_ratio=entry["alert_ratio"],
        )

    def report(self) -> list[BudgetState]:
        """Retourne le rapport de consommation trié par identifiant d'agent."""
        return sorted(
            (self.status(agent) for agent in self._data),
            key=lambda state: state.agent,
        )
