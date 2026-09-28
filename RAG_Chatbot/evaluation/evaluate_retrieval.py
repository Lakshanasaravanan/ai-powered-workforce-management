"""Run production dense/hybrid retrieval against the static Phase 21 set."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import get_settings
from app.rag.embeddings import EmbeddingService
from app.rag.hybrid import HybridRetriever
from app.rag.reranker import DisabledReranker
from app.rag.retriever import DenseRetriever
from app.rag.sparse import BM25SparseRetriever
from app.services.vector_store import FaissVectorStore
from evaluation.metrics import aggregate, by_field, per_query
from evaluation.validate import validate

ROOT = Path(__file__).resolve().parents[1]


def run() -> dict:
    settings = get_settings(); cases = json.loads((Path(__file__).parent / "dataset/benchmark.json").read_text())
    store = FaissVectorStore(ROOT / "data/runtime/vectorstore")
    records = json.loads((ROOT / "data/runtime/vectorstore/records.json").read_text())
    errors = validate(cases, records)
    if errors:
        raise ValueError("Invalid benchmark: " + "; ".join(errors))
    dense = DenseRetriever(store, EmbeddingService(settings.embedding_model, device=settings.embedding_device, local_files_only=settings.embedding_local_files_only), 10)
    sparse = BM25SparseRetriever.from_artifact(ROOT / "data/runtime/sparse/bm25_corpus.json", store)
    modes = {"dense": HybridRetriever(dense, None, DisabledReranker(), settings.rag_retrieval_candidate_k, 10, settings.rag_rrf_k, False, False), "hybrid": HybridRetriever(dense, sparse, DisabledReranker(), settings.rag_retrieval_candidate_k, 10, settings.rag_rrf_k, True, False)}
    corpus_sources = sorted({item["metadata"]["source"] for item in records.values()})
    cases_by_id = {case["id"]: case for case in cases}
    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "questions": len(cases),
        "answerable_questions": sum(case["answerable"] for case in cases),
        "unanswerable_questions": sum(not case["answerable"] for case in cases),
        "corpus": {"documents": len(corpus_sources), "chunks": len(records), "sources": corpus_sources},
        "configuration": {"embedding_model": settings.embedding_model, "evaluation_depth": 10, "candidate_k": settings.rag_retrieval_candidate_k, "rrf_k": settings.rag_rrf_k, "reranking": "not configured in current production settings"},
        "stages": {},
    }
    for name, retriever in modes.items():
        rows=[]
        for case in cases:
            # Unsupported cases are still retrieved for traceability, but do
            # not enter chunk relevance metrics because their label set is empty.
            ranked = retriever.retrieve(case["question"]).chunks
            ids=[item.id for item in ranked]
            docs=list(dict.fromkeys(item.metadata.source for item in ranked))
            metrics = per_query(ids,set(case["relevant_chunk_ids"]))
            document_metrics = per_query(docs, set(case["relevant_documents"]))
            rows.append({"id":case["id"], "ranking":ids, "documents":docs, "metrics":metrics, "document_metrics":document_metrics})
        document_rows = [{"id": row["id"], "metrics": row["document_metrics"]} for row in rows]
        output["stages"][name]={
            "aggregate":aggregate(rows),
            "document_aggregate":aggregate(document_rows),
            "breakdowns": {field: by_field(rows, cases_by_id, field) for field in ("category", "difficulty", "question_type", "split")},
            "per_question":rows,
        }
    return output


if __name__ == "__main__":
    result=run(); path=Path(__file__).parent / "results/retrieval_results.json"; path.parent.mkdir(exist_ok=True); path.write_text(json.dumps(result,indent=2)+"\n"); print(json.dumps({key:value["aggregate"] for key,value in result["stages"].items()}))
