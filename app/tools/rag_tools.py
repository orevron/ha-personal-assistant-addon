"""RAG retrieval tool — searches indexed HA data.

Results pass through Content Firewall (M8) before reaching the agent.
Pure Python + local sqlite-vec. No HA dependency.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.tools import tool

from tools.content_firewall import ContentFirewall

_LOGGER = logging.getLogger(__name__)


def create_rag_tool(rag_engine: Any):
    """Create the RAG retrieval tool bound to the given RAGEngine."""

    firewall = ContentFirewall()

    @tool
    async def retrieve_knowledge(query: str) -> str:
        """Search indexed Home Assistant knowledge for relevant information.

        Use this to find information about automations, entities, scenes,
        entity history, and user profile data that has been indexed.

        Args:
            query: Natural language query about your Home Assistant setup.
        """
        try:
            results = await rag_engine.retrieve(query)

            if not results:
                return "No relevant knowledge found in the index."

            # Apply Content Firewall (M8) to RAG results
            clean_results: list[str] = []
            for i, chunk in enumerate(results):
                clean = firewall.sanitize_content(chunk, f"rag_chunk_{i}")
                if clean.strip():
                    clean_results.append(clean)

            if not clean_results:
                return "Knowledge found but filtered by content firewall."

            return "\n\n---\n\n".join(clean_results)

        except Exception as err:
            _LOGGER.error("RAG retrieval failed: %s", err)
            return f"Knowledge retrieval failed: {err}"

    return retrieve_knowledge
