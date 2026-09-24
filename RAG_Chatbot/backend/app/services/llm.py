"""Provider-independent cloud and local LLM integration."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import httpx
from openai import APIError, APITimeoutError, OpenAI, RateLimitError

from app.core.config import Settings


class LLMProviderError(RuntimeError):
    """Safe, provider-agnostic generation failure."""


class LLMProvider(ABC):
    @abstractmethod
    def generate(self, system_prompt: str, user_prompt: str, response_schema: dict[str, Any] | None = None) -> str: ...

    def is_ready(self) -> bool:
        """Return whether the selected provider is usable without generation."""
        return True


class UnavailableLLMProvider(LLMProvider):
    def __init__(self, reason: str) -> None:
        self.reason = reason

    def generate(self, system_prompt: str, user_prompt: str, response_schema: dict[str, Any] | None = None) -> str:
        raise LLMProviderError(self.reason)

    def is_ready(self) -> bool:
        return False


class OpenRouterProvider(LLMProvider):
    """OpenRouter's OpenAI-compatible chat-completions client."""

    def __init__(self, settings: Settings) -> None:
        if not settings.llm_api_key or not settings.llm_base_url or not settings.llm_model:
            raise LLMProviderError("Cloud LLM is not configured")
        self.model = settings.llm_model
        self.client = OpenAI(
            api_key=settings.llm_api_key.get_secret_value(),
            base_url=str(settings.llm_base_url),
            timeout=settings.llm_timeout_seconds,
            max_retries=2,
        )

    def generate(self, system_prompt: str, user_prompt: str, response_schema: dict[str, Any] | None = None) -> str:
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                temperature=0,
            )
            answer = response.choices[0].message.content
            if not answer:
                raise LLMProviderError("Cloud LLM returned an empty response")
            return answer
        except (APITimeoutError, RateLimitError, APIError) as exc:
            raise LLMProviderError("Cloud LLM request failed") from exc


class OllamaProvider(LLMProvider):
    """Local Ollama chat API client; it never falls back to cloud providers."""

    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        if not settings.ollama_base_url or not settings.ollama_model:
            raise LLMProviderError("Local Ollama is not configured")
        self.model = settings.ollama_model
        self._base_url = str(settings.ollama_base_url).rstrip("/")
        self._timeout = settings.llm_timeout_seconds
        self._client = client

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            if self._client is not None:
                return self._client.request(method, f"{self._base_url}{path}", timeout=self._timeout, **kwargs)
            with httpx.Client(timeout=self._timeout) as client:
                return client.request(method, f"{self._base_url}{path}", **kwargs)
        except (httpx.HTTPError, ValueError) as exc:
            raise LLMProviderError("Local Ollama is unavailable") from exc

    def generate(self, system_prompt: str, user_prompt: str, response_schema: dict[str, Any] | None = None) -> str:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            "stream": False,
            "think": False,
            "options": {"temperature": 0},
        }
        if response_schema is not None:
            payload["format"] = response_schema
        response = self._request("POST", "/api/chat", json=payload)
        if response.status_code != 200:
            raise LLMProviderError("Local Ollama request failed")
        try:
            body = response.json()
            answer = body["message"]["content"]
        except (KeyError, TypeError, ValueError) as exc:
            raise LLMProviderError("Local Ollama returned an invalid response") from exc
        if not isinstance(answer, str) or not answer.strip():
            raise LLMProviderError("Local Ollama returned an empty response")
        return answer

    def is_ready(self) -> bool:
        response = self._request("GET", "/api/tags")
        if response.status_code != 200:
            raise LLMProviderError("Local Ollama is unavailable")
        try:
            models = response.json().get("models", [])
            return any(isinstance(item, dict) and item.get("name") == self.model for item in models)
        except (AttributeError, ValueError, TypeError) as exc:
            raise LLMProviderError("Local Ollama returned an invalid response") from exc


def build_llm_provider(settings: Settings) -> LLMProvider:
    if settings.llm_provider == "ollama":
        try:
            return OllamaProvider(settings)
        except LLMProviderError as exc:
            return UnavailableLLMProvider(str(exc))
    try:
        return OpenRouterProvider(settings)
    except LLMProviderError as exc:
        return UnavailableLLMProvider(str(exc))
