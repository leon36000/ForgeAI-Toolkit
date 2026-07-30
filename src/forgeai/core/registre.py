#!/usr/bin/env python3
"""Registre append-only hash-chaîné (JSONL) — module canonique du Toolkit.

Tier 0 : SHA-256 nu sur le JSON canonique de l'entrée sans son champ ``hash``.
Tier 1 (TRUST-019B) : HMAC-SHA256 à clé locale par entrée, optionnel et
rétro-compatible via le champ ``key_id``.

Chaque entrée : {seq, ts, type, actor, payload, prev_hash, hash[, key_id]} où
hash = sha256 du JSON canonique (clés triées) de l'entrée sans son champ "hash",
ou HMAC-SHA256(clé, JSON canonique) lorsqu'un ``key_id`` est présent,
et prev_hash = hash de l'entrée précédente (64 zéros pour la genèse).

Usage :
    registre.py append <fichier.jsonl> --type <t> --actor <a> [--payload-json '<json>'] [--key <clé.hex>]
    registre.py verify <fichier.jsonl> [...] [--key <clé.hex>]
"""
import argparse
import hashlib
import hmac
import json
import os
import secrets
import sys

try:
    from forgeai.core._portable_lock import LockTimeoutError, locked_exclusive
except ImportError:  # exécution directe par chemin de fichier, sans paquet installé
    import importlib.util as _ilu
    from pathlib import Path as _P

    _spec = _ilu.spec_from_file_location(
        "_portable_lock", _P(__file__).resolve().with_name("_portable_lock.py")
    )
    _mod = _ilu.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    LockTimeoutError = _mod.LockTimeoutError
    locked_exclusive = _mod.locked_exclusive
from datetime import datetime, timezone
from pathlib import Path

GENESIS = "0" * 64

APPEND_LOCK_TIMEOUT_S = 30.0  # verrou portable — ADR #286 (C2/C6)


def _key_id(key: bytes) -> str:
    """Empreinte publique d'une clé HMAC (16 premiers hex de sha256)."""
    return hashlib.sha256(key).hexdigest()[:16]


def _load_key(key_path: Path) -> bytes:
    """Lit une clé stockée en hexadécimal."""
    return bytes.fromhex(key_path.read_text(encoding="utf-8").strip())


def _canonical_material(entry: dict) -> bytes:
    material = {k: v for k, v in entry.items() if k != "hash"}
    return json.dumps(material, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _entry_hash(entry: dict) -> str:
    return hashlib.sha256(_canonical_material(entry)).hexdigest()


def _entry_hmac(key: bytes, entry: dict) -> str:
    return hmac.new(key, _canonical_material(entry), hashlib.sha256).hexdigest()


def _parse_entries_from_text(text: str, source: str = "") -> list[dict]:
    prefix = f"{source}:" if source else "ligne "
    entries = []
    for lineno, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"{prefix}{lineno}: JSON invalide — {exc}")
    return entries


def _read_entries(path: Path) -> list[dict]:
    if not path.exists():
        return []
    # `path` = emplacement du registre choisi par l'app/l'opérateur (jamais une entrée HTTP) ;
    # correctif de concurrence, aucun chemin dérivé d'input → faux positif path-traversal.
    return _parse_entries_from_text(path.read_text(encoding="utf-8"), source=str(path))  # NOSONAR


def init_key(path: Path) -> str:
    """Crée une clé HMAC locale (32 octets, permissions 0600) et renvoie son key_id.

    Idempotent : si le fichier existe déjà, renvoie le key_id de la clé existante.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_CREAT | os.O_WRONLY | os.O_EXCL, 0o600)
    except FileExistsError:
        existing_hex = path.read_text(encoding="utf-8").strip()
        return _key_id(bytes.fromhex(existing_hex))

    try:
        key = secrets.token_bytes(32)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(key.hex() + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        return _key_id(key)
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        raise


def append(
    path: Path,
    type_: str,
    actor: str,
    payload: dict,
    *,
    key_path: Path | None = None,
) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)  # ex. ~/.forgeai/Registres/ (P3)
    # `path` = registre app/opérateur (pas d'entrée HTTP) ; chemin non dérivé d'input.
    with path.open("a+", encoding="utf-8") as fh:  # NOSONAR
        with locked_exclusive(fh.fileno(), timeout_s=APPEND_LOCK_TIMEOUT_S):
            fh.seek(0)
            entries = _parse_entries_from_text(fh.read(), source=str(path))
            prev_hash = entries[-1]["hash"] if entries else GENESIS
            entry = {
                "seq": len(entries) + 1,
                "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "type": type_,
                "actor": actor,
                "payload": payload,
                "prev_hash": prev_hash,
            }
            if key_path is not None:
                key = _load_key(key_path)
                entry["key_id"] = _key_id(key)
                entry["hash"] = _entry_hmac(key, entry)
            else:
                entry["hash"] = _entry_hash(entry)
            line = json.dumps(entry, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
            fh.seek(0, os.SEEK_END)
            fh.write(line + "\n")
            fh.flush()
            os.fsync(fh.fileno())
    return entry


def verify(path: Path, *, key_path: Path | None = None) -> str | None:
    """Retourne None si la chaîne est intègre, sinon la description de la rupture.

    - Entrée sans ``key_id`` : vérification SHA-256 nu (rétro-compatible Tier 0)
      uniquement si aucune clé n'est fournie.
    - Entrée avec ``key_id`` : vérification HMAC-SHA256 avec ``key_path``.
      Si ``key_path`` est manquant ou ne correspond pas au ``key_id``,
      une erreur explicite est retournée (jamais None silencieux).
    - Si une clé est fournie mais qu'une entrée n'a pas de ``key_id``,
      l'entrée est refusée (défense contre le déclassement Tier 1 -> Tier 0).
    """
    key: bytes | None = None
    expected_key_id: str | None = None
    if key_path is not None:
        key = _load_key(key_path)
        expected_key_id = _key_id(key)

    prev_hash = GENESIS
    for entry in _read_entries(path):
        seq = entry.get("seq")
        if entry.get("prev_hash") != prev_hash:
            return f"seq {seq}: prev_hash ne chaîne pas avec l'entrée précédente"

        entry_key_id = entry.get("key_id")
        if key is not None:
            if entry_key_id is None:
                return (
                    f"seq {seq}: entrée sans key_id alors qu'une clé est fournie "
                    f"(déclassement Tier 1 -> Tier 0 refusé)"
                )
            if entry_key_id != expected_key_id:
                return f"seq {seq}: key_id {entry_key_id} ne correspond pas à la clé fournie"
            if not hmac.compare_digest(_entry_hmac(key, entry), entry.get("hash", "")):
                return f"seq {seq}: hash HMAC invalide (entrée altérée)"
        else:
            if entry_key_id is not None:
                return f"seq {seq}: key_id {entry_key_id} présent mais aucune clé fournie (UNVERIFIED)"
            if not hmac.compare_digest(_entry_hash(entry), entry.get("hash", "")):
                return f"seq {seq}: hash invalide (entrée altérée)"

        prev_hash = entry["hash"]
    return None


def verify_status(path: Path, *, key_path: Path | None = None) -> str:
    """Renvoie OK, UNVERIFIED ou INVALID selon l'état du registre.

    - OK        : la chaîne est intègre.
    - UNVERIFIED: au moins une entrée porte un key_id mais aucune clé n'est disponible.
    - INVALID   : une erreur de chaînage, d'intégrité ou de déclassement est détectée.
    """
    entries = _read_entries(path)
    has_keyed = any("key_id" in e for e in entries)

    if has_keyed:
        if key_path is None or not key_path.exists():
            return "UNVERIFIED"
        try:
            _load_key(key_path)
        except (OSError, ValueError):
            return "UNVERIFIED"

    if key_path is not None and entries and any("key_id" not in e for e in entries):
        return "INVALID"

    error = verify(path, key_path=key_path)
    if error is not None:
        return "INVALID"
    return "OK"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_append = sub.add_parser("append", help="ajoute une entrée chaînée")
    p_append.add_argument("registre", type=Path)
    p_append.add_argument("--type", required=True, dest="type_")
    p_append.add_argument("--actor", required=True)
    p_append.add_argument("--payload-json", default="{}")
    p_append.add_argument("--key", type=Path, default=None, help="clé HMAC locale (hex)")

    p_verify = sub.add_parser("verify", help="vérifie l'intégrité de la chaîne")
    p_verify.add_argument("registres", type=Path, nargs="+")
    p_verify.add_argument("--key", type=Path, default=None, help="clé HMAC locale (hex)")

    args = parser.parse_args()
    if args.cmd == "append":
        entry = append(
            args.registre,
            args.type_,
            args.actor,
            json.loads(args.payload_json),
            key_path=args.key,
        )
        print(json.dumps(entry, ensure_ascii=False))
        return

    failed = False
    for path in args.registres:
        error = verify(path, key_path=args.key)
        if error:
            print(f"ECHEC {path}: {error}")
            failed = True
        else:
            print(f"OK {path}: {len(_read_entries(path))} entrées, chaîne intègre")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
