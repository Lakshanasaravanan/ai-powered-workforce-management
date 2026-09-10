"""Deterministic local BM25 sparse retrieval built from the indexed chunk corpus."""

from __future__ import annotations

import json
import re
from pathlib import Path

from rank_bm25 import BM25Okapi

from app.schemas.rag import DocumentChunk, MetadataFilter, RetrievedChunk
from app.services.vector_store import FaissVectorStore


TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


class SparseIndexError(RuntimeError):
    pass


def tokenize(text: str) -> list[str]:
    return TOKEN_PATTERN.findall(text.lower())


def write_sparse_corpus(path: Path, chunks: list[DocumentChunk]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([chunk.model_dump(mode="json") for chunk in sorted(chunks, key=lambda item: item.id)], ensure_ascii=False),
        encoding="utf-8",
    )


class BM25SparseRetriever:
    def __init__(self, chunks: list[DocumentChunk]) -> None:
        self.chunks = sorted(chunks, key=lambda item: item.id)
        self._bm25 = BM25Okapi([tokenize(chunk.text) for chunk in self.chunks]) if self.chunks else None

    @classmethod
    def from_artifact(cls, path: Path, vector_store: FaissVectorStore) -> "BM25SparseRetriever":
        if not path.exists():
            raise SparseIndexError("Sparse index artifact is missing; run offline indexing")
        try:
            chunks = [DocumentChunk.model_validate(value) for value in json.loads(path.read_text(encoding="utf-8"))]
        except (OSError, ValueError, TypeError) as exc:
            raise SparseIndexError("Sparse index artifact is unreadable") from exc
        vector_ids = {chunk.id for chunk in vector_store.all_chunks()}
        sparse_ids = {chunk.id for chunk in chunks}
        if vector_ids != sparse_ids:
            raise SparseIndexError("Sparse and dense indexes are inconsistent; run offline indexing")
        return cls(chunks)

    def retrieve(self, query: str, limit: int, metadata_filter: MetadataFilter | None = None) -> list[RetrievedChunk]:
        if not query.strip() or not self._bm25 or limit < 1:
            return []
        scores = self._bm25.get_scores(tokenize(query))
        ranked = sorted(enumerate(scores), key=lambda item: (-float(item[1]), self.chunks[item[0]].id))
        results: list[RetrievedChunk] = []
        for index, score in ranked:
            if score <= 0:
                break
            chunk = self.chunks[index]
            if not FaissVectorStore._matches_filter(chunk, metadata_filter):
                continue
            results.append(RetrievedChunk(**chunk.model_dump(), score=float(score), sparse_score=float(score)))
            if len(results) == limit:
                break
        return results
