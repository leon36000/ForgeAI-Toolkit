#!/usr/bin/env python3
"""Story P1-S03 (outillage) — convertit l'extraction texte du catalogue maître
unifié (PDF 1021 entrées) en catalogue/catalogue.json + empreinte sha256.

Validation intégrée par comptage contre les invariants connus du document :
1021 entrées uniques, 742 traductions EN en attente, 231 entrées Atlas sans
description enrichie. Tout écart = échec (exit 1) — pas de catalogue silencieusement
faux (§8bis).

Usage : build_catalogue.py <extraction.txt> <sortie.json>
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

EN_PENDING = "[EN — en attente du lot de traduction]"
ATLAS_ONLY_PREFIX = "[Entrée Atlas —"
CATEGORY_RE = re.compile(r"^(.{3,80}) — (\d+) entrées$")
URL_RE = re.compile(r"https?://\S+")


def _blocks(text: str) -> list[list[str]]:
    lines = [ln.rstrip() for ln in text.replace("\f", "\n").splitlines()]
    blocks, current = [], []
    for line in lines:
        if line.strip():
            current.append(line.strip())
        elif current:
            blocks.append(current)
            current = []
    if current:
        blocks.append(current)
    return blocks


def parse_catalogue(text: str) -> list[dict]:
    raw: list[dict] = []
    category = "non classé"
    for block in _blocks(text):
        header = CATEGORY_RE.match(block[0])
        if header:
            category = header.group(1).strip()
            block = block[1:]
            if not block:
                continue
        joined = "\n".join(block)
        if not ("Source:" in joined or "Atlas:" in joined):
            # Bloc de continuation (entrée coupée par un saut de page) : les
            # marqueurs et la fin de description s'appliquent à l'entrée précédente.
            if raw and not raw[-1]["_closed"]:
                _absorb(raw[-1], block)
            continue

        entry = {
            "name": block[0], "category": category, "atlas_status": "",
            "source_url": None, "desc_lines": [], "en_pending": False,
            "atlas_only": False, "_closed": False,
        }
        _absorb(entry, block[1:])
        raw.append(entry)

    return [_finalize(e) for e in raw]


def _absorb(entry: dict, lines: list[str]) -> None:
    for line in lines:
        if line.startswith("Source:"):
            m = URL_RE.search(line)
            entry["source_url"] = m.group(0) if m else entry["source_url"]
        elif line.startswith("Atlas:"):
            entry["atlas_status"] = line.removeprefix("Atlas:").split("·")[0].strip()
            m = URL_RE.search(line)
            if m:
                entry["source_url"] = m.group(0)
        elif line.startswith(EN_PENDING[:20]):
            entry["en_pending"] = True
            entry["_closed"] = True  # le marqueur EN clôt toujours une entrée
        elif line.startswith(ATLAS_ONLY_PREFIX):
            entry["atlas_only"] = True
            entry["_closed"] = "cette passe).]" in line
        elif entry["atlas_only"] and not entry["_closed"]:
            entry["_closed"] = "cette passe).]" in line  # suite du pavé Atlas
        else:
            entry["desc_lines"].append(line)


def _finalize(entry: dict) -> dict:
    desc_lines = entry.pop("desc_lines")
    closed = entry.pop("_closed")  # noqa: F841 — état interne de parsing
    description_fr, description_en = "", None
    if entry["atlas_only"]:
        description_fr = (f"Entrée Atlas ({entry['atlas_status'] or 'statut inconnu'}) "
                          "— description à enrichir depuis le tableau source.")
    elif entry["en_pending"]:
        description_fr = " ".join(desc_lines)
    elif len(desc_lines) >= 2:
        description_fr = " ".join(desc_lines[:-1])
        description_en = desc_lines[-1]
    elif desc_lines:
        description_fr = desc_lines[0]
    entry["description_fr"] = description_fr
    entry["description_en"] = description_en
    entry["id"] = re.sub(r"[^a-z0-9]+", "-", entry["name"].lower()).strip("-")
    return entry


def main() -> None:
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    entries = parse_catalogue(src.read_text(encoding="utf-8"))
    total = len(entries)
    pending = sum(1 for e in entries if e["en_pending"])
    atlas_only = sum(1 for e in entries if e["atlas_only"])
    print(f"entrées: {total} | EN en attente: {pending} | Atlas seul: {atlas_only}")
    problems = []
    if total != 1021:
        problems.append(f"total {total} ≠ 1021")
    if pending != 742:
        problems.append(f"EN en attente {pending} ≠ 742")
    if atlas_only != 231:
        problems.append(f"Atlas seul {atlas_only} ≠ 231")
    if problems:
        print("ECHEC validation invariants:", "; ".join(problems))
        sys.exit(1)
    payload = json.dumps({"version": "2026-07-13", "entries": entries},
                         ensure_ascii=False, sort_keys=True, indent=1)
    dst.write_text(payload, encoding="utf-8")
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    dst.with_suffix(".sha256").write_text(digest + "\n", encoding="utf-8")
    print(f"OK {dst} sha256={digest}")


if __name__ == "__main__":
    main()
