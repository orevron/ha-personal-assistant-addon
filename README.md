# Personal Assistant — Home Assistant Add-on

An AI-powered personal assistant running as a Home Assistant add-on. Uses LangGraph + Ollama for local LLM inference, RAG for knowledge grounding, and Telegram for interaction.

## Features

- 🤖 **LangGraph ReAct Agent** — tool-calling agent with per-conversation memory
- 🏠 **HA Integration** — queries entities, calls services, reads history via REST/WebSocket
- 📚 **RAG Knowledge** — sqlite-vec indexed HA entities, automations, scenes, and history
- 🧠 **Profile Learning** — learns preferences, habits, and patterns over time
- 🔍 **Web Search** — DuckDuckGo with PII sanitizer and content firewall
- 🔒 **Security** — 9 mitigation controls (M1–M9) covering PII leaks, prompt injection, action gating
- 📱 **Telegram** — communicates via HA's Telegram integration (WebSocket events)
- 🔔 **Proactive Alerts** — monitors for open doors, leaks, smoke, temperature anomalies
- 👥 **Multi-User** — per-user profiles and conversation sessions
- 🐳 **Dockerized** — isolated container, zero risk to HA Core

## Prerequisites

1. **Home Assistant OS** or **Supervised** installation (add-ons require the Supervisor)
2. **Telegram Bot** set up via HA's [Telegram integration](https://www.home-assistant.io/integrations/telegram/)
3. **Ollama** running on your network (default: `http://192.168.1.97:11434`)
4. Pull models: `ollama pull gpt-oss:20b` and `ollama pull nomic-embed-text`

## Installation

### Add Repository
1. Go to **Settings → Add-ons → Add-on Store → ⋮ → Repositories**
2. Add this repository URL
3. Find "Personal Assistant" and click **Install**

### Configure
1. Open the add-on **Configuration** tab
2. Set your **Ollama URL** and **model name**
3. (Optional) Add cloud LLM API keys, InfluxDB connection, custom PII keywords
4. Click **Save** → **Start**

### Verify
- Check the **Log** tab for `Personal Assistant add-on is ready!`
- Send a message to your Telegram bot: *"What lights are on?"*

## Configuration Options

| Option | Default | Description |
|---|---|---|
| `ollama_url` | `http://192.168.1.97:11434` | Ollama API endpoint |
| `ollama_model` | `gpt-oss:20b` | LLM model for chat |
| `embedding_model` | `nomic-embed-text` | Model for RAG embeddings |
| `cloud_llm_provider` | `none` | Optional: `openai` or `gemini` |
| `session_timeout_minutes` | `30` | Conversation session timeout |
| `rag_reindex_hours` | `24` | Full RAG re-index interval |
| `action_policy_restricted_domains` | `lock, camera` | Domains requiring Telegram confirmation |
| `action_policy_blocked_domains` | `homeassistant` | Domains the agent can NEVER call |
| `log_level` | `info` | Logging verbosity |

See [docs/configuration.md](docs/configuration.md) for the full reference.

## Security

This add-on implements 9 security controls:

| Control | Purpose |
|---|---|
| **M1** PII Sanitizer | Strips personal data from web search queries |
| **M3** System Prompt Rules | Hard-coded, non-overridable security instructions |
| **M4** Cloud Data Policy | Strips sensitive context when using cloud LLMs |
| **M7** Action Permission | Domain-based allow/restrict/block with Telegram confirmation |
| **M8** Content Firewall | Detects and strips prompt injection from web/RAG results |
| **M9** Context Budget | Token-budgeted context assembly to prevent context overflow |

See [docs/security.md](docs/security.md) for the full threat model.

## Architecture

The add-on runs as an isolated Docker container communicating with HA Core via the Supervisor API:

```
Telegram → HA Telegram Integration → Event Bus
                                        ↓ (WebSocket)
                                    Add-on Container
                                        ↓ (REST API)
                                    HA Core (entities, services)
```

See [docs/architecture.md](docs/architecture.md) for detailed diagrams.

## Documentation

- [Architecture](docs/architecture.md) — system design, data flow, async model
- [Security](docs/security.md) — threat model, all M1–M9 controls
- [Tools](docs/tools.md) — agent tool reference
- [RAG & Memory](docs/rag_and_memory.md) — knowledge engine, profile system
- [Configuration](docs/configuration.md) — full options reference
- [Troubleshooting](docs/troubleshooting.md) — common issues and fixes

## License

MIT
