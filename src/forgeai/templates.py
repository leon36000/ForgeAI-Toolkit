"""Alias hérités « templates » → stacks (P1, fusion décidée le 2026-07-19).

Le système des templates (B-13/B-14) et celui des stacks (IMPL-3) faisaient double
emploi (constat d'audit). Décision : UN SEUL système — les stacks. Les commandes
`forge template …` restent rétro-compatibles via ce mapping ; les JSON dupliqués
(data/templates/) ont été retirés.
"""
from __future__ import annotations

from forgeai.i18n import t
from forgeai.stacks import list_stacks, load_stack

# Noms hérités → stack équivalent (périmètre validé en fusion)
LEGACY_ALIASES: dict[str, str] = {
    "dev-agentic": "agentique",
    "rag-souverain": "assistant-entreprise",
    "lab-fine-tuning": "mlops",
    "production-souveraine": "tout-en-un",
}

class TemplateError(Exception):
    """Nom hérité ou stack inconnu."""


def resolve_alias(name: str) -> str:
    """Nom hérité ou id de stack → id de stack ; TemplateError sinon."""
    stack_id = LEGACY_ALIASES.get(name, name)
    if stack_id not in list_stacks():
        connus = sorted(set(LEGACY_ALIASES) | set(list_stacks()))
        raise TemplateError(t("templates.resolve_alias.nom_inconnu", name=name, connus=connus))
    return stack_id


def list_templates() -> list[str]:
    """Les stacks (système unique), noms hérités affichés comme alias."""
    return sorted(list_stacks())


def load_template(name: str) -> dict:
    """Charge le STACK correspondant au nom (hérité ou direct)."""
    return load_stack(resolve_alias(name))
