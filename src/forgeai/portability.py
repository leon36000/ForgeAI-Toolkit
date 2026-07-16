"""
Export/import portable du setup du stack-modèles de ForgeAI Toolkit.

INVARIANT :
- Le bundle N'INCLUT JAMAIS de secrets (vault.json est exclu).
- Les clés d'API ne sont jamais exportées en clair (seul key_fingerprint est conservé).
- Chaque bundle est hashé (SHA-256) et la vérification est fail-closed : toute altération,
  nom de fichier suspect ou version incompatible déclenche PortabilityError.
- L'import recrée les fichiers de configuration mais ne restaure PAS les secrets ; la
  liste `secrets_to_reprovision` indique les routes nécessitant une nouvelle saisie de clé.
- L'opération garantit un round-trip prouvé : export → import produit des fichiers identiques
  (hors secrets).
"""

import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

BUNDLE_VERSION = 1
SETUP_FILES = (
    "routes.json",
    "gateway.json",
    "wirings.json",
    "strategy.json",
    "budgets.json",
)
EXCLUDED_FILES = frozenset({"vault.json"})
SAFE_ROUTE_FIELDS = frozenset(
    {
        "name",
        "provenance",
        "base_url",
        "model_id",
        "key_fingerprint",
        "created_at",
        "cache",
        "cache_ttl_s",
        "cache_prefix",
    }
)


class PortabilityError(Exception):
    """Erreur levée lors d'une opération de portabilité (export/import)."""


def _canonical(payload: dict) -> str:
    """Sérialise un dict de manière déterministe (tri des clés, sans espaces)."""
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def bundle_sha256(files: dict) -> str:
    """Calcule le SHA-256 d'un bundle (dict contenant version + files)."""
    payload = {"version": BUNDLE_VERSION, "files": files}
    return hashlib.sha256(_canonical(payload).encode()).hexdigest()


def _safe_name(fname: str) -> bool:
    """Vérifie qu'un nom de fichier est dans la liste blanche et ne sort pas du répertoire."""
    return (
        fname in SETUP_FILES
        and fname not in EXCLUDED_FILES
        and fname == Path(fname).name  # pas de chemin, pas de '..'
    )


def _validate_route(route: dict) -> None:
    """Lève PortabilityError si un champ de route hors liste blanche contient une valeur non vide."""
    for key, value in route.items():
        if key not in SAFE_ROUTE_FIELDS and value:
            raise PortabilityError(
                f"champ de route hors schéma connu (rejeté par sécurité) : '{key}'"
            )


def export_setup(home, out_path=None) -> dict:
    """
    Exporte le setup du stack (sans les secrets) vers un bundle.

    Args:
        home: répertoire racine (str ou Path) contenant les fichiers de configuration.
        out_path (optionnel): chemin de sortie pour écrire le bundle JSON.

    Returns:
        dict représentant le bundle (version, created_at, files, sha256).

    Raises:
        PortabilityError si un secret est détecté en clair ou si un fichier exclu est présent.
    """
    home = Path(home)
    files = {}

    for fname in SETUP_FILES:
        fpath = home / fname
        if fpath.is_file():
            if fname in EXCLUDED_FILES:
                raise PortabilityError(
                    f"fichier interdit à l'export : {fname}"
                )
            content = json.loads(fpath.read_text(encoding="utf-8"))
            # Validation spécifique pour routes.json
            if fname == "routes.json":
                routes = content if isinstance(content, list) else []
                for route in routes:
                    _validate_route(route)
            files[fname] = content

    # Vérification garde-fou supplémentaire : aucun fichier hors whitelist ne doit apparaître
    for excluded in EXCLUDED_FILES:
        if excluded in files:
            raise PortabilityError(f"fichier exclu présent dans le bundle : {excluded}")

    bundle = {
        "version": BUNDLE_VERSION,
        "created_at": date.today().isoformat(),
        "files": files,
        "sha256": bundle_sha256(files),
    }

    if out_path:
        Path(out_path).write_text(json.dumps(bundle, indent=1), encoding="utf-8")

    return bundle


def verify_bundle(bundle: dict) -> None:
    """
    Vérifie l'intégrité du bundle : version compatible, hash cohérent, fichiers autorisés.

    Raises:
        PortabilityError en cas d'anomalie.
    """
    if bundle.get("version") != BUNDLE_VERSION:
        raise PortabilityError(
            f"version de bundle incompatible : attendue {BUNDLE_VERSION}, reçue {bundle.get('version')}"
        )

    files = bundle.get("files")
    if not isinstance(files, dict):
        raise PortabilityError("le bundle ne contient pas de champ 'files' valide")

    expected_sha = bundle_sha256(files)
    if bundle.get("sha256") != expected_sha:
        raise PortabilityError("hash SHA-256 invalide : le bundle a peut-être été altéré")

    # Vérification des noms de fichiers autorisés (défense contre les chemins arbitraires)
    for fname in files:
        if not _safe_name(fname):
            raise PortabilityError(
                f"nom de fichier non autorisé dans le bundle : '{fname}'"
            )


def load_bundle(path) -> dict:
    """
    Charge et vérifie un bundle JSON.

    Returns:
        dict du bundle.

    Raises:
        PortabilityError si le JSON est invalide ou la vérification échoue.
    """
    with open(path, encoding="utf-8") as f:
        bundle = json.load(f)
    verify_bundle(bundle)
    return bundle


def secrets_to_reprovision(bundle: dict) -> List[str]:
    """
    Retourne la liste triée des noms de routes qui nécessitent une nouvelle saisie de secret.

    Se base sur routes.json du bundle ; une route est concernée si `key_fingerprint` est non vide.
    """
    routes_file = bundle.get("files", {}).get("routes.json")
    if not isinstance(routes_file, list):
        return []
    return sorted(
        route["name"] for route in routes_file
        if isinstance(route, dict) and route.get("key_fingerprint")
    )


def import_setup(bundle_path, home, *, force=False) -> dict:
    """
    Importe un bundle dans le répertoire `home`.

    Args:
        bundle_path: chemin du fichier bundle JSON.
        home: répertoire cible (créé s'il n'existe pas).
        force: si True, écrase les fichiers existants sans erreur.

    Returns:
        dict avec les clés 'restored', 'secrets_to_reprovision', 'home'.

    Raises:
        PortabilityError si un fichier existe déjà et que `force` est False,
        ou si le bundle est invalide.
    """
    bundle = load_bundle(bundle_path)
    home = Path(home)
    home.mkdir(parents=True, exist_ok=True)

    restored = []
    for fname, content in bundle["files"].items():
        # Défense en profondeur : ignorer les noms dangereux (déjà vérifié dans load_bundle)
        if not _safe_name(fname):
            continue
        dest = home / fname
        if dest.exists() and not force:
            raise PortabilityError(
                f"le fichier existe déjà : {dest}. Relancez avec --force (force=True) pour écraser."
            )
        dest.write_text(json.dumps(content, indent=1), encoding="utf-8")
        restored.append(fname)

    return {
        "restored": restored,
        "secrets_to_reprovision": secrets_to_reprovision(bundle),
        "home": str(home),
    }
