# Phase 22 retrieval diagnosis and evidence-driven optimization

## Reproducibility and identity

The Phase 21 strict baseline reproduced exactly. All 65 original chunk references resolve; there are no ID collisions, page mismatches, or document mismatches.

## Diagnosis

Of 57 correct-document/top-5 strict misses, 56 are independently verified duplicate source sections with the same recorded heading and 1 is a true retrieval miss. No label alignment or neighbor-boundary errors were found.

The audited benchmark expands 55 items only to same-PDF chunks with identical static section/subsection headings. Phase 21 labels and results remain preserved unchanged.

## Original vs audited baseline

| Stage | R@5 | MRR | mAP | Document Hit@5 |
| --- | ---: | ---: | ---: | ---: |
| Phase 21 dense strict | 0.0167 (1.7%) | 0.0076 | 0.0076 | 0.9833 (98.3%) |
| Phase 21 hybrid strict | 0.0333 (3.3%) | 0.0263 | 0.0263 | 0.9833 (98.3%) |
| Phase 22 audited dense | 0.4708 (47.1%) | 0.8660 | 0.4301 | 0.9833 (98.3%) |
| Phase 22 audited hybrid_rrf60 | 0.4917 (49.2%) | 0.8818 | 0.4513 | 0.9833 (98.3%) |
| Phase 22 audited bm25 | 0.9208 (92.1%) | 0.8407 | 0.8311 | 0.9833 (98.3%) |

## Experiments

| Experiment | Change | Dev R@5 | Dev MRR | Held-out R@5 | Held-out MRR | Mean latency | Retained |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| dense | candidate_k=30; RRF=60; hybrid=False | 0.4667 (46.7%) | 0.8324 | 0.4833 (48.3%) | 0.9667 | 7.39 ms | NO |
| bm25 | BM25 standalone | 0.9333 (93.3%) | 0.8313 | 0.8833 (88.3%) | 0.8689 | 0.72 ms | YES |
| hybrid_rrf60 | candidate_k=30; RRF=60; hybrid=True | 0.4889 (48.9%) | 0.8647 | 0.5000 (50.0%) | 0.9333 | 8.43 ms | NO |
| hybrid_rrf30 | candidate_k=30; RRF=30; hybrid=True | 0.4889 (48.9%) | 0.8647 | 0.5000 (50.0%) | 0.9333 | 8.40 ms | NO |
| hybrid_rrf90 | candidate_k=30; RRF=90; hybrid=True | 0.4889 (48.9%) | 0.8647 | 0.5000 (50.0%) | 0.9333 | 8.38 ms | NO |
| hybrid_candidate10 | candidate_k=10; RRF=60; hybrid=True | 0.5111 (51.1%) | 0.8717 | 0.5000 (50.0%) | 0.9333 | 8.00 ms | NO |
| hybrid_candidate20 | candidate_k=20; RRF=60; hybrid=True | 0.4889 (48.9%) | 0.8689 | 0.5000 (50.0%) | 0.9333 | 8.18 ms | NO |

## Final production configuration

`RAG_RETRIEVAL_MODE=sparse` selects the existing local BM25 artifact. It has no silent dense/hybrid fallback; a missing sparse artifact fails visibly. Embeddings, FAISS, chunking, prompts, source PDFs, reranking, and context configuration are unchanged.

## Granularity and specialist diagnostics

Final audited page HitRate@5: 0.9500 (95.0%); document HitRate@5: 0.9833 (98.3%). Multi-document coverage is 1.0000 at @5 and 1.0000 at @10. Neighbor-aware metric is implemented but has zero qualifying independently supported neighbor cases, so it equals the audited strict metric.

## Reranking, chunking, and generation

The cross-encoder model was not cached (only lock files were present), so no reranker was downloaded or evaluated. RRF was measured at 30/60/90 and did not beat standalone BM25 on the predeclared development primary metric (audited evidence Recall@5, then MRR). No weighted fusion or chunking experiment was justified. Local Ollama was unavailable; generation, citation, abstention, and end-to-end metrics remain N/A rather than estimated.

## Remaining limitations

The corpus is synthetic and contains repeated headings, which made original exact labels overly narrow. The audited label-expansion rule is recorded per item. Future tuning must retain the held-out split and should assess generation only with a safe local provider.
