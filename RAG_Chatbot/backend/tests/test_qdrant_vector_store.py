"""In-memory Qdrant contract tests; no external Qdrant service is required."""

from __future__ import annotations

import numpy as np
import pytest
from qdrant_client import QdrantClient

from app.core.config import Settings
from app.schemas.rag import ChunkMetadata, DocumentChunk, MetadataFilter
from app.services.qdrant_vector_store import QdrantVectorStore
from app.services.vector_store import VectorStoreError, create_vector_store


def chunk(identifier: str, source: str = "policy.pdf", page: int = 1) -> DocumentChunk:
    return DocumentChunk(
        id=identifier, text=f"text for {identifier}",
        metadata=ChunkMetadata(document_id="doc-a", source=source, file_path=source, page=page,
                               section="Policy", subsection="Details", chunk_index=page - 1,
                               content_hash=f"hash-{identifier}", document_version="version-a"),
    )


def store() -> QdrantVectorStore:
    return QdrantVectorStore("http://unused", "policy-test", client=QdrantClient(":memory:"))


def test_qdrant_creates_cosine_collection_upserts_filters_and_preserves_provenance():
    vector_store = store()
    vector_store.create_collection(2)
    first, second = chunk("chunk-one", "leave.pdf", 1), chunk("chunk-two", "security.pdf", 2)
    vector_store.upsert([first, second], np.asarray([[1, 0], [0, 1]], dtype=np.float32))
    results = vector_store.search(np.asarray([1, 0], dtype=np.float32), 5, MetadataFilter(sources={"leave.pdf"}))
    assert vector_store.health_check() and vector_store.count() == 2
    assert [item.id for item in results] == ["chunk-one"]
    assert results[0].metadata.source == "leave.pdf"
    assert results[0].metadata.page == 1 and results[0].metadata.section == "Policy"
    assert results[0].metadata.document_version == "version-a"


def test_qdrant_rejects_dimension_mismatch_and_never_silently_recreates():
    vector_store = store()
    vector_store.create_collection(2)
    with pytest.raises(VectorStoreError):
        vector_store.create_collection(3)
    with pytest.raises(VectorStoreError):
        vector_store.create_collection(2, recreate=True)
    with pytest.raises(VectorStoreError):
        vector_store.search(np.asarray([1, 0, 0], dtype=np.float32), 1)


def test_qdrant_unavailable_collection_fails_safely():
    vector_store = store()
    assert vector_store.health_check() is False
    with pytest.raises(VectorStoreError):
        vector_store.search(np.asarray([1, 0], dtype=np.float32), 1)


def test_explicit_backend_selection(monkeypatch, tmp_path):
    faiss_settings = Settings(_env_file=None)
    assert create_vector_store(faiss_settings, tmp_path).__class__.__name__ == "FaissVectorStore"
    qdrant_settings = faiss_settings.model_copy(update={"vector_store_backend": "qdrant", "qdrant_url": None})
    with pytest.raises(VectorStoreError):
        create_vector_store(qdrant_settings, tmp_path)
