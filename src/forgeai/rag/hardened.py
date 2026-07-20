"""Client RAG DURCI (stories E2a + E2b).

Hérite de RagClient (DRY) et surcharge le chemin durci :
  - embeddings via TEI (bge-m3), génération via la passerelle LiteLLM authentifiée (E2a) ;
  - rerank optionnel via une 2e instance TEI (bge-reranker-v2-m3, endpoint /rerank) inséré entre
    le retrieval Qdrant élargi et la génération (E2b). `reranker_url` vide == chemin E2a inchangé.
La clé Bearer n'est JAMAIS journalisée.
"""
from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass

from forgeai.rag.client import RagClient, _post


def _post_bearer(url: str, payload: dict, bearer: str, timeout_s: float = 300.0) -> dict:
    """POST authentifié Bearer. Ne journalise JAMAIS la clé."""
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {bearer}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        return json.loads(resp.read().decode("utf-8"))


@dataclass
class HardenedRagClient(RagClient):
    """Client RAG durci : embeddings via TEI, génération via la passerelle LiteLLM."""

    tei_url: str = ""
    gateway_url: str = ""
    gateway_key: str = ""
    collection: str = "forgeai-rag-durci"
    reranker_url: str = ""

    def __post_init__(self) -> None:
        if not self.tei_url or not self.gateway_url or not self.gateway_key:
            raise ValueError("tei_url, gateway_url et gateway_key sont obligatoires")

    def _embed(self, texts: list[str]) -> list[list[float]]:
        """POST TEI /embed {'inputs': [...]} -> liste BRUTE de vecteurs (un par entrée)."""
        return _post(f"{self.tei_url}/embed", {"inputs": texts})

    def _rerank(self, query: str, hits: list[dict]) -> list[dict]:
        """Réordonne les hits via le service de reranking externe."""
        ranked = _post(
            f"{self.reranker_url}/rerank",
            {"query": query, "texts": [h["payload"]["text"] for h in hits]},
        )
        ordered = [
            hits[it["index"]]
            for it in ranked
            if isinstance(it.get("index"), int) and 0 <= it["index"] < len(hits)
        ]
        return ordered or hits

    def ask(self, question: str, top_k: int = 3, candidates: int = 20) -> dict:
        """Retrieval (élargi à `candidates` si rerank actif) -> rerank optionnel -> top_k ->
        génération via la passerelle. Retrieval vide -> réponse vide sans fabrication (jamais
        de POST /rerank sur un retrieval vide : contrôle négatif préservé)."""
        k = candidates if self.reranker_url else top_k
        hits = self._search(question, k)
        if not hits:
            return {"answer": "", "sources": [], "context_used": False}
        if self.reranker_url:
            hits = self._rerank(question, hits)[:top_k]
        else:
            hits = hits[:top_k]
        context = "\n---\n".join(h["payload"]["text"] for h in hits)
        prompt = (
            "Réponds à la question UNIQUEMENT à partir du contexte fourni, "
            "en une ou deux phrases factuelles.\n\n"
            f"CONTEXTE:\n{context}\n\nQUESTION: {question}\nRÉPONSE:"
        )
        response = _post_bearer(
            f"{self.gateway_url}/v1/chat/completions",
            {"model": self.llm_model, "messages": [{"role": "user", "content": prompt}]},
            self.gateway_key,
        )
        answer = response["choices"][0]["message"]["content"].strip()
        return {
            "answer": answer,
            "sources": sorted({h["payload"]["source"] for h in hits}),
            "context_used": True,
        }

    def pull_models(self) -> None:
        """Tire UNIQUEMENT le LLM via Ollama (l'embed est servi par TEI)."""
        _post(f"{self.ollama_url}/api/pull",
              {"model": self.llm_model, "stream": False}, timeout_s=900.0)
