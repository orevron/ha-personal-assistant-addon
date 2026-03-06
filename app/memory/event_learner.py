"""Event-Driven Behavior Learner — observes HA events to learn patterns.

Learns user behavior by:
  1. Subscribing to state_changed events via WebSocket (add-on model)
  2. Querying InfluxDB for historical patterns (if configured)

Detected patterns are stored as profile entries with source: 'observed'.

HA communication via WebSocket (HAClient) instead of hass.bus.async_listen.
InfluxDB queries are direct HTTP — no HA dependency.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)


class EventLearner:
    """Observes HA events and learns user behavior patterns."""

    def __init__(
        self,
        config: dict[str, Any],
        ha_client: Any,
        profile_manager: Any,
        llm_router: Any,
    ) -> None:
        self._config = config
        self._ha = ha_client
        self._profile_manager = profile_manager
        self._llm_router = llm_router
        self._influxdb_url = config.get("influxdb_url", "")
        self._influxdb_token = config.get("influxdb_token", "")
        self._influxdb_org = config.get("influxdb_org", "")
        self._influxdb_bucket = config.get("influxdb_bucket", "")
        self._running = False

        # Track state changes for pattern detection
        self._state_buffer: list[dict[str, Any]] = []

    async def run(self) -> None:
        """Main loop — periodically analyze patterns."""
        self._running = True
        _LOGGER.info("Event learner started")

        # Subscribe to state_changed events via WebSocket
        await self._ha.subscribe_events(
            "state_changed", self._handle_state_changed
        )

        while self._running:
            try:
                # Run pattern detection every 24 hours
                await asyncio.sleep(86400)
                await self._detect_patterns()
            except asyncio.CancelledError:
                break
            except Exception:
                _LOGGER.exception("Event learner error")

        _LOGGER.info("Event learner stopped")

    async def stop(self) -> None:
        """Stop the learner."""
        self._running = False

    async def _handle_state_changed(
        self, event_data: dict[str, Any]
    ) -> None:
        """Handle a state_changed event from WebSocket."""
        entity_id = event_data.get("entity_id", "")
        new_state = event_data.get("new_state", {})
        old_state = event_data.get("old_state", {})

        if not entity_id or not new_state:
            return

        # Buffer the state change for pattern analysis
        self._state_buffer.append({
            "entity_id": entity_id,
            "old_state": old_state.get("state") if old_state else None,
            "new_state": new_state.get("state"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        # Keep buffer manageable (last 1000 events)
        if len(self._state_buffer) > 1000:
            self._state_buffer = self._state_buffer[-500:]

    async def _detect_patterns(self) -> None:
        """Analyze buffered events and InfluxDB data for patterns."""
        _LOGGER.info("Running pattern detection...")

        # Method 1: Analyze buffered state changes
        await self._analyze_state_buffer()

        # Method 2: Query InfluxDB (if configured)
        if self._influxdb_url:
            await self._analyze_influxdb()

    async def _analyze_state_buffer(self) -> None:
        """Simple pattern detection from buffered state changes."""
        if not self._state_buffer:
            return

        # Count entity transitions
        transitions: dict[str, dict[str, int]] = {}
        for event in self._state_buffer:
            entity_id = event["entity_id"]
            transition = f"{event.get('old_state')} → {event.get('new_state')}"
            if entity_id not in transitions:
                transitions[entity_id] = {}
            transitions[entity_id][transition] = (
                transitions[entity_id].get(transition, 0) + 1
            )

        # Log patterns with significant count
        for entity_id, trans in transitions.items():
            for transition, count in trans.items():
                if count >= 5:  # Minimum threshold
                    _LOGGER.info(
                        "Pattern detected: %s %s (%d times)",
                        entity_id,
                        transition,
                        count,
                    )

    async def _analyze_influxdb(self) -> None:
        """Query InfluxDB for historical patterns using Flux."""
        if not all([
            self._influxdb_url,
            self._influxdb_token,
            self._influxdb_org,
            self._influxdb_bucket,
        ]):
            return

        # Example: Find average time lights turn off in each area
        flux_query = f"""
        from(bucket: "{self._influxdb_bucket}")
            |> range(start: -7d)
            |> filter(fn: (r) => r._measurement == "state" and r.domain == "light")
            |> filter(fn: (r) => r._value == "off")
            |> aggregateWindow(every: 1h, fn: count)
            |> group(columns: ["entity_id"])
        """

        try:
            headers = {
                "Authorization": f"Token {self._influxdb_token}",
                "Content-Type": "application/vnd.flux",
                "Accept": "application/csv",
            }
            url = f"{self._influxdb_url}/api/v2/query?org={self._influxdb_org}"

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url, headers=headers, data=flux_query,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.text()
                        _LOGGER.debug(
                            "InfluxDB query returned %d bytes", len(data)
                        )
                        # Parse and extract patterns
                        # (Full implementation would use LLM to interpret)
                    else:
                        _LOGGER.warning(
                            "InfluxDB query failed: %d", resp.status
                        )
        except Exception:
            _LOGGER.exception("InfluxDB query error")
