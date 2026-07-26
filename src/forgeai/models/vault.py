"""Coffre de secrets chiffré — stdlib PUR (invariant portabilité `dependencies=[]`).

Menace couverte : protection AU REPOS des clés d'API sur la machine de l'utilisateur
(inspection de disque, commit accidentel, fuite de sauvegarde). PAS un HSM.

Compromis assumé (revue aveugle 3 vendors) : l'invariant portabilité `dependencies=[]`
interdit une lib AEAD standard (AES-GCM/ChaCha20-Poly1305 absents de la stdlib). La
construction EtM(HMAC-CTR) est saine pour cette menace (salt+nonce aléatoires par
scellement, tag vérifié en temps constant AVANT déchiffrement). Si la contrainte de
portabilité est un jour relâchée, migrer vers `cryptography` (Fernet/AES-GCM).

Construction (chiffrement authentifié, primitives stdlib vérifiées — aucune primitive
maison) :
  clé  = scrypt(passphrase, salt, n=2^14, r=8, p=1, dklen=64) → enc_key(32) | mac_key(32)
  flux = HMAC-SHA256(enc_key, nonce || compteur_be64) par blocs (mode CTR)
  ct   = plaintext XOR flux
  tag  = HMAC-SHA256(mac_key, salt || nonce || ct)          (chiffrer-puis-MAC)
  blob = MAGIC | salt(16) | nonce(16) | tag(32) | ct
Unicité (salt, nonce) aléatoires par scellement → pas de réutilisation de flux.
Vérification du tag en temps constant (hmac.compare_digest) avant tout déchiffrement.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import stat
from pathlib import Path

from forgeai.models._locking import (
    MODELS_TRANSACTION_JOURNAL,
    MODELS_TRANSACTION_LOCK,
    _paths_identify_same_file,
    atomic_write_text,
    file_lock,
    recover_models_transaction_locked,
)

MAGIC = b"FGV1"
_SALT = 16
_NONCE = 16
_TAG = 32
# Revue aveugle 3 vendors (DeepSeek/Grok/Gemini) : N=2^14 jugé bas pour une attaque
# hors-ligne sur blob volé (cible « au repos ») → relevé à 2^16 (~67 Mo, <1 s, portable).
_SCRYPT = dict(n=2 ** 16, r=8, p=1, dklen=64, maxmem=128 * 1024 * 1024)


class VaultError(Exception):
    """Tag invalide : passphrase erronée ou données altérées."""


def atomic_write_secret_text(
    path: Path, payload: str, *, mode: int = 0o600
) -> None:
    """Remplace un fichier secret atomiquement sans suivre une cible symlink."""
    path = Path(path)
    try:
        target = path.lstat()
    except FileNotFoundError:
        target = None
    if target is not None and stat.S_ISLNK(target.st_mode):
        raise OSError("refus d'écrire un secret via un lien symbolique")
    atomic_write_text(path, payload, mode=mode)


def republish_existing_secret_file(path: Path, *, mode: int = 0o600) -> None:
    """Relit un secret régulier sans suivre de lien, puis le republie atomiquement."""
    no_follow = getattr(os, "O_NOFOLLOW", None)
    if no_follow is None:
        raise OSError("ouverture sans suivi de lien indisponible")
    flags = os.O_RDONLY | no_follow
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NONBLOCK", 0)
    # S2083 est un faux positif : cible locale de bootstrap choisie par
    # l'opérateur, ouverte O_NOFOLLOW puis validée comme fichier régulier avant
    # lecture; la publication passe ensuite par le writer atomique.
    descriptor = os.open(Path(path), flags)  # NOSONAR S2083
    try:
        target = os.fstat(descriptor)
        if not stat.S_ISREG(target.st_mode):
            raise OSError("refus de republier un secret non régulier")
        content = bytearray()
        while chunk := os.read(descriptor, 8_192):
            content.extend(chunk)
    finally:
        os.close(descriptor)
    try:
        payload = bytes(content).decode("utf-8")
    except UnicodeDecodeError:
        raise OSError("secret existant non UTF-8") from None
    atomic_write_secret_text(path, payload, mode=mode)


def _keystream(enc_key: bytes, nonce: bytes, length: int) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < length:
        block = hmac.new(enc_key, nonce + counter.to_bytes(8, "big"), hashlib.sha256).digest()
        out.extend(block)
        counter += 1
    return bytes(out[:length])


def _derive(passphrase: str, salt: bytes) -> tuple[bytes, bytes]:
    full = hashlib.scrypt(passphrase.encode("utf-8"), salt=salt, **_SCRYPT)
    return full[:32], full[32:]


def seal(plaintext: bytes, passphrase: str) -> bytes:
    """Scelle `plaintext` sous `passphrase` → blob auto-porteur (salt+nonce+tag+ct)."""
    salt = secrets.token_bytes(_SALT)
    nonce = secrets.token_bytes(_NONCE)
    enc_key, mac_key = _derive(passphrase, salt)
    ct = bytes(a ^ b for a, b in zip(plaintext, _keystream(enc_key, nonce, len(plaintext))))
    tag = hmac.new(mac_key, salt + nonce + ct, hashlib.sha256).digest()
    return MAGIC + salt + nonce + tag + ct


def unseal(blob: bytes, passphrase: str) -> bytes:
    """Ouvre un blob scellé. Lève VaultError si tag invalide (mauvaise passphrase/altéré)."""
    if len(blob) < len(MAGIC) + _SALT + _NONCE + _TAG or not blob.startswith(MAGIC):
        raise VaultError("format de coffre invalide")
    off = len(MAGIC)
    salt = blob[off:off + _SALT]; off += _SALT
    nonce = blob[off:off + _NONCE]; off += _NONCE
    tag = blob[off:off + _TAG]; off += _TAG
    ct = blob[off:]
    enc_key, mac_key = _derive(passphrase, salt)
    expected = hmac.new(mac_key, salt + nonce + ct, hashlib.sha256).digest()
    if not hmac.compare_digest(tag, expected):
        raise VaultError("tag invalide : passphrase erronée ou coffre altéré")
    return bytes(a ^ b for a, b in zip(ct, _keystream(enc_key, nonce, len(ct))))


def fingerprint(secret: str) -> str:
    """Empreinte NON réversible d'un secret — pour le registre/affichage. Jamais le secret."""
    return "sha256:" + hashlib.sha256(secret.encode("utf-8")).hexdigest()[:16]


class Vault:
    """Coffre fichier (un blob par clé logique). Fichier 0600, répertoire 0700."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.transaction_lock_path = self.path.parent / MODELS_TRANSACTION_LOCK
        self.transaction_journal_path = self.path.parent / MODELS_TRANSACTION_JOURNAL

    def _load(self) -> dict[str, str]:
        import json
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _save(self, data: dict[str, str]) -> None:
        import json
        self.path.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(self.path.parent, 0o700)
        payload = json.dumps(data, ensure_ascii=False, indent=1)
        atomic_write_secret_text(self.path, payload, mode=0o600)

    def _with_secret(
        self, name: str, secret: str, passphrase: str
    ) -> tuple[dict[str, str], str]:
        """Prépare une nouvelle image du coffre sans l'écrire."""
        import base64

        data = self._load()
        blob = seal(secret.encode("utf-8"), passphrase)
        data[name] = base64.b64encode(blob).decode("ascii")
        return data, fingerprint(secret)

    def _recover_pending_transaction_locked(self) -> None:
        canonical_vault_path = self.path.parent / "vault.json"
        path_is_canonical_alias = _paths_identify_same_file(
            self.path, canonical_vault_path
        )
        recovery_path = (
            self.path if path_is_canonical_alias else canonical_vault_path
        )
        recovered = recover_models_transaction_locked(
            self.path.parent, recovery_path
        )
        if recovered and path_is_canonical_alias:
            self.path = canonical_vault_path

    def put(self, name: str, secret: str, passphrase: str) -> str:
        """Scelle `secret` sous `name`. Retourne l'empreinte (jamais le secret)."""
        with file_lock(self.transaction_lock_path):
            self._recover_pending_transaction_locked()
            data, secret_fingerprint = self._with_secret(name, secret, passphrase)
            self._save(data)
        return secret_fingerprint

    def get(self, name: str, passphrase: str) -> str:
        import base64

        with file_lock(self.transaction_lock_path):
            self._recover_pending_transaction_locked()
            data = self._load()
        if name not in data:
            raise KeyError(name)
        return unseal(base64.b64decode(data[name]), passphrase).decode("utf-8")

    def names(self) -> list[str]:
        with file_lock(self.transaction_lock_path):
            self._recover_pending_transaction_locked()
            return sorted(self._load())
