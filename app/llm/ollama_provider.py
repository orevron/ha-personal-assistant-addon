"""Ollama LLM provider wrapper.

Thin wrapper around langchain_ollama.ChatOllama for local inference.
No HA dependency — communicates directly with Ollama API.
"""

from __future__ import annotations

import logging

from langchain_core.language_models import BaseChatModel
from langchain_ollama import ChatOllama

_LOGGER = logging.getLogger(__name__)


def create_ollama_model(
    base_url: str = "http://192.168.1.97:11434",
    model: str = "gpt-oss:20b",
    **kwargs,
) -> BaseChatModel:
    """Create a ChatOllama instance.

    Args:
        base_url: Ollama server URL.
        model: Model name.
        **kwargs: Additional ChatOllama parameters.
    """
    _LOGGER.info("Creating Ollama model: %s @ %s", model, base_url)
    return ChatOllama(
        base_url=base_url,
        model=model,
        **kwargs,
    )
