"""Phase Modèles locaux — téléchargement hash-vérifié + déploiement + test réel (DM-5, B-08).

Garanties (testées) :
  - la liste proposée est filtrée par la VRAM du nœud cible ET le moteur/backend déterminé ;
  - le téléchargement est vérifié par SHA-256 (intégrité chaîne d'appro) — une empreinte qui
    ne correspond pas ABANDONNE et supprime le fichier corrompu ;
  - le déploiement passe par le moteur du nœud (runner injectable) ;
  - la validation exige un test de complétion RÉEL → réponse non vide = GREEN (pas une
    présence de fichier ni un code de retour seul).
Tout est journalisable via un callback `journal` (empreinte, jamais de secret).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

from forgeai.core.validation import valider_schema_url
from forgeai.i18n import t

from ..core.runner import CommandRunner
from ..core.validation import ValidationError, resolve_within, valider_nom_simple
from .probe import ProbeResult, Transport, probe_route


class LocalModelError(Exception):
    pass


@dataclass(frozen=True)
class LocalModel:
    name: str
    engine: str            # "ollama" | "llamacpp" | "vllm"
    vram_required_mb: int
    model_ref: str         # identifiant côté moteur (ex. "qwen2.5-coder:1.5b")
    download_url: str
    sha256: str            # empreinte attendue de l'artefact


def filter_available(models: list[LocalModel], vram_mb: int,
                     engines: set[str]) -> list[LocalModel]:
    """Modèles tenant dans la VRAM du nœud ET servis par un moteur disponible."""
    return [m for m in models
            if m.vram_required_mb <= vram_mb and m.engine in engines]


class Fetcher(Protocol):
    def fetch(self, url: str, dest: Path, timeout: float = 300.0) -> int:
        """Écrit l'artefact de `url` vers `dest`, retourne le nombre d'octets."""


class UrllibFetcher:
    """Téléchargement en flux (stdlib) — ne charge pas tout l'artefact en mémoire."""

    def __init__(self, chunk: int = 1 << 20) -> None:
        self.chunk = chunk

    def fetch(self, url: str, dest: Path, timeout: float = 300.0) -> int:
        import urllib.request
        total = 0
        dest.parent.mkdir(parents=True, exist_ok=True)
        valider_schema_url(url)
        with urllib.request.urlopen(url, timeout=timeout) as resp, dest.open("wb") as fh:
            while True:
                buf = resp.read(self.chunk)
                if not buf:
                    break
                fh.write(buf)
                total += len(buf)
        return total


def _sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def download_verified(model: LocalModel, dest_dir: Path, fetcher: Fetcher) -> Path:
    """Télécharge puis VÉRIFIE l'empreinte. Mismatch → supprime et lève.

    Revue aveugle 3 vendors (TOCTOU) : on télécharge dans un fichier temporaire `.part`,
    on vérifie, PUIS on renomme atomiquement vers la destination finale. Ainsi le fichier
    présent à `dest` est toujours exactement l'artefact vérifié (pas de fenêtre de
    substitution entre vérification et usage)."""
    try:
        valider_nom_simple(model.name)
        dest = resolve_within(Path(dest_dir) / f"{model.name}.bin", dest_dir)
    except ValidationError:
        raise LocalModelError(t("models.local.download_verified.nom_invalide", name=model.name)) from None
    tmp = dest.with_suffix(".part")
    fetcher.fetch(model.download_url, tmp)
    actual = _sha256_file(tmp)
    if actual != model.sha256:
        tmp.unlink(missing_ok=True)  # artefact corrompu/altéré : ne jamais conserver
        raise LocalModelError(
            t("models.local.download_verified.empreinte_invalide",
              name=model.name, attendu=model.sha256[:12], obtenu=actual[:12]))
    tmp.replace(dest)  # renommage atomique de l'artefact VÉRIFIÉ
    return dest


_DEPLOY_CMD = {
    "ollama": lambda ref: ["ollama", "pull", ref],
    "llamacpp": lambda ref: ["true"],   # artefact déjà local (GGUF) — servi directement
    "vllm": lambda ref: ["true"],       # servi par le manifeste de déploiement du nœud
}


def deploy(model: LocalModel, runner: CommandRunner) -> None:
    """Déploie le modèle sur le moteur du nœud (runner injectable). Lève si échec."""
    builder = _DEPLOY_CMD.get(model.engine)
    if not builder:
        raise LocalModelError(t("models.local.deploy.moteur_inconnu", engine=model.engine))
    code, out = runner.run(builder(model.model_ref))
    if code != 0:
        raise LocalModelError(
            t("models.local.deploy.deploiement_echoue", name=model.name, engine=model.engine, code=code))


def check_completion(engine_url: str, model_ref: str, transport: Transport | None = None
                    ) -> ProbeResult:
    """Test de complétion RÉEL contre le moteur local (endpoint compatible OpenAI)."""
    return probe_route(engine_url, model_ref, api_key="local", transport=transport)


def add_local(model: LocalModel, dest_dir: Path, engine_url: str, *,
              vram_mb: int, engines: set[str], fetcher: Fetcher, runner: CommandRunner,
              transport: Transport | None = None,
              journal: Callable[[str, dict], None] | None = None) -> ProbeResult:
    """Orchestre filtre → téléchargement vérifié → déploiement → test réel. Fail-fast.
    Une étape échoue = exception claire, rien n'est validé (pas de modèle à demi-installé)."""
    def _log(step: str, data: dict) -> None:
        if journal:
            journal(step, data)

    if not filter_available([model], vram_mb, engines):
        raise LocalModelError(
            t("models.local.add_local.incompatible", name=model.name,
              vram_requis=model.vram_required_mb, engine=model.engine,
              vram_noeud=vram_mb, moteurs=sorted(engines)))

    path = download_verified(model, dest_dir, fetcher)
    _log("modele_local_telecharge", {"name": model.name, "sha256": model.sha256,
                                     "octets": path.stat().st_size})
    try:
        deploy(model, runner)
        _log("modele_local_deploye", {"name": model.name, "engine": model.engine,
                                      "ref": model.model_ref})
        result = check_completion(engine_url, model.model_ref, transport)
        if not result.ok:
            raise LocalModelError(t("models.local.add_local.test_completion_echec",
                                     light=result.light, detail=result.detail))
        _log("modele_local_valide", {"name": model.name, "light": result.light})
        return result
    except Exception:
        path.unlink(missing_ok=True)
        raise
