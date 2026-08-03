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

from forgeai.i18n import t

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
_MAX_SECRET_TEXT_BYTES = 1024 * 1024
# Revue aveugle 3 vendors (DeepSeek/Grok/Gemini) : N=2^14 jugé bas pour une attaque
# hors-ligne sur blob volé (cible « au repos ») → relevé à 2^16 (~67 Mo, <1 s, portable).
_SCRYPT = dict(n=2 ** 16, r=8, p=1, dklen=64, maxmem=128 * 1024 * 1024)


class VaultError(Exception):
    """Tag invalide : passphrase erronée ou données altérées."""


def _same_inode(left: os.stat_result, right: os.stat_result) -> bool:
    return (left.st_dev, left.st_ino) == (right.st_dev, right.st_ino)


def _set_mode_without_following_preexisting_symlink(
    path: Path, mode: int, expected_state: os.stat_result
) -> os.stat_result:
    current = path.lstat()
    if (
        stat.S_IFMT(current.st_mode) != stat.S_IFMT(expected_state.st_mode)
        or not _same_inode(current, expected_state)
    ):
        raise OSError(t("models.vault.chemin_a_change"))

    if os.chmod in os.supports_follow_symlinks:
        os.chmod(path, mode, follow_symlinks=False)
    else:
        # Limite POSIX : le fallback pathname repose sur un parent contrôlé par
        # l'opérateur et non soumis à un renommage hostile entre les deux lstat.
        os.chmod(path, mode)

    updated = path.lstat()
    if (
        stat.S_IFMT(updated.st_mode) != stat.S_IFMT(expected_state.st_mode)
        or not _same_inode(updated, expected_state)
    ):
        raise OSError(t("models.vault.chemin_a_change"))
    return updated


def _open_directory_with_mode(
    path: Path, path_state: os.stat_result, final_mode: int
) -> int:
    no_follow = getattr(os, "O_NOFOLLOW", None)
    directory = getattr(os, "O_DIRECTORY", None)
    if no_follow is None or directory is None:
        raise OSError(t("models.vault.validation_repertoire_indisponible"))
    if not stat.S_ISDIR(path_state.st_mode):
        raise OSError(t("models.vault.chemin_pas_repertoire"))

    if stat.S_IMODE(path_state.st_mode) & 0o500 != 0o500:
        path_state = _set_mode_without_following_preexisting_symlink(
            path, final_mode, path_state
        )

    flags = os.O_RDONLY | no_follow | directory
    flags |= getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(path, flags)
    try:
        descriptor_state = os.fstat(descriptor)
        if (
            not stat.S_ISDIR(descriptor_state.st_mode)
            or not _same_inode(descriptor_state, path_state)
        ):
            raise OSError(t("models.vault.chemin_pas_repertoire"))
        os.fchmod(descriptor, final_mode)
        current = path.lstat()
        if not stat.S_ISDIR(current.st_mode) or not _same_inode(
            current, descriptor_state
        ):
            raise OSError(t("models.vault.repertoire_a_change"))
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor


def prepare_secure_directory(
    path: Path,
    *,
    final_mode: int = 0o700,
    preserve_existing_final: bool = False,
) -> None:
    """Crée/valide une chaîne de répertoires sans symlink, umask-indépendante."""
    path = Path(path)
    creation_chain_started = False
    for candidate in (*reversed(path.parents), path):
        try:
            current = candidate.lstat()
        except FileNotFoundError:
            creation_chain_started = True
            try:
                candidate.mkdir(mode=0o700)
            except FileExistsError:
                current = candidate.lstat()
            else:
                current = candidate.lstat()

        if not stat.S_ISDIR(current.st_mode):
            raise OSError(t("models.vault.chemin_pas_repertoire"))

        permissions = stat.S_IMODE(current.st_mode)
        is_final = candidate == path
        if is_final and not preserve_existing_final:
            desired_mode = final_mode
        elif creation_chain_started:
            desired_mode = final_mode if is_final else 0o700
        elif permissions & 0o700 != 0o700:
            desired_mode = permissions | 0o700
        else:
            continue

        descriptor = _open_directory_with_mode(
            candidate, current, desired_mode
        )
        os.close(descriptor)


def _ensure_regular_path_matches(
    path: Path, expected_state: os.stat_result
) -> None:
    current = path.lstat()
    if (
        not stat.S_ISREG(current.st_mode)
        or current.st_nlink != 1
        or not _same_inode(current, expected_state)
    ):
        raise OSError(t("models.vault.fichier_verrou_a_change"))


def prepare_lock_file(path: Path) -> None:
    """Établit le même inode de verrou 0600 avant file_lock."""
    mode = 0o600
    no_follow = getattr(os, "O_NOFOLLOW", None)
    if no_follow is None:
        raise OSError(t("models.vault.ouverture_sans_suivi_indisponible"))
    flags = os.O_RDWR | no_follow
    flags |= getattr(os, "O_CLOEXEC", 0)
    lock_path = Path(str(path) + ".lock")

    try:
        descriptor = os.open(
            lock_path, flags | os.O_CREAT | os.O_EXCL, mode
        )
        expected_state = None
    except FileExistsError:
        expected_state = lock_path.lstat()
        if (
            not stat.S_ISREG(expected_state.st_mode)
            or expected_state.st_nlink != 1
        ):
            raise OSError(t("models.vault.verrou_pas_fichier_regulier"))
        if stat.S_IMODE(expected_state.st_mode) & 0o600 != 0o600:
            expected_state = _set_mode_without_following_preexisting_symlink(
                lock_path, mode, expected_state
            )
        descriptor = os.open(lock_path, flags)

    try:
        descriptor_state = os.fstat(descriptor)
        if (
            not stat.S_ISREG(descriptor_state.st_mode)
            or descriptor_state.st_nlink != 1
        ):
            raise OSError(t("models.vault.verrou_pas_fichier_regulier"))
        if expected_state is not None and not _same_inode(
            descriptor_state, expected_state
        ):
            raise OSError(t("models.vault.fichier_verrou_a_change"))
        os.fchmod(descriptor, mode)
        _ensure_regular_path_matches(lock_path, descriptor_state)
    finally:
        os.close(descriptor)


def _reject_secret_target_symlink(path: Path) -> None:
    try:
        target = path.lstat()
    except FileNotFoundError:
        target = None
    if target is not None and stat.S_ISLNK(target.st_mode):
        raise OSError(t("models.vault.refus_lien_symbolique"))


def atomic_write_secret_text(
    path: Path, payload: str, *, mode: int = 0o600
) -> None:
    """Remplace un fichier secret atomiquement sans suivre une cible symlink."""
    path = Path(path)
    _reject_secret_target_symlink(path)
    atomic_write_text(path, payload, mode=mode)


def read_secret_text(
    path: Path, *, max_bytes: int = _MAX_SECRET_TEXT_BYTES
) -> str:
    """Lit un petit fichier secret régulier sans suivre son composant final."""
    no_follow = getattr(os, "O_NOFOLLOW", None)
    if no_follow is None:
        raise OSError(t("models.vault.ouverture_sans_suivi_indisponible"))
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
            raise OSError(t("models.vault.refus_secret_non_regulier"))
        if target.st_size > max_bytes:
            raise OSError(t("models.vault.secret_trop_volumineux"))
        content = bytearray()
        while chunk := os.read(
            descriptor, min(8_192, max_bytes + 1 - len(content))
        ):
            content.extend(chunk)
            if len(content) > max_bytes:
                raise OSError(t("models.vault.secret_trop_volumineux"))
    finally:
        os.close(descriptor)
    try:
        return bytes(content).decode("utf-8")
    except UnicodeDecodeError:
        raise OSError(t("models.vault.secret_non_utf8")) from None


def republish_existing_secret_file(path: Path, *, mode: int = 0o600) -> None:
    """Relit un secret régulier sans suivre de lien, puis le republie atomiquement."""
    payload = read_secret_text(path)
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
        raise VaultError(t("models.vault.format_coffre_invalide"))
    off = len(MAGIC)
    salt = blob[off:off + _SALT]; off += _SALT
    nonce = blob[off:off + _NONCE]; off += _NONCE
    tag = blob[off:off + _TAG]; off += _TAG
    ct = blob[off:]
    enc_key, mac_key = _derive(passphrase, salt)
    expected = hmac.new(mac_key, salt + nonce + ct, hashlib.sha256).digest()
    if not hmac.compare_digest(tag, expected):
        raise VaultError(t("models.vault.tag_invalide"))
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

    def _prepare_storage(self) -> None:
        prepare_secure_directory(self.path.parent, final_mode=0o700)
        _reject_secret_target_symlink(self.path)
        prepare_lock_file(self.transaction_lock_path)

    def _load(self) -> dict[str, str]:
        import json

        try:
            payload = read_secret_text(self.path)
        except FileNotFoundError:
            return {}
        return json.loads(payload)

    def _save(self, data: dict[str, str]) -> None:
        import json

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
        self._prepare_storage()
        with file_lock(self.transaction_lock_path):
            self._recover_pending_transaction_locked()
            data, secret_fingerprint = self._with_secret(name, secret, passphrase)
            self._save(data)
        return secret_fingerprint

    def get(self, name: str, passphrase: str) -> str:
        import base64

        self._prepare_storage()
        with file_lock(self.transaction_lock_path):
            self._recover_pending_transaction_locked()
            data = self._load()
        if name not in data:
            raise KeyError(name)
        return unseal(base64.b64decode(data[name]), passphrase).decode("utf-8")

    def names(self) -> list[str]:
        self._prepare_storage()
        with file_lock(self.transaction_lock_path):
            self._recover_pending_transaction_locked()
            return sorted(self._load())
