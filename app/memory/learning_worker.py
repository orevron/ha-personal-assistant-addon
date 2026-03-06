"""Background Learning Worker — decoupled from response path.

Processes an async queue of interactions independently. Extracts
patterns and updates profile entries. Never in the response path —
zero added latency to user responses.

Pure Python + local SQLite.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import aiosqlite

_LOGGER = logging.getLogger(__name__)


class LearningWorker:
    """Background worker that processes interactions and learns patterns."""

    def __init__(
        self,
        profile_manager: Any,
        llm_router: Any,
        db_path: str,
    ) -> None:
        self._profile_manager = profile_manager
        self._llm_router = llm_router
        self._db_path = db_path
        self._queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._running = False

    async def queue_interaction(
        self,
        session_id: str,
        chat_id: int,
        user_message: str,
        assistant_response: str,
        tools_used: list[str] | None = None,
        entities_mentioned: list[str] | None = None,
    ) -> None:
        """Queue an interaction for background processing.

        This returns immediately — never blocks the response path.
        """
        await self._queue.put({
            "session_id": session_id,
            "chat_id": chat_id,
            "user_message": user_message,
            "assistant_response": assistant_response,
            "tools_used": tools_used or [],
            "entities_mentioned": entities_mentioned or [],
        })

    async def run(self) -> None:
        """Main worker loop — processes queued interactions."""
        self._running = True
        _LOGGER.info("Learning worker started")

        while self._running:
            try:
                # Wait for an interaction (with timeout for graceful shutdown)
                try:
                    interaction = await asyncio.wait_for(
                        self._queue.get(), timeout=60.0
                    )
                except asyncio.TimeoutError:
                    continue

                await self._process_interaction(interaction)

            except asyncio.CancelledError:
                break
            except Exception:
                _LOGGER.exception("Learning worker error")

        _LOGGER.info("Learning worker stopped")

    async def stop(self) -> None:
        """Stop the worker."""
        self._running = False

    async def _process_interaction(
        self, interaction: dict[str, Any]
    ) -> None:
        """Process a single interaction — log it and extract learnings."""
        # 1. Log to interaction_log table
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "INSERT INTO interaction_log "
                "(session_id, chat_id, user_message, assistant_response, "
                "tools_used, entities_mentioned) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    interaction["session_id"],
                    interaction["chat_id"],
                    interaction["user_message"],
                    interaction["assistant_response"],
                    json.dumps(interaction["tools_used"]),
                    json.dumps(interaction["entities_mentioned"]),
                ),
            )
            await db.commit()

        # 2. Extract learnings (simple heuristic-based for now)
        await self._extract_learnings(interaction)

    async def _extract_learnings(
        self, interaction: dict[str, Any]
    ) -> None:
        """Extract potential learnings from an interaction.

        Uses simple heuristics. Can be enhanced with LLM-based
        extraction in the future.
        """
        user_msg = interaction["user_message"].lower()

        # Look for preference statements
        preference_patterns = [
            ("i like", "preference"),
            ("i prefer", "preference"),
            ("i want", "preference"),
            ("my favorite", "preference"),
            ("i usually", "habit"),
            ("i always", "habit"),
            ("i never", "preference"),
            ("call me", "fact"),
            ("my name is", "fact"),
        ]

        for pattern, category in preference_patterns:
            if pattern in user_msg:
                # Extract the value after the pattern
                idx = user_msg.index(pattern)
                value = interaction["user_message"][
                    idx + len(pattern) :
                ].strip()
                if value and len(value) < 200:
                    key = pattern.replace(" ", "_").strip("_")
                    await self._profile_manager.upsert_entry(
                        category=category,
                        key=key,
                        value=value,
                        source="told",
                    )
                    _LOGGER.info(
                        "Learned from conversation: %s/%s = %s",
                        category,
                        key,
                        value[:50],
                    )
                break
