#!/usr/bin/env python3
"""Pipeline F23 — fan-out des traductions EN du catalogue (P2).

Sous-commandes :
    next N                 → liste les N prochaines entrées en attente (« nom | description_fr »)
    apply <lot.yaml> [...] → applique un ou plusieurs lots au catalogue + régénère le sha256
    stats                  → état d'avancement

Le format de lot est le sous-ensemble YAML des livrables Qwen :
    - {nom: "X", en: "…"}  ou  bloc « - nom: "X" / en: "…" ».
Garde-fous §8bis : nom inconnu = échec; entrée déjà traduite = échec (pas d'écrasement
silencieux); traduction vide = échec.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CATALOGUE = REPO / "catalogue" / "catalogue.json"

LOT_INLINE_RE = re.compile(r'nom: "((?:[^"\\]|\\.)*)",\s*en: "((?:[^"\\]|\\.)*)"')
LOT_BLOCK_RE = re.compile(r'- nom: "([^"]+)"\n\s+en: (?:"((?:[^"\\]|\\.)*)"|\'([^\']+)\')')


def parse_lot(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    out: dict[str, str] = {}
    for m in LOT_INLINE_RE.finditer(text):
        out[m.group(1).replace('\\"', '"')] = m.group(2).replace('\\"', '"')
    for m in LOT_BLOCK_RE.finditer(text):
        out[m.group(1)] = (m.group(2) or m.group(3)).replace('\\"', '"')
    if not out:
        raise SystemExit(f"{path}: aucun couple nom/en reconnu")
    return out


def _load() -> dict:
    return json.loads(CATALOGUE.read_text(encoding="utf-8"))


def _save(data: dict) -> str:
    payload = json.dumps(data, ensure_ascii=False, sort_keys=True, indent=1)
    CATALOGUE.write_text(payload, encoding="utf-8")
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    CATALOGUE.with_suffix(".sha256").write_text(digest + "\n", encoding="utf-8")
    return digest


def cmd_next(n: int) -> None:
    for e in [e for e in _load()["entries"] if e["en_pending"]][:n]:
        print(f"{e['name']} | {e['description_fr'].replace('|', '/')[:180]}")


def cmd_apply(paths: list[Path]) -> None:
    translations: dict[str, str] = {}
    for path in paths:
        translations.update(parse_lot(path))
    data = _load()
    by_name = {e["name"]: e for e in data["entries"]}
    errors = []
    for name, en in translations.items():
        entry = by_name.get(name)
        if entry is None:
            errors.append(f"nom inconnu au catalogue : {name}")
        elif not entry["en_pending"]:
            errors.append(f"déjà traduit (refus d'écrasement silencieux) : {name}")
        elif not en.strip():
            errors.append(f"traduction vide : {name}")
    if errors:
        print("ECHEC apply :", *errors, sep="\n  ")
        raise SystemExit(1)
    for name, en in translations.items():
        by_name[name]["description_en"] = en
        by_name[name]["en_pending"] = False
    digest = _save(data)
    rest = sum(1 for e in data["entries"] if e["en_pending"])
    print(f"OK {len(translations)} appliquées | restantes: {rest} | sha256: {digest[:16]}…")


def cmd_stats() -> None:
    data = _load()
    total = len(data["entries"])
    pending = sum(1 for e in data["entries"] if e["en_pending"])
    atlas = sum(1 for e in data["entries"] if e["atlas_only"])
    print(f"total: {total} | EN en attente: {pending} | Atlas à enrichir: {atlas} "
          f"| traduites: {742 - pending}/742")


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in ("next", "apply", "stats"):
        raise SystemExit(__doc__)
    if sys.argv[1] == "next":
        cmd_next(int(sys.argv[2]))
    elif sys.argv[1] == "apply":
        cmd_apply([Path(p) for p in sys.argv[2:]])
    else:
        cmd_stats()


if __name__ == "__main__":
    main()
