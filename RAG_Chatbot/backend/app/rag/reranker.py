"""Lazy cross-encoder reranking with a no-op disabled path."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

import numpy as np

from app.schemas.rag import RetrievedChunk


def _cross_encoder_factory(model_name: str, **kwargs: object) -> Any:
    """Avoid importing Torch until reranking is actually enabled and used."""
    from sentence_transformers import CrossEncoder

    return CrossEncoder(model_name, **kwargs)


class Reranker:
    def rerank(self, query: str, candidates: list[RetrievedChunk]) -> list[RetrievedChunk]:
        raise NotImplementedError


class DisabledReranker(Reranker):
    def rerank(self, query: str, candidates: list[RetrievedChunk]) -> list[RetrievedChunk]:
        return candidates


class CrossEncoderReranker(Reranker):
    def __init__(self, model_name: str, batch_size: int = 16, model_factory: Callable[..., Any] = _cross_encoder_factory, cache_dir: str | None = None, local_files_only: bool = False) -> None:
        self.model_name, self.batch_size, self._factory = model_name, batch_size, model_factory
        self._model: Any | None = None
        self._lock = threading.Lock()
        self._cache_dir, self._local_files_only = cache_dir, local_files_only

    @property
    def model(self) -> Any:
        if self._model is None:
            with self._lock:
                if self._model is None:
                    kwargs: dict[str, object] = {}
                    if self._cache_dir:
                        kwargs["cache_folder"] = self._cache_dir
                    if self._local_files_only:
                        kwargs["local_files_only"] = True
                    self._model = self._factory(self.model_name, **kwargs)
        return self._model

    def rerank(self, query: str, candidates: list[RetrievedChunk]) -> list[RetrievedChunk]:
        if not candidates:
            return []
        scores = np.asarray(self.model.predict([(query, item.text) for item in candidates], batch_size=self.batch_size), dtype=float)
        scored = [item.model_copy(update={"rerank_score": float(score)}) for item, score in zip(candidates, scores, strict=True)]
        return sorted(scored, key=lambda item: (-(item.rerank_score or 0.0), item.id))
