"""Gemini LLM provider wrapper (optional cloud fallback).

No HA dependency — communicates directly with Google AI API.
"""

from __future__ import annotations

import logging

from langchain_core.language_models import BaseChatModel
from langchain_google_genai import ChatGoogleGenerativeAI

_LOGGER = logging.getLogger(__name__)


def create_gemini_model(
    api_key: str,
    model: str = "gemini-2.0-flash",
    **kwargs,
) -> BaseChatModel:
    """Create a ChatGoogleGenerativeAI instance.

    Args:
        api_key: Google AI API key.
        model: Model name.
        **kwargs: Additional parameters.
    """
    _LOGGER.info("Creating Gemini model: %s", model)
    return ChatGoogleGenerativeAI(
        google_api_key=api_key,
        model=model,
        **kwargs,
    )
