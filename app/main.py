"""Personal Assistant add-on — main entry point.

Replaces the HA custom integration's __init__.py. Runs its own asyncio
event loop, connects to HA via REST/WebSocket, and orchestrates all
agent components.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import sys
from typing import Any

from const import CONFIG_PATH, DB_PATH
from ha_client import HAClient

# Configure logging
LOG_LEVELS = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
}

log_level_name = os.environ.get("PA_LOG_LEVEL", "info").lower()
logging.basicConfig(
    level=LOG_LEVELS.get(log_level_name, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)

# Sanitize sensitive data from logs
class SanitizedFormatter(logging.Formatter):
    """Log formatter that strips tokens and sensitive data."""

    REDACT_PATTERNS = [
        ("SUPERVISOR_TOKEN", "Bearer "),
        ("api_key", "api_key"),
    ]

    def format(self, record: logging.LogRecord) -> str:
        msg = super().format(record)
        # Redact bearer tokens
        import re
        msg = re.sub(
            r"Bearer\s+[A-Za-z0-9._-]+",
            "Bearer [REDACTED]",
            msg,
        )
        # Redact API keys
        msg = re.sub(
            r"(api[_-]?key[\"']?\s*[:=]\s*[\"']?)[A-Za-z0-9._-]{10,}",
            r"\1[REDACTED]",
            msg,
            flags=re.IGNORECASE,
        )
        return msg


# Apply sanitized formatter to root logger
for handler in logging.root.handlers:
    handler.setFormatter(
        SanitizedFormatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )

_LOGGER = logging.getLogger("personal_assistant")


def load_config() -> dict:
    """Load configuration from the Supervisor-provided options file."""
    config_file = os.environ.get("PA_CONFIG_FILE", CONFIG_PATH)
    try:
        with open(config_file) as f:
            config = json.load(f)
        _LOGGER.info("Configuration loaded from %s", config_file)
        return config
    except FileNotFoundError:
        _LOGGER.warning(
            "Config file %s not found — using defaults", config_file
        )
        return {}
    except json.JSONDecodeError as err:
        _LOGGER.error("Invalid JSON in config file: %s", err)
        return {}


async def main() -> None:
    """Main async entry point."""
    _LOGGER.info("Personal Assistant add-on starting...")

    # 1. Load config
    config = load_config()

    # 2. Initialize HA client (REST + WebSocket)
    supervisor_token = os.environ.get("SUPERVISOR_TOKEN", "")
    if not supervisor_token:
        _LOGGER.error(
            "SUPERVISOR_TOKEN not set — cannot communicate with HA. "
            "Ensure the add-on has 'homeassistant_api: true' in config.yaml."
        )
        sys.exit(1)

    ha = HAClient(token=supervisor_token)

    # 3. Initialize database
    from memory.models import init_database
    await init_database(DB_PATH)
    _LOGGER.info("Database initialized at %s", DB_PATH)

    # 4. Initialize multi-user manager
    from memory.multi_user import MultiUserManager
    user_manager = MultiUserManager(DB_PATH)
    await user_manager.ensure_initialized()

    # 5. Initialize components
    from agent.router import LLMRouter
    from memory.profile_manager import ProfileManager
    from memory.conversation_memory import ConversationMemory
    from rag.engine import RAGEngine
    from agent.graph import PersonalAssistantAgent

    llm_router = LLMRouter(config)
    profile_manager = ProfileManager(DB_PATH)
    conversation_memory = ConversationMemory(
        DB_PATH,
        session_timeout_minutes=config.get("session_timeout_minutes", 30),
    )
    rag_engine = RAGEngine(config, ha, DB_PATH)

    agent = PersonalAssistantAgent(
        config=config,
        ha_client=ha,
        llm_router=llm_router,
        profile_manager=profile_manager,
        conversation_memory=conversation_memory,
        rag_engine=rag_engine,
    )

    # 6. Start HA client (connects REST + WebSocket)
    await ha.start()

    # 7. Subscribe to Telegram events via WebSocket
    await ha.subscribe_events("telegram_text", agent.handle_telegram_text)
    await ha.subscribe_events(
        "telegram_callback", agent.handle_telegram_callback
    )
    _LOGGER.info("Subscribed to Telegram events")

    # 8. Start background workers
    from memory.learning_worker import LearningWorker
    from memory.event_learner import EventLearner

    learning_worker = LearningWorker(
        profile_manager=profile_manager,
        llm_router=llm_router,
        db_path=DB_PATH,
    )
    asyncio.create_task(learning_worker.run())
    agent.set_learning_worker(learning_worker)

    event_learner = EventLearner(
        config=config,
        ha_client=ha,
        profile_manager=profile_manager,
        llm_router=llm_router,
    )
    asyncio.create_task(event_learner.run())

    # 9. Start proactive notification system
    from notifications import ProactiveNotifier

    notifier = ProactiveNotifier(config=config, ha_client=ha)
    # Get known user chat IDs for notifications
    chat_ids = await user_manager.get_user_chat_ids()
    if chat_ids:
        notifier.set_chat_ids(chat_ids)
    asyncio.create_task(notifier.run())

    # 10. Start RAG re-indexing background task
    asyncio.create_task(
        rag_reindex_loop(
            config, rag_engine,
            reindex_hours=config.get("rag_reindex_hours", 24),
            history_hours=config.get("history_reindex_hours", 6),
        )
    )
    _LOGGER.info("Background workers started")

    # 11. Set up graceful shutdown
    shutdown_event = asyncio.Event()

    def _signal_handler() -> None:
        _LOGGER.info("Received shutdown signal")
        shutdown_event.set()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _signal_handler)

    # 12. Run forever
    _LOGGER.info("Personal Assistant add-on is ready!")
    try:
        # Wait for either WS disconnect or shutdown signal
        ws_task = asyncio.create_task(ha.run_forever())
        shutdown_task = asyncio.create_task(shutdown_event.wait())

        done, pending = await asyncio.wait(
            [ws_task, shutdown_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()

    except KeyboardInterrupt:
        _LOGGER.info("Keyboard interrupt received")
    finally:
        _LOGGER.info("Shutting down...")
        await notifier.stop()
        await learning_worker.stop()
        await event_learner.stop()
        await ha.stop()
        _LOGGER.info("Shutdown complete")


async def rag_reindex_loop(
    config: dict,
    rag_engine: Any,
    reindex_hours: int = 24,
    history_hours: int = 6,
) -> None:
    """Periodically re-index HA data for the RAG engine."""
    logger = logging.getLogger("personal_assistant.rag_reindex")

    # Initial indexing on startup (with retry)
    for attempt in range(3):
        try:
            await rag_engine.full_reindex()
            logger.info("Initial RAG indexing complete")
            break
        except Exception:
            logger.exception(
                "Initial RAG indexing failed (attempt %d/3)", attempt + 1
            )
            if attempt < 2:
                await asyncio.sleep(30)

    history_counter = 0
    full_counter = 0
    while True:
        await asyncio.sleep(3600)  # Check every hour
        history_counter += 1
        full_counter += 1

        try:
            if history_counter >= history_hours:
                await rag_engine.reindex_history()
                history_counter = 0
                logger.info("History re-indexed")

            if full_counter >= reindex_hours:
                await rag_engine.full_reindex()
                full_counter = 0
                logger.info("Full re-index complete")
        except Exception:
            logger.exception("RAG re-indexing error")


if __name__ == "__main__":
    asyncio.run(main())
