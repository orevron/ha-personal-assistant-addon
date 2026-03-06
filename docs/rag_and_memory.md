# RAG & Memory

## RAG Engine

### Overview
The RAG engine uses **sqlite-vec** for vector search in the same SQLite database as profile/memory data. Embeddings generated via Ollama `nomic-embed-text`.

### Indexed Content

| Source | Content | Refresh |
|---|---|---|
| Entity registry | entity_id, friendly_name, domain, area | Every `rag_reindex_hours` |
| Automations | Name, status, last triggered | Every `rag_reindex_hours` |
| Scenes | Name, entity_id | Every `rag_reindex_hours` |
| Entity history | Summarized last 24h states | Every `history_reindex_hours` |
| User profile | Profile entries | On change |

### Retrieval
- Top-5 chunks by cosine similarity
- Results pass through Content Firewall (M8)
- sqlite-vec KNN when available, Python fallback otherwise

## Profile System

### Schema
```sql
profile_entries (category, key, value, confidence, sensitivity, source)
```

- **Categories**: preference, habit, pattern, fact
- **Sensitivity**: public, private, sensitive (M5)
- **Source**: told (user said it), observed (event learner), inferred
- **Confidence**: 0.0–1.0, increases with repeated observations

### Learning Pipeline
```
Response path:  User → Agent → Response (fast, no learning delay)
Learning path:  Interaction → Queue → Background Worker → Profile update
```

The learning worker is **fully decoupled** from the response path — zero added latency.

## Conversation Memory

- **Sessions**: Per-chat, expire after `session_timeout_minutes` of inactivity
- **History**: Stored in `conversation_history` table, archived on session expiry
- **Context**: Recent turns preserved verbatim, older turns summarized

## Event-Driven Learner

Observes HA state changes via WebSocket and InfluxDB queries:
- Detects patterns (e.g., lights off at 11 PM every night)
- Stores as profile entries with `source: observed`
- Runs analysis every 24 hours

## Multi-User

- Users auto-registered on first Telegram message
- Per-user settings stored in `user_profiles` table
- Chat IDs used for proactive notification targeting
