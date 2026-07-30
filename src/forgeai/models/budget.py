"""Gestion de l'économie de tokens : budget alloué par agent."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Tuple

from forgeai.models._locking import file_lock, atomic_write_text


class BudgetError(Exception):
    """Erreur liée à la gestion d'un budget de tokens."""
    pass


class QuotaAtteint(BudgetError):
    """Levée par ``BudgetTracker.check`` quand un agent est en état ``COUPURE``.

    Hérite de ``BudgetError`` (compatibilité avec les handlers existants)
    tout en restant capturable distinctement. Sert de signal dédié aux
    points de mesure en pré-dispatch : l'appel réseau en cours, s'il y
    en a un, finit normalement ; seuls les appels suivants sont bloqués
    tant que le budget n'est pas ré-alimenté via ``set_budget``.
    """
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


def extraire_tokens(reponse: dict) -> Tuple[int, bool]:
    """Extrait le nombre de tokens consommés d'une réponse LLM, sans lever.

    Formats reconnus (premier match gagne) :

    * OpenAI : ``reponse["usage"]["total_tokens"]`` est un entier
      (à l'exclusion de ``bool``). Retourne ``(total_tokens, True)``.
      Le champ est utilisé tel quel — jamais la somme
      ``prompt_tokens + completion_tokens``, qui manquerait les
      tokens de reasoning.
    * Ollama : ``reponse["prompt_eval_count"]`` et
      ``reponse["eval_count"]`` (à la racine du dict) sont tous deux
      des entiers (à l'exclusion de ``bool``). Retourne
      ``(prompt_eval_count + eval_count, True)``.

    Toute autre forme — ``usage`` présent mais ``total_tokens`` absent
    ou non entier, champs Ollama partiels, ``usage`` de type
    incorrect, dictionnaire vide, entrée non-dict — produit
    ``(0, False)``. **Aucune estimation n'est faite.**

    Cette fonction ne lève jamais : une réponse mal formée ne doit pas
    casser un appel réseau réussi.

    Args:
        reponse: Dictionnaire représentant la réponse brute d'un
            fournisseur LLM.

    Returns:
        Couple ``(tokens_extraits, succes)``. ``succes`` vaut ``True``
        si et seulement si un format complet et bien typé a été reconnu.
    """
    if not isinstance(reponse, dict):
        return (0, False)

    if "usage" in reponse:
        usage = reponse["usage"]
        if isinstance(usage, dict):
            total = usage.get("total_tokens")
            if isinstance(total, int) and not isinstance(total, bool):
                return (total, True)
        return (0, False)

    prompt_count = reponse.get("prompt_eval_count")
    eval_count = reponse.get("eval_count")
    if (
        isinstance(prompt_count, int)
        and not isinstance(prompt_count, bool)
        and isinstance(eval_count, int)
        and not isinstance(eval_count, bool)
    ):
        return (prompt_count + eval_count, True)

    return (0, False)


class BudgetTracker:
    """Persistance et suivi des budgets de tokens par agent.

    Les données sont stockées dans ``<home>/budgets.json`` sous la forme
    ``{agent: {"quota_tokens": int, "used_tokens": int, "alert_ratio": float}}``.

    La persistance est protégée par un verrou fichier dédié
    (``<home>/budgets.lock``) : chaque opération publique acquiert le
    verrou, **relit** l'état depuis le disque, le modifie, puis écrit
    via ``atomic_write_text`` (création d'un temporaire + ``fsync`` +
    ``os.replace``). Le fichier est l'unique source de vérité : aucun
    cache mémoire n'est conservé entre opérations, ce qui rend deux
    instances concurrentes sûres vis-à-vis des écritures perdues.
    """

    _FILENAME = "budgets.json"

    def __init__(
        self,
        home: Path,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._home = Path(home)
        self._home.mkdir(parents=True, exist_ok=True)
        self._path = self._home / self._FILENAME
        # ``file_lock`` crée un fichier ``<arg>.lock`` ; on passe donc
        # ``<home>/budgets`` pour obtenir le fichier dédié
        # ``<home>/budgets.lock`` (sibling de ``budgets.json``).
        self._lock_path = self._home / "budgets"
        # B-20b : journal des anomalies de mesure (usage absent / timeout).
        # Fichier frère append-only, NON autoritaire (le compteur reste dans
        # budgets.json). Horloge injectable pour un ``ts`` déterministe en test.
        self._journal_path = self._home / "meter-events.jsonl"
        self._clock: Callable[[], datetime] = clock or (
            lambda: datetime.now(timezone.utc)
        )

    def _load(self) -> Dict[str, Dict[str, Any]]:
        if not self._path.exists():
            return {}
        with self._path.open("r", encoding="utf-8") as fh:
            try:
                data = json.load(fh)
            except json.JSONDecodeError:
                raise BudgetError(f"budgets.json corrompu : {self._path}")
        if not isinstance(data, dict):
            raise BudgetError(f"budgets.json corrompu (structure inattendue) : {self._path}")
        return data

    def _save(self, data: Dict[str, Dict[str, Any]]) -> None:
        atomic_write_text(
            self._path,
            json.dumps(data, indent=2, ensure_ascii=False),
        )

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

        with file_lock(self._lock_path):
            data = self._load()
            data[agent] = {
                "quota_tokens": int(quota_tokens),
                "used_tokens": 0,
                "alert_ratio": float(alert_ratio),
            }
            self._save(data)

    def record(
        self,
        agent: str,
        tokens: int,
        *,
        exact: bool = True,
        motif: str | None = None,
    ) -> str:
        """Enregistre une consommation de tokens pour un agent.

        Cas normal (``exact=True``) : incrémente ``used_tokens`` de ``tokens``.
        Cas anomalie (``exact=False``) : ``tokens`` DOIT valoir 0 (aucune
        estimation inventée, ADR §3) ; le compteur n'est pas modifié et une
        ligne est ajoutée au journal ``meter-events.jsonl`` avec le ``motif``.

        Args:
            agent: Identifiant de l'agent.
            tokens: Nombre de tokens consommés (>= 0).
            exact: False si ``usage`` était absent/illisible ou timeout.
            motif: Obligatoire ssi ``exact`` est False (ex. "usage_absent",
                "timeout") ; doit être None si ``exact`` est True.

        Returns:
            L'état résultant du budget : 'OK', 'ALERTE' ou 'COUPURE'.

        Raises:
            ValueError: Contrat ``exact``/``motif``/``tokens`` violé (bug
                d'appelant — distinct de BudgetError, jamais une condition
                budgétaire).
            BudgetError: Si l'agent est inconnu ou si tokens est négatif.
        """
        if exact and motif is not None:
            raise ValueError("motif doit être None quand exact=True")
        if not exact:
            if motif is None:
                raise ValueError("motif est obligatoire quand exact=False")
            if tokens != 0:
                raise ValueError(
                    "exact=False exige tokens=0 (aucune estimation inventée)"
                )
        if tokens < 0:
            raise BudgetError("La consommation de tokens ne peut pas être négative.")

        with file_lock(self._lock_path):
            data = self._load()
            if agent not in data:
                raise BudgetError(f"Agent inconnu : {agent}")
            if exact:
                data[agent]["used_tokens"] += int(tokens)
                self._save(data)
            else:
                ligne = {
                    "ts": self._clock().isoformat(),
                    "agent": agent,
                    "tokens": 0,
                    "exact": False,
                    "motif": motif,
                }
                with self._journal_path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(ligne, ensure_ascii=False) + "\n")
            entry = data[agent]
            state = BudgetState(
                agent=agent,
                quota_tokens=entry["quota_tokens"],
                used_tokens=entry["used_tokens"],
                alert_ratio=entry["alert_ratio"],
            )
            return state.etat

    def status(self, agent: str) -> BudgetState:
        """Retourne l'état courant du budget d'un agent.

        L'état est relu sous verrou pour garantir la fraîcheur de la
        lecture vis-à-vis d'une écriture concurrente.

        Raises:
            BudgetError: Si l'agent est inconnu.
        """
        with file_lock(self._lock_path):
            data = self._load()
            if agent not in data:
                raise BudgetError(f"Agent inconnu : {agent}")
            entry = data[agent]
            return BudgetState(
                agent=agent,
                quota_tokens=entry["quota_tokens"],
                used_tokens=entry["used_tokens"],
                alert_ratio=entry["alert_ratio"],
            )

    def report(self) -> list[BudgetState]:
        """Retourne le rapport de consommation trié par identifiant d'agent.

        L'état complet est relu sous verrou, puis projeté en une liste
        de ``BudgetState`` triée par nom d'agent.
        """
        with file_lock(self._lock_path):
            data = self._load()
            return sorted(
                (
                    BudgetState(
                        agent=agent_name,
                        quota_tokens=entry["quota_tokens"],
                        used_tokens=entry["used_tokens"],
                        alert_ratio=entry["alert_ratio"],
                    )
                    for agent_name, entry in data.items()
                ),
                key=lambda state: state.agent,
            )

    def check(self, agent: str) -> None:
        """Verrou pré-dispatch : refuse l'émission si l'agent est en COUPURE.

        Re-lit l'état sous verrou pour fonder la décision sur la dernière
        version persistée. Si l'état résultant est ``COUPURE``, lève
        ``QuotaAtteint`` avec un message chiffrant l'agent, sa
        consommation et son quota. Sinon (état ``OK`` ou ``ALERTE``),
        retourne ``None`` — l'appel en cours finit normalement et les
        appels suivants ne sont pas bloqués rétroactivement.

        Args:
            agent: Identifiant de l'agent à vérifier.

        Raises:
            QuotaAtteint: Si l'agent a atteint ou dépassé son quota.
            BudgetError: Si l'agent est inconnu.
        """
        with file_lock(self._lock_path):
            data = self._load()
            if agent not in data:
                raise BudgetError(f"Agent inconnu : {agent}")
            entry = data[agent]
            state = BudgetState(
                agent=agent,
                quota_tokens=entry["quota_tokens"],
                used_tokens=entry["used_tokens"],
                alert_ratio=entry["alert_ratio"],
            )
            if state.etat == "COUPURE":
                raise QuotaAtteint(
                    f"COUPURE: agent '{agent}' a dépassé son budget "
                    f"({state.used_tokens}/{state.quota_tokens} tokens)"
                )
