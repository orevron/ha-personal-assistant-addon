"""RAG Indexer — fetches HA data and indexes it for RAG retrieval.

Indexed content:
  - Entity registry (entity_id, friendly_name, domain, area, device)
  - Automations (name, triggers, conditions, actions)
  - Scenes (name, entities, states)
  - Entity history (summarized recent states)
  - User profile entries

HA data fetched via HAClient REST API instead of hass object.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import struct
from datetime import datetime, timedelta, timezone
from typing import Any

_LOGGER = logging.getLogger(__name__)


class RAGIndexer:
    """Indexes HA data into the RAG sqlite-vec store."""

    def __init__(
        self,
        ha_client: Any,
        embedding_model: Any,
        db_path: str,
    ) -> None:
        self._ha = ha_client
        self._embeddings = embedding_model
        self._db_path = db_path

    async def index_all(self) -> None:
        """Full re-index of all data sources."""
        _LOGGER.info("Starting full RAG re-index...")

        await self._index_entities()
        await self._index_automations()
        await self._index_scenes()
        await self._index_history()
        await self._index_profile()

        _LOGGER.info("Full RAG re-index complete")

    async def index_history(self) -> None:
        """Re-index entity history only."""
        await self._index_history()

    async def _index_entities(self) -> None:
        """Index all HA entities."""
        try:
            states = await self._ha.get_states()
            documents: list[tuple[str, str, str]] = []

            for state in states:
                entity_id = state.get("entity_id", "")
                friendly_name = state.get("attributes", {}).get(
                    "friendly_name", entity_id
                )
                domain = entity_id.split(".")[0] if "." in entity_id else ""
                area = state.get("attributes", {}).get("area", "")
                current_state = state.get("state", "unknown")

                content = (
                    f"Entity: {friendly_name}\n"
                    f"ID: {entity_id}\n"
                    f"Domain: {domain}\n"
                    f"Area: {area}\n"
                    f"Current state: {current_state}"
                )
                metadata = json.dumps({
                    "type": "entity",
                    "entity_id": entity_id,
                    "domain": domain,
                })
                documents.append(("entity", content, metadata))

            await self._store_documents(documents, "entity")
            _LOGGER.info("Indexed %d entities", len(documents))
        except Exception:
            _LOGGER.exception("Failed to index entities")

    async def _index_automations(self) -> None:
        """Index automations."""
        try:
            states = await self._ha.get_states()
            documents: list[tuple[str, str, str]] = []

            for state in states:
                entity_id = state.get("entity_id", "")
                if not entity_id.startswith("automation."):
                    continue

                friendly_name = state.get("attributes", {}).get(
                    "friendly_name", entity_id
                )
                current_state = state.get("state", "")
                last_triggered = state.get("attributes", {}).get(
                    "last_triggered", ""
                )

                content = (
                    f"Automation: {friendly_name}\n"
                    f"ID: {entity_id}\n"
                    f"Status: {current_state}\n"
                    f"Last triggered: {last_triggered}"
                )
                metadata = json.dumps({
                    "type": "automation",
                    "entity_id": entity_id,
                })
                documents.append(("automation", content, metadata))

            await self._store_documents(documents, "automation")
            _LOGGER.info("Indexed %d automations", len(documents))
        except Exception:
            _LOGGER.exception("Failed to index automations")

    async def _index_scenes(self) -> None:
        """Index scenes."""
        try:
            states = await self._ha.get_states()
            documents: list[tuple[str, str, str]] = []

            for state in states:
                entity_id = state.get("entity_id", "")
                if not entity_id.startswith("scene."):
                    continue

                friendly_name = state.get("attributes", {}).get(
                    "friendly_name", entity_id
                )

                content = (
                    f"Scene: {friendly_name}\n"
                    f"ID: {entity_id}"
                )
                metadata = json.dumps({
                    "type": "scene",
                    "entity_id": entity_id,
                })
                documents.append(("scene", content, metadata))

            await self._store_documents(documents, "scene")
            _LOGGER.info("Indexed %d scenes", len(documents))
        except Exception:
            _LOGGER.exception("Failed to index scenes")

    async def _index_history(self) -> None:
        """Index recent entity history summaries."""
        try:
            start_time = (
                datetime.now(timezone.utc) - timedelta(hours=24)
            ).isoformat()
            history = await self._ha.get_history(start_time=start_time)

            documents: list[tuple[str, str, str]] = []
            for entity_history in (history or []):
                if not entity_history:
                    continue

                entity_id = entity_history[0].get("entity_id", "")
                states_summary = []
                for entry in entity_history[:10]:
                    states_summary.append(
                        f"  {entry.get('state')} at {entry.get('last_changed', '')}"
                    )

                content = (
                    f"History for {entity_id} (last 24h):\n"
                    + "\n".join(states_summary)
                )
                metadata = json.dumps({
                    "type": "history",
                    "entity_id": entity_id,
                })
                documents.append(("history", content, metadata))

            await self._store_documents(documents, "history")
            _LOGGER.info("Indexed history for %d entities", len(documents))
        except Exception:
            _LOGGER.exception("Failed to index history")

    async def _index_profile(self) -> None:
        """Index user profile entries."""
        try:
            conn = sqlite3.connect(self._db_path)
            cursor = conn.execute(
                "SELECT category, key, value FROM profile_entries"
            )
            documents: list[tuple[str, str, str]] = []

            for row in cursor:
                content = f"User {row[0]}: {row[1]} = {row[2]}"
                metadata = json.dumps({
                    "type": "profile",
                    "category": row[0],
                    "key": row[1],
                })
                documents.append(("profile", content, metadata))

            conn.close()
            await self._store_documents(documents, "profile")
            _LOGGER.info("Indexed %d profile entries", len(documents))
        except Exception:
            _LOGGER.exception("Failed to index profile entries")

    async def _store_documents(
        self,
        documents: list[tuple[str, str, str]],
        source_type: str,
    ) -> None:
        """Store documents with their embeddings in the RAG database.

        Clears existing documents of the same source type before inserting.
        """
        if not documents:
            return

        # Generate embeddings for all documents
        texts = [doc[1] for doc in documents]
        try:
            embeddings = await self._embeddings.embed(texts)
        except Exception:
            _LOGGER.exception("Failed to generate embeddings")
            return

        # Store in database
        conn = sqlite3.connect(self._db_path)
        try:
            # Clear existing documents of this source type
            conn.execute(
                "DELETE FROM rag_documents WHERE source = ?", (source_type,)
            )

            # Insert new documents with embeddings
            for (source, content, metadata), embedding in zip(
                documents, embeddings
            ):
                # Serialize embedding to bytes
                embedding_bytes = struct.pack(f"{len(embedding)}f", *embedding)
                conn.execute(
                    "INSERT INTO rag_documents (source, content, metadata, embedding) "
                    "VALUES (?, ?, ?, ?)",
                    (source, content, metadata, embedding_bytes),
                )

            conn.commit()
        finally:
            conn.close()
