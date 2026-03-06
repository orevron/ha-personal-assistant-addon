# Security

## Threat Model

| Vector | Risk | Severity | Mitigation |
|---|---|---|---|
| Web search queries | PII leaks to DuckDuckGo | 🔴 Critical | M1 PII Sanitizer |
| Cloud LLM requests | Conversation data sent externally | 🔴 Critical | M4 Cloud Data Policy |
| Agent reasoning | Combines profile + search | 🟠 High | M3 System Prompt Rules |
| Prompt injection | Malicious web/RAG content | 🔴 Critical | M8 Content Firewall |
| Uncontrolled HA actions | Agent hallucinates service calls | 🔴 Critical | M7 Action Permission Layer |
| Error messages | Tokens/IPs in logs | 🟡 Medium | Sanitized Logging |
| SQLite at rest | Unencrypted local storage | 🟡 Medium | Docker isolation + HA file permissions |

## Controls

### M1 — PII Sanitizer (`tools/sanitizer.py`)

Pre-filters ALL outbound web search queries:
- Blocks phone numbers, emails, IP addresses, entity IDs
- User-configurable blocked keywords (names, addresses)
- Queries with too much PII are blocked entirely
- All queries logged to `search_audit_log`

### M3 — System Prompt Security Rules (`agent/prompts.py`)

Hard-coded, non-overridable rules in every LLM call:
- Never include PII in searches
- Never guess entity IDs — always use tool results
- Search recovery protocol for blocked queries

### M4 — Cloud LLM Data Policy

When using OpenAI/Gemini:
- Profile data excluded by default (`cloud_llm_send_profile: false`)
- HA state excluded by default (`cloud_llm_send_ha_state: false`)
- User warned during configuration

### M5 — Sensitive Data Classification

Profile entries tagged: `public` | `private` | `sensitive`
- `public`: safe for all contexts
- `private`: local LLM only
- `sensitive`: never sent externally

### M7 — Action Permission Layer (`tools/action_policy.py`)

Every HA service call is gated:
- **Allowed** domains: proceed immediately
- **Restricted** domains (lock, camera): Telegram confirmation required
- **Blocked** domains (homeassistant): NEVER callable

Confirmation uses Telegram inline keyboards (✅ Yes / ❌ Cancel).

### M8 — Content Firewall (`tools/content_firewall.py`)

Strips prompt injection from web results and RAG content:
- "Ignore previous instructions" patterns
- Tool call injection attempts
- "Unlock door" / "disarm alarm" instructions in external content

### M9 — Context Budget Control (`agent/context_assembler.py`)

Token-budgeted context assembly (default for 8K context):
- System prompt: ~800 tokens
- User profile: ~400 tokens
- HA context: ~800 tokens
- Conversation: ~2000 tokens
- RAG results: ~800 tokens
- Auto-scales with larger context windows

### Sanitized Logging

Custom log formatter redacts:
- Bearer tokens
- API keys
- Never logs full user messages at default log level
