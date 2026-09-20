"""Resilient PDF ingestion and the repeatable local indexing entry point."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import tempfile
from pathlib import Path
from uuid import uuid4

from pypdf import PdfReader

from app.core.config import get_settings
from app.rag.cleaning import clean_documents
from app.rag.chunking import chunk_documents
from app.rag.embeddings import EmbeddingService
from app.schemas.rag import PageDocument
from app.services.vector_store import FaissVectorStore
from app.rag.sparse import write_sparse_corpus
from app.rag.index_lifecycle import (
    IndexLifecycleError,
    create_manifest,
    discover_policy_pdfs,
    validate_index,
    write_manifest,
)


logger = logging.getLogger(__name__)
PROJECT_DIR = Path(__file__).resolve().parents[3]
DOCUMENTS_DIR = PROJECT_DIR / "data" / "documents"


def _runtime_artifact_path(variable: str, default: Path) -> Path:
    """Allow an explicit local runtime index without changing repository artifacts."""
    configured = os.environ.get(variable)
    return Path(configured).expanduser() if configured else default


# Generated local artifacts belong under the ignored runtime directory by
# default.  Explicit environment values remain available for deployments and
# controlled builds, but local serving must never depend on the caller's cwd.
VECTOR_STORE_DIR = _runtime_artifact_path("RAG_RUNTIME_VECTOR_STORE_DIR", PROJECT_DIR / "data" / "runtime" / "vectorstore")
SPARSE_INDEX_PATH = _runtime_artifact_path("RAG_RUNTIME_SPARSE_INDEX_PATH", PROJECT_DIR / "data" / "runtime" / "sparse" / "bm25_corpus.json")


def _sha256(value: bytes | str) -> str:
    if isinstance(value, str):
        value = value.encode("utf-8")
    return hashlib.sha256(value).hexdigest()


def ingest_pdf(file_path: Path) -> list[PageDocument]:
    """Extract non-empty PDF pages while retaining deterministic provenance metadata."""
    try:
        file_hash = _sha256(file_path.read_bytes())
        reader = PdfReader(str(file_path))
    except Exception as exc:
        # pypdf has several parser exception types across releases; one bad file is non-fatal.
        logger.warning("pdf_open_failed", extra={"source": file_path.name, "error_type": type(exc).__name__})
        return []

    document_id = f"doc_{file_hash[:24]}"
    version = file_hash[:12]
    pages: list[PageDocument] = []
    for page_number, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception as exc:  # A malformed page must not discard healthy pages.
            logger.warning(
                "pdf_page_extract_failed",
                extra={"source": file_path.name, "page": page_number, "error_type": type(exc).__name__},
            )
            continue
        if not text.strip():
            continue
        pages.append(
            PageDocument(
                document_id=document_id,
                source=file_path.name,
                # Citation provenance needs the stable source name, not a
                # machine-specific absolute path.
                file_path=file_path.name,
                page=page_number,
                text=text,
                document_version=version,
                content_hash=_sha256(text),
            )
        )
    return pages


def ingest_directory(documents_dir: Path = DOCUMENTS_DIR) -> list[PageDocument]:
    """Ingest each PDF independently so a bad document never aborts a batch."""
    if not documents_dir.exists():
        logger.warning("documents_directory_missing")
        return []
    documents: list[PageDocument] = []
    for pdf_path in discover_policy_pdfs(documents_dir):
        documents.extend(ingest_pdf(pdf_path))
    return documents


def _remove_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def _promote_artifacts(staged_vector_dir: Path, staged_sparse_path: Path, vector_dir: Path, sparse_path: Path) -> None:
    """Replace validated artifacts with rollback backups if promotion itself fails."""
    token = uuid4().hex
    vector_backup = vector_dir.parent / f".{vector_dir.name}.backup-{token}"
    sparse_backup = sparse_path.parent / f".{sparse_path.name}.backup-{token}"
    moved_vector = moved_sparse = False
    try:
        if vector_dir.exists():
            os.replace(vector_dir, vector_backup)
            moved_vector = True
        os.replace(staged_vector_dir, vector_dir)
        if sparse_path.exists():
            os.replace(sparse_path, sparse_backup)
            moved_sparse = True
        os.replace(staged_sparse_path, sparse_path)
    except Exception:
        # A failed promotion is rolled back to the previous complete generation.
        if vector_dir.exists():
            _remove_path(vector_dir)
        if sparse_path.exists():
            _remove_path(sparse_path)
        if moved_vector and vector_backup.exists():
            os.replace(vector_backup, vector_dir)
        if moved_sparse and sparse_backup.exists():
            os.replace(sparse_backup, sparse_path)
        raise
    finally:
        if vector_backup.exists():
            _remove_path(vector_backup)
        if sparse_backup.exists():
            _remove_path(sparse_backup)


def build_local_index(
    *,
    documents_dir: Path = DOCUMENTS_DIR,
    vector_dir: Path = VECTOR_STORE_DIR,
    sparse_path: Path = SPARSE_INDEX_PATH,
    settings=None,
) -> dict[str, int]:
    """Explicit offline build with staged validation and rollback-safe promotion.

    This function is intentionally never invoked from API startup or requests.
    """
    settings = settings or get_settings()
    documents = discover_policy_pdfs(documents_dir)
    pages = clean_documents(ingest_directory(documents_dir))
    chunks = chunk_documents(pages, settings.rag_chunk_size, settings.rag_chunk_overlap, settings.rag_min_chunk_tokens)
    if not chunks:
        raise IndexLifecycleError("No indexable policy chunks were produced; existing artifacts were preserved")

    embedding_options: dict[str, object] = {}
    if settings.embedding_cache_dir:
        embedding_options["cache_dir"] = str(settings.embedding_cache_dir)
    if settings.embedding_local_files_only:
        embedding_options["local_files_only"] = True
    embeddings = EmbeddingService(settings.embedding_model, device=settings.embedding_device, **embedding_options).encode([chunk.text for chunk in chunks])
    vector_dir.parent.mkdir(parents=True, exist_ok=True)
    sparse_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f".{vector_dir.name}.build-", dir=vector_dir.parent) as temporary:
        staging_root = Path(temporary)
        staged_vector_dir = staging_root / vector_dir.name
        staged_sparse_path = staging_root / sparse_path.name
        store = FaissVectorStore(staged_vector_dir)
        store.create_collection(embeddings.shape[1], recreate=True)
        store.upsert(chunks, embeddings)
        write_sparse_corpus(staged_sparse_path, chunks)
        manifest = create_manifest(
            settings,
            documents,
            pages,
            chunks,
            int(embeddings.shape[1]),
            sparse_path.name,
        )
        write_manifest(staged_vector_dir, manifest)
        validate_index(settings, documents_dir, staged_vector_dir, staged_sparse_path)
        _promote_artifacts(staged_vector_dir, staged_sparse_path, vector_dir, sparse_path)
    return {
        "documents": len({page.document_id for page in pages}),
        "pages": len(pages),
        "chunks": len(chunks),
        "embedding_dimension": int(embeddings.shape[1]),
    }


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Build the local policy index offline")
    parser.add_argument("command", nargs="?", default="build", choices=["build"])
    parser.parse_args()
    print(json.dumps(build_local_index(), sort_keys=True))
