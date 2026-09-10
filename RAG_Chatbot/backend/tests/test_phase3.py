from __future__ import annotations

import numpy as np
import pytest

from app.core.config import Settings
from app.rag.evaluation import evaluate
from app.rag.fusion import reciprocal_rank_fusion
from app.rag.hybrid import HybridRetriever
from app.rag.reranker import CrossEncoderReranker, DisabledReranker
from app.rag.sparse import BM25SparseRetriever
from app.schemas.rag import MetadataFilter, RetrievedChunk

from test_rag import chunk


def retrieved(identifier: str, text: str, score: float = 1.0) -> RetrievedChunk:
    return RetrievedChunk(**chunk(text, identifier).model_dump(), score=score, dense_score=score)


def test_candidate_configuration_validation(monkeypatch):
    monkeypatch.setenv("RAG_RETRIEVAL_TOP_K", "10")
    monkeypatch.setenv("RAG_RETRIEVAL_CANDIDATE_K", "5")
    with pytest.raises(ValueError):
        Settings(_env_file=None)


def test_hybrid_and_reranking_are_disabled_by_default():
    settings = Settings(_env_file=None)
    assert settings.rag_hybrid_enabled is False
    assert settings.rag_rerank_enabled is False


def test_metadata_filter_validates_ranges():
    with pytest.raises(ValueError):
        MetadataFilter(page_min=4, page_max=3)


def test_bm25_exact_term_and_filtering():
    sparse = BM25SparseRetriever([chunk("The zero trust passwordless policy applies.", "security"), chunk("Medical leave policy.", "leave"), chunk("Attendance reporting guidance.", "attendance")])
    assert sparse.retrieve("passwordless", 1)[0].id == "security"
    assert sparse.retrieve("policy", 5, MetadataFilter(sources={"policy.pdf"}))


def test_rrf_preserves_scores_and_ties_are_stable():
    first = retrieved("a", "medical leave", 0.9)
    second = retrieved("b", "password policy", 0.8)
    fused = reciprocal_rank_fusion([[first, second], [second, first]], 60, 2)
    assert [item.id for item in fused] == ["a", "b"]
    assert all(item.fusion_score is not None for item in fused)


def test_reranker_and_disabled_path():
    class Model:
        def predict(self, pairs, batch_size): return np.array([0.1, 0.9])
    candidates = [retrieved("a", "one"), retrieved("b", "two")]
    reranked = CrossEncoderReranker("fake", model_factory=lambda _: Model()).rerank("q", candidates)
    assert [item.id for item in reranked] == ["b", "a"]
    assert reranked[0].rerank_score == 0.9
    assert DisabledReranker().rerank("q", candidates) == candidates


def test_evaluation_metrics():
    cases = [{"id": "one", "category": "leave", "expected_sources": ["leave.pdf"]}]
    metrics = evaluate({"one": [retrieved("a", "text").model_copy(update={"metadata": chunk("text", "a").metadata.model_copy(update={"source": "leave.pdf"})})]}, cases, 5)
    assert metrics["aggregate"]["hit_rate"] == 1.0
    assert metrics["aggregate"]["mrr"] == 1.0


def test_default_service_does_not_construct_optional_retrievers(monkeypatch, tmp_path):
    """Dense-only defaults must not initialize BM25 or a cross-encoder."""
    import app.rag.service as service_module

    settings = Settings(_env_file=None)

    class FakeStore:
        def count(self):
            return 1

    class FakeEmbeddings:
        def encode(self, queries):
            return np.array([[1.0, 0.0] for _ in queries])

    class FakeDense:
        def __init__(self, *args):
            self.embeddings = FakeEmbeddings()
            self.vector_store = FakeStore()

        def retrieve_vector(self, vector, limit, metadata_filter):
            return [retrieved("dense", "Dense-only policy evidence")]

    def optional_component(*args, **kwargs):
        raise AssertionError("disabled optional component was constructed")

    monkeypatch.setattr(service_module, "FaissVectorStore", lambda *_: FakeStore())
    monkeypatch.setattr(service_module, "EmbeddingService", lambda *_: FakeEmbeddings())
    monkeypatch.setattr(service_module, "DenseRetriever", FakeDense)
    monkeypatch.setattr(service_module.BM25SparseRetriever, "from_artifact", optional_component)
    monkeypatch.setattr(service_module, "CrossEncoderReranker", optional_component)
    monkeypatch.setattr(service_module, "build_llm_provider", lambda _: object())

    service = service_module.create_rag_service(settings, tmp_path)
    assert service.retriever.sparse is None
    assert isinstance(service.retriever.reranker, DisabledReranker)

    class Context:
        def assemble(self, chunks):
            assert [item.id for item in chunks] == ["dense"]
            return "Dense-only policy evidence", []

    class Generator:
        def generate(self, question, evidence):
            assert question == "leave policy" and evidence == "Dense-only policy evidence"
            return "grounded answer"

    service.context, service.generator = Context(), Generator()
    assert service.answer("leave policy").answer == "grounded answer"


def test_hybrid_retriever_supports_dense_hybrid_and_reranked_modes():
    class Embeddings:
        def encode(self, queries):
            return np.array([[1.0, 0.0] for _ in queries])

    class Store:
        def count(self):
            return 1

    class Dense:
        embeddings = Embeddings()
        vector_store = Store()

        def __init__(self):
            self.calls = 0

        def retrieve_vector(self, vector, limit, metadata_filter):
            self.calls += 1
            return [retrieved("dense-a", "leave policy"), retrieved("dense-b", "attendance policy")]

    class Sparse:
        def __init__(self):
            self.calls = 0

        def retrieve(self, query, limit, metadata_filter):
            self.calls += 1
            return [retrieved("sparse-b", "attendance policy"), retrieved("sparse-c", "passwordless policy")]

    class Reranker:
        def __init__(self):
            self.calls = 0

        def rerank(self, query, candidates):
            self.calls += 1
            return list(reversed(candidates))

    dense, sparse, reranker = Dense(), Sparse(), Reranker()
    dense_only = HybridRetriever(dense, sparse, reranker, 3, 2, 60, False, False).retrieve("leave")
    assert [item.id for item in dense_only.chunks] == ["dense-a", "dense-b"]
    assert sparse.calls == reranker.calls == 0

    hybrid = HybridRetriever(dense, sparse, reranker, 3, 2, 60, True, False).retrieve("leave")
    assert hybrid.hybrid_enabled is True and sparse.calls == 1 and reranker.calls == 0

    reranked = HybridRetriever(dense, sparse, reranker, 3, 2, 60, True, True).retrieve("leave")
    assert reranked.rerank_enabled is True and reranker.calls == 1
