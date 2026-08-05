#!/usr/bin/env python3
"""Gate CI `reviews-sealed` — ferme la déviation D9 de l'audit de dérive.

Rien n'empêchait structurellement un merge sans revue aveugle scellée passante (les stories
models/ ont été mergées puis trouvées défectueuses). Ce gate rend la revue OBLIGATOIRE et
BLOQUANTE côté CI pour les revues déclarées LIANTES.

Modèle : `reviews/BINDING.txt` liste les dossiers de revue qui DOIVENT actuellement dépouiller
en APPROVE (un par ligne ; # = commentaire). Une story ajoute son dossier quand elle passe ;
une revue superseded (ex. code remédié + re-revu) est retirée du manifeste (les dossiers
historiques/legacy restent au dépôt pour la traçabilité mais ne sont PAS liants).

Le dépouillement réutilise `scripts/revue.py` (fonction pure `tally`, invariant #10 : aucun
LLM n'écrit un score). Le gate échoue (exit 1) si un dossier liant n'est pas APPROVE, est
absent, ou n'a pas ses verdicts.

Usage : reviews_gate.py [--manifest reviews/BINDING.txt] [--reviews-root reviews]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _load_revue():
    spec = importlib.util.spec_from_file_location("revue", REPO / "scripts" / "revue.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def read_manifest(path: Path) -> list[str]:
    if not path.exists():
        return []
    lines = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            lines.append(line)
    return lines


def check(manifest: Path, reviews_root: Path) -> tuple[bool, list[str]]:
    revue = _load_revue()
    report: list[str] = []
    ok = True
    binding = read_manifest(manifest)
    if not binding:
        ok = False
        report.append(
            f"ECHEC : manifeste {manifest} vide ou absent — aucune revue liante vérifiée"
        )
    for entry in binding:
        d = reviews_root / entry if not Path(entry).is_absolute() else Path(entry)
        verdict_files = sorted(d.glob("*.verdict.json"))
        if not verdict_files:
            ok = False
            report.append(f"ECHEC {entry} : aucun verdict scellé (dossier absent/vide)")
            continue
        verdicts = [json.loads(p.read_text(encoding="utf-8")) for p in verdict_files]
        res = revue.tally(verdicts)
        if res.get("result") != "APPROVE":
            ok = False
            report.append(f"ECHEC {entry} : dépouillement = {res.get('result')} "
                          f"({res.get('reason', '')})")
        else:
            report.append(f"OK    {entry} : APPROVE {res.get('reason', '')} "
                          f"vendors {res.get('vendors')}")
    return ok, report


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default=str(REPO / "reviews" / "BINDING.txt"))
    ap.add_argument("--reviews-root", default=str(REPO / "reviews"))
    args = ap.parse_args()
    ok, report = check(Path(args.manifest), Path(args.reviews_root))
    print("REVIEWS-SEALED GATE (déviation D9)")
    for line in report:
        print("  " + line)
    if not ok:
        print("GATE ECHOUÉ : une revue liante n'est pas APPROVE — merge bloqué.")
        sys.exit(1)
    print("GATE OK : toutes les revues liantes sont APPROVE 3/3.")


if __name__ == "__main__":
    main()
