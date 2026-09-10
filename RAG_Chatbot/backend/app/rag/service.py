"""Application service that coordinates retrieval, evidence assembly, and generation."""

from app.core.config import Settings
from app.rag.context import ContextAssembler
from app.rag.embeddings import EmbeddingService
from app.rag.generator import GroundedGenerator
from app.rag.retriever import DenseRetriever
from app.rag.hybrid import HybridRetriever
from app.rag.reranker import CrossEncoderReranker, DisabledReranker
from app.rag.sparse import BM25SparseRetriever, SparseIndexError
from app.schemas.rag import RAGAnswer
from app.services.llm import LLMProviderError, build_llm_provider
from app.services.vector_store import FaissVectorStore, VectorStoreError
from app.rag.ingestion import SPARSE_INDEX_PATH


class RAGServiceError(RuntimeError):
    """Safe RAG failure suitable for mapping to an API service error."""


class RAGService:
    def __init__(self, retriever, context: ContextAssembler, generator: GroundedGenerator) -> None:
        self.retriever = retriever
        self.context = context
        self.generator = generator

    def answer(self, question: str) -> RAGAnswer:
        try:
            retrieval = self.retriever.retrieve(question)
            chunks = retrieval.chunks if hasattr(retrieval, "chunks") else retrieval
            if not chunks:
                return RAGAnswer(
                    answer="The available company knowledge does not contain enough information to answer that question.",
                    sources=[],
                )
            evidence, sources = self.context.assemble(chunks)
            if not evidence:
                return RAGAnswer(
                    answer="The available company knowledge does not contain enough information to answer that question.",
                    sources=[],
                )
            return RAGAnswer(answer=self.generator.generate(question, evidence), sources=sources)
        except (VectorStoreError, LLMProviderError) as exc:
            raise RAGServiceError("The policy assistant is temporarily unavailable. Please try again later.") from exc


def create_rag_service(settings: Settings, vector_directory) -> RAGService:
    store = FaissVectorStore(vector_directory)
    embeddings = EmbeddingService(settings.embedding_model)
    dense = DenseRetriever(store, embeddings, settings.rag_retrieval_candidate_k)
    sparse = None
    if settings.rag_hybrid_enabled:
        try:
            sparse = BM25SparseRetriever.from_artifact(SPARSE_INDEX_PATH, store)
        except SparseIndexError:
            sparse = None
    reranker = CrossEncoderReranker(settings.rag_rerank_model) if settings.rag_rerank_enabled else DisabledReranker()
    retriever = HybridRetriever(dense, sparse, reranker, settings.rag_retrieval_candidate_k, settings.rag_retrieval_top_k, settings.rag_rrf_k, settings.rag_hybrid_enabled, settings.rag_rerank_enabled and sparse is not None)
    return RAGService(
        retriever,
        ContextAssembler(settings.rag_max_context_tokens),
        GroundedGenerator(build_llm_provider(settings)),
    )
