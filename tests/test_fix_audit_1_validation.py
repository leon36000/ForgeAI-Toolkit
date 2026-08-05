"""Régression FIX-AUDIT-1 : les noms de nœud ne doivent pas accepter de saut de ligne."""
from forgeai.core.validation import NODE_NAME_RE


def test_defaut_node_name_re_accepte_saut_de_ligne_terminal_est_rejete() -> None:
    assert NODE_NAME_RE.match("node1\n") is None
