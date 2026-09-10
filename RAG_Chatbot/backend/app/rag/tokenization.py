"""Token counting with a local fallback when tiktoken's encoding cache is unavailable."""

from __future__ import annotations

import logging
import re
from functools import lru_cache
from typing import Any

import tiktoken


logger = logging.getLogger(__name__)


class WhitespaceTokenizer:
    """Deterministic fallback preserving words and trailing whitespace for local development."""

    def encode(self, text: str) -> list[str]:
        return re.findall(r"\S+\s*", text)

    def decode(self, tokens: list[str]) -> str:
        return "".join(tokens)


@lru_cache
def get_tokenizer() -> Any:
    try:
        return tiktoken.get_encoding("cl100k_base")
    except Exception:
        logger.warning("tiktoken_encoding_unavailable_using_local_fallback")
        return WhitespaceTokenizer()
