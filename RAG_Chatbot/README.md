# Agentic RAG workforce service

## Overview

This FastAPI service provides policy retrieval and safe employee self-service for SLAMS. The browser uses the employee assistant in the SLAMS Thymeleaf UI; it never receives a trusted employee ID, assistant secret, delegation key, database credential, or provider key.

## RAG pipeline and evaluation

Indexing is explicit and offline: `PYTHONPATH=backend .venv/bin/python -m app.rag.ingestion`. It cleans policy PDFs, chunks them, embeds with BGE `BAAI/bge-small-en-v1.5`, and writes ignored FAISS artifacts. Chat startup never rebuilds embeddings. Dense FAISS retrieval is the default. BM25 plus reciprocal-rank fusion and a cross-encoder reranker are optional through `RAG_HYBRID_ENABLED` and `RAG_RERANK_ENABLED`.

The final dense evaluation at k=5 on a 12-case manually reviewed synthetic/document-level fixture measured Hit@5 **1.000**, MRR **0.9583**, Recall@5 **0.9583**, and average retrieval latency **17.74 ms**. This small fixture is useful regression evidence, not proof of quality for arbitrary production queries.

## Agent, tools, and actions

`AgentService` uses deterministic planning, typed tool contracts, an immutable execution context, and server-side authorization. Employees can retrieve profile, leave balance, attendance summary, attendance records, and policy answers. Leave requests and attendance regularizations are proposed first, then execute against SLAMS only after explicit confirmation.

Confirmation accepts only opaque `action_id` and `conversation_id`. Stored action arguments are immutable, employee/conversation-bound, and cannot be replaced by browser input. Persisted idempotency keys, atomic claims, and concurrent-confirmation protections prevent duplicate mutations. Redis mode shares pending-action state across replicas; stale execution lease recovery reuses the same stored idempotency key.

## Trust boundaries and integration

SLAMS authenticates the browser and its server-side bridge issues a short-lived assistant token. FastAPI validates its HS256 algorithm, issuer, audience, expiry, type, and subject/employee consistency; assistant role claims are ignored. FastAPI calls SLAMS workforce APIs with short-lived RS256 delegation tokens; SLAMS validates the key/claims and resolves employee authorization itself. Real integration failures never fall back to mock mutations.

## Operations

`GET /health` is liveness, `GET /ready` reports readiness of required dependencies, and `GET /metrics` exposes Prometheus metrics with low-cardinality labels. Chat and confirmation limits are separate per employee. `POST /api/v1/auth/token` exists only when `DEVELOPMENT_AUTH_ENABLED=true`; production requires it false and rejects missing or placeholder JWT, assistant-token, Redis, SLAMS/delegation, and provider configuration.

## Development, testing, and deployment

Use Python 3.13. Install dependencies with `.venv/bin/pip install -r requirements.txt`, then run `PYTHONPATH=backend .venv/bin/pytest backend/tests -q`. The root `compose.yaml` defines FastAPI, SLAMS, Redis, and MySQL; secrets are environment-supplied and `.env` is never copied into images. Prebuild and mount/provide ignored FAISS artifacts for deployment. CI runs the Python suite and Java 21 Maven test/package checks.

## Limitations

FAISS is local rather than a managed vector database. The evaluation fixture is small. OpenRouter is an external dependency. H2 concurrency is not identical to MySQL. The project does not include enterprise SSO, Kubernetes autoscaling, or a cloud staging load test.
