"""FAI-0016 (#122) — dette : `_NODE_RE` était compilé À L'IDENTIQUE dans cli.py ET web/server.py.
Spécification : le motif de nom de nœud n'est défini QU'UNE fois (forgeai.core.validation.NODE_NAME_RE)
et réutilisé par import. (Note : un test d'identité `is` serait trompeur — `re.compile` met en cache les
motifs identiques ; on vérifie donc la SOURCE.)
"""
import pathlib

import forgeai
from forgeai.core.validation import NODE_NAME_RE

# Ancre de fin `\Z` et non `$` : en Python, `$` matche AUSSI avant un saut de ligne
# terminal, donc "node1\n" passait la validation (audit 2026-08-05, constat L07-001).
_PATTERN_SRC = r'r"^[a-z0-9]([a-z0-9.-]{0,62})\Z"'


def test_motif_node_defini_une_seule_fois():
    root = pathlib.Path(forgeai.__file__).resolve().parent
    hits = [p.relative_to(root) for p in root.rglob("*.py")
            if _PATTERN_SRC in p.read_text(encoding="utf-8")]
    assert len(hits) == 1, f"motif de nom de nœud dupliqué dans : {[str(h) for h in hits]}"
    assert hits[0].name == "validation.py"


def test_cli_et_web_reutilisent_la_source():
    import forgeai.cli as cli
    import forgeai.web.server as server
    assert cli._NODE_RE is NODE_NAME_RE
    assert server._NODE_RE is NODE_NAME_RE


def test_comportement_inchange():
    assert NODE_NAME_RE.match("worker-1.lan")
    assert NODE_NAME_RE.match("pc4")
    assert not NODE_NAME_RE.match("-bad")
    assert not NODE_NAME_RE.match("UPPER")
    assert not NODE_NAME_RE.match("a" * 64)
