# Phase 21 evaluation

This directory measures the existing policy RAG without changing production retrieval. Benchmark labels are selected from static PDF-derived index records before retrieval; returned rankings are never used to create or change labels.

Run from `RAG_Chatbot` with cached embeddings:

```sh
PYTHONPATH=backend:. .venv/bin/python evaluation/build_benchmark.py
KMP_DUPLICATE_LIB_OK=TRUE EMBEDDING_LOCAL_FILES_ONLY=true OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 TOKENIZERS_PARALLELISM=false PYTHONPATH=backend:. .venv/bin/python evaluation/evaluate_retrieval.py
PYTHONPATH=backend:. .venv/bin/python evaluation/evaluate_generation.py
PYTHONPATH=backend:. .venv/bin/python evaluation/report.py
```

`evaluate_generation.py` never calls a paid cloud provider implicitly. If a reproducible local provider is unavailable, it writes an explicit `NOT_EXECUTED` result rather than manufacturing generation metrics.
