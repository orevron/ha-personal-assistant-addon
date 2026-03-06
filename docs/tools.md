# Agent Tools Reference

## HA Tools (`tools/ha_tools.py`)

### `get_ha_entities`
Lists HA entities with optional domain/area filtering. Returns `friendly_name → entity_id` mapping.

| Param | Type | Description |
|---|---|---|
| `domain` | `str?` | Filter by domain (light, switch, climate) |
| `area` | `str?` | Filter by area name |
| **Returns** | `dict[str, str]` | `{friendly_name: entity_id}` |

### `get_entity_state`
Gets current state and attributes for a specific entity.

| Param | Type | Description |
|---|---|---|
| `entity_id` | `str` | Exact entity ID from `get_ha_entities` |
| **Returns** | `dict` | state, attributes, last_changed, last_updated |

### `call_ha_service`
Calls a HA service — passes through Action Permission Layer (M7).

| Param | Type | Description |
|---|---|---|
| `domain` | `str` | Service domain (light, switch) |
| `service` | `str` | Service name (turn_on, turn_off) |
| `entity_id` | `str` | Target entity |
| **Returns** | `str` | Success/failure message |

**Blocked domains** return an error. **Restricted domains** trigger Telegram confirmation.

### `get_entity_history`
Returns historical states for an entity.

| Param | Type | Description |
|---|---|---|
| `entity_id` | `str` | Target entity |
| `hours` | `int` | Lookback period (default: 24) |

## Web Search (`tools/web_search.py`)

### `search_web`
DuckDuckGo search with M1 (PII sanitizer) pre-filter and M8 (content firewall) post-filter.

| Param | Type | Description |
|---|---|---|
| `query` | `str` | Search query (must not contain PII) |
| **Returns** | `str` | Top 5 results with title, snippet, URL |

Blocked queries return an error with reformulation instructions.

## Profile Tools (`tools/profile_tools.py`)

### `get_user_profile`
Reads stored user preferences and learned facts.

### `update_user_profile`
Stores a new learning (category: preference/habit/pattern/fact).

## RAG Tool (`tools/rag_tools.py`)

### `retrieve_knowledge`
Searches indexed HA knowledge (entities, automations, scenes, history, profile). Results pass through Content Firewall (M8).
