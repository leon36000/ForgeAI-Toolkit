# Réfutation déterministe des 2 objections (Qwen3.6-40B, tour 1 — APPROVE 2/3, 0 critique)

## Objection 1 (mineure) : « pas de séparateur `*` -> params non keyword-only » — FAUX
`assemble.py:110` contient bien `*,` AVANT `placement` (l.115) et `rag_node` (l.116) : ils SONT keyword-only.
Preuve d'exécution : `assemble_plan('minimal-cpu', p, {'a':'b'})` (positionnel) ->
`TypeError: assemble_plan() takes 2 positional arguments but 3 were given`. Le lecteur a mal lu le diff.

## Objection 2 (mineure) : « si DeploymentPlan a slots=True -> AttributeError » — HYPOTHÈSE NON RÉALISÉE
`core/models.py:117` : `@dataclass(frozen=True)` — **sans** `slots=True`. L'ajout d'attribut fonctionne.
Preuve d'exécution : `assemble_plan(..., rag_node='n1').placement_reasons` ->
`{'vector-store': 'service RAG relocalisé via rag_node'}`. Le code gère par ailleurs les deux cas
(object.__setattr__ pour frozen, affectation sinon). Si un futur package ajoutait `slots=True`, ce serait
à lui d'étendre le contrat — hors périmètre PLACE-026A (models.py non modifiable ici sans élargissement).

Conclusion : aucune objection ne tient à la vérification déterministe ; aucune correction de code requise.
Les 2 autres vendors (Gemini, DeepSeek) approuvent sans objection. Verdict retenu : APPROVE 2/3, 0 critique.
