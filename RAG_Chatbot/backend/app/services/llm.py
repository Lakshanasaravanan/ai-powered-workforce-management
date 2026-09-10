"""Provider-independent, OpenAI-compatible cloud LLM integration."""

from __future__ import annotations

from abc import ABC, abstractmethod

from openai import APIError, APITimeoutError, OpenAI, RateLimitError

from app.core.config import Settings


class LLMProviderError(RuntimeError):
    """Safe, provider-agnostic generation failure."""


class LLMProvider(ABC):
    @abstractmethod
    def generate(self, system_prompt: str, user_prompt: str) -> str: ...


class UnavailableLLMProvider(LLMProvider):
    def __init__(self, reason: str) -> None:
        self.reason = reason

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        raise LLMProviderError(self.reason)


class OpenRouterProvider(LLMProvider):
    """OpenRouter's OpenAI-compatible chat-completions API client."""

    def __init__(self, settings: Settings) -> None:
        if not settings.llm_api_key or not settings.llm_base_url or not settings.llm_model:
            raise LLMProviderError("Cloud LLM is not configured")
        self.model = settings.llm_model
        self.client = OpenAI(
            api_key=settings.llm_api_key.get_secret_value(),
            base_url=str(settings.llm_base_url),
            timeout=30.0,
            max_retries=2,
        )

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0,
            )
            answer = response.choices[0].message.content
            if not answer:
                raise LLMProviderError("Cloud LLM returned an empty response")
            return answer
        except (APITimeoutError, RateLimitError, APIError) as exc:
            raise LLMProviderError("Cloud LLM request failed") from exc


def build_llm_provider(settings: Settings) -> LLMProvider:
    provider = (settings.llm_provider or "openrouter").lower()
    if provider != "openrouter":
        return UnavailableLLMProvider("Configured LLM provider is not supported")
    try:
        return OpenRouterProvider(settings)
    except LLMProviderError as exc:
        return UnavailableLLMProvider(str(exc))
