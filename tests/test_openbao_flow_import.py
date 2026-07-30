"""Test d'import réel multi-OS de forgeai.deploy.openbao_flow.

Ferme l'objection mineure des revues scellées SECRET-020B : l'import conditionnel du
module POSIX `grp` (hérité de PORT-286) était prouvé par mock sous Linux, mais pas par
un import réel sur Windows/macOS. Ce test s'exécute sur les runners `guard-fs-multi-os`
(ubuntu-latest, macos-latest, windows-latest) qui n'installent que pytest : il démontre
que le module s'importe correctement partout et que `resolve_openbao_gid()` bascule sur
le repli documenté (`None`) quand `grp` est absent (Windows).
"""

import os


def test_openbao_flow_import():
    """L'import réel de openbao_flow doit réussir sur tous les OS CI.

    Sur Windows, `grp` n'existe pas : `flow.grp` vaut None et `resolve_openbao_gid()`
    renvoie None. Sur POSIX, `grp` est importé avec succès.
    """
    import forgeai.deploy.openbao_flow as flow

    gid = flow.resolve_openbao_gid()
    assert gid is None or isinstance(gid, int)

    if os.name == "nt":
        # Windows : le module POSIX `grp` est réellement absent -> repli documenté.
        assert flow.grp is None
        assert gid is None
    else:
        # POSIX (Linux/macOS) : le module `grp` est présent (import conditionnel réussi).
        assert flow.grp is not None
