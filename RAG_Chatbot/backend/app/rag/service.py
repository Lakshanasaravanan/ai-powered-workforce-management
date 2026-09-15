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
from app.services.vector_store import VectorStoreError, create_vector_store
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
            generated = self.generator.generate(question, evidence)
            if generated.insufficient_evidence:
                return RAGAnswer(answer="I’m not sure based on the available company policy documents.", sources=[])
            valid_ids = {f"E{index}" for index in range(1, len(sources) + 1)}
            if not generated.evidence_ids or any(item not in valid_ids for item in generated.evidence_ids):
                return RAGAnswer(answer="I’m not sure based on the available company policy documents.", sources=[])
            selected = [sources[int(item[1:]) - 1] for item in generated.evidence_ids]
            deduplicated = list(dict.fromkeys((item.document, item.page, item.section, item.subsection) for item in selected))
            return RAGAnswer(answer=generated.answer, sources=[
                next(item for item in selected if (item.document, item.page, item.section, item.subsection) == key)
                for key in deduplicated
            ])
        except (VectorStoreError, LLMProviderError) as exc:
            raise RAGServiceError("The policy assistant is temporarily unavailable. Please try again later.") from exc


def create_rag_service(settings: Settings, vector_directory) -> RAGService:
    store = create_vector_store(settings, vector_directory)
    embedding_options: dict[str, object] = {}
    if settings.embedding_cache_dir:
        embedding_options["cache_dir"] = str(settings.embedding_cache_dir)
    if settings.embedding_local_files_only:
        embedding_options["local_files_only"] = True
    embeddings = EmbeddingService(settings.embedding_model, device=settings.embedding_device, **embedding_options)
    dense = DenseRetriever(store, embeddings, settings.rag_retrieval_candidate_k)
    sparse = None
    if settings.rag_hybrid_enabled:
        try:
            sparse = BM25SparseRetriever.from_artifact(SPARSE_INDEX_PATH, store)
        except SparseIndexError:
            sparse = None
    rerank_options: dict[str, object] = {}
    if settings.rerank_cache_dir:
        rerank_options["cache_dir"] = str(settings.rerank_cache_dir)
    if settings.rerank_local_files_only:
        rerank_options["local_files_only"] = True
    reranker = CrossEncoderReranker(settings.rag_rerank_model, **rerank_options) if settings.rag_rerank_enabled else DisabledReranker()
    retriever = HybridRetriever(dense, sparse, reranker, settings.rag_retrieval_candidate_k, settings.rag_retrieval_top_k, settings.rag_rrf_k, settings.rag_hybrid_enabled, settings.rag_rerank_enabled and sparse is not None)
    return RAGService(
        retriever,
        ContextAssembler(settings.rag_max_context_tokens),
        GroundedGenerator(build_llm_provider(settings)),
    )
