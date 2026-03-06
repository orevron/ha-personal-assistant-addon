"""OpenAI LLM provider wrapper (optional cloud fallback).

No HA dependency — communicates directly with OpenAI API.
"""

from __future__ import annotations

import logging

from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI

_LOGGER = logging.getLogger(__name__)


def create_openai_model(
    api_key: str,
    model: str = "gpt-4o-mini",
    **kwargs,
) -> BaseChatModel:
    """Create a ChatOpenAI instance.

    Args:
        api_key: OpenAI API key.
        model: Model name.
        **kwargs: Additional ChatOpenAI parameters.
    """
    _LOGGER.info("Creating OpenAI model: %s", model)
    return ChatOpenAI(
        api_key=api_key,
        model=model,
        **kwargs,
    )
