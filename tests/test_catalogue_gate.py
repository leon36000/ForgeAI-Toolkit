import json
import sys
from pathlib import Path

# Ensure the project root is in sys.path to import the scripts module
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from scripts.catalogue_gate import (
    load_entries,
    find_violations,
    default_catalogue_path,
    main,
)


def test_catalogue_reel_passe():
    entries = load_entries(default_catalogue_path())
    violations = find_violations(entries)
    assert violations == [], f"Violations trouvées dans le catalogue réel : {violations}"


def test_collision_sans_disambiguation_detectee():
    entries = [
        {"id": "a", "name": "x/y"},
        {"id": "b", "name": "x/y"},
    ]
    violations = find_violations(entries)
    # au moins une violation de collision
    assert any(
        "nom en collision sans disambiguation : 'x/y'" in v for v in violations
    ), f"Violations attendues, obtenues : {violations}"


def test_collision_avec_disambiguation_ok():
    entries = [
        {"id": "a", "name": "x/y", "disambiguation": "first"},
        {"id": "b", "name": "x/y", "disambiguation": "second"},
    ]
    violations = find_violations(entries)
    # Aucune violation de collision (peut-être d'autres si on oublie quelque chose, mais ici tout est propre)
    assert all(
        "nom en collision" not in v for v in violations
    ), f"Violations inattendues : {violations}"


def test_id_duplique_detecte():
    entries = [
        {"id": "dup", "name": "first"},
        {"id": "dup", "name": "second"},
    ]
    violations = find_violations(entries)
    assert any(
        "id dupliqué : 'dup' (2 entrées)" in v for v in violations
    ), f"Violations attendues, obtenues : {violations}"


def test_entree_sans_id_detectee():
    entries = [
        {"name": "foo"},  # pas d'id
    ]
    violations = find_violations(entries)
    assert any(
        "entrée sans id : 'foo'" in v for v in violations
    ), f"Violations attendues, obtenues : {violations}"


def test_main_retourne_1_sur_violation(tmp_path, capsys):
    # Créer un petit catalogue avec une collision
    catalogue = {"entries": [{"id": "1", "name": "a/b"}, {"id": "2", "name": "a/b"}]}
    tmp_catalogue = tmp_path / "catalogue.json"
    tmp_catalogue.write_text(json.dumps(catalogue), encoding="utf-8")

    ret = main(["--catalogue", str(tmp_catalogue)])
    out, err = capsys.readouterr()

    assert ret == 1
    assert "CATALOGUE-GATE : ÉCHEC" in err
    assert "nom en collision sans disambiguation" in out


def test_main_retourne_0_sur_catalogue_reel(capsys):
    ret = main([])
    out, err = capsys.readouterr()

    assert ret == 0
    assert "CATALOGUE-GATE : OK" in out
    assert err == "" or "CATALOGUE-GATE" not in err  # pas d'erreur


def test_disambiguation_declaree_au_schema():
    from scripts.catalogue_gate import load_schema, default_schema_path
    schema = load_schema(default_schema_path())
    assert "disambiguation" in schema.get("properties", {}), \
        "le champ 'disambiguation' doit être déclaré au schéma d'entrée"


def test_catalogue_reel_conforme_au_schema():
    from scripts.catalogue_gate import (
        load_entries, load_schema, default_catalogue_path,
        default_schema_path, schema_violations,
    )
    entries = load_entries(default_catalogue_path())
    schema = load_schema(default_schema_path())
    assert schema_violations(entries, schema) == []


def test_champ_non_declare_detecte():
    from scripts.catalogue_gate import schema_violations
    schema = {"properties": {"id": {}, "name": {}}, "required": ["id"],
              "additionalProperties": False}
    v = schema_violations([{"id": "a", "name": "n", "champ_inconnu": "x"}], schema)
    assert any("non déclaré" in s for s in v)


def test_champ_requis_manquant_detecte():
    from scripts.catalogue_gate import schema_violations
    schema = {"properties": {"id": {}, "name": {}}, "required": ["id", "name"],
              "additionalProperties": False}
    v = schema_violations([{"id": "a"}], schema)
    assert any("requis manquant" in s for s in v)
