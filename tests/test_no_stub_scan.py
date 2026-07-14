"""Tests du gate no-stub §8bis."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import no_stub_scan


def _scan_source(tmp_path, source, name="module.py"):
    path = tmp_path / name
    path.write_text(source, encoding="utf-8")
    return no_stub_scan.scan_file(path)


def test_detecte_corps_vide(tmp_path):
    violations = _scan_source(tmp_path, "def f():\n    pass\n")
    assert len(violations) == 1
    assert "corps vide" in violations[0]


def test_detecte_ellipsis_et_docstring_seule(tmp_path):
    source = 'def f():\n    """Doc."""\n    ...\n'
    assert any("corps vide" in v for v in _scan_source(tmp_path, source))


def test_detecte_not_implemented_error(tmp_path):
    source = "def f():\n    raise NotImplementedError('plus tard')\n"
    assert any("NotImplementedError" in v for v in _scan_source(tmp_path, source))


def test_detecte_assert_true(tmp_path):
    source = "def test_x():\n    assert True\n"
    assert any("faux vert" in v for v in _scan_source(tmp_path, source))


def test_detecte_marqueur_interdit(tmp_path):
    marqueur = "TO" + "DO"
    violations = _scan_source(tmp_path, f"# {marqueur}: finir plus tard\nx = 1\n")
    assert any("marqueur interdit" in v for v in violations)


def test_skip_pytest_sans_justification(tmp_path):
    source = "import pytest\n\ndef test_x():\n    pytest.skip('pas le temps')\n"
    assert any("sans justification" in v for v in _scan_source(tmp_path, source))


def test_skip_pytest_avec_justification_passe(tmp_path):
    source = (
        "import pytest\n\ndef test_x():\n"
        "    pytest.skip('hardware absent du CI, voir Registres/mission.jsonl seq 12')\n"
    )
    assert not _scan_source(tmp_path, source)


def test_fonction_abstraite_autorisee(tmp_path):
    source = (
        "from abc import ABC, abstractmethod\n\n"
        "class Base(ABC):\n"
        "    @abstractmethod\n"
        "    def f(self):\n        ...\n"
    )
    assert not _scan_source(tmp_path, source)


def test_classe_exception_idiomatique_autorisee(tmp_path):
    source = "class ErreurMetier(Exception):\n    pass\n"
    assert not _scan_source(tmp_path, source)


def test_code_sain_passe(tmp_path):
    source = "def somme(a, b):\n    return a + b\n"
    assert not _scan_source(tmp_path, source)


def test_membre_de_protocol_autorise(tmp_path):
    source = (
        "from typing import Protocol\n\n"
        "class Runner(Protocol):\n"
        '    def run(self, argv: list[str]) -> tuple[int, str]:\n'
        '        """Contrat d\'interface."""\n'
    )
    assert not _scan_source(tmp_path, source)
