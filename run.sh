#!/usr/bin/with-contenv bashio

bashio::log.info "Starting Personal Assistant add-on..."

# Config file path — Supervisor writes user options here
export PA_CONFIG_FILE="/data/options.json"

# SUPERVISOR_TOKEN is auto-injected by the HA Supervisor.
# It authenticates all REST/WebSocket calls to HA Core.

# Set log level from config
LOG_LEVEL=$(bashio::config 'log_level' 'info')
export PA_LOG_LEVEL="${LOG_LEVEL}"

bashio::log.info "Log level: ${LOG_LEVEL}"
bashio::log.info "Ollama URL: $(bashio::config 'ollama_url')"
bashio::log.info "Ollama model: $(bashio::config 'ollama_model')"

# Start the Python application
exec python3 /app/main.py
