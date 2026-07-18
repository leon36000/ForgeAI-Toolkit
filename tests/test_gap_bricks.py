"""IMPL-2 — preuve : les 33 briques [GAP] (voix/secrets/lineage) ajoutées au catalogue,
sourcées gh-api, valides au schéma, et classées dans une des 14 sphères."""
import json

from forgeai.catalogue.loader import verify_catalogue
from forgeai.catalogue.spheres import SPHERE_IDS, classify_sphere
from forgeai.resources import catalogue_path

GAP_IDS = [
    # 17 R3 — secrets / IaC / surfaces / lineage
    "hashicorp-vault", "infisical", "sops", "hashicorp-terraform", "pulumi", "flux2",
    "nextchat", "lobe-chat", "librechat", "paddleocr", "private-gpt", "strix",
    "bitnet", "kubeflow", "openai-evals", "datahub", "openlineage",
    # 16 voix / conversationnel
    "faster-whisper", "whisperx", "silero-vad", "smart-turn", "kokoro", "piper1-gpl",
    "coqui-ai-tts", "chatterbox", "moonshine", "sensevoice", "livekit", "speaches",
    "rasa", "vocode-core", "chatwoot", "chainlit",
]


def _entries():
    d = json.loads(catalogue_path().read_text(encoding="utf-8"))
    return d if isinstance(d, list) else d["entries"]


def test_33_gap_bricks_presentes():
    ids = {e["id"] for e in _entries()}
    manquantes = [g for g in GAP_IDS if g not in ids]
    assert manquantes == [], f"briques GAP manquantes : {manquantes}"


def test_gap_bricks_schema_et_source_reelle():
    by = {e["id"]: e for e in _entries()}
    for g in GAP_IDS:
        e = by[g]
        assert e["verified"] is True, g
        assert e["source_url"].startswith("https://github.com/"), g
        assert e["license"], g
        assert e["verify_method"].startswith("gh-api"), g
        assert e["flag"] == "PUBLIC-INSTALLABLE", g
        assert e["category"], g


def test_gap_bricks_classent_en_sphere():
    by = {e["id"]: e for e in _entries()}
    for g in GAP_IDS:
        assert classify_sphere(by[g]) in SPHERE_IDS, g


def test_catalogue_integrite_sha256():
    # lève si le catalogue a été altéré sans régénérer l'empreinte
    verify_catalogue(catalogue_path())


def test_catalogue_ids_uniques():
    ids = [e["id"] for e in _entries()]
    assert len(ids) == len(set(ids)), "id dupliqué dans le catalogue"


def test_gap_categories_sont_reelles():
    """Les 33 briques n'introduisent AUCUNE nouvelle catégorie : chacune réutilise
    une catégorie déjà présente parmi les autres entrées du catalogue."""
    ents = _entries()
    gap = set(GAP_IDS)
    cats_gap = {e["category"] for e in ents if e["id"] in gap}
    cats_autres = {e["category"] for e in ents if e["id"] not in gap}
    nouvelles = cats_gap - cats_autres
    assert nouvelles == set(), f"catégories inexistantes introduites : {nouvelles}"


def test_catalogue_compte_981():
    """948 (base) + 33 (GAP) = 981 entrées après IMPL-2."""
    assert len(_entries()) == 981
