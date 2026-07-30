#!/usr/bin/env python3
"""Garde CI B-20b §7.4 — la porte coopérative du metering.

Le metering (budget/quota par agent) ne bloque que les émissions passant par un
site INSTRUMENTÉ. Un nouvel appel de génération émis en direct (urllib/requests
vers un endpoint ``chat/completions``) contournerait le verrou et rendrait la
coupure inopérante. Cette garde interdit qu'un fichier ``.py`` du produit, hors
des deux sites mesurés (ADR B-20 §1 : chemin RAG ``hardened.py`` et chemin probe
``probe.py`` via ``MeteredTransport``), référence l'endpoint de génération.

Ce n'est PAS une preuve de sécurité (le contournement reste possible en
construisant l'URL autrement) : c'est un filet coopératif qui rend visible et
délibéré tout NOUVEAU site d'émission, exactement comme l'ADR §7.4 le prescrit.
Ajouter un site légitime = mettre à jour ``ALLOWLIST`` ci-dessous, ce qui force
la justification en revue.
"""
from __future__ import annotations

import pathlib
import sys

RACINE = pathlib.Path(__file__).resolve().parent.parent
SRC = RACINE / "src" / "forgeai"
MARQUEUR = "chat/completions"
# Sites instrumentés (ADR B-20 §1). Tout autre .py référençant l'endpoint est refusé.
ALLOWLIST = frozenset({
    SRC / "rag" / "hardened.py",
    SRC / "models" / "probe.py",
})


def sites_non_autorises(
    src: pathlib.Path = SRC,
    allowlist: frozenset[pathlib.Path] = ALLOWLIST,
) -> list[pathlib.Path]:
    """Retourne les .py de ``src`` (hors allowlist) qui référencent l'endpoint."""
    coupables = []
    for fichier in sorted(src.rglob("*.py")):
        if fichier in allowlist:
            continue
        if MARQUEUR in fichier.read_text(encoding="utf-8"):
            coupables.append(fichier)
    return coupables


def main() -> int:
    coupables = sites_non_autorises()
    if coupables:
        print(
            "GARDE METERING (B-20b §7.4) : emission "
            f"'{MARQUEUR}' hors site mesure :",
            file=sys.stderr,
        )
        for c in coupables:
            print(f"  {c.relative_to(RACINE)}", file=sys.stderr)
        print(
            "  -> router via HardenedRagClient (metered) ou MeteredTransport, "
            "OU ajouter le site a ALLOWLIST avec justification (ADR B-20 §7.4).",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
