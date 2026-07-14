"""Tests de l'outillage R-ALL — règle de rigueur : pas de source = rejet (comme un stub)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import rall


def _lot(tmp_path, body: str) -> Path:
    p = tmp_path / "lot.yaml"
    p.write_text(body, encoding="utf-8")
    return p


def test_parse_lot_champs(tmp_path):
    lot = _lot(tmp_path, '''lot: t
dossiers:
  - nom: "K3s"
    source_url: "https://github.com/k3s-io/k3s"
    flag: "PUBLIC-INSTALLABLE"
    license: "Apache-2.0"
    description_fr: "Distribution Kubernetes légère."
    install: "binaire: get.k3s.io"
    role: "socle cluster"
''')
    d = rall.parse_lot(lot)[0]
    assert d["nom"] == "K3s"
    assert d["source_url"].endswith("/k3s")
    assert d["license"] == "Apache-2.0"


def test_validate_refuse_sans_source(tmp_path):
    errs = rall._validate({"nom": "X", "flag": "PUBLIC-INSTALLABLE",
                           "license": "MIT", "description_fr": "d", "install": "i", "role": "r"})
    assert any("source_url" in e for e in errs)


def test_validate_refuse_flag_invalide():
    errs = rall._validate({"nom": "X", "source_url": "https://a", "flag": "PEUT-ETRE"})
    assert any("flag" in e for e in errs)


def test_validate_public_exige_les_champs():
    errs = rall._validate({"nom": "X", "source_url": "https://a", "flag": "PUBLIC-INSTALLABLE"})
    manquants = " ".join(errs)
    assert "license" in manquants and "description_fr" in manquants


def test_validate_introuvable_ok_sans_desc():
    # une entrée introuvable n'exige pas description/licence, juste la source de recherche
    errs = rall._validate({"nom": "X", "source_url": "https://github.com/search?q=x",
                           "flag": "INTROUVABLE-APRES-RECHERCHE"})
    assert errs == []


def test_apply_reel_sur_le_catalogue(tmp_path, monkeypatch):
    # copie de travail du catalogue réel pour ne pas muter le fichier versionné
    import json, shutil
    work = tmp_path / "catalogue.json"
    shutil.copy(rall.CATALOGUE, work)
    shutil.copy(rall.CATALOGUE.with_suffix(".sha256"), tmp_path / "catalogue.sha256")
    monkeypatch.setattr(rall, "CATALOGUE", work)
    # prend une entrée atlas_only réelle et l'enrichit
    data = json.loads(work.read_text(encoding="utf-8"))
    cible = next(e["name"] for e in data["entries"] if e.get("atlas_only"))
    lot = _lot(tmp_path, f'''lot: t
dossiers:
  - nom: "{cible}"
    source_url: "https://github.com/example/{cible.lower().replace(' ', '-')[:20]}"
    flag: "PUBLIC-INSTALLABLE"
    license: "Apache-2.0"
    maintenance: "active"
    description_fr: "Description vérifiée et sourcée."
    description_en: "Verified sourced description."
    install: "docker: example/img:1.0"
    role: "brique de test"
    verify_method: "web:github"
''')
    rall.cmd_apply([lot])
    after = json.loads(work.read_text(encoding="utf-8"))
    e = next(x for x in after["entries"] if x["name"] == cible)
    assert e["verified"] is True and e["atlas_only"] is False
    assert e["source_url"].startswith("https://github.com/")
    assert e["description_en"] == "Verified sourced description."


def test_apply_bloque_dossier_sans_source(tmp_path, monkeypatch):
    import shutil
    work = tmp_path / "catalogue.json"
    shutil.copy(rall.CATALOGUE, work)
    monkeypatch.setattr(rall, "CATALOGUE", work)
    import json
    cible = next(e["name"] for e in json.loads(work.read_text())["entries"])
    lot = _lot(tmp_path, f'''lot: t
dossiers:
  - nom: "{cible}"
    flag: "PUBLIC-INSTALLABLE"
    description_fr: "sans source"
''')
    with pytest.raises(SystemExit):
        rall.cmd_apply([lot])
