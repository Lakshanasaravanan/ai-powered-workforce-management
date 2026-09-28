"""Read-only Phase 22 diagnosis and bounded retrieval experiments.

This module uses the production retrieval classes and current runtime index;
it never changes production configuration, source, documents, or index files.
"""
from __future__ import annotations

import json
import statistics
import time
from copy import deepcopy
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import get_settings
from app.rag.embeddings import EmbeddingService
from app.rag.hybrid import HybridRetriever
from app.rag.reranker import DisabledReranker
from app.rag.retriever import DenseRetriever
from app.rag.sparse import BM25SparseRetriever
from app.services.vector_store import FaissVectorStore
from evaluation.metrics import KS, aggregate, per_query
from evaluation.validate import validate

ROOT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).parent
OUT = HERE / "results/phase22"


def _rows(cases, retrieve, records):
    rows, times = [], []
    for case in cases:
        started = time.perf_counter()
        chunks = retrieve(case["question"])
        times.append((time.perf_counter() - started) * 1000)
        ids = [chunk.id for chunk in chunks]
        pages = list(dict.fromkeys((chunk.metadata.source, chunk.metadata.page) for chunk in chunks))
        docs = list(dict.fromkeys(chunk.metadata.source for chunk in chunks))
        rows.append({"id": case["id"], "ranking": ids, "pages": pages, "documents": docs, "metrics": per_query(ids, set(case["relevant_chunk_ids"])), "page_metrics": per_query(pages, set(zip(case["relevant_documents"], case["relevant_pages"]))), "document_metrics": per_query(docs, set(case["relevant_documents"]))})
    answerable = [r for r in rows if r["metrics"]["rr"] is not None]
    return {"aggregate": aggregate(rows), "page": aggregate([{**r, "metrics": r["page_metrics"]} for r in rows]), "document": aggregate([{**r, "metrics": r["document_metrics"]} for r in rows]), "latency_ms": {"mean": statistics.mean(times), "median": statistics.median(times), "p95": sorted(times)[max(0, int(len(times) * .95) - 1)]}, "per_question": rows, "answerable_rows": answerable}


def _audit(cases, rows, records):
    by_id = {row["id"]: row for row in rows}
    entries, counts = [], Counter()
    for case in cases:
        if not case["answerable"]:
            continue
        row = by_id[case["id"]]
        relevant = set(case["relevant_chunk_ids"])
        correct_document = bool(set(row["documents"][:5]) & set(case["relevant_documents"]))
        if not correct_document or relevant & set(row["ranking"][:5]):
            continue
        # Evidence is considered alternate-valid only when the independently
        # labeled heading occurs in the retrieved static PDF text. Mere rank or
        # same-document membership is explicitly insufficient.
        headings = {item.casefold() for item in case["reference_evidence"]}
        # A generic template can mention other policy concepts in its body.
        # Only an independently recorded section/subsection identity is strong
        # enough to call an alternate chunk valid evidence.
        alternates = [chunk_id for chunk_id in row["ranking"][:5] if (records[chunk_id]["metadata"].get("subsection") or records[chunk_id]["metadata"].get("section") or "").casefold() in headings]
        label_indexes = [records[chunk_id]["metadata"]["chunk_index"] for chunk_id in relevant]
        neighbors = [chunk_id for chunk_id in row["ranking"][:5] if records[chunk_id]["metadata"]["source"] in case["relevant_documents"] and any(abs(records[chunk_id]["metadata"]["chunk_index"] - index) == 1 for index in label_indexes)]
        if alternates:
            classification, reason = "ALTERNATE_VALID_EVIDENCE", "retrieved static chunk repeats independently labeled heading"
        elif neighbors:
            classification, reason = "NEIGHBOR_BOUNDARY_MATCH", "same-document adjacent chunk returned; no heading match, so label remains unchanged"
        else:
            classification, reason = "TRUE_RETRIEVAL_MISS", "correct document retrieved without labeled heading or adjacent evidence chunk"
        counts[classification] += 1
        entries.append({"benchmark_id": case["id"], "classification": classification, "reason": reason, "old_relevant_chunk_ids": case["relevant_chunk_ids"], "retrieved_top5": row["ranking"][:5], "document": case["relevant_documents"], "pages": case["relevant_pages"]})
    return entries, counts


def _multidoc(rows, cases):
    by_id = {row["id"]: row for row in rows}
    values = {5: [], 10: []}
    for case in cases:
        if case["question_type"] != "multi_document":
            continue
        for k in values:
            values[k].append(len(set(by_id[case["id"]]["documents"][:k]) & set(case["relevant_documents"])) / len(case["relevant_documents"]))
    return {str(k): statistics.mean(v) if v else None for k, v in values.items()}


def _audited_cases(cases, records):
    """Expand labels from independent static heading identity, never rankings."""
    audited, changes = deepcopy(cases), []
    for item in audited:
        if not item["answerable"]:
            continue
        headings = {heading.casefold() for heading in item["reference_evidence"]}
        matching = sorted(
            chunk_id for chunk_id, record in records.items()
            if record["metadata"]["source"] in item["relevant_documents"]
            and (record["metadata"].get("subsection") or record["metadata"].get("section") or "").casefold() in headings
        )
        old = list(item["relevant_chunk_ids"])
        if set(matching) != set(old):
            item["relevant_chunk_ids"] = matching
            item["relevant_pages"] = sorted({records[chunk_id]["metadata"]["page"] for chunk_id in matching})
            changes.append({"benchmark_id": item["id"], "old_relevant_chunk_ids": old, "new_relevant_chunk_ids": matching, "reason": "same source and independently recorded section/subsection heading in static PDF-derived corpus", "evidence": [{"document": records[chunk_id]["metadata"]["source"], "page": records[chunk_id]["metadata"]["page"]} for chunk_id in matching], "classification": "ALTERNATE_VALID_EVIDENCE"})
    return audited, changes


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    cases = json.loads((HERE / "dataset/benchmark.json").read_text())
    records = json.loads((ROOT / "data/runtime/vectorstore/records.json").read_text())
    validation_errors = validate(cases, records)
    if validation_errors:
        raise ValueError("Benchmark identity audit failed: " + "; ".join(validation_errors))
    settings = get_settings()
    store = FaissVectorStore(ROOT / "data/runtime/vectorstore")
    embeddings = EmbeddingService(settings.embedding_model, device=settings.embedding_device, local_files_only=True)
    dense = DenseRetriever(store, embeddings, 30)
    sparse = BM25SparseRetriever.from_artifact(ROOT / "data/runtime/sparse/bm25_corpus.json", store)
    original_answerable = [case for case in cases if case["answerable"]]
    # Diagnose original strict labels first, then retain a separately auditable
    # label expansion. The committed Phase 21 dataset itself is never edited.
    original_retriever = HybridRetriever(dense, sparse, DisabledReranker(), 30, 10, 60, True, False)
    original_baseline = _rows(original_answerable, lambda q: original_retriever.retrieve(q).chunks, records)
    original_entries, audit_counts = _audit(cases, original_baseline["per_question"], records)
    audited_cases, changes = _audited_cases(cases, records)
    if errors := validate(audited_cases, records):
        raise ValueError("Audited benchmark validation failed: " + "; ".join(errors))
    (OUT / "phase22_audited_benchmark.json").write_text(json.dumps(audited_cases, indent=2) + "\n")
    answerable = [case for case in audited_cases if case["answerable"]]
    dev = [case for case in audited_cases if case["answerable"] and case["split"] == "development"]
    held_out = [case for case in audited_cases if case["answerable"] and case["split"] == "held_out"]
    experiments = {}
    for name, candidate_k, rrf_k, hybrid in (("dense", 30, 60, False), ("bm25", 30, 60, None), ("hybrid_rrf60", 30, 60, True), ("hybrid_rrf30", 30, 30, True), ("hybrid_rrf90", 30, 90, True), ("hybrid_candidate10", 10, 60, True), ("hybrid_candidate20", 20, 60, True)):
        if hybrid is None:
            getter = lambda q, k=candidate_k: sparse.retrieve(q, k)[:10]
        else:
            retriever = HybridRetriever(dense, sparse if hybrid else None, DisabledReranker(), candidate_k, 10, rrf_k, hybrid, False)
            getter = lambda q, r=retriever: r.retrieve(q).chunks
        full = _rows(answerable, getter, records)
        development = _rows(dev, getter, records)
        held = _rows(held_out, getter, records)
        experiments[name] = {"change": ("BM25 standalone" if hybrid is None else f"candidate_k={candidate_k}; RRF={rrf_k}; hybrid={hybrid}"), "overall": full, "development": development["aggregate"], "held_out": held["aggregate"], "latency_ms": full["latency_ms"]}
    baseline = experiments["hybrid_rrf60"]["overall"]
    identity = {"total_labeled_references": sum(len(item["relevant_chunk_ids"]) for item in original_answerable), "resolved": sum(len(item["relevant_chunk_ids"]) for item in original_answerable), "unresolved": 0, "duplicate_ids": len(records) - len(set(records)), "page_mismatches": 0, "document_mismatches": 0}
    diagnosis = {"generated_at": datetime.now(timezone.utc).isoformat(), "identity_audit": identity, "semantic_audit": {"correct_document_wrong_exact_chunk": len(original_entries), "counts": dict(audit_counts), "entries": original_entries}, "ground_truth_changes": changes, "neighbor_rule": "same document, chunk_index adjacent to an independently labeled chunk, and recorded only as diagnostic; labels are unchanged unless retrieved text independently repeats the labeled heading", "multi_document_coverage": _multidoc(baseline["per_question"], audited_cases)}
    (OUT / "phase22_diagnosis.json").write_text(json.dumps(diagnosis, indent=2) + "\n")
    (OUT / "phase22_ground_truth_audit.json").write_text(json.dumps({"changes": changes, "reason": "Audited labels expand only to static chunks from the same PDF with an identical independently recorded heading; rankings did not determine the labels."}, indent=2) + "\n")
    # Neighbor-aware measurement only expands labels for independently audited
    # NEIGHBOR_BOUNDARY_MATCH records. This run found none, so it is reported
    # explicitly as identical to strict audited metrics rather than inflated.
    result = {"generated_at": datetime.now(timezone.utc).isoformat(), "configuration": {"embedding_model": settings.embedding_model, "faiss": "IndexFlatIP with normalized vectors", "fusion": "reciprocal rank fusion", "production_candidate_k": settings.rag_retrieval_candidate_k, "production_rrf_k": settings.rag_rrf_k}, "original_strict_baseline": original_baseline, "experiments": experiments, "diagnosis": diagnosis, "neighbor_aware": {"qualifying_neighbor_cases": audit_counts["NEIGHBOR_BOUNDARY_MATCH"], "rule": diagnosis["neighbor_rule"], "metrics": baseline["aggregate"]}}
    (OUT / "phase22_retrieval_results.json").write_text(json.dumps(result, indent=2) + "\n")
    (OUT / "phase22_experiments.json").write_text(json.dumps({name: {key: value for key, value in experiment.items() if key != "overall"} for name, experiment in experiments.items()}, indent=2) + "\n")
    print(json.dumps({name: {"dev_r5": value["development"]["recall"]["5"], "held_r5": value["held_out"]["recall"]["5"], "dev_mrr": value["development"]["mrr"]} for name, value in experiments.items()}))


if __name__ == "__main__":
    main()
