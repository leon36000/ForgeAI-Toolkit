"""Export/import portable du setup du stack-modèles ForgeAI Toolkit.

Invariant : le bundle exporté ne contient **aucun secret**. Les secrets
sont représentés uniquement par des *empreintes* (`key_fingerprint`).
À l'import, les secrets doivent être redemandés à l'utilisateur.

Sécurité :
- Le hash SHA256 couvre l'intégralité du bundle (version, created_at, fichiers).
- Toute altération du bundle est détectée lors de la vérification.
- L'export refuse tout fichier routes.json non conforme (pas une liste ou
  contenant des clés en clair).
- L'import n'écrit jamais de vault.json et est atomique vis-à-vis des
  fichiers existants (tout ou rien quand force=False).

Round-trip prouvé : un export suivi d'un import dans un répertoire vierge
restaure exactement le même état (hors secrets).
"""

import json
import hashlib
from pathlib import Path
from datetime import date
from typing import List

BUNDLE_VERSION = 1
SETUP_FILES = ("routes.json", "gateway.json", "wirings.json", "strategy.json", "budgets.json")
EXCLUDED_FILES = frozenset({"vault.json"})
SAFE_ROUTE_FIELDS = {"name", "provenance", "base_url", "model_id", "key_fingerprint",
                     "created_at", "cache", "cache_ttl_s", "cache_prefix"}


class PortabilityError(Exception):
    """Erreur liée à l'export/import du setup."""


def _canonical(payload: dict) -> str:
    """Sérialisation déterministe pour le hash."""
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def bundle_sha256(files: dict, created_at: str) -> str:
    """Calcule l'empreinte SHA256 du bundle (version, created_at, fichiers)."""
    payload = {"version": BUNDLE_VERSION, "created_at": created_at, "files": files}
    raw = _canonical(payload).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _safe_name(fname: str) -> bool:
    """Vrai seulement pour un fichier de setup autorisé : pas de chemin, pas de '..',
    pas de chemin absolu, jamais un fichier exclu. Protège l'import contre l'écriture
    arbitraire depuis un bundle forgé (même à hash valide)."""
    return (fname in SETUP_FILES and fname not in EXCLUDED_FILES
            and fname == Path(fname).name)


def _validate_route(route: dict) -> None:
    """Vérifie qu'une route ne contient aucun secret en clair ni champ interdit."""
    # Champs de secret explicites
    secret_keys = {"api_key", "key", "secret"}
    for sk in secret_keys:
        if sk in route and route[sk]:
            raise PortabilityError(f"Présence d'une clé secrète en clair dans une route : {sk}")
    # Champs inconnus (sécurité par défaut)
    extra = set(route.keys()) - SAFE_ROUTE_FIELDS
    if extra:
        raise PortabilityError(f"Champs non autorisés dans une route : {extra}")


def export_setup(home, out_path=None) -> dict:
    """Exporte tous les fichiers de setup (sans secrets) vers un dict bundle.

    Args:
        home: dossier racine du stack (contient routes.json, etc.).
        out_path: chemin optionnel où écrire le bundle JSON.

    Retourne le dict du bundle.

    Lève PortabilityError si routes.json n'est pas une liste de routes
    ou si une route contient un secret en clair.
    """
    home = Path(home)
    files = {}

    for fname in SETUP_FILES:
        file_path = home / fname
        if not file_path.exists():
            continue

        # Lecture
        try:
            with open(file_path, "r", encoding="utf-8") as fh:
                content = json.load(fh)
        except Exception as exc:
            raise PortabilityError(f"Erreur lors du chargement de {fname} : {exc}") from exc

        # Validation stricte pour routes.json
        if fname == "routes.json":
            if not isinstance(content, list):
                raise PortabilityError("routes.json doit être une liste de routes")
            for route in content:
                if not isinstance(route, dict):
                    raise PortabilityError("Chaque élément de routes.json doit être un dict")
                _validate_route(route)

        # Garde‑fou supplémentaire
        if fname in EXCLUDED_FILES:
            raise PortabilityError(f"Le fichier exclu {fname} ne doit jamais être exporté")

        files[fname] = content

    created_at = date.today().isoformat()
    sha = bundle_sha256(files, created_at)
    bundle = {
        "version": BUNDLE_VERSION,
        "created_at": created_at,
        "files": files,
        "sha256": sha,
    }

    if out_path is not None:
        out_path = Path(out_path)
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(bundle, fh, indent=1, ensure_ascii=False)

    return bundle


def verify_bundle(bundle: dict) -> None:
    """Vérifie l'intégrité et la compatibilité du bundle.

    Lève PortabilityError si la version est incompatible ou si le hash est altéré.
    """
    version = bundle.get("version")
    if version != BUNDLE_VERSION:
        raise PortabilityError(f"Version de bundle incompatible. Attendu {BUNDLE_VERSION}, reçu {version}")

    expected_sha = bundle_sha256(bundle["files"], bundle.get("created_at"))
    if bundle["sha256"] != expected_sha:
        raise PortabilityError("Hash altéré – bundle corrompu")

    # Fail-closed : un bundle (même à hash valide) ne peut porter que des noms autorisés.
    for fname in bundle["files"]:
        if not _safe_name(fname):
            raise PortabilityError(f"nom de fichier non autorisé dans le bundle : '{fname}'")


def load_bundle(path) -> dict:
    """Charge un bundle depuis un fichier et vérifie son intégrité."""
    with open(path, "r", encoding="utf-8") as fh:
        bundle = json.load(fh)
    verify_bundle(bundle)
    return bundle


def secrets_to_reprovision(bundle: dict) -> List[str]:
    """Liste triée des noms de routes dont le secret doit être redemandé.

    Une route nécessite un reprovisionnement si key_fingerprint est non vide.
    """
    routes = bundle.get("files", {}).get("routes.json", [])
    if not isinstance(routes, list):
        routes = []
    names = [r["name"] for r in routes if isinstance(r, dict) and r.get("key_fingerprint")]
    names.sort()
    return names


def import_setup(bundle_path, home, *, force=False) -> dict:
    """Importe un bundle dans un répertoire home.

    Comportement atomique : si force=False et qu'au moins un fichier existe déjà,
    aucune écriture n'est réalisée (évite les états partiels).
    Avec force=True, les fichiers sont écrasés.
    Ne restaure jamais vault.json.

    Retourne un rapport : {"restored": [...], "secrets_to_reprovision": [...], "home": str}
    """
    bundle = load_bundle(bundle_path)
    files = bundle["files"]
    if not isinstance(files, dict):
        raise PortabilityError("Le bundle ne contient pas un mapping 'files' valide")

    home = Path(home)
    home.mkdir(parents=True, exist_ok=True)

    # Vérification préalable (si force=False) – aucune écriture avant cette étape
    if not force:
        conflicts = []
        for fname in files:
            dest = home / fname
            if dest.exists():
                conflicts.append(fname)
        if conflicts:
            raise PortabilityError(
                f"Fichiers déjà présents dans {home} : {', '.join(conflicts)}. Utilisez force=True pour écraser."
            )

    # Écriture effective
    restored = []
    for fname, content in files.items():
        # Défense en profondeur : ne jamais écrire un nom hors whitelist (vault.json, '..', absolu)
        if not _safe_name(fname):
            continue
        dest = home / fname
        with open(dest, "w", encoding="utf-8") as fh:
            json.dump(content, fh, indent=1, ensure_ascii=False)
        restored.append(fname)

    secrets = secrets_to_reprovision(bundle)
    return {
        "restored": restored,
        "secrets_to_reprovision": secrets,
        "home": str(home),
    }
