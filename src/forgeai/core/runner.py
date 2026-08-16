"""Exécuteur de commandes injectable — en production : subprocess; en test : fixtures.

Stratégie CI de la matrice Grok (archive/phase-a/matrice-tests-grok.md) : le détecteur
consomme un runner injectable; les fixtures sont des captures réelles anonymisées.
"""
from __future__ import annotations

import os
import subprocess
from typing import Protocol


class CommandRunner(Protocol):
    def run(self, argv: list[str]) -> tuple[int, str]:
        """Exécute argv, retourne (code_retour, stdout)."""


class SubprocessRunner:
    """Exécute avec LC_ALL=C : sorties locale-stables (les parseurs restent
    tolérants aux locales pour les fixtures capturées sur machines localisées)."""

    def __init__(self, timeout_s: float = 20.0) -> None:
        self.timeout_s = timeout_s

    def run(self, argv: list[str]) -> tuple[int, str]:
        env = dict(os.environ, LC_ALL="C", LANG="C")
        try:
            proc = subprocess.run(
                argv, capture_output=True, text=True, timeout=self.timeout_s, env=env,
            )
            return proc.returncode, proc.stdout
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return 127, ""


class FixtureRunner:
    """Runner de test : mappe la commande (premier argv) vers une sortie fixe."""

    def __init__(self, outputs: dict[str, str]) -> None:
        self.outputs = outputs
        self.calls: list[list[str]] = []

    def run(self, argv: list[str]) -> tuple[int, str]:
        self.calls.append(argv)
        key = argv[0]
        if key in self.outputs:
            return 0, self.outputs[key]
        return 127, ""
