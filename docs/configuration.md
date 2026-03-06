# Configuration

## Add-on Options

All configuration is done via the add-on panel in **Settings → Add-ons → Personal Assistant → Configuration**.

### LLM Settings

| Option | Type | Default | Description |
|---|---|---|---|
| `ollama_url` | URL | `http://192.168.1.97:11434` | Ollama API endpoint |
| `ollama_model` | string | `gpt-oss:20b` | Chat model name |
| `embedding_model` | string | `nomic-embed-text` | Embedding model for RAG |

### Cloud LLM (Optional)

| Option | Type | Default | Description |
|---|---|---|---|
| `cloud_llm_provider` | select | `none` | `none`, `openai`, or `gemini` |
| `cloud_llm_api_key` | string | | API key for cloud provider |
| `cloud_llm_model` | string | | Model name (e.g., `gpt-4o-mini`) |
| `cloud_llm_send_profile` | bool | `false` | Include profile data in cloud calls |
| `cloud_llm_send_ha_state` | bool | `false` | Include HA state in cloud calls |

> ⚠️ Using cloud LLMs sends conversation data to external servers.

### Agent Behavior

| Option | Type | Default | Description |
|---|---|---|---|
| `persona` | string | `You are a helpful...` | Agent personality prompt |
| `session_timeout_minutes` | int | `30` | Conversation session timeout |

### RAG Settings

| Option | Type | Default | Description |
|---|---|---|---|
| `rag_reindex_hours` | int | `24` | Full RAG re-index interval |
| `history_reindex_hours` | int | `6` | History re-index interval |

### InfluxDB (Optional)

| Option | Type | Default | Description |
|---|---|---|---|
| `influxdb_url` | URL | | InfluxDB endpoint |
| `influxdb_token` | string | | Auth token |
| `influxdb_org` | string | | Organization |
| `influxdb_bucket` | string | | Bucket name |

### Security & Action Policy

| Option | Type | Default | Description |
|---|---|---|---|
| `pii_blocked_keywords` | list | `[]` | Custom keywords to block in searches |
| `action_policy_allowed_domains` | string | `*` | Allowed HA domains |
| `action_policy_restricted_domains` | list | `lock, camera` | Require Telegram confirmation |
| `action_policy_blocked_domains` | list | `homeassistant` | NEVER callable |
| `action_policy_require_confirmation` | list | `lock.unlock, ...` | Specific services needing ✅/❌ |

### Logging

| Option | Type | Default | Description |
|---|---|---|---|
| `log_level` | select | `info` | `debug`, `info`, `warning`, `error` |

## Telegram Setup

This add-on **does not manage** the Telegram bot. Set up Telegram via HA's built-in integration:

1. Create a bot via [@BotFather](https://t.me/botfather)
2. In HA: **Settings → Integrations → Add → Telegram Bot**
3. Configure the bot token and allowed chat IDs
4. The add-on automatically subscribes to `telegram_text` events

## Ollama Setup

1. Install Ollama: `curl -fsSL https://ollama.com/install.sh | sh`
2. Pull models:
   ```bash
   ollama pull gpt-oss:20b
   ollama pull nomic-embed-text
   ```
3. Ensure Ollama is accessible from HA network
4. Set `ollama_url` in add-on config
