"""Typed contracts shared by the RAG pipeline and API."""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


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
    score: float | None = None
    dense_score: float | None = None
    sparse_score: float | None = None
    fusion_score: float | None = None
    rerank_score: float | None = None
    final_rank: int | None = None


class MetadataFilter(BaseModel):
    sources: set[str] | None = None
    document_ids: set[str] | None = None
    sections: set[str] | None = None
    document_version: str | None = None
    page_min: int | None = Field(default=None, ge=1)
    page_max: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_page_range(self) -> "MetadataFilter":
        if self.page_min is not None and self.page_max is not None and self.page_min > self.page_max:
            raise ValueError("page_min must not exceed page_max")
        return self


class RetrievalTimings(BaseModel):
    embedding_ms: float = 0.0
    dense_search_ms: float = 0.0
    sparse_search_ms: float = 0.0
    fusion_ms: float = 0.0
    dedup_ms: float = 0.0
    rerank_ms: float = 0.0
    total_retrieval_ms: float = 0.0


class RetrievalResult(BaseModel):
    chunks: list[RetrievedChunk]
    timings: RetrievalTimings
    dense_candidate_count: int = 0
    sparse_candidate_count: int = 0
    fused_candidate_count: int = 0
    hybrid_enabled: bool
    rerank_enabled: bool


class SourceCitation(BaseModel):
    document: str
    page: int
    section: str | None = None
    subsection: str | None = None


class RAGAnswer(BaseModel):
    answer: str
    sources: list[SourceCitation]
