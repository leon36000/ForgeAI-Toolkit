#!/usr/bin/env python3
"""Gate de cohérence registre ↔ code pour les exit codes CLI ForgeAI.

Ce module détecte la dérive entre le registre documentaire
``Docs/exit-codes.json`` et le code réel ``src/forgeai/cli.py``.
Il vérifie que chaque entrée du registre pointe vers une ligne contenant
bien ``return <code>`` attendu. Il ne s'agit PAS d'un inventaire
automatique des ``return`` présents dans le code : le registre reste la
source de vérité documentaire et le gate échoue si le code ne reflète
plus ce qui est documenté.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


def charger_registre(chemin: Path) -> dict:
    """Charge le registre JSON des exit codes.

    Lève FileNotFoundError si le fichier est absent et propage
    ValueError / json.JSONDecodeError si le contenu est invalide.
    Aucune valeur par défaut silencieuse n'est retournée.
    """
    if not chemin.is_file():
        raise FileNotFoundError(f"registre introuvable : {chemin!r}")
    texte = chemin.read_text(encoding="utf-8")
    contenu = json.loads(texte)
    return contenu


def anomalies(registre: dict, lignes_cli: list[str]) -> list[str]:
    """Retourne les anomalies entre registre et code.

    Pour chaque entrée de ``codes_par_commande``, vérifie que la ligne
    indiquée (1-indexée) contient la sous-chaîne littérale
    ``return <code>`` avec frontière de mot. Une anomalie est émise si
    l'index est hors bornes ou si la sous-chaîne est absente.
    """
    resultat: list[str] = []
    if not isinstance(registre, dict):
        return [f"registre invalide : n'est pas un objet {registre!r}"]
    codes_par_commande = registre.get("codes_par_commande", {})
    if not isinstance(codes_par_commande, dict):
        return ["registre invalide : codes_par_commande absent ou n'est pas un objet"]
    for commande, entrees in codes_par_commande.items():
        if not isinstance(entrees, list):
            continue
        for entree in entrees:
            if not isinstance(entree, dict):
                continue
            code = entree.get("code")
            ligne = entree.get("ligne")
            try:
                code_int = int(code)  # type: ignore[arg-type]
                ligne_int = int(ligne)  # type: ignore[arg-type]
            except Exception:
                resultat.append(f"{commande} : entrée invalide {entree!r}")
                continue
            if ligne_int < 1 or ligne_int > len(lignes_cli):
                resultat.append(
                    f"{commande} : ligne {ligne_int} hors bornes du fichier "
                    f"({len(lignes_cli)} lignes au total)"
                )
            else:
                contenu_reel = lignes_cli[ligne_int - 1]
                pattern = rf"(?<!\d)return\s+{code_int}(?!\d)"
                if not re.search(pattern, contenu_reel):
                    resultat.append(
                        f"{commande} : ligne {ligne_int} attendue avec "
                        f"'return {code_int}' mais contient "
                        f"'{contenu_reel.strip()}'"
                    )
    return resultat


def main(argv: list[str] | None = None) -> int:
    """Exécute le gate des exit codes."""
    parser = argparse.ArgumentParser(
        description="Vérifie la cohérence entre Docs/exit-codes.json et src/forgeai/cli.py."
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="affiche le nombre d'entrées vérifiées sans échouer",
    )
    arguments = parser.parse_args(argv)

    racine = Path(__file__).resolve().parents[1]
    chemin_registre = racine / "Docs" / "exit-codes.json"
    chemin_cli = racine / "src" / "forgeai" / "cli.py"

    try:
        registre = charger_registre(chemin_registre)
        lignes_cli = chemin_cli.read_text(encoding="utf-8").splitlines()
    except (OSError, ValueError, json.JSONDecodeError) as erreur:
        print(str(erreur), file=sys.stderr)
        return 1

    if not isinstance(registre, dict):
        print(f"registre invalide : n'est pas un objet {registre!r}", file=sys.stderr)
        return 1
    codes_par_commande_brut = registre.get("codes_par_commande", {})
    if not isinstance(codes_par_commande_brut, dict):
        print("registre invalide : codes_par_commande absent ou n'est pas un objet", file=sys.stderr)
        return 1

    rapport = anomalies(registre, lignes_cli)

    codes_par_commande = registre.get("codes_par_commande", {})
    if isinstance(codes_par_commande, dict):
        n = sum(
            len(v) for v in codes_par_commande.values() if isinstance(v, list)
        )
    else:
        n = 0

    if arguments.report:
        print(f"{n} entrées vérifiées dans Docs/exit-codes.json")
        return 0

    if rapport:
        for message in rapport:
            print(message, file=sys.stderr)
        return 1

    print(f"OK : {n} entrées vérifiées, aucune dérive détectée")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
