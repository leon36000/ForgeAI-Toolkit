"""Profils de déploiement (stacks) ForgeAI — IMPL-3.

Un profil (``data/stacks/<id>.json``) décrit le **SET DÉPLOYÉ synergique** d'un stack :

- ``deploy_by_sphere`` : les ids catalogue effectivement déployés+câblés par défaut, par sphère ;
- ``default_by_sphere`` : la brique primaire (1) de chaque sphère ;
- ``wiring`` : le graphe de câblage (qui parle à qui) issu de la recherche de perfection ;
- ``config_critique`` : les points de configuration qui rendent le stack « 100 % utilisable ».

Le **catalogue** est l'univers des options (activables à la carte) ; le **profil** décrit ce qui
démarre par défaut. Le champ catalogue ``default_eligible`` concerne le défaut ⭐ *de catégorie*
(B-21) — il est ORTHOGONAL au déploiement par profil : une brique peut être « non-éligible au ⭐ »
et pourtant déployée par un stack (ex. les briques voix du stack Support).
"""
from __future__ import annotations

import json
from pathlib import Path

from forgeai.i18n import t


def stacks_dir() -> Path:
    return Path(__file__).resolve().parent / "data" / "stacks"


def list_stacks() -> list[str]:
    """Ids des profils disponibles (nom de fichier sans extension), triés."""
    return sorted(p.stem for p in stacks_dir().glob("*.json"))


def load_stack(stack_id: str) -> dict:
    if not stack_id or "/" in stack_id or "\\" in stack_id or ".." in stack_id:
        raise FileNotFoundError(t("stacks.load_stack.invalide", stack_id=stack_id))
    path = stacks_dir() / f"{stack_id}.json"
    if not path.exists():
        raise FileNotFoundError(t("stacks.load_stack.inconnu", stack_id=stack_id))
    return json.loads(path.read_text(encoding="utf-8"))


def deploy_ids(stack: dict) -> list[str]:
    """Ids déployés (toutes sphères), dédupliqués, dans l'ordre de première apparition."""
    seen: dict[str, None] = {}
    for ids in stack.get("deploy_by_sphere", {}).values():
        for brick_id in ids:
            seen.setdefault(brick_id, None)
    return list(seen)


def validate_stack(stack: dict, catalogue_ids: set[str]) -> list[str]:
    """Retourne les violations du profil (liste vide = valide).

    Invariants : deploy non vide et entièrement dans le catalogue ; RAG durci ; gateway unique
    ``litellm`` ; ``hermes-agent`` déployé (imposé à tous) ; ``superpowers``+``openclaw`` pour
    l'agentique ; câblage présent.
    """
    errors: list[str] = []
    dep = deploy_ids(stack)
    if not dep:
        errors.append("deploy_by_sphere vide")
    missing = sorted(i for i in dep if i not in catalogue_ids)
    if missing:
        errors.append(f"ids déployés absents du catalogue : {missing[:5]}")
    s5 = set(stack.get("deploy_by_sphere", {}).get("S5", []))
    if "hermes-agent" not in s5:
        errors.append("S5 doit déployer hermes-agent (imposé à tous les stacks)")
    if stack.get("id") == "agentique":
        for req in ("superpowers", "openclaw"):
            if req not in s5:
                errors.append(f"S5 agentique doit déployer {req}")
    defaults = stack.get("default_by_sphere", {})
    if defaults.get("S4") != "litellm":
        errors.append("défaut S4 (gateway unique) doit être 'litellm'")
    if not defaults.get("S7"):
        errors.append("défaut S7 (RAG) manquant")
    if not stack.get("base_rag_durci"):
        errors.append("base_rag_durci doit être true")
    if not stack.get("wiring"):
        errors.append("câblage (wiring) manquant")
    return errors
