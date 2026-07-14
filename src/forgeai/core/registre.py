#!/usr/bin/env python3
"""Registre append-only hash-chaîné (JSONL) — module canonique du Toolkit.

Chaque entrée : {seq, ts, type, actor, payload, prev_hash, hash} où
hash = sha256 du JSON canonique (clés triées) de l'entrée sans son champ "hash",
et prev_hash = hash de l'entrée précédente (64 zéros pour la genèse).

Usage :
    registre.py append <fichier.jsonl> --type <t> --actor <a> [--payload-json '<json>']
    registre.py verify <fichier.jsonl> [...]
"""
import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

GENESIS = "0" * 64


def _entry_hash(entry: dict) -> str:
    material = {k: v for k, v in entry.items() if k != "hash"}
    blob = json.dumps(material, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _read_entries(path: Path) -> list[dict]:
    if not path.exists():
        return []
    entries = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"{path}:{lineno}: JSON invalide — {exc}")
    return entries


def append(path: Path, type_: str, actor: str, payload: dict) -> dict:
    entries = _read_entries(path)
    prev_hash = entries[-1]["hash"] if entries else GENESIS
    entry = {
        "seq": len(entries) + 1,
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "type": type_,
        "actor": actor,
        "payload": payload,
        "prev_hash": prev_hash,
    }
    entry["hash"] = _entry_hash(entry)
    line = json.dumps(entry, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    path.parent.mkdir(parents=True, exist_ok=True)  # ex. ~/.forgeai/Registres/ (P3)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    return entry


def verify(path: Path) -> str | None:
    """Retourne None si la chaîne est intègre, sinon la description de la rupture."""
    prev_hash = GENESIS
    for entry in _read_entries(path):
        seq = entry.get("seq")
        if entry.get("prev_hash") != prev_hash:
            return f"seq {seq}: prev_hash ne chaîne pas avec l'entrée précédente"
        if _entry_hash(entry) != entry.get("hash"):
            return f"seq {seq}: hash invalide (entrée altérée)"
        prev_hash = entry["hash"]
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_append = sub.add_parser("append", help="ajoute une entrée chaînée")
    p_append.add_argument("registre", type=Path)
    p_append.add_argument("--type", required=True, dest="type_")
    p_append.add_argument("--actor", required=True)
    p_append.add_argument("--payload-json", default="{}")

    p_verify = sub.add_parser("verify", help="vérifie l'intégrité de la chaîne")
    p_verify.add_argument("registres", type=Path, nargs="+")

    args = parser.parse_args()
    if args.cmd == "append":
        entry = append(args.registre, args.type_, args.actor, json.loads(args.payload_json))
        print(json.dumps(entry, ensure_ascii=False))
        return

    failed = False
    for path in args.registres:
        error = verify(path)
        if error:
            print(f"ECHEC {path}: {error}")
            failed = True
        else:
            print(f"OK {path}: {len(_read_entries(path))} entrées, chaîne intègre")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
