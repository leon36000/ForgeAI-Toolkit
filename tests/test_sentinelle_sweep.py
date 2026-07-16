"""Sentinelle — sweep de complétion (D4) : tests déterministes de la détection de surfaces."""
from __future__ import annotations

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("sweep", REPO / "scripts" / "sentinelle_sweep.py")
sweep_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sweep_mod)


def _mk(root: Path, rel: str, code: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(code, encoding="utf-8")
    return p


def test_symbole_touche_utilise_ailleurs_est_une_surface(tmp_path):
    src = tmp_path / "src"
    a = _mk(src, "mod_a.py", "def foo():\n    return 1\n")
    _mk(src, "mod_b.py", "from mod_a import foo\n\ndef bar():\n    return foo()\n")
    tests = tmp_path / "tests"
    tests.mkdir()
    res = sweep_mod.sweep([a], [src], tests)
    # foo (défini dans le changeset mod_a) est utilisé dans mod_b (non ouvert) → surface
    assert "foo" in res["surfaces_non_verifiees"]
    assert any("mod_b.py" in f for f in res["surfaces_non_verifiees"]["foo"])


def test_symbole_local_seulement_pas_de_surface(tmp_path):
    src = tmp_path / "src"
    a = _mk(src, "mod_a.py", "def foo():\n    return 1\n\ndef baz():\n    return foo()\n")
    tests = tmp_path / "tests"
    tests.mkdir()
    res = sweep_mod.sweep([a], [src], tests)
    # foo n'est utilisé que dans mod_a (le fichier changé) → aucune surface externe
    assert res["surfaces_non_verifiees"] == {}


def test_symbole_public_sans_test_est_signale(tmp_path):
    src = tmp_path / "src"
    a = _mk(src, "mod_a.py", "def foo():\n    return 1\n")
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_autre.py").write_text("def test_rien():\n    assert True\n", encoding="utf-8")
    res = sweep_mod.sweep([a], [src], tests)
    assert any("foo" in s for s in res["symboles_publics_sans_test"])


def test_symbole_avec_test_pas_signale(tmp_path):
    src = tmp_path / "src"
    a = _mk(src, "mod_a.py", "def foo():\n    return 1\n")
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_foo.py").write_text("from mod_a import foo\n\ndef test_foo():\n    assert foo() == 1\n",
                                       encoding="utf-8")
    res = sweep_mod.sweep([a], [src], tests)
    assert res["symboles_publics_sans_test"] == []


def test_symboles_prives_ignores(tmp_path):
    src = tmp_path / "src"
    a = _mk(src, "mod_a.py", "def _interne():\n    return 1\n")
    tests = tmp_path / "tests"
    tests.mkdir()
    res = sweep_mod.sweep([a], [src], tests)
    # les symboles _privés ne sont pas des surfaces d'API publique
    assert res["surfaces_non_verifiees"] == {} and res["symboles_publics_sans_test"] == []


def test_depot_sous_dossier_nomme_tests_nest_pas_ignore(tmp_path):
    # bug CRITIQUE corrige : le filtre ne doit PAS se baser sur le nom absolu ("tests" ancetre)
    src = tmp_path / "tests" / "pkg"        # chemin contenant "tests" comme ancetre
    a = _mk(src, "mod_a.py", "def foo():\n    return 1\n")
    _mk(src, "mod_b.py", "def bar():\n    return foo()\n")
    test_root = tmp_path / "realtests"      # le VRAI dossier de tests est ailleurs
    test_root.mkdir()
    res = sweep_mod.sweep([a], [src], test_root)
    assert "foo" in res["surfaces_non_verifiees"]   # mod_a n'a PAS ete ignore a tort


def test_fichier_non_utf8_ne_casse_pas(tmp_path):
    # bug ELEVE corrige : UnicodeDecodeError tolere
    src = tmp_path / "src"
    a = _mk(src, "mod_a.py", "def foo():\n    return 1\n")
    (src / "binaire.py").write_bytes(b"\xff\xfe def foo(): pass \x80\x81")
    test_root = tmp_path / "tests"
    test_root.mkdir()
    res = sweep_mod.sweep([a], [src], test_root)   # ne doit lever aucune exception
    assert isinstance(res, dict)
