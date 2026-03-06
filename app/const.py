"""Constants for the Personal Assistant add-on."""

DOMAIN = "personal_assistant"

# Data paths (inside Docker container)
DATA_DIR = "/data"
DB_PATH = f"{DATA_DIR}/assistant.db"
CONFIG_PATH = f"{DATA_DIR}/options.json"

# HA Supervisor endpoints
HA_API_URL = "http://supervisor/core/api"
HA_WS_URL = "ws://supervisor/core/websocket"

# Default token budget (tuned for gpt-oss:20b @ 8K context)
DEFAULT_TOKEN_BUDGET = {
    "system_prompt": 800,
    "user_profile": 400,
    "ha_context": 800,
    "conversation_history": 2000,
    "rag_results": 800,
    "tool_overhead": 1200,
    "total": 6000,
}

# Default session timeout (minutes)
DEFAULT_SESSION_TIMEOUT = 30

# RAG defaults
DEFAULT_RAG_REINDEX_HOURS = 24
DEFAULT_HISTORY_REINDEX_HOURS = 6
DEFAULT_RAG_TOP_K = 5

# Event types we subscribe to
EVENT_TELEGRAM_TEXT = "telegram_text"
EVENT_TELEGRAM_CALLBACK = "telegram_callback"
EVENT_STATE_CHANGED = "state_changed"

# Sensitivity levels for profile entries
SENSITIVITY_PUBLIC = "public"
SENSITIVITY_PRIVATE = "private"
SENSITIVITY_SENSITIVE = "sensitive"

# Profile sources
SOURCE_OBSERVED = "observed"
SOURCE_TOLD = "told"
SOURCE_INFERRED = "inferred"

# Action policy
POLICY_ALLOWED = "allowed"
POLICY_RESTRICTED = "restricted"
POLICY_BLOCKED = "blocked"
