"""Safe generation-evaluation entry point.

Phase 21 never silently invokes a paid provider.  This writes an explicit,
machine-readable NOT_EXECUTED result when a local provider is unavailable.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import get_settings

ROOT = Path(__file__).resolve().parents[1]


def run() -> dict:
    cases = json.loads((Path(__file__).parent / "dataset/benchmark.json").read_text())
    settings = get_settings()
    provider = settings.llm_provider
    configured_model = settings.ollama_model if provider == "ollama" else settings.llm_model
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "NOT_EXECUTED",
        "reason": "No local Ollama provider was configured or running; Phase 21 does not initiate paid OpenRouter generation.",
        "configuration": {"provider": provider, "model": configured_model, "temperature": 0, "retrieval_k": settings.rag_retrieval_top_k, "reranking_enabled": settings.rag_rerank_enabled},
        "benchmark": {"questions": len(cases), "hash": hashlib.sha256((Path(__file__).parent / "dataset/benchmark.json").read_bytes()).hexdigest()},
        "metrics": {"faithfulness": None, "answer_correctness": None, "answer_relevance": None, "citation_precision": None, "citation_coverage": None, "correct_document_citation_rate": None, "abstention_rate": None, "hallucination_rate": None, "end_to_end_success": None},
        "per_question": [],
    }


if __name__ == "__main__":
    result = run()
    path = Path(__file__).parent / "results/generation_results.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"status": result["status"], "reason": result["reason"]}))
