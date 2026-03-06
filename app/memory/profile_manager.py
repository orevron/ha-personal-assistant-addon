"""Profile Manager — CRUD operations for user profile entries.

Stores learned preferences, habits, patterns, and facts about the user.
Pure Python + local SQLite at /data/assistant.db.
"""

from __future__ import annotations

import logging
from typing import Any

import aiosqlite

_LOGGER = logging.getLogger(__name__)


class ProfileManager:
    """Manages user profile entries in SQLite."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    async def get_entries(
        self,
        category: str | None = None,
        key: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get profile entries, optionally filtered."""
        query = "SELECT * FROM profile_entries WHERE 1=1"
        params: list[Any] = []

        if category:
            query += " AND category = ?"
            params.append(category)
        if key:
            query += " AND key = ?"
            params.append(key)

        query += " ORDER BY last_seen DESC"

        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, params) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def get_relevant_entries(
        self, query: str, limit: int = 10
    ) -> list[dict[str, Any]]:
        """Get profile entries relevant to a query (keyword-based)."""
        query_lower = query.lower()
        keywords = set(query_lower.split())

        all_entries = await self.get_entries()
        scored: list[tuple[int, dict]] = []

        for entry in all_entries:
            score = 0
            entry_text = (
                f"{entry.get('category', '')} {entry.get('key', '')} "
                f"{entry.get('value', '')}"
            ).lower()

            for kw in keywords:
                if kw in entry_text:
                    score += 1

            if score > 0:
                scored.append((score, entry))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [e for _, e in scored[:limit]]

    async def upsert_entry(
        self,
        category: str,
        key: str,
        value: str,
        source: str = "told",
        sensitivity: str = "private",
        confidence: float = 0.5,
    ) -> None:
        """Insert or update a profile entry."""
        async with aiosqlite.connect(self._db_path) as db:
            # Check if entry exists
            async with db.execute(
                "SELECT id, occurrence_count, confidence FROM profile_entries "
                "WHERE category = ? AND key = ?",
                (category, key),
            ) as cursor:
                existing = await cursor.fetchone()

            if existing:
                # Update existing entry — increase confidence and count
                new_count = existing[1] + 1
                new_confidence = min(
                    1.0, existing[2] + 0.1
                )  # Increase confidence
                await db.execute(
                    "UPDATE profile_entries SET value = ?, confidence = ?, "
                    "occurrence_count = ?, last_seen = CURRENT_TIMESTAMP, "
                    "source = ? WHERE category = ? AND key = ?",
                    (value, new_confidence, new_count, source, category, key),
                )
            else:
                # Insert new entry
                await db.execute(
                    "INSERT INTO profile_entries "
                    "(category, key, value, confidence, sensitivity, source) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (category, key, value, confidence, sensitivity, source),
                )

            await db.commit()
            _LOGGER.info(
                "Profile %s: %s/%s = %s",
                "updated" if existing else "created",
                category,
                key,
                value[:50],
            )

    async def delete_entry(self, category: str, key: str) -> bool:
        """Delete a profile entry."""
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "DELETE FROM profile_entries WHERE category = ? AND key = ?",
                (category, key),
            )
            await db.commit()
            return cursor.rowcount > 0
