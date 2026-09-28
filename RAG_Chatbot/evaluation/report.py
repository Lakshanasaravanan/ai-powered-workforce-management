"""Build Phase 21 machine-readable and human-readable baseline reports."""
from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).parent


def _git_head() -> str:
    return subprocess.check_output(["git", "-C", str(ROOT.parent), "rev-parse", "HEAD"], text=True).strip()


def _format(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.4f} ({value * 100:.1f}%)"


def main() -> None:
    dataset = json.loads((HERE / "dataset/benchmark.json").read_text())
    retrieval = json.loads((HERE / "results/retrieval_results.json").read_text())
    generation = json.loads((HERE / "results/generation_results.json").read_text())
    best = retrieval["stages"]["hybrid"]
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": _git_head(),
        "benchmark_sha256": hashlib.sha256((HERE / "dataset/benchmark.json").read_bytes()).hexdigest(),
        "benchmark": {"questions": len(dataset), "answerable": sum(item["answerable"] for item in dataset), "unanswerable": sum(not item["answerable"] for item in dataset), "held_out": sum(item["split"] == "held_out" for item in dataset)},
        "corpus": retrieval["corpus"],
        "retrieval": {name: {"chunk": stage["aggregate"], "document": stage["document_aggregate"]} for name, stage in retrieval["stages"].items()},
        "generation": generation,
        "methodology": {
            "labels": "Static labels were derived from indexed PDF text and metadata before retrieval; rankings never update labels.",
            "ap_convention": "For each answerable query, AP is the sum of precision at each retrieved relevant rank divided by the number of independently labeled relevant chunks.",
            "generation_status": generation["status"],
        },
    }
    (HERE / "results/evaluation_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    # A review worksheet deliberately contains no invented human ratings.
    review = []
    rows = {row["id"]: row for row in best["per_question"]}
    for item in dataset[:20]:
        row = rows[item["id"]]
        review.append({
            "id": item["id"], "question": item["question"], "reference_answer": item["reference_answer"],
            "expected_evidence": {"documents": item["relevant_documents"], "pages": item["relevant_pages"], "chunks": item["relevant_chunk_ids"]},
            "retrieved_documents": row["documents"], "retrieved_chunk_ids": row["ranking"],
            "automatic_retrieval_metrics": row["metrics"],
            "generated_answer": None, "citations": [],
            "human_review": {"correct": None, "grounded": None, "citation_correct": None, "reviewer_notes": ""},
        })
    (HERE / "results/human_review_sample.json").write_text(json.dumps(review, indent=2) + "\n")
    dense, hybrid = retrieval["stages"]["dense"]["aggregate"], best["aggregate"]
    failures = [row for row in best["per_question"] if row["metrics"]["hit"]["10"] == 0][:5]
    report = f"""# Phase 21 RAG Baseline Evaluation

## Objective

This is a measurement-only baseline of the existing InfoTech/XYZ policy RAG.
No production embedding, chunking, retrieval weight, reranker, prompt, PDF, or
runtime configuration was changed for this evaluation.

## Corpus and benchmark

- Documents: {summary['corpus']['documents']}; indexed chunks: {summary['corpus']['chunks']}.
- Benchmark: {summary['benchmark']['questions']} questions ({summary['benchmark']['answerable']} answerable, {summary['benchmark']['unanswerable']} unanswerable); {summary['benchmark']['held_out']} deterministic held-out cases.
- Labels were selected from static PDF-derived index records before retrieval, never from returned rankings. Exact chunk relevance is intentionally stricter than document relevance.
- Retrieval depth: 10; candidate pool: {retrieval['configuration']['candidate_k']}; reranking: {retrieval['configuration']['reranking']}.

## Retrieval metrics (chunk-level)

| Retriever | R@1 | R@3 | R@5 | R@10 | P@5 | Hit@5 | MRR | mAP |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Dense | {_format(dense['recall']['1'])} | {_format(dense['recall']['3'])} | {_format(dense['recall']['5'])} | {_format(dense['recall']['10'])} | {_format(dense['precision']['5'])} | {_format(dense['hit_rate']['5'])} | {dense['mrr']:.4f} | {dense['map']:.4f} |
| Hybrid (dense + production BM25/RRF) | {_format(hybrid['recall']['1'])} | {_format(hybrid['recall']['3'])} | {_format(hybrid['recall']['5'])} | {_format(hybrid['recall']['10'])} | {_format(hybrid['precision']['5'])} | {_format(hybrid['hit_rate']['5'])} | {hybrid['mrr']:.4f} | {hybrid['map']:.4f} |

## Document-level retrieval

Hybrid document HitRate@5: {_format(best['document_aggregate']['hit_rate']['5'])}; document Recall@5: {_format(best['document_aggregate']['recall']['5'])}. This gap from exact-chunk metrics is a measured indication that the system often finds the policy document but not the labeled passage.

## Generation and end-to-end status

Generation was **{generation['status']}**: {generation['reason']}

Consequently faithfulness, answer correctness, relevance, citation metrics, abstention, and end-to-end success are **N/A**, not zero and not estimated. The framework records model/provider metadata without secrets and retains a 20-item blank human-review worksheet.

## Error analysis

The following representative answerable items had no independently labeled exact chunk in the hybrid top 10: {', '.join(row['id'] for row in failures)}.

Observed patterns: (1) document-level retrieval materially exceeds exact-chunk retrieval; (2) multi-document comparisons have zero exact-chunk Hit@10; (3) several policy categories have zero exact-chunk Hit@5; (4) no production reranker is configured, so no fair reranked comparison exists; (5) generation is unmeasured because safe local generation was unavailable and paid provider invocation was intentionally avoided.

## Limitations and reproducibility

The corpus is synthetic project policy content. Questions are deterministic and balanced by source, with wording variants and five multi-document cases; future tuning must use the development split and retain held-out cases. Run `PYTHONPATH=backend:. .venv/bin/python evaluation/build_benchmark.py`, then the documented local-only retrieval command, `evaluation/evaluate_generation.py`, and `evaluation/report.py`. Results carry commit and benchmark hashes. No human ratings were fabricated.

## Presentation summary

The measured hybrid baseline has chunk Recall@5 {_format(hybrid['recall']['5'])}, MRR {hybrid['mrr']:.4f}, and mAP {hybrid['map']:.4f}; it finds the correct document much more frequently than the exact labeled passage. Generation quality is deliberately unreported until a safe local provider is available.
"""
    (HERE / "results/evaluation_report.md").write_text(report)
    (HERE / "results/end_to_end_results.json").write_text(json.dumps({"status": "NOT_EXECUTED", "reason": "Generation evaluation was not safely executed; no end-to-end score can be calculated."}, indent=2) + "\n")


if __name__ == "__main__":
    main()
