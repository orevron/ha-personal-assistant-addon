"""Conversation Memory — per-session chat history management.

Each Telegram chat maintains conversation sessions. Sessions expire
after a configurable inactivity timeout. When expired, history is
archived and a fresh session starts.

Pure Python + local SQLite.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import aiosqlite

_LOGGER = logging.getLogger(__name__)


class ConversationMemory:
    """Manages conversation sessions and history."""

    def __init__(
        self, db_path: str, session_timeout_minutes: int = 30
    ) -> None:
        self._db_path = db_path
        self._timeout = timedelta(minutes=session_timeout_minutes)

    async def get_or_create_session(
        self, chat_id: int
    ) -> dict[str, Any]:
        """Get the active session for a chat, or create a new one.

        If the active session has timed out, it's closed and a new one
        is created.
        """
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row

            # Find active session for this chat
            async with db.execute(
                "SELECT * FROM conversation_sessions "
                "WHERE chat_id = ? AND is_active = TRUE "
                "ORDER BY last_activity DESC LIMIT 1",
                (chat_id,),
            ) as cursor:
                row = await cursor.fetchone()

            if row:
                session = dict(row)
                last_activity = datetime.fromisoformat(
                    session["last_activity"]
                )
                now = datetime.now(timezone.utc)

                # Check if session has timed out
                if now - last_activity.replace(tzinfo=timezone.utc) > self._timeout:
                    # Close expired session
                    await db.execute(
                        "UPDATE conversation_sessions SET is_active = FALSE "
                        "WHERE id = ?",
                        (session["id"],),
                    )
                    await db.commit()
                    _LOGGER.info(
                        "Session %s expired for chat %s",
                        session["id"],
                        chat_id,
                    )
                else:
                    # Update last activity
                    await db.execute(
                        "UPDATE conversation_sessions "
                        "SET last_activity = CURRENT_TIMESTAMP "
                        "WHERE id = ?",
                        (session["id"],),
                    )
                    await db.commit()
                    return session

            # Create new session
            session_id = str(uuid.uuid4())
            await db.execute(
                "INSERT INTO conversation_sessions (id, chat_id) VALUES (?, ?)",
                (session_id, chat_id),
            )
            await db.commit()
            _LOGGER.info(
                "New session %s created for chat %s", session_id, chat_id
            )
            return {
                "id": session_id,
                "chat_id": chat_id,
                "is_active": True,
            }

    async def add_message(
        self,
        session_id: str,
        chat_id: int,
        role: str,
        content: str,
    ) -> None:
        """Add a message to the conversation history."""
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "INSERT INTO conversation_history "
                "(session_id, chat_id, role, content) "
                "VALUES (?, ?, ?, ?)",
                (session_id, chat_id, role, content),
            )
            await db.commit()

    async def get_history(
        self, session_id: str, limit: int = 50
    ) -> list[dict[str, Any]]:
        """Get conversation history for a session."""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT role, content, timestamp FROM conversation_history "
                "WHERE session_id = ? ORDER BY timestamp ASC LIMIT ?",
                (session_id, limit),
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
