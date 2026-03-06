"""Web search tool — DuckDuckGo with PII sanitizer and Content Firewall.

Pipeline: Agent query → PII Sanitizer (M1) → DuckDuckGo → Content Firewall (M8) → Agent

All queries are logged to search_audit_log for auditing.
Pure Python — no HA dependency.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.tools import tool

from tools.sanitizer import PIISanitizer
from tools.content_firewall import ContentFirewall

_LOGGER = logging.getLogger(__name__)


def create_search_tool(config: dict[str, Any]):
    """Create the web search tool with PII sanitizer and content firewall."""

    sanitizer = PIISanitizer(config)
    firewall = ContentFirewall()

    @tool
    async def search_web(query: str) -> str:
        """Search the internet using DuckDuckGo.

        IMPORTANT: Never include personal information in searches.
        Use only generic, anonymized terms. If you need specific home
        data, use HA tools or RAG instead.

        Args:
            query: The search query. Must not contain PII.
        """
        # 1. Sanitize query (M1)
        sanitized_query, was_blocked, reason = sanitizer.sanitize_search_query(
            query
        )

        # Log to audit (will be persisted by the learning worker)
        _LOGGER.info(
            "Search query: original='%s', sanitized='%s', blocked=%s, reason='%s'",
            query[:50],
            sanitized_query[:50] if sanitized_query else "",
            was_blocked,
            reason,
        )

        if was_blocked:
            return (
                f"Search BLOCKED by PII sanitizer: {reason}\n"
                "Please reformulate your query using generic terms. "
                "Remove all personal names, entity IDs, IP addresses, "
                "and location-specific information."
            )

        # 2. Execute search
        try:
            from duckduckgo_search import AsyncDDGS

            async with AsyncDDGS() as ddgs:
                results = []
                async for result in ddgs.atext(
                    sanitized_query, max_results=5
                ):
                    results.append(result)

            if not results:
                return "No search results found."

            # 3. Apply Content Firewall (M8) to results
            output_parts: list[str] = []
            for i, result in enumerate(results, 1):
                title = result.get("title", "")
                body = result.get("body", "")
                href = result.get("href", "")

                # Firewall each result
                clean_title = firewall.sanitize_content(title, f"search_title_{i}")
                clean_body = firewall.sanitize_content(body, f"search_body_{i}")

                output_parts.append(
                    f"{i}. **{clean_title}**\n"
                    f"   {clean_body}\n"
                    f"   URL: {href}"
                )

            return "\n\n".join(output_parts)

        except ImportError:
            return "Web search unavailable: duckduckgo-search not installed."
        except Exception as err:
            _LOGGER.error("Search failed: %s", err)
            return f"Search failed: {err}"

    return search_web
