"""Home Assistant REST + WebSocket client for add-on communication.

This module replaces all direct `hass.*` calls that would be available in
a custom integration. The add-on communicates with HA Core exclusively
through:
  - REST API:  http://supervisor/core/api/
  - WebSocket: ws://supervisor/core/websocket

Authentication uses the SUPERVISOR_TOKEN environment variable, which is
auto-injected by the HA Supervisor into every add-on container.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, Callable, Coroutine

import aiohttp
import websockets
from websockets.asyncio.client import connect as ws_connect

from const import HA_API_URL, HA_WS_URL

_LOGGER = logging.getLogger(__name__)


class HAClient:
    """Client for Home Assistant REST + WebSocket API."""

    def __init__(
        self,
        api_url: str = HA_API_URL,
        ws_url: str = HA_WS_URL,
        token: str | None = None,
    ) -> None:
        self._api_url = api_url.rstrip("/")
        self._ws_url = ws_url
        self._token = token or os.environ.get("SUPERVISOR_TOKEN", "")
        self._session: aiohttp.ClientSession | None = None
        self._ws: websockets.asyncio.client.ClientConnection | None = None
        self._ws_id: int = 0
        self._event_handlers: dict[str, list[Callable]] = {}
        self._response_futures: dict[int, asyncio.Future] = {}
        self._running = False
        self._ws_task: asyncio.Task | None = None

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Initialize HTTP session and WebSocket connection."""
        self._session = aiohttp.ClientSession(headers=self._headers)
        self._running = True
        await self._connect_ws()
        _LOGGER.info("HAClient started — connected to %s", self._api_url)

    async def stop(self) -> None:
        """Gracefully shut down connections."""
        self._running = False
        if self._ws_task and not self._ws_task.done():
            self._ws_task.cancel()
        if self._ws:
            await self._ws.close()
        if self._session:
            await self._session.close()
        _LOGGER.info("HAClient stopped")

    async def run_forever(self) -> None:
        """Block until stopped — keeps the WebSocket listener alive."""
        if self._ws_task:
            try:
                await self._ws_task
            except asyncio.CancelledError:
                pass

    # ------------------------------------------------------------------
    # REST API — State & Services
    # ------------------------------------------------------------------

    async def get_states(self) -> list[dict[str, Any]]:
        """GET /api/states — all entity states."""
        return await self._rest_get("/states")

    async def get_state(self, entity_id: str) -> dict[str, Any]:
        """GET /api/states/{entity_id} — single entity state."""
        return await self._rest_get(f"/states/{entity_id}")

    async def call_service(
        self, domain: str, service: str, data: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """POST /api/services/{domain}/{service} — call a HA service."""
        return await self._rest_post(f"/services/{domain}/{service}", data or {})

    async def get_history(
        self,
        start_time: str,
        entity_id: str | None = None,
        end_time: str | None = None,
    ) -> list[list[dict[str, Any]]]:
        """GET /api/history/period/{start} — entity history."""
        path = f"/history/period/{start_time}"
        params: dict[str, str] = {}
        if entity_id:
            params["filter_entity_id"] = entity_id
        if end_time:
            params["end_time"] = end_time
        return await self._rest_get(path, params=params)

    async def get_config(self) -> dict[str, Any]:
        """GET /api/config — HA configuration."""
        return await self._rest_get("/config")

    async def fire_event(
        self, event_type: str, event_data: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """POST /api/events/{event_type} — fire an event on the HA bus."""
        return await self._rest_post(f"/events/{event_type}", event_data or {})

    # ------------------------------------------------------------------
    # REST API — Registries (via WebSocket commands for full access)
    # ------------------------------------------------------------------

    async def get_areas(self) -> list[dict[str, Any]]:
        """Fetch area registry via WebSocket command."""
        return await self._ws_command("config/area_registry/list")

    async def get_device_registry(self) -> list[dict[str, Any]]:
        """Fetch device registry via WebSocket command."""
        return await self._ws_command("config/device_registry/list")

    async def get_entity_registry(self) -> list[dict[str, Any]]:
        """Fetch entity registry via WebSocket command."""
        return await self._ws_command("config/entity_registry/list")

    # ------------------------------------------------------------------
    # WebSocket — Event Subscriptions
    # ------------------------------------------------------------------

    async def subscribe_events(
        self,
        event_type: str,
        handler: Callable[[dict[str, Any]], Coroutine[Any, Any, None]],
    ) -> None:
        """Subscribe to a HA event type and register an async handler."""
        if event_type not in self._event_handlers:
            self._event_handlers[event_type] = []
            # Send subscription to HA if WS is connected
            if self._ws:
                await self._ws_subscribe(event_type)
        self._event_handlers[event_type].append(handler)
        _LOGGER.info("Subscribed to event: %s", event_type)

    # ------------------------------------------------------------------
    # Internal — REST helpers
    # ------------------------------------------------------------------

    async def _rest_get(
        self, path: str, params: dict[str, str] | None = None
    ) -> Any:
        """Perform a GET request to the HA REST API."""
        assert self._session is not None, "HAClient not started"
        url = f"{self._api_url}{path}"
        try:
            async with self._session.get(url, params=params) as resp:
                resp.raise_for_status()
                return await resp.json()
        except aiohttp.ClientError as err:
            _LOGGER.error("REST GET %s failed: %s", url, err)
            raise

    async def _rest_post(self, path: str, data: dict[str, Any]) -> Any:
        """Perform a POST request to the HA REST API."""
        assert self._session is not None, "HAClient not started"
        url = f"{self._api_url}{path}"
        try:
            async with self._session.post(url, json=data) as resp:
                resp.raise_for_status()
                return await resp.json()
        except aiohttp.ClientError as err:
            _LOGGER.error("REST POST %s failed: %s", url, err)
            raise

    # ------------------------------------------------------------------
    # Internal — WebSocket
    # ------------------------------------------------------------------

    async def _connect_ws(self) -> None:
        """Establish WebSocket connection and authenticate."""
        self._ws = await ws_connect(self._ws_url)

        # Step 1: Receive auth_required
        msg = json.loads(await self._ws.recv())
        if msg.get("type") != "auth_required":
            raise ConnectionError(f"Unexpected WS message: {msg}")

        # Step 2: Send auth
        await self._ws.send(json.dumps({
            "type": "auth",
            "access_token": self._token,
        }))

        # Step 3: Receive auth_ok
        msg = json.loads(await self._ws.recv())
        if msg.get("type") != "auth_ok":
            raise ConnectionError(f"WS auth failed: {msg}")

        _LOGGER.info("WebSocket authenticated with HA Core")

        # Re-subscribe to previously registered event types
        for event_type in self._event_handlers:
            await self._ws_subscribe(event_type)

        # Start listener task
        self._ws_task = asyncio.create_task(self._ws_listener())

    async def _ws_subscribe(self, event_type: str) -> None:
        """Send a subscribe_events command over WebSocket."""
        self._ws_id += 1
        msg = {
            "id": self._ws_id,
            "type": "subscribe_events",
            "event_type": event_type,
        }
        assert self._ws is not None
        await self._ws.send(json.dumps(msg))
        _LOGGER.debug("WS subscribe sent: id=%d event_type=%s", self._ws_id, event_type)

    async def _ws_command(self, command_type: str, **kwargs: Any) -> Any:
        """Send a command over WebSocket and wait for the response."""
        self._ws_id += 1
        msg_id = self._ws_id
        msg = {"id": msg_id, "type": command_type, **kwargs}

        future: asyncio.Future[Any] = asyncio.get_event_loop().create_future()
        self._response_futures[msg_id] = future

        assert self._ws is not None
        await self._ws.send(json.dumps(msg))

        try:
            result = await asyncio.wait_for(future, timeout=30.0)
            return result
        except asyncio.TimeoutError:
            self._response_futures.pop(msg_id, None)
            raise TimeoutError(f"WS command {command_type} timed out")

    async def _ws_listener(self) -> None:
        """Listen for WebSocket messages and dispatch events."""
        reconnect_delay = 1.0
        max_delay = 60.0

        while self._running:
            try:
                assert self._ws is not None
                async for raw_msg in self._ws:
                    msg = json.loads(raw_msg)
                    msg_type = msg.get("type")

                    if msg_type == "event":
                        await self._dispatch_event(msg)
                        reconnect_delay = 1.0  # Reset on successful message
                    elif msg_type == "result":
                        msg_id = msg.get("id")
                        if msg_id in self._response_futures:
                            future = self._response_futures.pop(msg_id)
                            if msg.get("success"):
                                future.set_result(msg.get("result"))
                            else:
                                future.set_exception(
                                    RuntimeError(f"WS command failed: {msg.get('error')}")
                                )
                    elif msg_type == "pong":
                        pass  # Keepalive response
                    else:
                        _LOGGER.debug("WS unhandled message type: %s", msg_type)

            except (
                websockets.exceptions.ConnectionClosed,
                ConnectionError,
            ) as err:
                if not self._running:
                    break
                _LOGGER.warning(
                    "WebSocket disconnected: %s — reconnecting in %.0fs",
                    err,
                    reconnect_delay,
                )
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, max_delay)
                try:
                    await self._connect_ws()
                except Exception as reconn_err:
                    _LOGGER.error("WS reconnect failed: %s", reconn_err)
            except asyncio.CancelledError:
                break
            except Exception:
                _LOGGER.exception("Unexpected error in WS listener")
                if not self._running:
                    break
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, max_delay)

    async def _dispatch_event(self, msg: dict[str, Any]) -> None:
        """Dispatch a received event to registered handlers."""
        event = msg.get("event", {})
        event_type = event.get("event_type", "")
        event_data = event.get("data", {})

        handlers = self._event_handlers.get(event_type, [])
        for handler in handlers:
            try:
                await handler(event_data)
            except Exception:
                _LOGGER.exception(
                    "Error in handler for event %s", event_type
                )
