"""Profile tools — agent can read/write user profile entries.

Pure Python + local SQLite. No HA dependency.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.tools import tool

_LOGGER = logging.getLogger(__name__)


def create_profile_tools(profile_manager: Any) -> list:
    """Create profile read/write tools bound to the given ProfileManager."""

    @tool
    async def get_user_profile(
        category: str | None = None, key: str | None = None
    ) -> list[dict[str, Any]]:
        """Read stored user preferences and learned facts.

        Args:
            category: Filter by category (preference, habit, pattern, fact).
            key: Filter by specific key name.
        """
        try:
            entries = await profile_manager.get_entries(
                category=category, key=key
            )
            return [
                {
                    "category": e["category"],
                    "key": e["key"],
                    "value": e["value"],
                    "confidence": e.get("confidence", 0.5),
                    "source": e.get("source", "unknown"),
                }
                for e in entries
            ]
        except Exception as err:
            _LOGGER.error("Error reading profile: %s", err)
            return [{"error": str(err)}]

    @tool
    async def update_user_profile(
        category: str, key: str, value: str, source: str = "told"
    ) -> str:
        """Store a new learning about the user.

        Use this when the user explicitly tells you a preference,
        or when you observe a pattern worth remembering.

        Args:
            category: One of: preference, habit, pattern, fact
            key: A descriptive key (e.g., "preferred_temperature", "wake_time")
            value: The value to store (e.g., "22 degrees", "06:30")
            source: How this was learned: "told" (user said it) or "inferred"
        """
        try:
            await profile_manager.upsert_entry(
                category=category,
                key=key,
                value=value,
                source=source,
            )
            return f"Stored profile entry: {category}/{key} = {value}"
        except Exception as err:
            _LOGGER.error("Error updating profile: %s", err)
            return f"Failed to update profile: {err}"

    return [get_user_profile, update_user_profile]
