# Changelog

All notable changes to the Personal Assistant add-on will be documented here.

## [0.1.0] - 2026-03-06

### Added
- Initial add-on release (migrated from custom integration to Docker add-on)
- **Core**: LangGraph ReAct agent with tool-calling and SQLite checkpointing
- **HA Client**: REST + WebSocket communication with HA Core via Supervisor API
- **LLM Support**: Ollama (local, default), OpenAI and Gemini (optional cloud)
- **Telegram Integration**: WebSocket event subscription for telegram_text/callback
- **RAG Engine**: sqlite-vec based knowledge retrieval with Ollama embeddings
  - Indexes entities, automations, scenes, history, and profile data
  - Periodic re-indexing (configurable intervals)
- **Profile & Memory**: Per-user profiles, conversation sessions, learning worker
- **Multi-User**: Automatic user registration, per-user settings
- **Proactive Notifications**: Configurable rules for doors, leaks, smoke, temperature
- **Security Controls**:
  - M1: PII Sanitizer for outbound web queries
  - M3: Hard-coded system prompt security rules
  - M4: Cloud LLM data stripping
  - M5: Sensitive data classification (public/private/sensitive)
  - M7: Action Permission Layer with domain policies and Telegram confirmation
  - M8: Content Firewall against prompt injection
  - M9: Token budget context assembler
- **Web Search**: DuckDuckGo with PII sanitizer pre-filter and content firewall
- **Event Learner**: Observes state_changed events + InfluxDB pattern detection
- **CI/CD**: GitHub Actions auto-release on push to main
- **Logging**: Sanitized log formatter that redacts tokens and API keys
