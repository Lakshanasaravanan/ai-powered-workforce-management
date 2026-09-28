"""Focused Phase 22 regression coverage for the retained sparse mode."""
from app.core.config import Settings
from app.rag.hybrid import SparseOnlyRetriever
from app.schemas.rag import DocumentChunk, RetrievedChunk


def _chunk(identifier: str) -> RetrievedChunk:
    return RetrievedChunk.model_validate({
        "id": identifier,
        "text": "policy evidence",
        "metadata": {"document_id": "doc", "source": "policy.pdf", "file_path": "policy.pdf", "page": 1, "chunk_index": 0, "content_hash": identifier, "document_version": "v1"},
        "score": 1.0,
    })


def test_sparse_mode_is_the_explicit_default():
    assert Settings(_env_file=None).rag_retrieval_mode == "sparse"


def test_sparse_only_retriever_assigns_final_ranks_and_does_not_fallback():
    class Sparse:
        def retrieve(self, query, limit, metadata_filter):
            assert query == "leave policy" and limit == 2
            return [_chunk("one"), _chunk("two")]

    result = SparseOnlyRetriever(Sparse(), 2).retrieve("leave policy")
    assert [item.final_rank for item in result.chunks] == [1, 2]
    assert result.sparse_candidate_count == 2
    assert result.hybrid_enabled is False
