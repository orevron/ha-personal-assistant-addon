"""PII Sanitizer (M1) — strips personal/sensitive data from outbound queries.

Mandatory pre-filter on all web search queries. Ensures no personal
information (names, addresses, phone numbers, entity IDs, IP addresses,
routines) leaks to external search engines.

Pure Python — no HA dependency.
"""

from __future__ import annotations

import logging
import re
from typing import Any

_LOGGER = logging.getLogger(__name__)


class PIISanitizer:
    """Strips personal/sensitive data from outbound queries."""

    # Regex patterns for common PII
    BLOCKED_PATTERNS = [
        # Phone numbers
        r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b",
        # Email addresses
        r"\b[\w.+-]+@[\w-]+\.[\w.]+\b",
        # IP addresses
        r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b",
        # HA entity IDs (domain.object_id)
        r"\b[a-z_]+\.[a-z][a-z0-9_]+\b",
        # URLs with internal hostnames
        r"https?://(?:192\.168|10\.|172\.(?:1[6-9]|2\d|3[01]))\.\S+",
    ]

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        config = config or {}
        self._blocked_keywords: list[str] = [
            kw.lower()
            for kw in config.get("pii_blocked_keywords", [])
        ]
        self._compiled_patterns = [
            re.compile(p, re.IGNORECASE) for p in self.BLOCKED_PATTERNS
        ]

    def sanitize_search_query(self, query: str) -> tuple[str, bool, str]:
        """Sanitize a search query by removing PII.

        Returns:
            Tuple of (sanitized_query, was_blocked, block_reason)
            If was_blocked is True, the query should NOT be executed.
        """
        original = query
        reasons: list[str] = []

        # 1. Check regex patterns
        for pattern in self._compiled_patterns:
            matches = pattern.findall(query)
            if matches:
                for match in matches:
                    query = query.replace(match, "[REDACTED]")
                reasons.append(f"Pattern match: {pattern.pattern}")

        # 2. Check blocked keywords (user-configured names, addresses, etc.)
        query_lower = query.lower()
        for keyword in self._blocked_keywords:
            if keyword in query_lower:
                # Replace the keyword case-insensitively
                query = re.sub(
                    re.escape(keyword), "[REDACTED]", query, flags=re.IGNORECASE
                )
                reasons.append(f"Blocked keyword: {keyword}")

        # 3. If too much was redacted, block entirely
        redacted_count = query.count("[REDACTED]")
        if redacted_count >= 2 or (
            redacted_count >= 1 and len(query.split()) <= 3
        ):
            _LOGGER.warning(
                "Search query BLOCKED (too much PII): '%s' → reasons: %s",
                original[:50],
                reasons,
            )
            return "", True, "; ".join(reasons)

        was_modified = query != original
        if was_modified:
            _LOGGER.info(
                "Search query sanitized: '%s' → '%s'",
                original[:50],
                query[:50],
            )

        return query, False, "; ".join(reasons) if reasons else ""
