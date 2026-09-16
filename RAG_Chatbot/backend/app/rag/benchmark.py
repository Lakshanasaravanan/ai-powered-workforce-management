"""Repeatable local retrieval benchmark using temporary artifacts only."""
from __future__ import annotations
import json
import tempfile
from pathlib import Path

from app.core.config import get_settings
from app.rag.embeddings import EmbeddingService
from app.rag.evaluation import evaluate_retriever, load_cases
from app.rag.hybrid import HybridRetriever
from app.rag.ingestion import DOCUMENTS_DIR, build_local_index
from app.rag.reranker import CrossEncoderReranker, DisabledReranker
from app.rag.retriever import DenseRetriever
from app.rag.sparse import BM25SparseRetriever
from app.services.vector_store import FaissVectorStore


def run(include_reranker: bool = False) -> dict:
    settings = get_settings(); cases = load_cases(Path(__file__).parents[2] / "data/evaluation/retrieval_cases.json")
    with tempfile.TemporaryDirectory(prefix="rag-benchmark-") as directory:
        root = Path(directory); build_local_index(documents_dir=DOCUMENTS_DIR, vector_dir=root / "vector", sparse_path=root / "sparse.json", settings=settings)
        store = FaissVectorStore(root / "vector"); dense = DenseRetriever(store, EmbeddingService(settings.embedding_model, device=settings.embedding_device, local_files_only=settings.embedding_local_files_only), settings.rag_retrieval_candidate_k)
        sparse = BM25SparseRetriever.from_artifact(root / "sparse.json", store)
        modes = {"dense": HybridRetriever(dense, None, DisabledReranker(), 30, 5, 60, False, False), "hybrid": HybridRetriever(dense, sparse, DisabledReranker(), 30, 5, 60, True, False)}
        if include_reranker:
            reranker = CrossEncoderReranker(settings.rag_rerank_model, local_files_only=settings.rerank_local_files_only)
            reranker.model
            modes.update({"dense_rerank": HybridRetriever(dense, None, reranker, 30, 5, 60, False, True), "hybrid_rerank": HybridRetriever(dense, sparse, reranker, 30, 5, 60, True, True)})
        output = {}
        for name, retriever in modes.items():
            at = {k: evaluate_retriever(retriever, cases, k) for k in (1, 3, 5)}
            output[name] = {"hit_at_1": at[1]["aggregate"]["hit_rate"], "hit_at_3": at[3]["aggregate"]["hit_rate"], "hit_at_5": at[5]["aggregate"]["hit_rate"], "mrr_at_5": at[5]["aggregate"]["mrr"], "recall_at_5": at[5]["aggregate"]["recall"], "average_ms": at[5]["average_retrieval_ms"]}
        return output


if __name__ == "__main__":
    print(json.dumps(run(include_reranker=True), sort_keys=True))
