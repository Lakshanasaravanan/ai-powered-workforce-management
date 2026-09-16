"""Qdrant implementation of the RAG VectorStore contract.

Provisioning is offline-only.  This adapter never creates, recreates, or
mutates a collection during a search or readiness check.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from qdrant_client import QdrantClient, models

from app.schemas.rag import DocumentChunk, MetadataFilter, RetrievedChunk
from app.services.vector_store import FaissVectorStore, VectorStore, VectorStoreError


class QdrantVectorStore(VectorStore):
    def __init__(self, url: str, collection: str, api_key: str | None = None, client: QdrantClient | None = None) -> None:
        if not collection or not collection.replace("-", "").replace("_", "").isalnum():
            raise VectorStoreError("Qdrant collection name is invalid")
        self.collection = collection
        self._client = client or QdrantClient(url=url, api_key=api_key, timeout=3)

    @staticmethod
    def _payload(chunk: DocumentChunk) -> dict[str, Any]:
        return {"chunk": chunk.model_dump(mode="json"), "index_format_version": "1"}

    @staticmethod
    def _chunk(payload: dict[str, Any]) -> DocumentChunk:
        try:
            return DocumentChunk.model_validate(payload["chunk"])
        except (KeyError, TypeError, ValueError) as exc:
            raise VectorStoreError("Qdrant payload is invalid") from exc

    def _info(self):
        try:
            return self._client.get_collection(self.collection)
        except Exception as exc:
            raise VectorStoreError("Qdrant collection is unavailable") from exc

    def _validate(self, dimension: int | None = None) -> None:
        info = self._info()
        vectors = info.config.params.vectors
        if not isinstance(vectors, models.VectorParams) or vectors.distance != models.Distance.COSINE:
            raise VectorStoreError("Qdrant collection is incompatible")
        if dimension is not None and vectors.size != dimension:
            raise VectorStoreError("Qdrant collection dimension is incompatible")

    def validate_collection(self, dimension: int) -> None:
        self._validate(dimension)

    def create_collection(self, dimension: int, recreate: bool = False) -> None:
        try:
            self._validate(dimension)
            if recreate:
                raise VectorStoreError("Qdrant recreation is not permitted by this adapter")
            return
        except VectorStoreError as exc:
            if "unavailable" not in str(exc):
                raise
        try:
            self._client.create_collection(
                self.collection,
                vectors_config=models.VectorParams(size=dimension, distance=models.Distance.COSINE),
                metadata={"index_format_version": "1"},
            )
        except Exception as exc:
            raise VectorStoreError("Qdrant collection provisioning failed") from exc
        self._validate(dimension)

    def upsert(self, chunks: list[DocumentChunk], vectors: np.ndarray) -> None:
        vectors = np.asarray(vectors, dtype=np.float32)
        if len(chunks) != len(vectors) or vectors.ndim != 2:
            raise VectorStoreError("Chunks and vectors must have matching counts and dimensions")
        self._validate(vectors.shape[1])
        points = [
            models.PointStruct(id=FaissVectorStore._numeric_id(chunk.id), vector=vector.tolist(), payload=self._payload(chunk))
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]
        try:
            self._client.upsert(self.collection, points=points, wait=True)
        except Exception as exc:
            raise VectorStoreError("Qdrant upsert failed") from exc

    @staticmethod
    def _filter(metadata_filter: MetadataFilter | None):
        if metadata_filter is None:
            return None
        conditions = []
        mapping = {
            "sources": "chunk.metadata.source", "document_ids": "chunk.metadata.document_id",
            "sections": "chunk.metadata.section", "document_version": "chunk.metadata.document_version",
        }
        for field, key in mapping.items():
            value = getattr(metadata_filter, field)
            if value:
                values = [value] if isinstance(value, str) else sorted(value)
                conditions.append(models.FieldCondition(key=key, match=models.MatchAny(any=values)))
        if metadata_filter.page_min is not None:
            conditions.append(models.FieldCondition(key="chunk.metadata.page", range=models.Range(gte=metadata_filter.page_min)))
        if metadata_filter.page_max is not None:
            conditions.append(models.FieldCondition(key="chunk.metadata.page", range=models.Range(lte=metadata_filter.page_max)))
        return models.Filter(must=conditions) if conditions else None

    def search(self, vector: np.ndarray, limit: int, metadata_filter: MetadataFilter | None = None) -> list[RetrievedChunk]:
        if limit < 1:
            return []
        query = np.asarray(vector, dtype=np.float32).reshape(-1)
        self._validate(query.shape[0])
        try:
            response = self._client.query_points(self.collection, query=query.tolist(), query_filter=self._filter(metadata_filter), limit=limit, with_payload=True)
            return [RetrievedChunk(**self._chunk(point.payload).model_dump(), score=float(point.score), dense_score=float(point.score)) for point in response.points]
        except VectorStoreError:
            raise
        except Exception as exc:
            raise VectorStoreError("Qdrant search failed") from exc

    def all_chunks(self) -> list[DocumentChunk]:
        records, offset = [], None
        try:
            while True:
                batch, offset = self._client.scroll(self.collection, limit=256, offset=offset, with_payload=True)
                records.extend(batch)
                if offset is None:
                    break
            return sorted((self._chunk(record.payload) for record in records), key=lambda item: item.id)
        except Exception as exc:
            raise VectorStoreError("Qdrant records are unavailable") from exc

    def delete(self, ids: list[str]) -> None:
        if not ids:
            return
        try:
            self._client.delete(self.collection, points_selector=models.PointIdsList(points=[FaissVectorStore._numeric_id(value) for value in ids]), wait=True)
        except Exception as exc:
            raise VectorStoreError("Qdrant delete failed") from exc

    def count(self) -> int:
        try:
            return int(self._client.count(self.collection, exact=True).count)
        except Exception as exc:
            raise VectorStoreError("Qdrant collection is unavailable") from exc

    def health_check(self) -> bool:
        try:
            self._validate()
            return True
        except VectorStoreError:
            return False
