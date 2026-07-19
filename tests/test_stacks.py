"""IMPL-3 — preuve : les 6 profils de déploiement (data/stacks/*.json).

Chaque profil est valide, ne déploie que des ids réels du catalogue, porte le RAG durci + le
gateway unique litellm + hermes-agent, et l'agentique déploie superpowers + openclaw."""
import json

import pytest

from forgeai.resources import catalogue_path
from forgeai.stacks import deploy_ids, list_stacks, load_stack, validate_stack

EXPECTED = {
    "agentique",
    "assistant-entreprise",
    "support-conversationnel",
    "automatisation",
    "mlops",
    "tout-en-un",
}


def _catalogue_ids():
    d = json.loads(catalogue_path().read_text(encoding="utf-8"))
    entries = d if isinstance(d, list) else d["entries"]
    return {x["id"] for x in entries}


def test_les_6_profils_presents():
    assert set(list_stacks()) == EXPECTED


def test_chaque_profil_valide():
    cids = _catalogue_ids()
    for sid in sorted(EXPECTED):
        errs = validate_stack(load_stack(sid), cids)
        assert errs == [], f"{sid} : {errs}"


def test_tous_les_ids_deployes_sont_au_catalogue():
    cids = _catalogue_ids()
    for sid in sorted(EXPECTED):
        dep = deploy_ids(load_stack(sid))
        assert dep, f"{sid} : deploy vide"
        hors = sorted(i for i in dep if i not in cids)
        assert hors == [], f"{sid} déploie des ids hors catalogue : {hors}"


def test_rag_durci_et_gateway_partout():
    for sid in sorted(EXPECTED):
        s = load_stack(sid)
        assert s["base_rag_durci"] is True, sid
        assert s["default_by_sphere"]["S4"] == "litellm", sid
        assert s["default_by_sphere"].get("S7"), sid


def test_hermes_partout_superpowers_openclaw_agentique():
    for sid in sorted(EXPECTED):
        s5 = set(load_stack(sid)["deploy_by_sphere"].get("S5", []))
        assert "hermes-agent" in s5, f"{sid} : S5 sans hermes-agent"
    ag_s5 = set(load_stack("agentique")["deploy_by_sphere"]["S5"])
    assert {"superpowers", "openclaw"} <= ag_s5, "agentique doit déployer superpowers+openclaw"


def test_cablage_et_config_non_vides():
    for sid in sorted(EXPECTED):
        s = load_stack(sid)
        assert len(s.get("wiring", [])) >= 3, f"{sid} : câblage trop maigre"
        assert s.get("config_critique"), f"{sid} : config_critique manquante"


def test_load_stack_inconnu_leve():
    with pytest.raises(FileNotFoundError):
        load_stack("stack-inexistant-xyz")
