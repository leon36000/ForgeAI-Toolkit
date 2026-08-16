#!/usr/bin/env python3
"""Dépouillement déterministe des revues aveugles (§3.2 du plan maître).

Lit les verdicts scellés d'un répertoire evidence/reviews/<étape>/ (fichiers *.verdict.json,
format {verdict: APPROVE|REJECT, objections: [{severite, description, preuve}], ...})
et applique le seuil : nombre minimal d'APPROVE ET zéro objection critique non résolue.
Un script compte — jamais un LLM.

Usage :
    tally.py <répertoire> --approve-min 7 [--attendus 9]
Sortie : rapport lisible + exit 0 (consensus) / 1 (pas de consensus) / 2 (données invalides).
"""
import argparse
import json
import sys
from pathlib import Path

VERDICTS_VALIDES = {"APPROVE", "REJECT"}
SEVERITES_VALIDES = {"critique", "majeure", "mineure"}


def lire_verdicts(dossier: Path) -> list[dict]:
    verdicts = []
    for fichier in sorted(dossier.glob("*.verdict.json")):
        try:
            data = json.loads(fichier.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"INVALIDE {fichier.name}: JSON illisible — {exc}")
        if data.get("verdict") not in VERDICTS_VALIDES:
            raise SystemExit(f"INVALIDE {fichier.name}: verdict absent ou hors {VERDICTS_VALIDES}")
        for obj in data.get("objections", []):
            if obj.get("severite") not in SEVERITES_VALIDES:
                raise SystemExit(
                    f"INVALIDE {fichier.name}: severite d'objection hors {SEVERITES_VALIDES}"
                )
        data["_reviewer"] = fichier.name.removesuffix(".verdict.json")
        verdicts.append(data)
    return verdicts


def depouiller(verdicts: list[dict], approve_min: int) -> tuple[bool, str]:
    approves = [v for v in verdicts if v["verdict"] == "APPROVE"]
    critiques = [
        (v["_reviewer"], obj.get("description", ""))
        for v in verdicts
        for obj in v.get("objections", [])
        if obj.get("severite") == "critique" and not obj.get("resolu", False)
    ]
    lignes = [f"verdicts déposés : {len(verdicts)}",
              f"APPROVE : {len(approves)} ({', '.join(v['_reviewer'] for v in approves) or '—'})",
              f"REJECT : {len(verdicts) - len(approves)}",
              f"objections critiques non résolues : {len(critiques)}"]
    for reviewer, desc in critiques:
        lignes.append(f"  CRITIQUE [{reviewer}] {desc}")
    consensus = len(approves) >= approve_min and not critiques
    lignes.append(f"seuil : ≥{approve_min} APPROVE et 0 critique → "
                  f"{'CONSENSUS' if consensus else 'PAS DE CONSENSUS'}")
    return consensus, "\n".join(lignes)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dossier", type=Path)
    parser.add_argument("--approve-min", type=int, required=True)
    parser.add_argument("--attendus", type=int, default=None,
                        help="nombre de reviewers attendus (avertit si des verdicts manquent)")
    args = parser.parse_args()

    verdicts = lire_verdicts(args.dossier)
    if not verdicts:
        print(f"INVALIDE: aucun fichier *.verdict.json dans {args.dossier}")
        sys.exit(2)
    if args.attendus is not None and len(verdicts) < args.attendus:
        print(f"AVERTISSEMENT: {len(verdicts)}/{args.attendus} verdicts déposés "
              f"(absents journalisés au registre requis)")
    consensus, rapport = depouiller(verdicts, args.approve_min)
    print(rapport)
    sys.exit(0 if consensus else 1)


if __name__ == "__main__":
    main()
