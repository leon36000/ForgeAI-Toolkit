"""IMPL-2b — preuve : couverture complète awesome-opensource-ai + écosystème OpenClaw.

Les 596 briques ajoutées par IMPL-2b (tests/data/coverage_added_ids.json) sont sourcées
gh-api, valides au schéma, classées en sphère, et ajoutées comme OPTIONS (default=null :
jamais un défaut de catégorie ; le déploiement par stack est décidé par les profils, pas
par le catalogue). Manifeste réduit à 595 le 2026-08-04 (registre seq 411) : le dépôt de
`feder-cr-invisible-playwright` a disparu de GitHub (404 confirmé, aucun renommage
identifiable) — entrée retirée du catalogue et du manifeste plutôt que laissée comme
brique installable non fonctionnelle."""
import json
from pathlib import Path

from forgeai.catalogue.loader import category_defaults, verify_catalogue
from forgeai.catalogue.spheres import SPHERE_IDS, classify_sphere
from forgeai.resources import catalogue_path

_MANIFEST = Path(__file__).parent / "data" / "coverage_added_ids.json"
ADDED_IDS = json.loads(_MANIFEST.read_text(encoding="utf-8"))


def _entries():
    d = json.loads(catalogue_path().read_text(encoding="utf-8"))
    return d if isinstance(d, list) else d["entries"]


def test_manifeste_595_uniques():
    assert len(ADDED_IDS) == 595
    assert len(ADDED_IDS) == len(set(ADDED_IDS))


def test_toutes_les_ajoutees_sont_au_catalogue():
    ids = {e["id"] for e in _entries()}
    manquantes = [a for a in ADDED_IDS if a not in ids]
    assert manquantes == [], f"ajoutées absentes du catalogue : {manquantes[:10]}"


def test_ajoutees_sont_options_sourcees():
    by = {e["id"]: e for e in _entries()}
    for a in ADDED_IDS:
        e = by[a]
        assert e["default"] is None, f"{a} : option (default doit être null)"
        assert e["verified"] is True, a
        assert e["source_url"].startswith("https://github.com/"), a
        assert e["verify_method"].startswith("gh-api"), a
        assert e["license"], a
        assert e["flag"] == "PUBLIC-INSTALLABLE", a


def test_ajoutees_classent_en_sphere():
    by = {e["id"]: e for e in _entries()}
    for a in ADDED_IDS:
        assert classify_sphere(by[a]) in SPHERE_IDS, a


def test_ajoutees_categories_reelles():
    ents = _entries()
    added = set(ADDED_IDS)
    cats_add = {e["category"] for e in ents if e["id"] in added}
    cats_base = {e["category"] for e in ents if e["id"] not in added}
    assert cats_add <= cats_base, f"catégories inexistantes introduites : {cats_add - cats_base}"


def test_catalogue_1576_integre_et_unique():
    assert len(_entries()) == 1576
    verify_catalogue(catalogue_path())  # lève si sha256 ne correspond pas
    ids = [e["id"] for e in _entries()]
    assert len(ids) == len(set(ids)), "id dupliqué"


def test_options_jamais_defaut_de_categorie():
    """Règle Nathan : les 595 briques de couverture sont des OPTIONS (default_eligible=false)
    — jamais le défaut ⭐ d'une catégorie (fondamentaux/weights/bruit inclus)."""
    ents = _entries()
    by = {e["id"]: e for e in ents}
    for a in ADDED_IDS:
        assert by[a].get("default_eligible") is False, f"{a} doit porter default_eligible=false"
    added_names = {by[a]["name"] for a in ADDED_IDS}
    defauts = set(category_defaults(ents).values())
    intrus = added_names & defauts
    assert intrus == set(), f"option devenue défaut de catégorie : {sorted(intrus)[:5]}"
