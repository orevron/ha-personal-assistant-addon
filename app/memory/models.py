"""SQLite database models and initialization.

All tables live in a single SQLite database at /data/assistant.db.
sqlite-vec shares this database for vector storage.

No HA dependency — pure SQLite.
"""

from __future__ import annotations

import logging
import sqlite3

import aiosqlite

_LOGGER = logging.getLogger(__name__)

# Schema DDL
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS profile_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    confidence REAL DEFAULT 0.5,
    sensitivity TEXT DEFAULT 'private',
    source TEXT,
    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    occurrence_count INTEGER DEFAULT 1,
    UNIQUE(category, key)
);

CREATE TABLE IF NOT EXISTS conversation_sessions (
    id TEXT PRIMARY KEY,
    chat_id INTEGER NOT NULL,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS conversation_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    chat_id INTEGER NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES conversation_sessions(id)
);

CREATE TABLE IF NOT EXISTS interaction_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    chat_id INTEGER NOT NULL,
    user_message TEXT,
    assistant_response TEXT,
    tools_used TEXT,
    entities_mentioned TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS search_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    original_query TEXT NOT NULL,
    sanitized_query TEXT NOT NULL,
    was_blocked BOOLEAN DEFAULT FALSE,
    block_reason TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS rag_documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    content TEXT NOT NULL,
    metadata TEXT,
    embedding BLOB,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_profile_category ON profile_entries(category);
CREATE INDEX IF NOT EXISTS idx_profile_category_key ON profile_entries(category, key);
CREATE INDEX IF NOT EXISTS idx_conversation_chat ON conversation_sessions(chat_id);
CREATE INDEX IF NOT EXISTS idx_history_session ON conversation_history(session_id);
CREATE INDEX IF NOT EXISTS idx_interaction_chat ON interaction_log(chat_id);
CREATE INDEX IF NOT EXISTS idx_rag_source ON rag_documents(source);
"""


async def init_database(db_path: str) -> None:
    """Initialize the SQLite database with all required tables."""
    async with aiosqlite.connect(db_path) as db:
        await db.executescript(SCHEMA_SQL)
        await db.commit()
    _LOGGER.info("Database initialized at %s", db_path)


def init_database_sync(db_path: str) -> None:
    """Synchronous database initialization (for startup)."""
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(SCHEMA_SQL)
        conn.commit()
        _LOGGER.info("Database initialized (sync) at %s", db_path)
    finally:
        conn.close()
