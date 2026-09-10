"""Resilient PDF ingestion and the repeatable local indexing entry point."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from pypdf import PdfReader

from app.core.config import get_settings
from app.rag.cleaning import clean_documents
from app.rag.chunking import chunk_documents
from app.rag.embeddings import EmbeddingService
from app.schemas.rag import PageDocument
from app.services.vector_store import FaissVectorStore


logger = logging.getLogger(__name__)
PROJECT_DIR = Path(__file__).resolve().parents[3]
DOCUMENTS_DIR = PROJECT_DIR / "data" / "documents"
VECTOR_STORE_DIR = PROJECT_DIR / "data" / "vectorstore"


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
                file_path=str(file_path),
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
    for pdf_path in sorted(documents_dir.glob("*.pdf")):
        documents.extend(ingest_pdf(pdf_path))
    return documents


def build_local_index() -> dict[str, int]:
    """Build a fresh, deterministic FAISS baseline index; never called by chat requests."""
    settings = get_settings()
    pages = clean_documents(ingest_directory())
    chunks = chunk_documents(pages, settings.rag_chunk_size, settings.rag_chunk_overlap, settings.rag_min_chunk_tokens)
    if not chunks:
        return {"documents": 0, "pages": 0, "chunks": 0, "embedding_dimension": 0}

    embeddings = EmbeddingService(settings.embedding_model).encode([chunk.text for chunk in chunks])
    store = FaissVectorStore(VECTOR_STORE_DIR)
    store.create_collection(embeddings.shape[1], recreate=True)
    store.upsert(chunks, embeddings)
    return {
        "documents": len({page.document_id for page in pages}),
        "pages": len(pages),
        "chunks": len(chunks),
        "embedding_dimension": int(embeddings.shape[1]),
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(build_local_index())
