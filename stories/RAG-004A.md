# RAG-004A — Contrat d'ancrage vérifiable (FAI-U-004, DESIGN_FIRST)

Livrable : `CANON/adr/ADR-RAG-004A-grounding-contract.md` (ADR, design pur).

## Défaut prouvé
`src/forgeai/rag/hardened.py:101` : `scan_output(answer, context_used=True)` — booléen CODÉ EN DUR ->
`src/forgeai/guardrails/io_guard.py:59-60` (`if not context_used: raise ...`) est du CODE MORT ; l'ancrage
runtime n'est jamais vérifié.

## Décision (ADR)
Remplace le booléen par un contrat CALCULABLE : états grounded / ungrounded / unknown avec oracle de test
par transition, citations à provenance vérifiable, politique de refus (une réponse sans preuve n'est jamais
présentée comme ancrée), métriques, et interface retrieval -> guardrail -> réponse. Contrat d'implémentation/
test/migration/rollback fourni pour RAG-005 (runtime) et RAG-004B (câblage).

## Nature
DESIGN_FIRST : aucun code produit. Approbation finale = Nathan (gate). Arrêt après fusion de l'ADR ;
l'implémentation appartient à RAG-005/RAG-004B.
