#!/usr/bin/env python3
"""R-ALL (directive périmètre §2) — recherche vérifiée sur l'intégralité du catalogue.

Chaque entrée passe par un DOSSIER de recherche sourcé. Règle de rigueur transversale
codée en dur : aucune affirmation sans source vérifiable — un dossier sans `source_url`
non vide est REJETÉ, exactement comme un stub. Aucune classification par nom/supposition.

Format d'un lot de dossiers (YAML, sous-ensemble parseur maison) :
    lot: rall-XX
    dossiers:
      - nom: "<nom exact au catalogue>"
        source_url: "https://github.com/org/repo"     # OBLIGATOIRE, testée
        flag: "PUBLIC-INSTALLABLE" | "INTROUVABLE-APRES-RECHERCHE"
        license: "MIT"                                  # requis si PUBLIC-INSTALLABLE
        maintenance: "active" | "archived" | "inconnu"
        description_fr: "…"                             # requis si PUBLIC-INSTALLABLE
        description_en: "…"
        install: "docker: org/img:tag | pip: pkg==x"    # méthode officielle épinglable
        role: "…"                                       # rôle + points de branchement
        disambiguation: "…"                            # si collision de nom (optionnel)
        verify_method: "web:github"

Sous-commandes :
    rall.py next N              → N prochaines entrées sans dossier vérifié
    rall.py apply <lot> [...]   → applique, valide (source obligatoire), régénère sha256
    rall.py stats              → avancement
    rall.py collisions         → noms partagés sans qualificatif (gate B-26)
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CATALOGUE = REPO / "src" / "forgeai" / "data" / "catalogue.json"
VALID_FLAGS = {"PUBLIC-INSTALLABLE", "INTROUVABLE-APRES-RECHERCHE"}

# Parseur du sous-ensemble YAML des lots (blocs "- nom:" … champs indentés).
_ENTRY_RE = re.compile(r"- nom:\s*\"((?:[^\"\\]|\\.)*)\"((?:\n[ \t]+\w[\w-]*:.*)*)", re.M)
_FIELD_RE = re.compile(r"\n[ \t]+([\w-]+):\s*\"?((?:[^\"\n]|\\.)*?)\"?(?=\n[ \t]+[\w-]+:|\n*$)")


def parse_lot(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8")
    dossiers = []
    for m in _ENTRY_RE.finditer(text):
        d = {"nom": m.group(1).replace('\\"', '"')}
        for fm in _FIELD_RE.finditer(m.group(2)):
            d[fm.group(1)] = fm.group(2).replace('\\"', '"').strip()
        dossiers.append(d)
    if not dossiers:
        raise SystemExit(f"{path}: aucun dossier reconnu")
    return dossiers


def _load() -> dict:
    return json.loads(CATALOGUE.read_text(encoding="utf-8"))


def _save(data: dict) -> str:
    payload = json.dumps(data, ensure_ascii=False, sort_keys=True, indent=1)
    CATALOGUE.write_text(payload, encoding="utf-8")
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    CATALOGUE.with_suffix(".sha256").write_text(digest + "\n", encoding="utf-8")
    return digest


def _validate(d: dict) -> list[str]:
    errs = []
    if not d.get("source_url", "").startswith(("http://", "https://")):
        errs.append(f"{d['nom']}: source_url absente/invalide (règle : pas de source = stub)")
    flag = d.get("flag")
    if flag not in VALID_FLAGS:
        errs.append(f"{d['nom']}: flag hors {VALID_FLAGS}")
    if flag == "PUBLIC-INSTALLABLE":
        for champ in ("license", "description_fr", "install", "role"):
            if not d.get(champ, "").strip():
                errs.append(f"{d['nom']}: champ '{champ}' requis pour PUBLIC-INSTALLABLE")
    return errs


def cmd_next(n: int) -> None:
    for e in [e for e in _load()["entries"] if not e.get("verified")][:n]:
        marque = "ATLAS" if e.get("atlas_only") else "ok  "
        print(f"[{marque}] {e['name']} | {e.get('category', '')[:40]}")


def cmd_apply(paths: list[Path]) -> None:
    dossiers: dict[str, dict] = {}
    for p in paths:
        for d in parse_lot(p):
            dossiers[d["nom"]] = d
    data = _load()
    by_name = {e["name"]: e for e in data["entries"]}
    errs = []
    for nom, d in dossiers.items():
        if nom not in by_name:
            errs.append(f"{nom}: absent du catalogue")
        errs += _validate(d)
    if errs:
        print("ECHEC R-ALL apply :", *errs, sep="\n  ")
        raise SystemExit(1)
    today = date.today().isoformat()
    for nom, d in dossiers.items():
        e = by_name[nom]
        e["verified"] = True
        e["verified_at"] = today
        e["verify_method"] = d.get("verify_method", "web")
        e["source_url"] = d["source_url"]
        e["flag"] = d["flag"]
        for champ in ("license", "maintenance", "install", "role", "disambiguation"):
            if d.get(champ):
                e[champ] = d[champ]
        if d["flag"] == "PUBLIC-INSTALLABLE":
            e["description_fr"] = d["description_fr"]
            e["en_pending"] = False
            e["atlas_only"] = False
            if d.get("description_en"):
                e["description_en"] = d["description_en"]
    digest = _save(data)
    reste = sum(1 for e in data["entries"] if not e.get("verified"))
    introuv = sum(1 for e in data["entries"] if e.get("flag") == "INTROUVABLE-APRES-RECHERCHE")
    print(f"OK {len(dossiers)} dossiers appliqués | vérifiées manquantes: {reste} "
          f"| introuvables (à retirer sur preuve): {introuv} | sha256: {digest[:16]}…")


def cmd_stats() -> None:
    data = _load()
    total = len(data["entries"])
    verif = sum(1 for e in data["entries"] if e.get("verified"))
    print(f"catalogue: {total} | vérifiées R-ALL: {verif} | restantes: {total - verif}")


def cmd_collisions() -> None:
    data = _load()
    base: dict[str, list[str]] = {}
    for e in data["entries"]:
        key = re.split(r"[ /(]", e["name"])[0].lower()
        base.setdefault(key, []).append(e["name"])
    dup = {k: v for k, v in base.items() if len(v) > 1
           and not all(e_has_disambig(data, n) for n in v)}
    for k, v in sorted(dup.items()):
        print(f"COLLISION '{k}': {v}")
    sys.exit(1 if dup else 0)


def e_has_disambig(data: dict, name: str) -> bool:
    for e in data["entries"]:
        if e["name"] == name:
            return bool(e.get("disambiguation"))
    return False


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    cmd = sys.argv[1]
    if cmd == "next":
        cmd_next(int(sys.argv[2]))
    elif cmd == "apply":
        cmd_apply([Path(p) for p in sys.argv[2:]])
    elif cmd == "stats":
        cmd_stats()
    elif cmd == "collisions":
        cmd_collisions()
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
