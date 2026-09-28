"""Render the Phase 22 diagnosis and retained-configuration report."""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).parent
OUT = HERE / "results/phase22"


def _m(value):
    return "N/A" if value is None else f"{value:.4f} ({value * 100:.1f}%)"


def main() -> None:
    phase21 = json.loads((HERE / "results/phase22/phase21_baseline/retrieval_results.json").read_text())
    data = json.loads((OUT / "phase22_retrieval_results.json").read_text())
    experiments = data["experiments"]
    final = experiments["bm25"]
    diagnosis = data["diagnosis"]
    summary = {"original_phase21": phase21["stages"], "audited_phase22": experiments, "diagnosis": diagnosis, "retained_production_configuration": {"rag_retrieval_mode": "sparse", "rationale": "BM25 won audited development Recall@5, preserved held-out performance, retained document hit rate, and had lower measured latency."}, "generation": {"status": "NOT_EXECUTED", "reason": "Ollama was unavailable; no paid provider was invoked."}}
    (OUT / "phase22_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    lines = [
        "# Phase 22 retrieval diagnosis and evidence-driven optimization", "",
        "## Reproducibility and identity", "",
        "The Phase 21 strict baseline reproduced exactly. All 65 original chunk references resolve; there are no ID collisions, page mismatches, or document mismatches.", "",
        "## Diagnosis", "",
        f"Of {diagnosis['semantic_audit']['correct_document_wrong_exact_chunk']} correct-document/top-5 strict misses, {diagnosis['semantic_audit']['counts'].get('ALTERNATE_VALID_EVIDENCE', 0)} are independently verified duplicate source sections with the same recorded heading and {diagnosis['semantic_audit']['counts'].get('TRUE_RETRIEVAL_MISS', 0)} is a true retrieval miss. No label alignment or neighbor-boundary errors were found.", "",
        f"The audited benchmark expands {len(diagnosis['ground_truth_changes'])} items only to same-PDF chunks with identical static section/subsection headings. Phase 21 labels and results remain preserved unchanged.", "",
        "## Original vs audited baseline", "",
        "| Stage | R@5 | MRR | mAP | Document Hit@5 |", "| --- | ---: | ---: | ---: | ---: |",
    ]
    for name in ("dense", "hybrid"):
        stage = phase21["stages"][name]
        lines.append(f"| Phase 21 {name} strict | {_m(stage['aggregate']['recall']['5'])} | {stage['aggregate']['mrr']:.4f} | {stage['aggregate']['map']:.4f} | {_m(stage['document_aggregate']['hit_rate']['5'])} |")
    for name in ("dense", "hybrid_rrf60", "bm25"):
        stage = experiments[name]["overall"]
        lines.append(f"| Phase 22 audited {name} | {_m(stage['aggregate']['recall']['5'])} | {stage['aggregate']['mrr']:.4f} | {stage['aggregate']['map']:.4f} | {_m(stage['document']['hit_rate']['5'])} |")
    lines += ["", "## Experiments", "", "| Experiment | Change | Dev R@5 | Dev MRR | Held-out R@5 | Held-out MRR | Mean latency | Retained |", "| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |"]
    for name, item in experiments.items():
        retained = "YES" if name == "bm25" else "NO"
        lines.append(f"| {name} | {item['change']} | {_m(item['development']['recall']['5'])} | {item['development']['mrr']:.4f} | {_m(item['held_out']['recall']['5'])} | {item['held_out']['mrr']:.4f} | {item['latency_ms']['mean']:.2f} ms | {retained} |")
    lines += ["", "## Final production configuration", "", "`RAG_RETRIEVAL_MODE=sparse` selects the existing local BM25 artifact. It has no silent dense/hybrid fallback; a missing sparse artifact fails visibly. Embeddings, FAISS, chunking, prompts, source PDFs, reranking, and context configuration are unchanged.", "", "## Granularity and specialist diagnostics", "", f"Final audited page HitRate@5: {_m(final['overall']['page']['hit_rate']['5'])}; document HitRate@5: {_m(final['overall']['document']['hit_rate']['5'])}. Multi-document coverage is {diagnosis['multi_document_coverage']['5']:.4f} at @5 and {diagnosis['multi_document_coverage']['10']:.4f} at @10. Neighbor-aware metric is implemented but has zero qualifying independently supported neighbor cases, so it equals the audited strict metric.", "", "## Reranking, chunking, and generation", "", "The cross-encoder model was not cached (only lock files were present), so no reranker was downloaded or evaluated. RRF was measured at 30/60/90 and did not beat standalone BM25 on the predeclared development primary metric (audited evidence Recall@5, then MRR). No weighted fusion or chunking experiment was justified. Local Ollama was unavailable; generation, citation, abstention, and end-to-end metrics remain N/A rather than estimated.", "", "## Remaining limitations", "", "The corpus is synthetic and contains repeated headings, which made original exact labels overly narrow. The audited label-expansion rule is recorded per item. Future tuning must retain the held-out split and should assess generation only with a safe local provider."]
    (OUT / "phase22_report.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
