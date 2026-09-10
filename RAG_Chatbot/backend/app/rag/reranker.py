"""Lazy cross-encoder reranking with a no-op disabled path."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

import numpy as np
from sentence_transformers import CrossEncoder

from app.schemas.rag import RetrievedChunk


class Reranker:
    def rerank(self, query: str, candidates: list[RetrievedChunk]) -> list[RetrievedChunk]:
        raise NotImplementedError


class DisabledReranker(Reranker):
    def rerank(self, query: str, candidates: list[RetrievedChunk]) -> list[RetrievedChunk]:
        return candidates


class CrossEncoderReranker(Reranker):
    def __init__(self, model_name: str, batch_size: int = 16, model_factory: Callable[[str], Any] = CrossEncoder) -> None:
        self.model_name, self.batch_size, self._factory = model_name, batch_size, model_factory
        self._model: Any | None = None
        self._lock = threading.Lock()

    @property
    def model(self) -> Any:
        if self._model is None:
            with self._lock:
                if self._model is None:
                    self._model = self._factory(self.model_name)
        return self._model

    def rerank(self, query: str, candidates: list[RetrievedChunk]) -> list[RetrievedChunk]:
        if not candidates:
            return []
        scores = np.asarray(self.model.predict([(query, item.text) for item in candidates], batch_size=self.batch_size), dtype=float)
        scored = [item.model_copy(update={"rerank_score": float(score)}) for item, score in zip(candidates, scores, strict=True)]
        return sorted(scored, key=lambda item: (-(item.rerank_score or 0.0), item.id))
