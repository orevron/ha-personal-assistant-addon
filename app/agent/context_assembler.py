"""Context Assembler — Token budget controller (M9).

Builds a token-budgeted context for each LLM call by assembling:
  - System prompt + security rules (fixed)
  - User profile subset (relevant to query)
  - HA context (relevant entities only)
  - Conversation history (summarized if over budget)
  - RAG results (top-k, trimmed to budget)

HA state is fetched via REST API (HAClient) instead of hass object.
"""

from __future__ import annotations

import logging
from typing import Any

from const import DEFAULT_TOKEN_BUDGET

_LOGGER = logging.getLogger(__name__)


def estimate_tokens(text: str) -> int:
    """Rough token estimate — ~4 chars per token for English text."""
    return len(text) // 4


class ContextAssembler:
    """Assembles token-budgeted context for the LLM agent."""

    def __init__(
        self,
        budget: dict[str, int] | None = None,
        total_context_window: int = 8000,
    ) -> None:
        self._budget = budget or DEFAULT_TOKEN_BUDGET.copy()
        self._total_window = total_context_window

        # If total_context_window is larger than default 8K, scale budgets
        if total_context_window > 8000:
            scale = total_context_window / 8000
            self._budget = {
                k: int(v * scale) for k, v in self._budget.items()
            }

    async def build_context(
        self,
        query: str,
        ha_client: Any,
        profile_manager: Any,
        conversation_history: list[dict] | None = None,
        rag_results: list[str] | None = None,
    ) -> dict[str, str]:
        """Build the context dict with all slots filled within budget.

        Returns:
            Dict with keys: profile_context, ha_context, history_context,
            rag_context — each trimmed to its token budget.
        """
        result: dict[str, str] = {}

        # 1. Profile subset — relevant entries based on query
        profile_text = await self._build_profile_context(
            query, profile_manager
        )
        result["profile_context"] = self._trim_to_budget(
            profile_text, "user_profile"
        )

        # 2. HA context — relevant entities only
        ha_text = await self._build_ha_context(query, ha_client)
        result["ha_context"] = self._trim_to_budget(ha_text, "ha_context")

        # 3. Conversation history — summarize if over budget
        history_text = self._build_history_context(conversation_history or [])
        result["history_context"] = self._trim_to_budget(
            history_text, "conversation_history"
        )

        # 4. RAG results — top-k trimmed to remaining budget
        rag_text = "\n\n".join(rag_results or [])
        result["rag_context"] = self._trim_to_budget(rag_text, "rag_results")

        return result

    async def _build_profile_context(
        self, query: str, profile_manager: Any
    ) -> str:
        """Build profile context — only entries relevant to the query."""
        try:
            entries = await profile_manager.get_relevant_entries(query)
            if not entries:
                return ""
            lines = []
            for entry in entries:
                lines.append(
                    f"- {entry['category']}/{entry['key']}: {entry['value']} "
                    f"(confidence: {entry.get('confidence', 'unknown')})"
                )
            return "\n".join(lines)
        except Exception:
            _LOGGER.exception("Error building profile context")
            return ""

    async def _build_ha_context(self, query: str, ha_client: Any) -> str:
        """Build HA context — only entities relevant to the query.

        Uses keyword matching + area filtering to avoid dumping all state.
        """
        try:
            states = await ha_client.get_states()
            # Filter to relevant entities based on query keywords
            relevant = self._filter_relevant_entities(query, states)

            lines = []
            for state in relevant[:20]:  # Cap at 20 entities
                entity_id = state.get("entity_id", "")
                friendly = state.get("attributes", {}).get(
                    "friendly_name", entity_id
                )
                current_state = state.get("state", "unknown")
                lines.append(f"- {friendly} ({entity_id}): {current_state}")

            return "\n".join(lines) if lines else ""
        except Exception:
            _LOGGER.exception("Error building HA context")
            return ""

    def _filter_relevant_entities(
        self, query: str, states: list[dict]
    ) -> list[dict]:
        """Filter entities that are relevant to the user's query."""
        query_lower = query.lower()
        keywords = set(query_lower.split())

        scored: list[tuple[int, dict]] = []
        for state in states:
            entity_id = state.get("entity_id", "").lower()
            friendly = (
                state.get("attributes", {})
                .get("friendly_name", "")
                .lower()
            )
            area = (
                state.get("attributes", {}).get("area", "").lower()
            )

            score = 0
            for kw in keywords:
                if kw in entity_id:
                    score += 2
                if kw in friendly:
                    score += 2
                if kw in area:
                    score += 1

            if score > 0:
                scored.append((score, state))

        # Sort by relevance score (descending)
        scored.sort(key=lambda x: x[0], reverse=True)
        return [s[1] for s in scored]

    def _build_history_context(self, history: list[dict]) -> str:
        """Build conversation history context.

        If history exceeds budget, keep recent turns verbatim and
        summarize older turns.
        """
        if not history:
            return ""

        lines = []
        for msg in history:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            lines.append(f"{role}: {content}")

        full_text = "\n".join(lines)

        # If within budget, return as-is
        if estimate_tokens(full_text) <= self._budget.get(
            "conversation_history", 2000
        ):
            return full_text

        # Over budget: keep last 5 turns verbatim, summarize the rest
        if len(history) > 5:
            recent = history[-5:]
            recent_text = "\n".join(
                f"{m.get('role', 'user')}: {m.get('content', '')}"
                for m in recent
            )
            return (
                f"[{len(history) - 5} earlier messages summarized]\n"
                + recent_text
            )

        return full_text

    def _trim_to_budget(self, text: str, slot: str) -> str:
        """Trim text to fit within the token budget for the given slot."""
        if not text:
            return ""

        max_tokens = self._budget.get(slot, 500)
        max_chars = max_tokens * 4  # Rough: 4 chars per token

        if len(text) <= max_chars:
            return text

        # Truncate with indicator
        return text[: max_chars - 20] + "\n... [truncated]"
