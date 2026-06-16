"""
knowledge_base.py — Local vector store (ChromaDB + Sentence-Transformers)
No API key needed. Stores and retrieves web knowledge for RAG.
"""

import logging
import os
import time
import hashlib
from datetime import datetime, timezone
from typing import Optional

import chromadb
from chromadb.config import Settings

os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("TQDM_DISABLE", "1")

from sentence_transformers import SentenceTransformer

from config import (
    DB_DIR, COLLECTION_NAME, EMBED_MODEL, TOP_K_RESULTS,
    SIMILARITY_THRESHOLD, VECTOR_DB_MAX_SIZE
)

log = logging.getLogger("KnowledgeBase")


class KnowledgeBase:
    """
    Local vector knowledge base.
    - Embeds text using a local sentence-transformer model (no API key)
    - Stores vectors in ChromaDB (persisted on disk)
    - Retrieves semantically similar documents for RAG context
    """

    def __init__(self):
        log.info("Loading embedding model: %s ...", EMBED_MODEL)
        self.embedder = SentenceTransformer(EMBED_MODEL)
        self.embedder.encode("warmup", normalize_embeddings=True, show_progress_bar=False)

        self.client = chromadb.PersistentClient(
            path=str(DB_DIR),
            settings=Settings(anonymized_telemetry=False)
        )

        self.collection = self.client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"}
        )
        log.info("Knowledge base ready. Documents stored: %d", self.count())

    # ── Write ──────────────────────────────────────────────────────────────

    def add_document(
        self,
        text: str,
        source: str = "web",
        title: str = "",
        topic: str = ""
    ) -> bool:
        """Embed and store a document. Returns False if already exists."""
        if not text or len(text.strip()) < 40:
            return False

        doc_id = hashlib.md5(text[:500].encode()).hexdigest()

        # Skip duplicates
        try:
            existing = self.collection.get(ids=[doc_id])
            if existing["ids"]:
                return False
        except Exception:
            pass

        embedding = self.embedder.encode(
            text, normalize_embeddings=True, show_progress_bar=False
        ).tolist()

        self.collection.add(
            ids=[doc_id],
            embeddings=[embedding],
            documents=[text],
            metadatas=[{
                "source":    source,
                "title":     title[:200],
                "topic":     topic,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "length":    len(text),
            }]
        )

        # Prune if over max size
        if self.count() > VECTOR_DB_MAX_SIZE:
            self._prune_oldest(200)

        return True

    def add_documents_batch(self, docs: list[dict]) -> int:
        """Add multiple documents. Each dict: {text, source, title, topic}."""
        added = 0
        for doc in docs:
            if self.add_document(**doc):
                added += 1
        log.info("Batch insert: %d/%d new documents added.", added, len(docs))
        return added

    # ── Read ───────────────────────────────────────────────────────────────

    def search(
        self,
        query: str,
        top_k: int = TOP_K_RESULTS,
        topic_filter: Optional[str] = None
    ) -> list[dict]:
        """
        Semantic search over stored knowledge.
        Returns list of {text, source, title, topic, score}.
        """
        if self.count() == 0:
            return []

        query_emb = self.embedder.encode(
            query, normalize_embeddings=True, show_progress_bar=False
        ).tolist()

        where = {"topic": topic_filter} if topic_filter else None

        try:
            results = self.collection.query(
                query_embeddings=[query_emb],
                n_results=min(top_k, self.count()),
                where=where,
                include=["documents", "metadatas", "distances"]
            )
        except Exception as e:
            log.warning("Search error: %s", e)
            return []

        hits = []
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0]
        ):
            similarity = 1.0 - dist   # cosine distance → similarity
            if similarity >= SIMILARITY_THRESHOLD:
                hits.append({
                    "text":   doc,
                    "source": meta.get("source", ""),
                    "title":  meta.get("title", ""),
                    "topic":  meta.get("topic", ""),
                    "score":  round(similarity, 4),
                })

        hits.sort(key=lambda x: x["score"], reverse=True)
        return hits

    def build_rag_context(self, query: str, max_chars: int = 3000) -> str:
        """Build a RAG context string to inject into the LLM prompt."""
        hits = self.search(query)
        if not hits:
            return ""

        parts = ["### Relevant Knowledge (from web):\n"]
        total = 0
        for i, h in enumerate(hits, 1):
            snippet = h["text"][:800].strip()
            source  = h["source"]
            title   = h["title"] or source
            entry   = f"[{i}] **{title}** ({source})\n{snippet}\n"
            if total + len(entry) > max_chars:
                break
            parts.append(entry)
            total += len(entry)

        return "\n".join(parts)

    # ── Maintenance ────────────────────────────────────────────────────────

    def count(self) -> int:
        return self.collection.count()

    def _prune_oldest(self, n: int = 100):
        """Remove the N oldest documents to keep DB size manageable."""
        try:
            all_docs = self.collection.get(include=["metadatas"])
            pairs = sorted(
                zip(all_docs["ids"], all_docs["metadatas"]),
                key=lambda x: x[1].get("timestamp", "")
            )
            old_ids = [p[0] for p in pairs[:n]]
            self.collection.delete(ids=old_ids)
            log.info("Pruned %d old documents from knowledge base.", len(old_ids))
        except Exception as e:
            log.warning("Prune failed: %s", e)

    def stats(self) -> dict:
        return {
            "total_documents": self.count(),
            "embed_model":     EMBED_MODEL,
            "collection":      COLLECTION_NAME,
            "db_path":         str(DB_DIR),
        }
