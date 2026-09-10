"""Typed contracts shared by the RAG pipeline and API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PageDocument(BaseModel):
    document_id: str
    source: str
    file_path: str
    page: int = Field(ge=1)
    text: str
    document_version: str
    content_hash: str


class ChunkMetadata(BaseModel):
    document_id: str
    source: str
    file_path: str
    page: int = Field(ge=1)
    section: str | None = None
    subsection: str | None = None
    chunk_index: int = Field(ge=0)
    content_hash: str
    document_version: str


class DocumentChunk(BaseModel):
    id: str
    text: str
    metadata: ChunkMetadata


class RetrievedChunk(DocumentChunk):
    score: float


class SourceCitation(BaseModel):
    document: str
    page: int
    section: str | None = None
    subsection: str | None = None


class RAGAnswer(BaseModel):
    answer: str
    sources: list[SourceCitation]
