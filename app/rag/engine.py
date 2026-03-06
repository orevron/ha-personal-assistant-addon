"""RAG Engine — sqlite-vec based retrieval pipeline.

Stores embeddings in the same SQLite database alongside profile/memory.
Uses sqlite-vec for KNN vector search.

HA data is fetched via HAClient REST API instead of hass object.
Database lives at /data/assistant.db.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from typing import Any

from rag.embeddings import EmbeddingModel
from rag.indexer import RAGIndexer

_LOGGER = logging.getLogger(__name__)

# Paths to try for the sqlite-vec loadable extension (.so)
_VEC_EXTENSION_PATHS = [
    os.environ.get("SQLITE_VEC_PATH", ""),
    "/usr/local/lib/sqlite-vec/vec0",
    "/usr/lib/sqlite3/vec0",
    "vec0",
]


class RAGEngine:
    """RAG retrieval engine with sqlite-vec vector search."""

    def __init__(
        self,
        config: dict[str, Any],
        ha_client: Any,
        db_path: str,
    ) -> None:
        self._config = config
        self._ha = ha_client
        self._db_path = db_path
        self._embedding_model = EmbeddingModel(
            ollama_url=config.get("ollama_url", "http://192.168.1.97:11434"),
            model=config.get("embedding_model", "nomic-embed-text"),
        )
        self._indexer = RAGIndexer(
            ha_client=ha_client,
            embedding_model=self._embedding_model,
            db_path=db_path,
        )
        self._initialized = False
        self._has_vec_extension = False

    async def _ensure_initialized(self) -> None:
        """Ensure the RAG tables and sqlite-vec extension are loaded."""
        if self._initialized:
            return

        conn = sqlite3.connect(self._db_path)
        try:
            # Try to load sqlite-vec extension from known paths
            try:
                conn.enable_load_extension(True)
                loaded = False
                for ext_path in _VEC_EXTENSION_PATHS:
                    if not ext_path:
                        continue
                    try:
                        conn.load_extension(ext_path)
                        self._has_vec_extension = True
                        loaded = True
                        _LOGGER.info(
                            "Loaded sqlite-vec extension from %s", ext_path
                        )
                        break
                    except Exception:
                        continue
                if not loaded:
                    _LOGGER.warning(
                        "Could not load sqlite-vec extension from any path — "
                        "using fallback cosine similarity"
                    )
            except Exception:
                _LOGGER.warning(
                    "SQLite extension loading not supported — "
                    "using fallback cosine similarity"
                )

            # Create RAG tables
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS rag_documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata TEXT,
                    embedding BLOB,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_rag_source
                    ON rag_documents(source);
            """)

            conn.commit()
            self._initialized = True
            _LOGGER.info("RAG engine initialized")
        finally:
            conn.close()

    async def full_reindex(self) -> None:
        """Perform a full re-index of all HA data sources."""
        await self._ensure_initialized()
        await self._indexer.index_all()

    async def reindex_history(self) -> None:
        """Re-index entity history data only."""
        await self._ensure_initialized()
        await self._indexer.index_history()

    async def retrieve(
        self, query: str, top_k: int | None = None
    ) -> list[str]:
        """Retrieve the most relevant chunks for a query.

        Args:
            query: Natural language query.
            top_k: Number of results (default from config or 5).

        Returns:
            List of relevant text chunks.
        """
        await self._ensure_initialized()

        from const import DEFAULT_RAG_TOP_K
        k = top_k or self._config.get("rag_top_k", DEFAULT_RAG_TOP_K)

        try:
            # Generate query embedding
            query_embedding = await self._embedding_model.embed_single(query)

            # Retrieve using cosine similarity
            return await self._search_by_embedding(query_embedding, k)
        except Exception:
            _LOGGER.exception("RAG retrieval failed")
            return []

    async def _search_by_embedding(
        self, embedding: list[float], top_k: int
    ) -> list[str]:
        """Search for similar documents using embedding similarity.

        Uses sqlite-vec KNN if available, falls back to Python-based
        cosine similarity.
        """
        import struct

        conn = sqlite3.connect(self._db_path)
        try:
            # Serialize embedding to bytes for comparison
            results: list[tuple[float, str]] = []

            cursor = conn.execute(
                "SELECT content, embedding FROM rag_documents WHERE embedding IS NOT NULL"
            )
            for row in cursor:
                content = row[0]
                stored_embedding_bytes = row[1]
                if stored_embedding_bytes:
                    # Deserialize stored embedding
                    dim = len(embedding)
                    stored = list(
                        struct.unpack(f"{dim}f", stored_embedding_bytes)
                    )
                    # Cosine similarity
                    sim = self._cosine_similarity(embedding, stored)
                    results.append((sim, content))

            # Sort by similarity descending
            results.sort(key=lambda x: x[0], reverse=True)
            return [content for _, content in results[:top_k]]
        finally:
            conn.close()

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        """Compute cosine similarity between two vectors."""
        import math

        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)
