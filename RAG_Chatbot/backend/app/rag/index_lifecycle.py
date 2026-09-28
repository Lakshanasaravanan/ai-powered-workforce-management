"""Manifest-backed, offline-only lifecycle for local RAG index artifacts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from app.rag.sparse import BM25SparseRetriever, SparseIndexError
from app.services.vector_store import FaissVectorStore, VectorStoreError

if TYPE_CHECKING:
    from app.core.config import Settings
    from app.schemas.rag import DocumentChunk, PageDocument


INDEX_FORMAT_VERSION = "1"
MANIFEST_FILENAME = "manifest.json"


class IndexLifecycleError(RuntimeError):
    """An index is missing, stale, corrupt, or cannot be safely promoted."""


@dataclass(frozen=True)
class IndexStatus:
    available: bool
    reason: str | None = None


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def discover_policy_pdfs(documents_dir: Path) -> list[Path]:
    """Return only regular PDF files in deterministic filename order."""
    if not documents_dir.is_dir():
        return []
    root = documents_dir.resolve()
    paths = sorted((item for item in documents_dir.glob("*.pdf") if item.is_file()), key=lambda item: item.name)
    for item in paths:
        if root not in item.resolve().parents:
            raise IndexLifecycleError("Policy document path is outside the configured documents directory")
    return paths


def manifest_path(vector_directory: Path) -> Path:
    return vector_directory / MANIFEST_FILENAME


def create_manifest(
    settings: Settings,
    documents: list[Path],
    pages: list[PageDocument],
    chunks: list[DocumentChunk],
    embedding_dimension: int,
    sparse_artifact_name: str,
) -> dict:
    page_counts: dict[str, int] = {}
    chunk_counts: dict[str, int] = {}
    for page in pages:
        page_counts[page.source] = page_counts.get(page.source, 0) + 1
    for chunk in chunks:
        chunk_counts[chunk.metadata.source] = chunk_counts.get(chunk.metadata.source, 0) + 1
    sources = [
        {
            "source": item.name,
            "sha256": sha256_file(item),
            "pages": page_counts.get(item.name, 0),
            "chunks": chunk_counts.get(item.name, 0),
        }
        for item in documents
    ]
    return {
        "format_version": INDEX_FORMAT_VERSION,
        "built_at": datetime.now(timezone.utc).isoformat(),
        "embedding": {"model": settings.embedding_model, "dimension": embedding_dimension},
        "chunking": {
            "chunk_size": settings.rag_chunk_size,
            "chunk_overlap": settings.rag_chunk_overlap,
            "min_chunk_tokens": settings.rag_min_chunk_tokens,
        },
        "sources": sources,
        "page_count": len(pages),
        "chunk_count": len(chunks),
        "artifacts": {"faiss": "faiss.index", "records": "records.json", "sparse": sparse_artifact_name},
    }


def write_manifest(vector_directory: Path, manifest: dict) -> None:
    vector_directory.mkdir(parents=True, exist_ok=True)
    manifest_path(vector_directory).write_text(json.dumps(manifest, sort_keys=True, indent=2), encoding="utf-8")


def _read_manifest(vector_directory: Path) -> dict:
    try:
        value = json.loads(manifest_path(vector_directory).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise IndexLifecycleError("RAG index manifest is missing or unreadable; run the offline index build") from exc
    if not isinstance(value, dict):
        raise IndexLifecycleError("RAG index manifest is invalid; run the offline index build")
    return value


def validate_index(
    settings: Settings,
    documents_dir: Path,
    vector_directory: Path,
    sparse_path: Path,
) -> None:
    """Prove persisted artifacts match current non-secret source/config metadata."""
    manifest = _read_manifest(vector_directory)
    if manifest.get("format_version") != INDEX_FORMAT_VERSION:
        raise IndexLifecycleError("RAG index format is incompatible; run the offline index build")
    embedding = manifest.get("embedding", {})
    if embedding.get("model") != settings.embedding_model:
        raise IndexLifecycleError("RAG index embedding model is stale; run the offline index build")
    chunking = manifest.get("chunking", {})
    expected_chunking = {
        "chunk_size": settings.rag_chunk_size,
        "chunk_overlap": settings.rag_chunk_overlap,
        "min_chunk_tokens": settings.rag_min_chunk_tokens,
    }
    if chunking != expected_chunking:
        raise IndexLifecycleError("RAG index chunking configuration is stale; run the offline index build")
    documents = discover_policy_pdfs(documents_dir)
    expected_sources = [{"source": item.name, "sha256": sha256_file(item)} for item in documents]
    recorded_sources = manifest.get("sources")
    if not isinstance(recorded_sources, list) or [
        {"source": item.get("source"), "sha256": item.get("sha256")} for item in recorded_sources
    ] != expected_sources:
        raise IndexLifecycleError("RAG index policy documents are stale; run the offline index build")
    try:
        store = FaissVectorStore(vector_directory)
        dimension = int(embedding["dimension"])
        if store.count() != int(manifest["chunk_count"]) or store.count() == 0 or store._index is None or store._index.d != dimension:
            raise IndexLifecycleError("RAG index artifacts are inconsistent; run the offline index build")
        source_names = {item["source"] for item in recorded_sources}
        chunks = store.all_chunks()
        if not store.health_check() or any(
            chunk.metadata.source not in source_names
            or chunk.metadata.page < 1
            or not chunk.metadata.document_id
            or not chunk.metadata.document_version
            or not chunk.metadata.content_hash
            for chunk in chunks
        ):
            raise IndexLifecycleError("RAG index metadata is invalid; run the offline index build")
        BM25SparseRetriever.from_artifact(sparse_path, store)
    except IndexLifecycleError:
        raise
    except Exception as exc:
        raise IndexLifecycleError("RAG index artifacts are invalid; run the offline index build") from exc


def index_status(settings: Settings, documents_dir: Path, vector_directory: Path, sparse_path: Path) -> IndexStatus:
    try:
        validate_index(settings, documents_dir, vector_directory, sparse_path)
    except IndexLifecycleError as exc:
        return IndexStatus(False, str(exc))
    return IndexStatus(True)
