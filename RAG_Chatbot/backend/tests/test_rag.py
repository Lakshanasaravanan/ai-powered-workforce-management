from __future__ import annotations

from pathlib import Path

import numpy as np

from app.rag.chunking import chunk_documents
from app.rag.tokenization import get_tokenizer
from app.rag.cleaning import clean_documents, clean_text
from app.rag.context import ContextAssembler
from app.rag.embeddings import EmbeddingService
from app.rag.generator import GroundedGenerator, SYSTEM_PROMPT
from app.rag.ingestion import ingest_pdf
from app.rag.retriever import DenseRetriever
from app.rag.service import RAGService
from app.schemas.rag import ChunkMetadata, DocumentChunk, PageDocument, RAGAnswer, RetrievedChunk, SourceCitation
from app.services.llm import LLMProvider
from app.services.vector_store import FaissVectorStore


def page(text: str, number: int = 1) -> PageDocument:
    return PageDocument(
        document_id="doc-test", source="policy.pdf", file_path="/tmp/policy.pdf", page=number,
        text=text, document_version="version", content_hash="hash",
    )


def chunk(text: str, identifier: str = "one", page_number: int = 1) -> DocumentChunk:
    return DocumentChunk(
        id=identifier,
        text=text,
        metadata=ChunkMetadata(
            document_id="doc-test", source="policy.pdf", file_path="/tmp/policy.pdf", page=page_number,
            section="Leave", subsection=None, chunk_index=0, content_hash=f"hash-{identifier}", document_version="version",
        ),
    )


def test_ingestion_preserves_metadata_and_skips_bad_pages(monkeypatch, tmp_path: Path):
    pdf = tmp_path / "example.pdf"
    pdf.write_bytes(b"pretend-pdf")

    class GoodPage:
        def extract_text(self): return "Medical leave policy"

    class EmptyPage:
        def extract_text(self): return ""

    class BadPage:
        def extract_text(self): raise ValueError("broken")

    class Reader:
        pages = [GoodPage(), EmptyPage(), BadPage()]

    monkeypatch.setattr("app.rag.ingestion.PdfReader", lambda _: Reader())
    pages = ingest_pdf(pdf)
    assert len(pages) == 1
    assert pages[0].page == 1
    assert pages[0].document_id.startswith("doc_")
    assert pages[0].content_hash


def test_cleaning_removes_repeated_margins_and_keeps_paragraphs():
    pages = [
        page("XYZ Handbook\nMedical leave is available.\nPage 1", 1),
        page("XYZ Handbook\nAttendance is required.\nPage 2", 2),
    ]
    cleaned = clean_documents(pages)
    assert cleaned[0].text == "Medical leave is available."
    assert cleaned[1].text == "Attendance is required."
    assert clean_text("A   policy\n\n\nB policy") == "A policy\n\nB policy"


def test_cleaning_preserves_short_title_headings_for_chunking():
    text = "Leave Categories\nParental Leave — Operational Guidance\nEmployees should follow the process."
    assert clean_text(text) == "Leave Categories\n\nParental Leave — Operational Guidance\n\nEmployees should follow the process."


def test_chunking_is_token_based_and_retains_metadata():
    text = "1. Leave Policy\n\n" + "medical leave eligibility and approval process " * 20
    chunks = chunk_documents([page(text)], chunk_size=30, overlap=5)
    assert len(chunks) > 1
    assert chunks[0].metadata.section == "1. Leave Policy"
    assert all(len(get_tokenizer().encode(item.text)) <= 30 for item in chunks)
    assert chunks[0].metadata.document_id == "doc-test"
    assert chunks[0].text.startswith("1. Leave Policy")


def test_embedding_service_batches_and_normalizes_without_real_model():
    calls = []

    class Model:
        def encode(self, texts, **kwargs):
            calls.append((texts, kwargs))
            return np.array([[0.6, 0.8] for _ in texts])

    service = EmbeddingService("fake", batch_size=7, model_factory=lambda _: Model())
    vectors = service.encode(["one", "two"])
    assert vectors.shape == (2, 2)
    assert np.allclose(np.linalg.norm(vectors, axis=1), 1)
    assert calls[0][1]["batch_size"] == 7
    assert calls[0][1]["normalize_embeddings"] is True


def test_faiss_store_upsert_search_count_and_delete(tmp_path: Path):
    store = FaissVectorStore(tmp_path)
    store.create_collection(2)
    store.upsert([chunk("medical leave", "a"), chunk("password policy", "b")], np.array([[1, 0], [0, 1]], dtype=np.float32))
    assert store.count() == 2 and store.health_check()
    assert store.search(np.array([1, 0], dtype=np.float32), 1)[0].id == "a"
    store.delete(["a"])
    assert store.count() == 1


def test_faiss_store_rejects_duplicate_batch_ids(tmp_path: Path):
    store = FaissVectorStore(tmp_path)
    store.create_collection(2)
    with np.testing.assert_raises_regex(Exception, "Duplicate chunk identifier"):
        store.upsert([chunk("first", "same"), chunk("second", "same")], np.array([[1, 0], [0, 1]], dtype=np.float32))


def test_retriever_context_and_duplicate_removal(tmp_path: Path):
    store = FaissVectorStore(tmp_path)
    store.create_collection(2)
    first = chunk("Medical leave requires manager approval.", "a")
    duplicate = chunk("Medical leave requires manager approval.", "b", 2)
    store.upsert([first, duplicate], np.array([[1, 0], [0.9, 0.1]], dtype=np.float32))

    class Embeddings:
        def encode(self, texts): return np.array([[1, 0]], dtype=np.float32)

    results = DenseRetriever(store, Embeddings(), 5).retrieve("medical leave")
    context, sources = ContextAssembler(100).assemble(results)
    assert context.count("Medical leave requires") == 1
    assert len(sources) == 1


def test_grounded_generation_and_rag_service_flow():
    class Provider(LLMProvider):
        def __init__(self): self.calls = []
        def generate(self, system_prompt, user_prompt):
            self.calls.append((system_prompt, user_prompt))
            return "Medical leave is available. [policy.pdf, p. 1]"

    class Retriever:
        def retrieve(self, question): return [RetrievedChunk(**chunk("Medical leave is available.").model_dump(), score=0.9)]

    provider = Provider()
    answer = RAGService(Retriever(), ContextAssembler(100), GroundedGenerator(provider)).answer("What is medical leave?")
    assert answer.sources[0].document == "policy.pdf"
    assert "untrusted data" in provider.calls[0][0]
    assert "What is medical leave?" in provider.calls[0][1]
    assert "ignore previous instructions" not in SYSTEM_PROMPT.lower()
