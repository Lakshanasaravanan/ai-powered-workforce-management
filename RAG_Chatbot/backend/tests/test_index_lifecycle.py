"""Deterministic, isolated coverage for offline RAG artifact lifecycle safety."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from app.core.config import Settings
from app.rag.index_lifecycle import (
    IndexLifecycleError,
    create_manifest,
    discover_policy_pdfs,
    index_status,
    validate_index,
    write_manifest,
)
from app.rag.ingestion import DOCUMENTS_DIR, _runtime_artifact_path, build_local_index
from app.rag.sparse import write_sparse_corpus
from app.schemas.rag import ChunkMetadata, DocumentChunk, PageDocument
from app.services.vector_store import FaissVectorStore


def settings() -> Settings:
    return Settings(_env_file=None)


def make_artifacts(tmp_path: Path):
    document_dir = tmp_path / "documents"
    document_dir.mkdir(parents=True)
    source = document_dir / "policy.pdf"
    source.write_bytes(b"policy fixture")
    source_hash = __import__("hashlib").sha256(source.read_bytes()).hexdigest()
    page = PageDocument(
        document_id=f"doc_{source_hash[:24]}", source=source.name, file_path="documents/policy.pdf", page=1,
        text="Policy text", document_version=source_hash[:12], content_hash="page-hash",
    )
    chunk = DocumentChunk(
        id="chunk-one", text="Policy text",
        metadata=ChunkMetadata(document_id=page.document_id, source=source.name, file_path="documents/policy.pdf", page=1,
                               chunk_index=0, content_hash="chunk-hash", document_version=source_hash[:12]),
    )
    vector_dir, sparse = tmp_path / "vectorstore", tmp_path / "sparse.json"
    store = FaissVectorStore(vector_dir)
    store.create_collection(2, recreate=True)
    store.upsert([chunk], np.asarray([[1.0, 0.0]], dtype=np.float32))
    write_sparse_corpus(sparse, [chunk])
    write_manifest(vector_dir, create_manifest(settings(), [source], [page], [chunk], 2, sparse.name))
    return document_dir, vector_dir, sparse, source, page, chunk


def test_discovery_is_sorted_and_real_policy_fixture_has_all_five_documents(tmp_path: Path):
    for name in ("z.pdf", "a.pdf", "not-policy.txt"):
        (tmp_path / name).write_bytes(b"x")
    assert [item.name for item in discover_policy_pdfs(tmp_path)] == ["a.pdf", "z.pdf"]
    real_documents = discover_policy_pdfs(DOCUMENTS_DIR)
    expected = [
        "XYZ_Code_of_Conduct.pdf", "XYZ_Employee_Policies.pdf", "XYZ_IT_Security_Policy.pdf",
        "XYZ_Leave_Attendance_Policy.pdf", "XYZ_Workforce_Management_Handbook.pdf",
    ]
    assert [item.name for item in real_documents] == expected
    assert [item["source"] for item in create_manifest(settings(), real_documents, [], [], 384, "bm25_corpus.json")["sources"]] == expected


def test_runtime_artifact_paths_are_opt_in(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    default = tmp_path / "historical" / "vectorstore"
    assert _runtime_artifact_path("RAG_TEST_RUNTIME_ARTIFACT", default) == default
    configured = tmp_path / "runtime" / "vectorstore"
    monkeypatch.setenv("RAG_TEST_RUNTIME_ARTIFACT", str(configured))
    assert _runtime_artifact_path("RAG_TEST_RUNTIME_ARTIFACT", default) == configured


def test_manifest_and_valid_artifacts_are_accepted(tmp_path: Path):
    documents, vector_dir, sparse, _, _, _ = make_artifacts(tmp_path)
    validate_index(settings(), documents, vector_dir, sparse)
    assert index_status(settings(), documents, vector_dir, sparse).available is True


@pytest.mark.parametrize("change", ["document", "embedding", "chunking"])
def test_stale_configuration_or_documents_are_rejected(tmp_path: Path, change: str):
    documents, vector_dir, sparse, source, _, _ = make_artifacts(tmp_path)
    current = settings()
    if change == "document":
        source.write_bytes(b"changed policy fixture")
    elif change == "embedding":
        current = current.model_copy(update={"embedding_model": "other-model"})
    else:
        current = current.model_copy(update={"rag_chunk_size": current.rag_chunk_size + 1})
    with pytest.raises(IndexLifecycleError):
        validate_index(current, documents, vector_dir, sparse)


def test_missing_or_inconsistent_artifacts_are_rejected(tmp_path: Path):
    documents, vector_dir, sparse, _, _, _ = make_artifacts(tmp_path)
    (vector_dir / "manifest.json").unlink()
    assert index_status(settings(), documents, vector_dir, sparse).available is False

    documents, vector_dir, sparse, _, _, _ = make_artifacts(tmp_path / "inconsistent")
    store = FaissVectorStore(vector_dir)
    store.create_collection(3, recreate=True)
    with pytest.raises(IndexLifecycleError):
        validate_index(settings(), documents, vector_dir, sparse)


def test_faiss_record_count_mismatch_and_invalid_metadata_are_rejected(tmp_path: Path):
    documents, vector_dir, sparse, _, _, _ = make_artifacts(tmp_path)
    store = FaissVectorStore(vector_dir)
    store._index.add_with_ids(np.asarray([[0.0, 1.0]], dtype=np.float32), np.asarray([99], dtype=np.int64))
    store._persist()
    with pytest.raises(IndexLifecycleError):
        validate_index(settings(), documents, vector_dir, sparse)

    documents, vector_dir, sparse, _, _, _ = make_artifacts(tmp_path / "metadata")
    records = vector_dir / "records.json"
    records.write_text("{not-json", encoding="utf-8")
    with pytest.raises(IndexLifecycleError):
        validate_index(settings(), documents, vector_dir, sparse)


def test_failed_offline_build_preserves_last_known_good_artifacts(monkeypatch, tmp_path: Path):
    documents, vector_dir, sparse, source, page, _ = make_artifacts(tmp_path)
    before = ((vector_dir / "faiss.index").read_bytes(), (vector_dir / "records.json").read_bytes(), sparse.read_bytes())
    monkeypatch.setattr("app.rag.ingestion.ingest_directory", lambda _: [page.model_copy(update={"text": "policy " * 40})])

    class FailingEmbeddings:
        def __init__(self, *args, **kwargs): pass
        def encode(self, texts): raise RuntimeError("embedding failed")

    monkeypatch.setattr("app.rag.ingestion.EmbeddingService", FailingEmbeddings)
    with pytest.raises(RuntimeError):
        build_local_index(documents_dir=documents, vector_dir=vector_dir, sparse_path=sparse, settings=settings())
    assert before == ((vector_dir / "faiss.index").read_bytes(), (vector_dir / "records.json").read_bytes(), sparse.read_bytes())
    assert source.exists()


def test_offline_build_promotes_only_valid_staged_artifacts(monkeypatch, tmp_path: Path):
    documents = tmp_path / "documents"
    documents.mkdir()
    source = documents / "policy.pdf"
    source.write_bytes(b"policy fixture")
    source_hash = __import__("hashlib").sha256(source.read_bytes()).hexdigest()
    page = PageDocument(document_id=f"doc_{source_hash[:24]}", source=source.name, file_path="documents/policy.pdf", page=1,
                        text="policy " * 40, document_version=source_hash[:12], content_hash="page-hash")

    class Embeddings:
        def __init__(self, *args, **kwargs): pass
        def encode(self, texts): return np.asarray([[1.0, 0.0] for _ in texts], dtype=np.float32)

    monkeypatch.setattr("app.rag.ingestion.ingest_directory", lambda _: [page])
    monkeypatch.setattr("app.rag.ingestion.EmbeddingService", Embeddings)
    vector_dir, sparse = tmp_path / "vectorstore", tmp_path / "sparse.json"
    report = build_local_index(documents_dir=documents, vector_dir=vector_dir, sparse_path=sparse, settings=settings())
    assert report["chunks"] > 0
    validate_index(settings(), documents, vector_dir, sparse)
