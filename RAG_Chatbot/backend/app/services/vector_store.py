"""Vector-store abstraction with a local FAISS development implementation."""

from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from pathlib import Path

import faiss
import numpy as np

from app.schemas.rag import DocumentChunk, MetadataFilter, RetrievedChunk

# Keep the local baseline deterministic and avoid OpenMP oversubscription in API/test workers.
faiss.omp_set_num_threads(1)


class VectorStoreError(RuntimeError):
    """Raised for a local vector persistence or search failure."""


class VectorStore(ABC):
    @abstractmethod
    def create_collection(self, dimension: int, recreate: bool = False) -> None: ...

    @abstractmethod
    def upsert(self, chunks: list[DocumentChunk], vectors: np.ndarray) -> None: ...

    @abstractmethod
    def search(self, vector: np.ndarray, limit: int, metadata_filter: MetadataFilter | None = None) -> list[RetrievedChunk]: ...

    @abstractmethod
    def all_chunks(self) -> list[DocumentChunk]: ...

    @abstractmethod
    def delete(self, ids: list[str]) -> None: ...

    @abstractmethod
    def count(self) -> int: ...

    @abstractmethod
    def health_check(self) -> bool: ...


class FaissVectorStore(VectorStore):
    """Persistent cosine-similarity baseline; replaceable by Qdrant in Phase 3."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.index_path = directory / "faiss.index"
        self.records_path = directory / "records.json"
        self._index: faiss.IndexIDMap2 | None = None
        self._records: dict[str, DocumentChunk] = {}
        self._id_lookup: dict[int, str] = {}
        self._load()

    def _load(self) -> None:
        if self.index_path.exists() and self.records_path.exists():
            self._index = faiss.read_index(str(self.index_path))
            raw_records = json.loads(self.records_path.read_text(encoding="utf-8"))
            self._records = {key: DocumentChunk.model_validate(value) for key, value in raw_records.items()}
            self._id_lookup = {self._numeric_id(key): key for key in self._records}

    @staticmethod
    def _numeric_id(chunk_id: str) -> int:
        # Limit to signed int64 range expected by FAISS and resolve collisions deterministically below.
        return int(hashlib.sha256(chunk_id.encode("utf-8")).hexdigest()[:15], 16)

    def create_collection(self, dimension: int, recreate: bool = False) -> None:
        if self._index is not None and not recreate:
            if self._index.d != dimension:
                raise VectorStoreError("Existing index dimension does not match embedding dimension")
            return
        self.directory.mkdir(parents=True, exist_ok=True)
        self._index = faiss.IndexIDMap2(faiss.IndexFlatIP(dimension))
        self._records, self._id_lookup = {}, {}
        self._persist()

    def _require_index(self) -> faiss.IndexIDMap2:
        if self._index is None:
            raise VectorStoreError("Vector collection has not been created; run indexing first")
        return self._index

    def _persist(self) -> None:
        if self._index is None:
            return
        self.directory.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self._index, str(self.index_path))
        self.records_path.write_text(
            json.dumps({key: value.model_dump(mode="json") for key, value in self._records.items()}, ensure_ascii=False),
            encoding="utf-8",
        )

    def upsert(self, chunks: list[DocumentChunk], vectors: np.ndarray) -> None:
        index = self._require_index()
        vectors = np.asarray(vectors, dtype=np.float32)
        if len(chunks) != len(vectors) or vectors.ndim != 2 or vectors.shape[1] != index.d:
            raise VectorStoreError("Chunks and vectors must have matching counts and dimensions")
        ids: list[int] = []
        batch_ids: set[int] = set()
        for chunk in chunks:
            numeric_id = self._numeric_id(chunk.id)
            if numeric_id in batch_ids:
                raise VectorStoreError("Duplicate chunk identifier in one upsert batch")
            batch_ids.add(numeric_id)
            existing = self._id_lookup.get(numeric_id)
            if existing is not None and existing != chunk.id:
                raise VectorStoreError("Deterministic FAISS identifier collision")
            ids.append(numeric_id)
        replace_ids = np.asarray([numeric_id for numeric_id in ids if numeric_id in self._id_lookup], dtype=np.int64)
        if len(replace_ids):
            index.remove_ids(replace_ids)
        index.add_with_ids(vectors, np.asarray(ids, dtype=np.int64))
        for chunk, numeric_id in zip(chunks, ids, strict=True):
            self._records[chunk.id] = chunk
            self._id_lookup[numeric_id] = chunk.id
        self._persist()

    @staticmethod
    def _matches_filter(chunk: DocumentChunk, metadata_filter: MetadataFilter | None) -> bool:
        if metadata_filter is None:
            return True
        metadata = chunk.metadata
        return (
            (not metadata_filter.sources or metadata.source in metadata_filter.sources)
            and (not metadata_filter.document_ids or metadata.document_id in metadata_filter.document_ids)
            and (not metadata_filter.sections or metadata.section in metadata_filter.sections)
            and (not metadata_filter.document_version or metadata.document_version == metadata_filter.document_version)
            and (metadata_filter.page_min is None or metadata.page >= metadata_filter.page_min)
            and (metadata_filter.page_max is None or metadata.page <= metadata_filter.page_max)
        )

    def search(self, vector: np.ndarray, limit: int, metadata_filter: MetadataFilter | None = None) -> list[RetrievedChunk]:
        index = self._require_index()
        if limit < 1:
            return []
        vector = np.asarray(vector, dtype=np.float32).reshape(1, -1)
        if vector.shape[1] != index.d:
            raise VectorStoreError("Query vector dimension does not match the collection")
        # FAISS has no payload filters. Search all local vectors when filtering so valid matches
        # are not lost behind non-matching high-score vectors; Qdrant can optimize this natively.
        search_limit = index.ntotal if metadata_filter is not None else min(limit, index.ntotal)
        scores, ids = index.search(vector, search_limit)
        results: list[RetrievedChunk] = []
        for score, numeric_id in zip(scores[0], ids[0], strict=True):
            if numeric_id < 0 or (chunk_id := self._id_lookup.get(int(numeric_id))) is None:
                continue
            chunk = self._records[chunk_id]
            if self._matches_filter(chunk, metadata_filter):
                results.append(RetrievedChunk(**chunk.model_dump(), score=float(score), dense_score=float(score)))
            if len(results) == limit:
                break
        return results

    def all_chunks(self) -> list[DocumentChunk]:
        return [self._records[key] for key in sorted(self._records)]

    def delete(self, ids: list[str]) -> None:
        index = self._require_index()
        numeric_ids = [self._numeric_id(chunk_id) for chunk_id in ids if chunk_id in self._records]
        if numeric_ids:
            index.remove_ids(np.asarray(numeric_ids, dtype=np.int64))
            for numeric_id in numeric_ids:
                chunk_id = self._id_lookup.pop(numeric_id)
                self._records.pop(chunk_id, None)
            self._persist()

    def count(self) -> int:
        return int(self._index.ntotal) if self._index is not None else 0

    def health_check(self) -> bool:
        return self._index is not None and self._index.ntotal == len(self._records)
