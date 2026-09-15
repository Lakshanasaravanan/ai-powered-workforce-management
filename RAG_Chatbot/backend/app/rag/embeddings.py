"""Reusable, normalized Sentence Transformer embedding service."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

import numpy as np
from sentence_transformers import SentenceTransformer


class EmbeddingService:
    """Lazy singleton-by-instance model wrapper; model loading never occurs per query."""

    def __init__(
        self,
        model_name: str,
        batch_size: int = 32,
        model_factory: Callable[[str], Any] = SentenceTransformer,
        device: str = "cpu",
        cache_dir: str | None = None,
        local_files_only: bool = False,
    ) -> None:
        self.model_name = model_name
        self.batch_size = batch_size
        self._model_factory = model_factory
        self._device = device
        self._model: Any | None = None
        self._lock = threading.Lock()
        self._cache_dir = cache_dir
        self._local_files_only = local_files_only

    @property
    def model(self) -> Any:
        if self._model is None:
            with self._lock:
                if self._model is None:
                    kwargs: dict[str, object] = {}
                    if self._cache_dir:
                        kwargs["cache_folder"] = self._cache_dir
                    kwargs["device"] = self._device
                    if self._local_files_only:
                        kwargs["local_files_only"] = True
                    self._model = self._model_factory(self.model_name, **kwargs)
        return self._model

    def encode(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, 0), dtype=np.float32)
        vectors = self.model.encode(
            texts,
            batch_size=self.batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        vectors = np.asarray(vectors, dtype=np.float32)
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        if np.any(norms == 0):
            raise ValueError("Embedding model returned a zero vector")
        return vectors / norms
