# Phase 21 RAG Baseline Evaluation

## Objective

This is a measurement-only baseline of the existing InfoTech/XYZ policy RAG.
No production embedding, chunking, retrieval weight, reranker, prompt, PDF, or
runtime configuration was changed for this evaluation.

## Corpus and benchmark

- Documents: 5; indexed chunks: 795.
- Benchmark: 68 questions (60 answerable, 8 unanswerable); 16 deterministic held-out cases.
- Labels were selected from static PDF-derived index records before retrieval, never from returned rankings. Exact chunk relevance is intentionally stricter than document relevance.
- Retrieval depth: 10; candidate pool: 30; reranking: not configured in current production settings.

## Retrieval metrics (chunk-level)

| Retriever | R@1 | R@3 | R@5 | R@10 | P@5 | Hit@5 | MRR | mAP |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Dense | 0.0000 (0.0%) | 0.0167 (1.7%) | 0.0167 (1.7%) | 0.0333 (3.3%) | 0.0033 (0.3%) | 0.0167 (1.7%) | 0.0076 | 0.0076 |
| Hybrid (dense + production BM25/RRF) | 0.0167 (1.7%) | 0.0333 (3.3%) | 0.0333 (3.3%) | 0.0667 (6.7%) | 0.0067 (0.7%) | 0.0333 (3.3%) | 0.0263 | 0.0263 |

## Document-level retrieval

Hybrid document HitRate@5: 0.9833 (98.3%); document Recall@5: 0.9833 (98.3%). This gap from exact-chunk metrics is a measured indication that the system often finds the policy document but not the labeled passage.

## Generation and end-to-end status

Generation was **NOT_EXECUTED**: No local Ollama provider was configured or running; Phase 21 does not initiate paid OpenRouter generation.

Consequently faithfulness, answer correctness, relevance, citation metrics, abstention, and end-to-end success are **N/A**, not zero and not estimated. The framework records model/provider metadata without secrets and retains a 20-item blank human-review worksheet.

## Error analysis

The following representative answerable items had no independently labeled exact chunk in the hybrid top 10: xyz_code_of_conduct_002, xyz_code_of_conduct_003, xyz_code_of_conduct_004, xyz_code_of_conduct_005, xyz_code_of_conduct_006.

Observed patterns: (1) document-level retrieval materially exceeds exact-chunk retrieval; (2) multi-document comparisons have zero exact-chunk Hit@10; (3) several policy categories have zero exact-chunk Hit@5; (4) no production reranker is configured, so no fair reranked comparison exists; (5) generation is unmeasured because safe local generation was unavailable and paid provider invocation was intentionally avoided.

## Limitations and reproducibility

The corpus is synthetic project policy content. Questions are deterministic and balanced by source, with wording variants and five multi-document cases; future tuning must use the development split and retain held-out cases. Run `PYTHONPATH=backend:. .venv/bin/python evaluation/build_benchmark.py`, then the documented local-only retrieval command, `evaluation/evaluate_generation.py`, and `evaluation/report.py`. Results carry commit and benchmark hashes. No human ratings were fabricated.

## Presentation summary

The measured hybrid baseline has chunk Recall@5 0.0333 (3.3%), MRR 0.0263, and mAP 0.0263; it finds the correct document much more frequently than the exact labeled passage. Generation quality is deliberately unreported until a safe local provider is available.
