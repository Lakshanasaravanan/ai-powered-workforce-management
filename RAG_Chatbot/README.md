# Agentic RAG service

This directory contains the standalone AI-assistant service for the Workforce Management Platform. It does not access the `SLAMS` database; future workforce integration will use authenticated REST clients.

## Retrieval architecture

Policy retrieval defaults to BGE dense search, bounded to `RAG_RETRIEVAL_CANDIDATE_K` (default 30) and reduced to final `RAG_RETRIEVAL_TOP_K` (default 5) before context assembly. This is the current baseline because a manual, synthetic document-level evaluation set showed better retrieval quality and latency than the hybrid variants. BM25 plus Reciprocal Rank Fusion (RRF), and cross-encoder reranking, are available as explicit opt-ins through `RAG_HYBRID_ENABLED=true` and `RAG_RERANK_ENABLED=true`.

On the 12-case fixture in `backend/data/evaluation/retrieval_cases.json`, dense-only achieved Hit@5 1.000, MRR 0.958, and Recall@5 0.958. Hybrid without reranking measured 0.917, 0.833, and 0.917; hybrid with reranking measured the same quality and added substantial latency. These are small synthetic document-level results, so hybrid and reranking should only be enabled after broader representative evaluation.

## Local setup

Use Python 3.13 for local development and indexing. This matches the Docker image and the verified FAISS runtime; the local FAISS wheel has not been reliable under Python 3.14 on macOS arm64.

```bash
cd RAG_Chatbot
python3.13 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
.venv/bin/uvicorn app.main:app --app-dir backend --reload
```

Set a unique `JWT_SECRET_KEY` before any non-development deployment. In development, an ephemeral process-local signing key is used only if no key is configured; readiness reports this as a warning.

## API

- `GET /health` checks that the process is running.
- `GET /ready` checks Phase 1 configuration.
- `POST /api/v1/auth/token` issues a development token for `EMP001` or `EMP002`.
- `POST /api/v1/chat` is an authenticated placeholder endpoint.

For development login, use `EMP001` / `demo-emp001` or `EMP002` / `demo-emp002`. These mock credentials are not a production authentication mechanism.

```bash
curl -X POST http://localhost:8000/api/v1/auth/token \
  -H 'Content-Type: application/json' \
  -d '{"username":"EMP001","password":"demo-emp001"}'
```

Use the returned access token as a bearer token when calling `/api/v1/chat`.

## Index company policy PDFs

Indexing is an explicit offline operation; chat requests never process PDFs or build vectors.

```bash
cd RAG_Chatbot
PYTHONPATH=backend .venv/bin/python -m app.rag.ingestion
```

The command reads `data/documents/`, writes an ignored local FAISS baseline under `data/vectorstore/`, and reports document/page/chunk counts plus embedding dimension. Configure chunk sizes and retrieval limits with the `RAG_*` environment variables in `.env.example`.

It also writes an ignored, inspectable BM25 corpus at `data/sparse/bm25_corpus.json`. The sparse corpus is loaded only when hybrid retrieval is enabled and is validated against the FAISS records. The reranker model is downloaded lazily on its first enabled request; normal tests mock it and do not download models.

## Retrieval evaluation

The manually reviewed document-level fixture is at `backend/data/evaluation/retrieval_cases.json`. Evaluation computes Hit Rate@K, MRR, and source-level Recall@K without an LLM. FAISS metadata filtering scans the local corpus for correctness; a future Qdrant backend can apply the same typed filters natively.

## Tests

```bash
cd RAG_Chatbot
PYTHONPATH=backend .venv/bin/pytest backend/tests -q
```
