"""LLM provider abstraction for multi-provider support."""

import os
from abc import ABC, abstractmethod
from typing import Optional

from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field


class LLMConfig(BaseModel):
    """Configuration for LLM provider."""

    provider: str = Field(default="anthropic", description="Provider: anthropic, openai, ollama")
    model: str = Field(default="claude-sonnet-4-20250514", description="Model name")
    api_key: Optional[str] = Field(None, description="API key (will use env var if not set)")
    base_url: Optional[str] = Field(None, description="Base URL for custom endpoints")
    temperature: float = Field(default=0.7, ge=0, le=2)
    max_tokens: int = Field(default=4096, ge=1)


class BaseLLMProvider(ABC):
    """Abstract base class for LLM providers."""

    def __init__(self, config: LLMConfig):
        self.config = config
        self._llm = None

    @abstractmethod
    def get_llm(self):
        """Get the LangChain LLM instance."""
        pass


class AnthropicProvider(BaseLLMProvider):
    """Anthropic Claude provider."""

    def get_llm(self):
        if self._llm is None:
            api_key = self.config.api_key or os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                raise ValueError("ANTHROPIC_API_KEY not set. Please set it in environment or config.")

            self._llm = ChatAnthropic(
                model=self.config.model,
                api_key=api_key,
                temperature=self.config.temperature,
                max_tokens_to_sample=self.config.max_tokens,
            )
        return self._llm


class OpenAIProvider(BaseLLMProvider):
    """OpenAI provider."""

    def get_llm(self):
        if self._llm is None:
            api_key = self.config.api_key or os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY not set. Please set it in environment or config.")

            # Support custom base URL from config or environment
            base_url = self.config.base_url or os.getenv("OPENAI_BASE_URL")

            self._llm = ChatOpenAI(
                model=self.config.model,
                api_key=api_key,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
                base_url=base_url,
            )
        return self._llm


class OllamaProvider(BaseLLMProvider):
    """Ollama provider for local models."""

    def get_llm(self):
        if self._llm is None:
            # Ollama uses OpenAI-compatible API
            base_url = self.config.base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")

            self._llm = ChatOpenAI(
                model=self.config.model,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
                base_url=base_url,
                api_key="ollama",  # Ollama doesn't need a real key
            )
        return self._llm


def get_llm_provider(config: Optional[LLMConfig] = None) -> BaseLLMProvider:
    """Factory function to get the appropriate LLM provider.

    Args:
        config: LLM configuration. If None, will use environment variables.

    Returns:
        Appropriate LLM provider instance.
    """
    if config is None:
        provider = os.getenv("LLM_PROVIDER", "anthropic")
        # For openai provider, support custom base URL from env
        base_url = None
        if provider == "openai":
            base_url = os.getenv("OPENAI_BASE_URL")
        elif provider == "ollama":
            base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")

        config = LLMConfig(
            provider=provider,
            model=os.getenv("LLM_MODEL", "claude-sonnet-4-20250514"),
            temperature=float(os.getenv("LLM_TEMPERATURE", "0.7")),
            max_tokens=int(os.getenv("LLM_MAX_TOKENS", "4096")),
            base_url=base_url,
        )

    providers = {
        "anthropic": AnthropicProvider,
        "openai": OpenAIProvider,
        "ollama": OllamaProvider,
    }

    provider_class = providers.get(config.provider)
    if not provider_class:
        raise ValueError(
            f"Unknown provider: {config.provider}. "
            f"Supported providers: {list(providers.keys())}"
        )

    return provider_class(config)
