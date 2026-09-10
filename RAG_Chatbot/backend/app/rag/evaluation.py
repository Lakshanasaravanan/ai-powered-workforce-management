"""Deterministic retrieval evaluation without LLM calls."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from statistics import mean

from app.schemas.rag import RetrievedChunk


def load_cases(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def evaluate(results: dict[str, list[RetrievedChunk]], cases: list[dict], k: int) -> dict:
    totals = defaultdict(lambda: {"count": 0, "hit": 0.0, "mrr": 0.0, "recall": 0.0})
    for case in cases:
        expected = set(case["expected_sources"])
        retrieved = [item.metadata.source for item in results.get(case["id"], [])[:k]]
        category = totals[case["category"]]
        category["count"] += 1
        category["hit"] += float(bool(expected.intersection(retrieved)))
        category["recall"] += len(expected.intersection(retrieved)) / len(expected)
        for rank, source in enumerate(retrieved, start=1):
            if source in expected:
                category["mrr"] += 1.0 / rank
                break
    def summarize(values):
        count = values["count"] or 1
        return {"count": values["count"], "hit_rate": values["hit"] / count, "mrr": values["mrr"] / count, "recall": values["recall"] / count}
    per_category = {key: summarize(value) for key, value in totals.items()}
    aggregate = summarize({key: sum(value[key] for value in totals.values()) for key in ("count", "hit", "mrr", "recall")})
    return {"k": k, "aggregate": aggregate, "per_category": per_category}


def evaluate_retriever(retriever, cases: list[dict], k: int) -> dict:
    results: dict[str, list[RetrievedChunk]] = {}
    latencies: list[float] = []
    for case in cases:
        outcome = retriever.retrieve(case["query"])
        if hasattr(outcome, "chunks"):
            results[case["id"]] = outcome.chunks
            latencies.append(outcome.timings.total_retrieval_ms)
        else:
            results[case["id"]] = outcome
    report = evaluate(results, cases, k)
    report["average_retrieval_ms"] = mean(latencies) if latencies else None
    return report
