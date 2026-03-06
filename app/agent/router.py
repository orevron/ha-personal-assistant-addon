"""LLM provider router.

Routes LLM calls to Ollama (default/local) or optional cloud providers
(OpenAI, Gemini). Performs health checks and handles fallback.

Config comes from /data/options.json instead of HA config entry.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.language_models import BaseChatModel

_LOGGER = logging.getLogger(__name__)


class LLMRouter:
    """Routes LLM calls to the appropriate provider."""

    def __init__(self, config: dict[str, Any]) -> None:
        self._config = config
        self._ollama_url = config.get("ollama_url", "http://192.168.1.97:11434")
        self._ollama_model = config.get("ollama_model", "gpt-oss:20b")
        self._cloud_provider = config.get("cloud_llm_provider", "none")
        self._cloud_api_key = config.get("cloud_llm_api_key", "")
        self._cloud_model = config.get("cloud_llm_model", "")
        self._primary: BaseChatModel | None = None
        self._fallback: BaseChatModel | None = None

    @property
    def is_cloud(self) -> bool:
        """Whether the currently active LLM is a cloud provider."""
        return self._cloud_provider != "none" and self._primary is None

    def get_chat_model(self, use_cloud: bool = False) -> BaseChatModel:
        """Get the LLM chat model.

        Args:
            use_cloud: Force cloud provider (if configured).

        Returns:
            A LangChain BaseChatModel with tool-calling + async support.
        """
        if use_cloud and self._cloud_provider != "none":
            return self._get_cloud_model()

        if self._primary is None:
            self._primary = self._create_ollama_model()

        return self._primary

    def get_embedding_model_name(self) -> str:
        """Return the configured embedding model name."""
        return self._config.get("embedding_model", "nomic-embed-text")

    def get_ollama_url(self) -> str:
        """Return the configured Ollama URL."""
        return self._ollama_url

    def _create_ollama_model(self) -> BaseChatModel:
        """Create a ChatOllama instance."""
        from langchain_ollama import ChatOllama

        _LOGGER.info(
            "Initializing Ollama LLM: %s @ %s",
            self._ollama_model,
            self._ollama_url,
        )
        return ChatOllama(
            base_url=self._ollama_url,
            model=self._ollama_model,
        )

    def _get_cloud_model(self) -> BaseChatModel:
        """Create a cloud LLM provider model."""
        if self._fallback is not None:
            return self._fallback

        if self._cloud_provider == "openai":
            from langchain_openai import ChatOpenAI

            _LOGGER.info("Initializing OpenAI LLM: %s", self._cloud_model)
            self._fallback = ChatOpenAI(
                api_key=self._cloud_api_key,
                model=self._cloud_model or "gpt-4o-mini",
            )
        elif self._cloud_provider == "gemini":
            from langchain_google_genai import ChatGoogleGenerativeAI

            _LOGGER.info("Initializing Gemini LLM: %s", self._cloud_model)
            self._fallback = ChatGoogleGenerativeAI(
                google_api_key=self._cloud_api_key,
                model=self._cloud_model or "gemini-2.0-flash",
            )
        else:
            raise ValueError(f"Unknown cloud provider: {self._cloud_provider}")

        return self._fallback

    async def health_check(self) -> bool:
        """Check if Ollama is reachable."""
        import aiohttp

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self._ollama_url}/api/tags", timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    return resp.status == 200
        except Exception as err:
            _LOGGER.warning("Ollama health check failed: %s", err)
            return False
