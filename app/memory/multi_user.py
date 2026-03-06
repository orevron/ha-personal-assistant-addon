"""Multi-user profile support.

Extends the ProfileManager to support per-user profiles identified
by Telegram chat_id. Each user gets their own set of profile entries,
conversation sessions, and learned patterns.

Pure Python + local SQLite.
"""

from __future__ import annotations

import logging
from typing import Any

import aiosqlite

_LOGGER = logging.getLogger(__name__)


# Additional schema for multi-user support
MULTI_USER_SCHEMA = """
CREATE TABLE IF NOT EXISTS user_profiles (
    chat_id INTEGER PRIMARY KEY,
    display_name TEXT,
    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE,
    settings TEXT DEFAULT '{}'
);

-- Add chat_id column to profile_entries if not present
-- (handled via migration check in code)
"""


class MultiUserManager:
    """Manages per-user profiles for multi-user support."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._initialized = False

    async def ensure_initialized(self) -> None:
        """Create multi-user tables if they don't exist."""
        if self._initialized:
            return

        async with aiosqlite.connect(self._db_path) as db:
            await db.executescript(MULTI_USER_SCHEMA)

            # Check if profile_entries has chat_id column, add if missing
            cursor = await db.execute("PRAGMA table_info(profile_entries)")
            columns = [row[1] async for row in cursor]
            if "chat_id" not in columns:
                await db.execute(
                    "ALTER TABLE profile_entries ADD COLUMN chat_id INTEGER DEFAULT 0"
                )
                _LOGGER.info("Added chat_id column to profile_entries")

            await db.commit()
            self._initialized = True

    async def get_or_create_user(
        self, chat_id: int, display_name: str = ""
    ) -> dict[str, Any]:
        """Get or create a user profile."""
        await self.ensure_initialized()

        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row

            async with db.execute(
                "SELECT * FROM user_profiles WHERE chat_id = ?",
                (chat_id,),
            ) as cursor:
                row = await cursor.fetchone()

            if row:
                # Update last_seen and display_name
                await db.execute(
                    "UPDATE user_profiles SET last_seen = CURRENT_TIMESTAMP, "
                    "display_name = COALESCE(NULLIF(?, ''), display_name) "
                    "WHERE chat_id = ?",
                    (display_name, chat_id),
                )
                await db.commit()
                return dict(row)

            # Create new user
            await db.execute(
                "INSERT INTO user_profiles (chat_id, display_name) VALUES (?, ?)",
                (chat_id, display_name),
            )
            await db.commit()
            _LOGGER.info(
                "New user created: chat_id=%s, name=%s", chat_id, display_name
            )
            return {
                "chat_id": chat_id,
                "display_name": display_name,
                "is_active": True,
                "settings": "{}",
            }

    async def get_all_users(self) -> list[dict[str, Any]]:
        """Get all registered users."""
        await self.ensure_initialized()

        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM user_profiles WHERE is_active = TRUE "
                "ORDER BY last_seen DESC"
            ) as cursor:
                return [dict(row) async for row in cursor]

    async def get_user_chat_ids(self) -> list[int]:
        """Get all active user chat IDs (for proactive notifications)."""
        users = await self.get_all_users()
        return [u["chat_id"] for u in users]

    async def update_user_settings(
        self, chat_id: int, settings: dict[str, Any]
    ) -> None:
        """Update user-specific settings."""
        import json

        await self.ensure_initialized()

        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "UPDATE user_profiles SET settings = ? WHERE chat_id = ?",
                (json.dumps(settings), chat_id),
            )
            await db.commit()
