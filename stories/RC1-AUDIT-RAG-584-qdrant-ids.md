# AUDIT-RAG #584 — Identifiants Qdrant stables et disjoints entre documents

## Constat vérifié (ne pas re-dériver)

`src/forgeai/rag/client.py::RagClient.ingest()` (lignes 84-96) construit l'`id` de chaque point
Qdrant via `enumerate(zip(chunks, vectors))` — ce compteur repart TOUJOURS de 0 à chaque appel de
`ingest()`, indépendamment de tout appel précédent. Deux documents ingérés séparément dans la même
collection produisent donc des points avec les MÊMES identifiants (0, 1, 2...), et l'upsert Qdrant
(`PUT .../points`) REMPLACE silencieusement le point existant au lieu d'en ajouter un nouveau —
perte de corpus.

Vérifié empiriquement AVANT cette story (ROUGE reproduit, `_embed`/`ensure_collection`/`_put`
mockés) : deux appels successifs `ingest("doc A", "a.md")` puis `ingest("doc B", "b.md")`
produisent chacun un point d'`id` `0` — collision confirmée.

## Livrable attendu

1. **`src/forgeai/rag/client.py`** : remplacer la construction de l'`id` de chaque point dans
   `ingest()` par une identité DÉTERMINISTE et STABLE dérivée d'au minimum la collection, la
   source et l'index du chunk dans le document — un compteur local à l'appel ne suffit plus.
   Utiliser `uuid.uuid5(uuid.NAMESPACE_URL, f"{self.collection}:{source}:{i}")` converti en
   chaîne (`str(...)`) comme `id` du point (Qdrant accepte les UUID string comme identifiant de
   point). Ajouter `import uuid` en tête de fichier (stdlib pur, aucune nouvelle dépendance).
   Remplacer EXACTEMENT ce bloc :
   ```python
           points = [
               {"id": i, "vector": vec, "payload": {"text": chunk, "source": source}}
               for i, (chunk, vec) in enumerate(zip(chunks, vectors))
           ]
   ```
   par :
   ```python
           points = [
               {
                   "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"{self.collection}:{source}:{i}")),
                   "vector": vec,
                   "payload": {"text": chunk, "source": source},
               }
               for i, (chunk, vec) in enumerate(zip(chunks, vectors))
           ]
   ```
   Propriétés garanties par cette construction (ne PAS en dévier) : (a) déterministe — mêmes
   `collection`/`source`/`i` produisent toujours le même UUID, permettant une ré-ingestion
   idempotente du même document (upsert sur le MÊME point, pas de doublon) ; (b) disjoint entre
   documents différents — deux `source` distinctes (même avec un contenu de chunk similaire)
   produisent des UUID distincts pour chaque index `i`, car `source` fait partie de l'espace de
   noms hashé.
2. **`tests/test_rag_units.py`** (fourni en contexte intégral, style `fake_http` déjà établi à
   réutiliser tel quel — NE PAS modifier les tests déjà présents, uniquement AJOUTER) :
   - Test reproduisant EXACTEMENT le scénario de l'issue #584 : deux ingestions successives
     (`ingest("doc A", "a.md")` puis `ingest("doc B", "b.md")`, sources différentes) dans la même
     collection → les IDs de points capturés par les 2 appels sont DISJOINTS (aucune intersection
     entre l'ensemble des IDs du premier appel et celui du second).
   - Test de ré-ingestion idempotente : `ingest(meme_texte, meme_source)` appelé DEUX fois de
     suite → les IDs de points produits par les 2 appels sont IDENTIQUES (même texte, même
     source, même chunking → mêmes UUID déterministes).
   - Test que deux SOURCES différentes avec un contenu de chunk chunké de façon identique
     produisent des IDs différents (isole la contribution de `source` à l'espace de noms, pas
     seulement l'index).

## Contraintes

- Ne PAS modifier `ensure_collection()`, `_search()`, `ask()`, `chunk_text()`, `_embed()` — hors
  périmètre de cette story (uniquement la construction des `id` dans `ingest()`).
- Ne PAS modifier `tests/test_rc1580_tests_aggregate.py` ni aucun autre fichier de test existant.
- Zéro nouvelle dépendance tierce (`uuid` est stdlib).
- Préserver la signature de `ingest(self, text: str, source: str) -> int` (retourne toujours
  `len(points)`, inchangé).
