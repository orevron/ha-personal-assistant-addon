"""Action Permission Layer (M7) — gates every HA service call.

Pipeline: Agent → Intent Validator → Policy Engine → HA Service Call

Domain-based policies:
  - allowed: Call proceeds immediately
  - restricted: Requires Telegram confirmation (LangGraph interrupt)
  - blocked: NEVER callable

Config comes from /data/options.json (add-on options).
"""

from __future__ import annotations

import logging
from typing import Any

from const import POLICY_ALLOWED, POLICY_BLOCKED, POLICY_RESTRICTED

_LOGGER = logging.getLogger(__name__)


class ActionPolicy:
    """Evaluates whether a HA service call is permitted."""

    def __init__(self, config: dict[str, Any]) -> None:
        self._allowed_domains = config.get(
            "action_policy_allowed_domains", "*"
        )
        self._restricted_domains: set[str] = set(
            config.get("action_policy_restricted_domains", ["lock", "camera"])
        )
        self._blocked_domains: set[str] = set(
            config.get("action_policy_blocked_domains", ["homeassistant"])
        )
        self._require_confirmation: set[str] = set(
            config.get("action_policy_require_confirmation", [
                "lock.unlock",
                "lock.lock",
                "camera.turn_on",
                "camera.turn_off",
            ])
        )

    def check_permission(self, domain: str, service: str) -> str:
        """Check whether a service call is allowed.

        Returns:
            "allowed", "requires_confirmation", or "blocked"
        """
        full_service = f"{domain}.{service}"

        # 1. Blocked domains — NEVER callable
        if domain in self._blocked_domains:
            _LOGGER.warning("BLOCKED service call: %s", full_service)
            return POLICY_BLOCKED

        # 2. Specific service requires confirmation
        if full_service in self._require_confirmation:
            _LOGGER.info(
                "Service %s requires confirmation", full_service
            )
            return POLICY_RESTRICTED

        # 3. Restricted domain — all services need confirmation
        if domain in self._restricted_domains:
            _LOGGER.info(
                "Domain %s is restricted — confirmation required", domain
            )
            return POLICY_RESTRICTED

        # 4. Allowed (default or explicit)
        return POLICY_ALLOWED

    def get_confirmation_message(
        self, domain: str, service: str, entity_id: str
    ) -> dict[str, Any]:
        """Build a Telegram inline keyboard for confirmation.

        Returns the data dict for telegram_bot.send_message with
        inline_keyboard for Yes/No confirmation.
        """
        import uuid

        action_id = str(uuid.uuid4())[:8]
        friendly_action = f"{service.replace('_', ' ').title()} {entity_id}"

        return {
            "message": f"⚠️ **Confirmation required**\n\n"
                       f"Action: {friendly_action}\n"
                       f"Service: `{domain}.{service}`\n"
                       f"Entity: `{entity_id}`\n\n"
                       f"Do you want to proceed?",
            "parse_mode": "markdown",
            "inline_keyboard": [
                [
                    {
                        "text": "✅ Yes",
                        "callback_data": f"confirm:{action_id}:yes",
                    },
                    {
                        "text": "❌ Cancel",
                        "callback_data": f"confirm:{action_id}:no",
                    },
                ]
            ],
            "_action_id": action_id,
        }
