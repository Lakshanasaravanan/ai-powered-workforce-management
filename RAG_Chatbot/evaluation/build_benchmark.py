"""Build a static, balanced Phase 21 baseline from indexed PDF evidence.

Labels are selected from index metadata/text before any retrieval run.  This
is appropriate for the synthetic project corpus and deliberately never reads
retrieval results while constructing labels.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECORDS = ROOT / "data/runtime/vectorstore/records.json"
OUT = Path(__file__).parent / "dataset/benchmark.json"


def main() -> None:
    records = json.loads(RECORDS.read_text())
    by_source: dict[str, list[tuple[str, dict]]] = {}
    for chunk_id, item in records.items():
        meta = item["metadata"]
        if meta.get("subsection") != "Example policy for RAG testing":
            by_source.setdefault(meta["source"], []).append((chunk_id, item))
    items = []
    deferred: list[tuple[str, str, dict]] = []
    for source, rows in sorted(by_source.items()):
        seen: set[str] = set()
        selected: list[tuple[str, dict]] = []
        for chunk_id, item in rows:
            heading = item["metadata"].get("subsection") or item["metadata"].get("section")
            if not heading or heading in seen:
                continue
            seen.add(heading)
            selected.append((chunk_id, item))
            if len(selected) == 12:
                break
        # Eleven independently labeled single-chunk questions per document.
        # The wording variants exercise retrieval without consulting rankings.
        variants = [
            ("What guidance does the company policy provide about {heading}?", "direct", "direct"),
            ("What does the policy say about {heading}?", "direct", "direct"),
            ("Which policy guidance applies to {heading}?", "direct", "direct"),
            ("How should employees handle {heading} under company policy?", "direct", "direct"),
            ("Summarize the policy rule for {heading}.", "direct", "direct"),
            ("What responsibility is described for {heading}?", "direct", "direct"),
            ("Where can staff find guidance on {heading}?", "direct", "direct"),
            ("Explain the company's approach to {heading}.", "medium", "paraphrase"),
            ("In practical terms, how is {heading} addressed?", "medium", "paraphrase"),
            ("What does the policy say about {typo_heading}?", "hard", "typo_robustness"),
            ("Does a similarly named rule override the published guidance on {heading}?", "hard", "hard_negative"),
        ]
        for position, (chunk_id, item) in enumerate(selected[:11]):
            heading = item["metadata"].get("subsection") or item["metadata"].get("section")
            text = " ".join(item["text"].split())
            template, difficulty, question_type = variants[position]
            items.append({
                "id": f"{Path(source).stem.lower()}_{position + 1:03d}",
                "question": template.format(heading=heading, typo_heading=heading.replace("i", "ie", 1)),
                "category": source.removeprefix("XYZ_").removesuffix(".pdf").lower(),
                "answerable": True,
                "relevant_documents": [source],
                "relevant_pages": [item["metadata"]["page"]],
                "relevant_chunk_ids": [chunk_id],
                "reference_answer": text[:500],
                "reference_evidence": [heading],
                "difficulty": difficulty,
                "question_type": question_type,
                "split": "held_out" if (position + 1) % 5 == 0 else "development",
            })
        deferred.append((source, selected[11][0], selected[11][1]))

    # Five real multi-document/multi-chunk comparisons, each grounded in the
    # static text and metadata of two different PDFs.
    for index, (left, right) in enumerate(zip(deferred, deferred[1:] + deferred[:1], strict=True), 1):
        left_source, left_id, left_item = left
        right_source, right_id, right_item = right
        left_heading = left_item["metadata"].get("subsection") or left_item["metadata"].get("section")
        right_heading = right_item["metadata"].get("subsection") or right_item["metadata"].get("section")
        left_text = " ".join(left_item["text"].split())
        right_text = " ".join(right_item["text"].split())
        items.append({
            "id": f"multi_document_{index:03d}",
            "question": f"Compare the policy guidance on {left_heading} and {right_heading}.",
            "category": "multi_document",
            "answerable": True,
            "relevant_documents": [left_source, right_source],
            "relevant_pages": [left_item["metadata"]["page"], right_item["metadata"]["page"]],
            "relevant_chunk_ids": [left_id, right_id],
            "reference_answer": f"{left_text[:250]} {right_text[:250]}",
            "reference_evidence": [left_heading, right_heading],
            "difficulty": "hard",
            "question_type": "multi_document",
            "split": "held_out",
        })
    unsupported = ["What is the exact remaining leave balance for an employee?", "What bank account receives payroll?", "Who is my current manager?", "What is the company office parking allocation?", "What is my attendance yesterday?", "What is the next salary payment amount?", "Which employee has the highest overtime?", "What is the company stock-price policy?"]
    for index, question in enumerate(unsupported, 1):
        items.append({"id": f"unanswerable_{index:03d}", "question": question, "category": "unanswerable", "answerable": False, "relevant_documents": [], "relevant_pages": [], "relevant_chunk_ids": [], "reference_answer": "The provided company policy documents do not contain this information.", "reference_evidence": [], "difficulty": "hard", "question_type": "unanswerable", "split": "held_out" if index % 5 == 0 else "development"})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(items, indent=2) + "\n")
    print(json.dumps({"count": len(items), "hash": hashlib.sha256(OUT.read_bytes()).hexdigest()}))


if __name__ == "__main__": main()
