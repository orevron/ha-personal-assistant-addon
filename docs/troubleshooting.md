# Troubleshooting

## Common Issues

### Add-on won't start

**Symptom**: Add-on immediately stops after starting.

**Check**:
1. **Log tab** → look for `SUPERVISOR_TOKEN not set` error
   - Fix: Ensure `homeassistant_api: true` in `config.yaml`
2. **Python import errors** → dependency not installed
   - Fix: Rebuild the add-on (Settings → Add-ons → Rebuild)
3. **Permission errors on `/data`** → filesystem issue
   - Fix: Check add-on has `map: config:rw` in config

### No response to Telegram messages

**Symptom**: Bot receives messages but doesn't reply.

**Checks**:
1. HA Telegram integration is working: check **Developer Tools → Events → Listen** for `telegram_text`
2. Add-on logs show `Subscribed to Telegram events`
3. Add-on logs show incoming message: `Telegram message from...`
4. Check Ollama is reachable: `curl http://YOUR_OLLAMA_IP:11434/api/tags`

### Ollama unreachable

**Symptom**: `Ollama health check failed` or `Connection refused`

**Fixes**:
1. Verify Ollama is running: `systemctl status ollama` or `docker ps`
2. Check the URL in add-on config matches your Ollama host
3. Ensure Ollama binds to `0.0.0.0` (not just localhost):
   ```bash
   OLLAMA_HOST=0.0.0.0 ollama serve
   ```
4. Check firewall allows port 11434 from HA

### Entity ID mismatches

**Symptom**: Agent says "entity not found" or calls wrong entity.

**Fix**: The agent must call `get_ha_entities` first to discover exact IDs. If this keeps happening:
1. Trigger RAG re-index (wait for `rag_reindex_hours` or restart add-on)
2. Check entity naming — avoid duplicate friendly names

### RAG returns stale data

**Symptom**: Agent references deleted/renamed entities.

**Fix**: Lower `rag_reindex_hours` or restart the add-on (triggers immediate re-index).

### Web search blocked

**Symptom**: Agent reports "Search BLOCKED by PII sanitizer"

**This is correct behavior** — the PII sanitizer blocked a query containing personal information. The agent should reformulate with generic terms. If searches are blocked too aggressively:
1. Check `pii_blocked_keywords` in config — remove over-broad keywords
2. Entity ID patterns (like `light.bedroom`) are always blocked — this is by design

### Token budget overflow

**Symptom**: Agent responses are truncated or incoherent.

**Fix**: If using a model with larger context, Ollama's `num_ctx` needs to match. The context assembler auto-scales with the configured window.

### High memory usage

**Symptom**: Add-on container uses excessive memory.

**Checks**:
1. Ollama runs separately — it handles the heavy GPU/RAM load
2. The add-on itself needs ~200MB for Python + SQLite
3. Large conversation histories can accumulate — reduce `session_timeout_minutes`

## Debug Mode

Set `log_level: debug` in add-on configuration for verbose logging. This will show:
- All WebSocket messages
- REST API calls and responses
- Tool invocations and results
- RAG query results
- Profile updates

> ⚠️ Debug logging may contain entity IDs and state data. Disable in production.

## Log Locations

- **Add-on panel** → Log tab (preferred)
- **SSH/Terminal**: `docker logs addon_local_personal_assistant`
- Logs are sanitized — tokens and API keys are redacted automatically
