"""HA entity tools — query entities, get state, call services.

All HA interactions go through HAClient (REST API) instead of
the direct `hass` Python object available in integrations.

`get_ha_entities` returns a strict friendly_name → entity_id mapping.
The agent MUST use exact entity IDs from tool results (never guess).
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.tools import tool

_LOGGER = logging.getLogger(__name__)


def create_ha_tools(ha_client: Any, config: dict[str, Any]) -> list:
    """Create HA-related tools bound to the given HAClient instance."""

    from tools.action_policy import ActionPolicy
    policy = ActionPolicy(config)

    @tool
    async def get_ha_entities(
        domain: str | None = None, area: str | None = None
    ) -> dict[str, str]:
        """List Home Assistant entities, optionally filtered by domain or area.

        Returns a mapping of friendly_name → entity_id.
        ALWAYS call this before calling services — you need the exact entity_id.

        Args:
            domain: Filter by entity domain (e.g., "light", "switch", "climate").
            area: Filter by area name (e.g., "Living Room", "Bedroom").
        """
        try:
            states = await ha_client.get_states()
            result: dict[str, str] = {}

            for state in states:
                entity_id = state.get("entity_id", "")
                friendly_name = state.get("attributes", {}).get(
                    "friendly_name", entity_id
                )
                entity_domain = entity_id.split(".")[0] if "." in entity_id else ""

                # Apply filters
                if domain and entity_domain != domain:
                    continue
                if area:
                    entity_area = state.get("attributes", {}).get("area", "")
                    if area.lower() not in entity_area.lower():
                        continue

                result[friendly_name] = entity_id

            return result
        except Exception as err:
            _LOGGER.error("Error fetching entities: %s", err)
            return {"error": str(err)}

    @tool
    async def get_entity_state(entity_id: str) -> dict[str, Any]:
        """Get the current state and attributes of a specific entity.

        Args:
            entity_id: The exact entity ID (e.g., "light.living_room").
                       Get this from get_ha_entities first.
        """
        try:
            state = await ha_client.get_state(entity_id)
            return {
                "entity_id": state.get("entity_id"),
                "state": state.get("state"),
                "attributes": state.get("attributes", {}),
                "last_changed": state.get("last_changed"),
                "last_updated": state.get("last_updated"),
            }
        except Exception as err:
            _LOGGER.error("Error getting state for %s: %s", entity_id, err)
            return {"error": str(err)}

    @tool
    async def call_ha_service(
        domain: str, service: str, entity_id: str, **extra_data: Any
    ) -> str:
        """Call a Home Assistant service on an entity.

        This action goes through the Action Permission Layer.
        Some domains may require user confirmation via Telegram.

        Args:
            domain: Service domain (e.g., "light", "switch", "climate").
            service: Service name (e.g., "turn_on", "turn_off", "set_temperature").
            entity_id: Target entity ID (e.g., "light.living_room").
            **extra_data: Additional service data (e.g., brightness=128).
        """
        service_call = f"{domain}.{service}"

        # Check action policy
        permission = policy.check_permission(domain, service)

        if permission == "blocked":
            return (
                f"Action '{service_call}' is BLOCKED by policy. "
                f"The domain '{domain}' is not allowed."
            )

        if permission == "requires_confirmation":
            # In a full implementation, this would use LangGraph interrupt()
            # For now, proceed with a warning
            _LOGGER.warning(
                "Action '%s' requires confirmation — proceeding (interrupt TODO)",
                service_call,
            )

        # Execute the service call via REST API
        try:
            data = {"entity_id": entity_id, **extra_data}
            await ha_client.call_service(domain, service, data)
            return f"Successfully called {service_call} on {entity_id}"
        except Exception as err:
            _LOGGER.error("Service call failed: %s", err)
            return f"Failed to call {service_call}: {err}"

    @tool
    async def get_entity_history(
        entity_id: str, hours: int = 24
    ) -> list[dict[str, Any]]:
        """Get historical states for an entity over the specified period.

        Args:
            entity_id: The entity to get history for.
            hours: Number of hours to look back (default: 24).
        """
        from datetime import datetime, timedelta, timezone

        try:
            start_time = (
                datetime.now(timezone.utc) - timedelta(hours=hours)
            ).isoformat()
            history = await ha_client.get_history(
                start_time=start_time, entity_id=entity_id
            )

            if not history or not history[0]:
                return [{"info": f"No history found for {entity_id}"}]

            # Simplify the history entries
            result = []
            for entry in history[0][:20]:  # Cap at 20 entries
                result.append({
                    "state": entry.get("state"),
                    "last_changed": entry.get("last_changed"),
                })
            return result
        except Exception as err:
            _LOGGER.error("Error getting history for %s: %s", entity_id, err)
            return [{"error": str(err)}]

    return [get_ha_entities, get_entity_state, call_ha_service, get_entity_history]
