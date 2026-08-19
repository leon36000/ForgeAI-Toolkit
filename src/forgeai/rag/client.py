"""Stories P1-S08/S09 — ingestion de documents et réponse RAG (codeur : kimi/fable).

Client stdlib pur (urllib) vers les briques déployées : Ollama (embeddings +
génération) et Qdrant (stockage/recherche vectorielle). La preuve e2e du plan
maître : la réponse à une question DOIT contenir un fait du document ingéré.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass

from forgeai.core.validation import valider_schema_url
from forgeai.i18n import t


def _post(url: str, payload: dict, timeout_s: float = 300.0) -> dict:
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    valider_schema_url(url)
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _put(url: str, payload: dict, timeout_s: float = 60.0) -> dict:
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="PUT",
    )
    valider_schema_url(url)
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        return json.loads(resp.read().decode("utf-8"))


def chunk_text(text: str, max_chars: int = 800) -> list[str]:
    """Découpe par paragraphes, regroupés sous max_chars (chunks non vides)."""
    chunks, current = [], ""
    for para in text.split("\n\n"):
        para = para.strip()
        if not para:
            continue
        if current and len(current) + len(para) + 2 > max_chars:
            chunks.append(current)
            current = para
        else:
            current = f"{current}\n\n{para}" if current else para
    if current:
        chunks.append(current)
    return chunks


@dataclass
class RagClient:
    ollama_url: str      # ex. http://127.0.0.1:21434
    qdrant_url: str      # ex. http://127.0.0.1:26333
    llm_model: str
    embed_model: str
    collection: str = "forgeai-p1"

    def pull_models(self) -> None:
        for model in (self.llm_model, self.embed_model):
            _post(f"{self.ollama_url}/api/pull", {"model": model, "stream": False},
                  timeout_s=900.0)

    def _embed(self, texts: list[str]) -> list[list[float]]:
        result = _post(f"{self.ollama_url}/api/embed",
                       {"model": self.embed_model, "input": texts})
        return result["embeddings"]

    def ensure_collection(self, dim: int) -> None:
        """Idempotente : 409 = la collection existe déjà (re-run du wizard sur une
        machine ayant déjà déployé) — cas légitime, pas une erreur (corrective #49,
        trouvée au premier déploiement UI réel du 2026-07-19)."""
        try:
            _put(f"{self.qdrant_url}/collections/{self.collection}",
                 {"vectors": {"size": dim, "distance": "Cosine"}})
        except urllib.error.HTTPError as exc:
            if exc.code != 409:
                raise

    def ingest(self, text: str, source: str) -> int:
        chunks = chunk_text(text)
        if not chunks:
            raise ValueError(t("rag.client.ingest.document_vide"))
        vectors = self._embed(chunks)
        self.ensure_collection(dim=len(vectors[0]))
        points = [
            {
                "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"{self.collection}:{source}:{i}")),
                "vector": vec,
                "payload": {"text": chunk, "source": source},
            }
            for i, (chunk, vec) in enumerate(zip(chunks, vectors))
        ]
        _put(f"{self.qdrant_url}/collections/{self.collection}/points?wait=true",
             {"points": points})
        return len(points)

    def _search(self, question: str, top_k: int = 3) -> list[dict]:
        vector = self._embed([question])[0]
        result = _post(
            f"{self.qdrant_url}/collections/{self.collection}/points/search",
            {"vector": vector, "limit": top_k, "with_payload": True},
        )
        return result.get("result", [])

    def ask(self, question: str, top_k: int = 3) -> dict:
        hits = self._search(question, top_k)
        if not hits:
            return {"answer": "", "sources": [], "context_used": False}
        context = "\n---\n".join(h["payload"]["text"] for h in hits)
        prompt = (
            "Réponds à la question UNIQUEMENT à partir du contexte fourni, "
            "en une ou deux phrases factuelles.\n\n"
            f"CONTEXTE:\n{context}\n\nQUESTION: {question}\nRÉPONSE:"
        )
        result = _post(f"{self.ollama_url}/api/generate",
                       {"model": self.llm_model, "prompt": prompt, "stream": False})
        return {
            "answer": result.get("response", "").strip(),
            "sources": sorted({h["payload"]["source"] for h in hits}),
            "context_used": True,
        }
