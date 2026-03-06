"""Proactive Notifications — monitors HA state and sends alerts.

Watches for conditions that warrant proactive Telegram notifications:
  - Doors/windows left open too long
  - Unusual device activity
  - Climate anomalies
  - Custom user-defined triggers

Sends notifications via HA REST API (telegram_bot.send_message).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

_LOGGER = logging.getLogger(__name__)


class ProactiveNotifier:
    """Monitors HA state and sends proactive Telegram notifications."""

    # Default rules — can be extended via config or learned patterns
    DEFAULT_RULES = [
        {
            "name": "door_left_open",
            "description": "Alert when a door/window is left open",
            "domain": "binary_sensor",
            "device_class": ["door", "window", "garage_door"],
            "state": "on",
            "duration_minutes": 30,
            "message_template": "⚠️ **{friendly_name}** has been open for {duration} minutes.",
        },
        {
            "name": "water_leak",
            "description": "Immediate alert on water leak detection",
            "domain": "binary_sensor",
            "device_class": ["moisture"],
            "state": "on",
            "duration_minutes": 0,  # Immediate
            "message_template": "🚨 **Water leak detected!** {friendly_name} triggered.",
        },
        {
            "name": "smoke_detected",
            "description": "Immediate alert on smoke/CO detection",
            "domain": "binary_sensor",
            "device_class": ["smoke", "carbon_monoxide", "gas"],
            "state": "on",
            "duration_minutes": 0,
            "message_template": "🚨🔥 **{friendly_name}** — immediate attention required!",
        },
        {
            "name": "high_temperature",
            "description": "Alert when indoor temperature is too high",
            "domain": "sensor",
            "device_class": ["temperature"],
            "threshold_above": 35.0,
            "message_template": "🌡️ **{friendly_name}** reports {state}°C — unusually high!",
        },
    ]

    def __init__(
        self,
        config: dict[str, Any],
        ha_client: Any,
        notification_chat_ids: list[int] | None = None,
    ) -> None:
        self._config = config
        self._ha = ha_client
        self._chat_ids = notification_chat_ids or []
        self._running = False
        self._alerted: dict[str, datetime] = {}  # Prevent duplicate alerts
        self._alert_cooldown_minutes = 60  # Don't re-alert within this window

    async def run(self) -> None:
        """Main loop — periodically checks state against rules."""
        self._running = True
        _LOGGER.info("Proactive notifier started")

        while self._running:
            try:
                await self._check_rules()
                await asyncio.sleep(60)  # Check every minute
            except asyncio.CancelledError:
                break
            except Exception:
                _LOGGER.exception("Proactive notifier error")
                await asyncio.sleep(60)

        _LOGGER.info("Proactive notifier stopped")

    async def stop(self) -> None:
        """Stop the notifier."""
        self._running = False

    def set_chat_ids(self, chat_ids: list[int]) -> None:
        """Set the Telegram chat IDs to notify."""
        self._chat_ids = chat_ids

    async def _check_rules(self) -> None:
        """Check all notification rules against current HA state."""
        if not self._chat_ids:
            return

        try:
            states = await self._ha.get_states()
        except Exception:
            _LOGGER.debug("Could not fetch states for proactive check")
            return

        now = datetime.now(timezone.utc)

        for state in states:
            entity_id = state.get("entity_id", "")
            entity_state = state.get("state", "")
            attrs = state.get("attributes", {})
            domain = entity_id.split(".")[0] if "." in entity_id else ""
            device_class = attrs.get("device_class", "")
            friendly_name = attrs.get("friendly_name", entity_id)

            for rule in self.DEFAULT_RULES:
                if domain != rule.get("domain"):
                    continue

                # Check device class match
                rule_classes = rule.get("device_class", [])
                if rule_classes and device_class not in rule_classes:
                    continue

                triggered = False

                # State-based rule
                if "state" in rule and entity_state == rule["state"]:
                    # Check duration
                    duration_min = rule.get("duration_minutes", 0)
                    if duration_min > 0:
                        last_changed = state.get("last_changed", "")
                        if last_changed:
                            try:
                                changed_dt = datetime.fromisoformat(
                                    last_changed.replace("Z", "+00:00")
                                )
                                elapsed = (now - changed_dt).total_seconds() / 60
                                if elapsed >= duration_min:
                                    triggered = True
                            except (ValueError, TypeError):
                                pass
                    else:
                        triggered = True

                # Threshold-based rule
                elif "threshold_above" in rule:
                    try:
                        value = float(entity_state)
                        if value > rule["threshold_above"]:
                            triggered = True
                    except (ValueError, TypeError):
                        pass

                if triggered:
                    await self._send_alert(
                        entity_id, rule, friendly_name, entity_state, now
                    )

    async def _send_alert(
        self,
        entity_id: str,
        rule: dict[str, Any],
        friendly_name: str,
        state: str,
        now: datetime,
    ) -> None:
        """Send a proactive alert if not in cooldown."""
        alert_key = f"{rule['name']}:{entity_id}"

        # Check cooldown
        if alert_key in self._alerted:
            last_alert = self._alerted[alert_key]
            elapsed = (now - last_alert).total_seconds() / 60
            if elapsed < self._alert_cooldown_minutes:
                return

        # Format message
        message = rule.get("message_template", "Alert: {friendly_name}").format(
            friendly_name=friendly_name,
            state=state,
            entity_id=entity_id,
            duration=self._alert_cooldown_minutes,
        )

        # Send to all configured chat IDs
        for chat_id in self._chat_ids:
            try:
                await self._ha.call_service("telegram_bot", "send_message", {
                    "message": message,
                    "target": chat_id,
                    "parse_mode": "markdown",
                })
                _LOGGER.info(
                    "Proactive alert sent: %s → chat %s", alert_key, chat_id
                )
            except Exception:
                _LOGGER.exception(
                    "Failed to send proactive alert to chat %s", chat_id
                )

        self._alerted[alert_key] = now
