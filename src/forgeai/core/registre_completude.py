"""Contrôles de complétude structurée pour les registres JSONL."""

from __future__ import annotations

import json
from pathlib import Path

SCHEMA_PAR_TYPE = {
    "tdad_green": {"story", "preuve"},
    "revue_scellee": {"story", "prompt_sha256", "vendors"},
    "story_complete": {"story"},
}


def story_de(entree: dict) -> str | None:
    """Rattache une entrée à sa story selon les conventions historiques."""
    payload = entree.get("payload")
    if not isinstance(payload, dict):
        return None

    for cle in ("story", "package"):
        valeur = payload.get(cle)
        if isinstance(valeur, str):
            return valeur

    dossier = payload.get("dossier")
    if isinstance(dossier, str) and dossier:
        dossier = dossier.rstrip("/")
        if dossier:
            return dossier.rsplit("/", 1)[-1]

    return None


def anomalies(entrees: list[dict]) -> list[dict]:
    """Retourne les anomalies de schéma et d'attestation sans modifier les entrées."""
    resultat: list[dict] = []
    stories_avec_revue = {
        story
        for entree in entrees
        if entree.get("type") == "revue_scellee"
        for story in [story_de(entree)]
        if story is not None
    }

    for entree in entrees:
        type_entree = entree.get("type")
        payload = entree.get("payload")
        payload_dict = payload if isinstance(payload, dict) else {}
        seq = entree.get("seq")
        story = story_de(entree)

        for champ in sorted(SCHEMA_PAR_TYPE.get(type_entree, set())):
            if champ not in payload_dict:
                resultat.append(
                    {
                        "type": "schema",
                        "seq": seq,
                        "story": story,
                        "raison": f"champ obligatoire manquant: {champ}",
                    }
                )

        if type_entree == "story_complete":
            attestation_en_ligne = (
                "revue" in payload_dict or "preuve" in payload_dict
            )
            if not attestation_en_ligne and story not in stories_avec_revue:
                resultat.append(
                    {
                        "type": "attestation",
                        "seq": seq,
                        "story": story,
                        "raison": "aucune revue attestée pour cette story",
                    }
                )

    return resultat


def charger(chemin: str | Path) -> list[dict]:
    """Lit un registre JSONL et retourne une liste vide si le fichier est absent."""
    try:
        with Path(chemin).open(encoding="utf-8") as fichier:
            return [
                json.loads(ligne)
                for ligne in fichier
                if ligne.strip()
            ]
    except FileNotFoundError:
        return []
