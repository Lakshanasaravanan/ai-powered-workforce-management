"""Production retrieval orchestrator: dense, BM25, RRF, dedupe, and reranking."""

from __future__ import annotations

import logging
from time import perf_counter

from app.rag.fusion import reciprocal_rank_fusion
from app.rag.reranker import Reranker
from app.rag.retriever import DenseRetriever
from app.rag.sparse import BM25SparseRetriever
from app.schemas.rag import MetadataFilter, RetrievalResult, RetrievalTimings, RetrievedChunk


logger = logging.getLogger(__name__)


def _deduplicate(candidates: list[RetrievedChunk]) -> list[RetrievedChunk]:
    seen: set[str] = set()
    result: list[RetrievedChunk] = []
    for candidate in candidates:
        if candidate.metadata.content_hash not in seen:
            seen.add(candidate.metadata.content_hash)
            result.append(candidate)
    return result


class HybridRetriever:
    def __init__(
        self, dense: DenseRetriever, sparse: BM25SparseRetriever | None, reranker: Reranker,
        candidate_k: int, top_k: int, rrf_k: int, hybrid_enabled: bool, rerank_enabled: bool,
    ) -> None:
        self.dense, self.sparse, self.reranker = dense, sparse, reranker
        self.candidate_k, self.top_k, self.rrf_k = candidate_k, top_k, rrf_k
        self.hybrid_enabled, self.rerank_enabled = hybrid_enabled, rerank_enabled

    def retrieve(self, query: str, metadata_filter: MetadataFilter | None = None) -> RetrievalResult:
        started = perf_counter()
        timings = RetrievalTimings()
        embedding_started = perf_counter()
        query_vector = self.dense.embeddings.encode([query])[0] if query.strip() and self.dense.vector_store.count() else None
        timings.embedding_ms = (perf_counter() - embedding_started) * 1000
        dense_started = perf_counter()
        dense = self.dense.retrieve_vector(query_vector, self.candidate_k, metadata_filter) if query_vector is not None else []
        timings.dense_search_ms = (perf_counter() - dense_started) * 1000
        sparse: list[RetrievedChunk] = []
        if self.hybrid_enabled and self.sparse is not None:
            sparse_started = perf_counter()
            sparse = self.sparse.retrieve(query, self.candidate_k, metadata_filter)
            timings.sparse_search_ms = (perf_counter() - sparse_started) * 1000
        fusion_started = perf_counter()
        fused = reciprocal_rank_fusion([dense, sparse], self.rrf_k, self.candidate_k) if self.hybrid_enabled and self.sparse else dense[:self.candidate_k]
        timings.fusion_ms = (perf_counter() - fusion_started) * 1000
        dedup_started = perf_counter()
        candidates = _deduplicate(fused)[:self.candidate_k]
        timings.dedup_ms = (perf_counter() - dedup_started) * 1000
        rerank_started = perf_counter()
        ranked = self.reranker.rerank(query, candidates) if self.rerank_enabled else candidates
        timings.rerank_ms = (perf_counter() - rerank_started) * 1000
        final = [item.model_copy(update={"final_rank": rank}) for rank, item in enumerate(ranked[:self.top_k], start=1)]
        timings.total_retrieval_ms = (perf_counter() - started) * 1000
        logger.info("retrieval_completed", extra={"dense_candidate_count": len(dense), "sparse_candidate_count": len(sparse), "fused_candidate_count": len(candidates), "final_candidate_count": len(final), "hybrid_enabled": self.hybrid_enabled, "rerank_enabled": self.rerank_enabled, **timings.model_dump()})
        return RetrievalResult(chunks=final, timings=timings, dense_candidate_count=len(dense), sparse_candidate_count=len(sparse), fused_candidate_count=len(candidates), hybrid_enabled=self.hybrid_enabled and self.sparse is not None, rerank_enabled=self.rerank_enabled)
