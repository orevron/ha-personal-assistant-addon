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
import sys

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

    # 4. Initialize components
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

    # 5. Start HA client (connects REST + WebSocket)
    await ha.start()

    # 6. Subscribe to Telegram events via WebSocket
    await ha.subscribe_events("telegram_text", agent.handle_telegram_text)
    await ha.subscribe_events(
        "telegram_callback", agent.handle_telegram_callback
    )
    _LOGGER.info("Subscribed to Telegram events")

    # 7. Start background workers
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

    # 8. Start RAG re-indexing background task
    asyncio.create_task(
        rag_reindex_loop(
            config, rag_engine,
            reindex_hours=config.get("rag_reindex_hours", 24),
            history_hours=config.get("history_reindex_hours", 6),
        )
    )
    _LOGGER.info("Background workers started")

    # 9. Run forever (WebSocket listener keeps us alive)
    _LOGGER.info("Personal Assistant add-on is ready!")
    try:
        await ha.run_forever()
    except KeyboardInterrupt:
        _LOGGER.info("Shutting down...")
    finally:
        await ha.stop()


async def rag_reindex_loop(
    config: dict,
    rag_engine: "RAGEngine",
    reindex_hours: int = 24,
    history_hours: int = 6,
) -> None:
    """Periodically re-index HA data for the RAG engine."""
    _LOGGER = logging.getLogger("personal_assistant.rag_reindex")

    # Initial indexing on startup
    try:
        await rag_engine.full_reindex()
        _LOGGER.info("Initial RAG indexing complete")
    except Exception:
        _LOGGER.exception("Initial RAG indexing failed")

    history_counter = 0
    while True:
        # Sleep for 1 hour, then check what needs re-indexing
        await asyncio.sleep(3600)
        history_counter += 1

        try:
            if history_counter >= history_hours:
                await rag_engine.reindex_history()
                history_counter = 0
                _LOGGER.info("History re-indexed")

            # Full re-index every N hours (tracked separately)
            # The full loop runs every reindex_hours iterations
        except Exception:
            _LOGGER.exception("RAG re-indexing error")


if __name__ == "__main__":
    asyncio.run(main())
