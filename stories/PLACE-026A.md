# PLACE-026A — Câbler le placement par service (FAI-U-026)

## Cause racine
`planner/assemble.py::assemble_plan` ne peuplait JAMAIS `ServiceSpec.node` (zéro occurrence de `node=`) :
la capacité de placement par service, pourtant supportée par le renderer k3s, était MORTE. Conséquence
documentée par l'audit : `rag_node` était appliqué comme nœud GLOBAL au rendu -> relocalisation
SILENCIEUSE de TOUT le plan au lieu des seuls services RAG.

## Changement (minimal, rétro-compatible)
Deux paramètres keyword-only avec défauts (`placement: dict[str,str] | None`, `rag_node: str | None`) :
- `placement` = décision EXPLICITE par service ({nom: noeud}), PRIME sur rag_node ;
- `rag_node` ne relocalise QUE les services du périmètre RAG (`_RAG_SERVICES`, liste explicite) ;
- `node=` passé au constructeur ServiceSpec dans LES DEUX boucles (stack minimal + briques châssis) ;
- `plan.placement_reasons` expose la RAISON de chaque placement (vide si aucun placement).

## Preuves
- ROUGE : reviews/PLACE-026A/RED-reproduction.txt (3 tests : TypeError, params inexistants -> capacité morte).
- VERTE : reviews/PLACE-026A/GREEN-focused.txt (17/17). Suite complète verte (0 régression).
- no-stub-scan OK (264 fichiers) ; gitleaks 0.
- Rétro-compat prouvée : appel sans les nouveaux paramètres -> node=None partout, reasons vide.

## Périmètre
assemble.py, tests/test_placement_noeud.py — tous allowed_paths. (models.py non modifié : `node` existait déjà.)

## Rollback
`git revert` -> retire les paramètres et la traçabilité ; baseline origin/main reste verte.
