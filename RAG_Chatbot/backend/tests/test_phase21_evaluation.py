"""Deterministic unit coverage for transparent Phase 21 metrics."""
import json
from pathlib import Path

from evaluation.metrics import aggregate, per_query
from evaluation.validate import validate


def test_rank_metrics_match_hand_calculated_values():
    values = per_query(["A", "B", "C", "D"], {"B", "D"})
    assert values["recall"] == {1: 0.0, 3: 0.5, 5: 1.0, 10: 1.0}
    assert values["precision"] == {1: 0.0, 3: 1 / 3, 5: 2 / 5, 10: 2 / 10}
    assert values["hit"] == {1: 0.0, 3: 1.0, 5: 1.0, 10: 1.0}
    assert values["rr"] == 0.5
    assert values["ap"] == (0.5 + 0.5) / 2


def test_aggregate_computes_mrr_and_map_without_unanswerable_rows():
    rows = [
        {"metrics": per_query(["A"], {"A"})},
        {"metrics": per_query(["A", "B"], {"B"})},
        {"metrics": per_query(["A"], set())},
    ]
    result = aggregate(rows)
    assert result["count"] == 2
    assert result["mrr"] == 0.75
    assert result["map"] == 0.75


def test_dataset_validator_rejects_invalid_evidence():
    records = {"chunk_1": {"metadata": {"source": "policy.pdf", "page": 1}}}
    valid = [{"id": "one", "question": "Question?", "category": "policy", "answerable": True, "difficulty": "direct", "question_type": "direct", "relevant_chunk_ids": ["chunk_1"], "relevant_documents": ["policy.pdf"], "relevant_pages": [1]}]
    assert validate(valid, records) == []
    invalid = [dict(valid[0], id="", relevant_chunk_ids=["missing"])]
    assert validate(invalid, records)


def test_committed_phase21_dataset_validates_against_static_pdf_index():
    root = Path(__file__).resolve().parents[2]
    cases = json.loads((root / "evaluation/dataset/benchmark.json").read_text())
    records = json.loads((root / "data/runtime/vectorstore/records.json").read_text())
    assert len(cases) == 68
    assert sum(item["answerable"] for item in cases) == 60
    assert validate(cases, records) == []
