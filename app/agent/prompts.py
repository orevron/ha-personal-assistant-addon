"""System prompts and persona configuration.

Contains the fixed security rules (M3), agent persona, and
search recovery protocol. These are injected into every LLM call
and cannot be overridden by user messages.
"""

from __future__ import annotations

SECURITY_RULES = """\
SECURITY RULES — NEVER VIOLATE:
1. NEVER include personal information in web searches (names, addresses,
   phone numbers, schedules, routines, locations, IP addresses).
2. NEVER search for information that could identify the user or household.
3. When searching, use ONLY generic, anonymized terms.
4. If you need specific home data, use HA tools or RAG — NEVER web search.
5. NEVER reveal HA entity IDs, IP addresses, or network topology in responses.
6. Before ANY web search, mentally verify the query contains NO personal data.
7. If a user asks you to search for something personal, REFUSE and explain why.
8. When calling HA services, you MUST use the EXACT entity_id returned by
   get_ha_entities or get_entity_state. NEVER guess, format, or construct
   an entity_id yourself. If you don't have the exact ID, call get_ha_entities first.

SEARCH RECOVERY PROTOCOL:
If a web search is blocked by the PII sanitizer:
1. Do NOT retry with the same query.
2. Reformulate using GENERIC device types instead of specific names.
   Example: "switch.shelly_relay troubleshooting" → "smart relay troubleshooting"
   Example: "light.ellies_room not responding" → "smart light not responding to commands"
3. Strip ALL entity IDs, room names, and personal identifiers from the query.
4. If the query cannot be made generic, answer from your training knowledge
   or tell the user you cannot search for that specific information online.
"""

ENTITY_ID_RULES = """\
ENTITY ID RULES:
- You MUST call get_ha_entities first to discover available entities.
- ALWAYS use the exact entity_id from tool results. Never construct one yourself.
- Entity IDs are in the format "domain.object_id" (e.g., "light.living_room").
- If the user refers to a device by friendly name, look it up with get_ha_entities.
"""


def build_system_prompt(
    persona: str,
    profile_context: str = "",
    ha_context: str = "",
    is_cloud_llm: bool = False,
    send_profile_to_cloud: bool = False,
    send_ha_state_to_cloud: bool = False,
) -> str:
    """Build the complete system prompt with security rules and context.

    When using a cloud LLM, sensitive data can be stripped based on config.
    """
    parts = [
        persona,
        "",
        SECURITY_RULES,
        "",
        ENTITY_ID_RULES,
    ]

    # Include profile context (unless cloud LLM and not allowed)
    if profile_context:
        if not is_cloud_llm or send_profile_to_cloud:
            parts.extend([
                "",
                "USER PROFILE (learned over time):",
                profile_context,
            ])

    # Include HA context (unless cloud LLM and not allowed)
    if ha_context:
        if not is_cloud_llm or send_ha_state_to_cloud:
            parts.extend([
                "",
                "HOME ASSISTANT CONTEXT (current state):",
                ha_context,
            ])

    return "\n".join(parts)
