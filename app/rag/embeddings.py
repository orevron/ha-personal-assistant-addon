"""Embedding model interface — Ollama nomic-embed-text.

Communicates directly with Ollama API for embedding generation.
No HA dependency.
"""

from __future__ import annotations

import logging
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)


class EmbeddingModel:
    """Generate embeddings via Ollama API."""

    def __init__(self, ollama_url: str, model: str = "nomic-embed-text") -> None:
        self._url = f"{ollama_url.rstrip('/')}/api/embed"
        self._model = model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a list of texts.

        Args:
            texts: List of text strings to embed.

        Returns:
            List of embedding vectors (list of floats).
        """
        if not texts:
            return []

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self._url,
                    json={"model": self._model, "input": texts},
                    timeout=aiohttp.ClientTimeout(total=60),
                ) as resp:
                    resp.raise_for_status()
                    data = await resp.json()
                    return data.get("embeddings", [])
        except aiohttp.ClientError as err:
            _LOGGER.error("Embedding request failed: %s", err)
            raise

    async def embed_single(self, text: str) -> list[float]:
        """Generate embedding for a single text string."""
        results = await self.embed([text])
        if results:
            return results[0]
        raise ValueError("No embedding returned")
