# InfoTech Policy RAG service

## Phase 4 scope

This FastAPI service provides **policy question answering only** for InfoTech Workspace. It does not create leave, approve leave, modify attendance, write the EMS database, call SLAMS action APIs, or run arbitrary tools. Those workflows are deliberately outside Phase 4.

```text
React InfoTech Workspace
        |  existing EMS bearer token
        v
POST /api/v1/agent/query
        |-- validate EMS HS256 JWT (expiration and UUID subject)
        |-- EMS GET /api/v1/auth/me (active identity is authoritative)
        |-- dense BGE retrieval
        |     |-- local FAISS (default)
        |     `-- existing Qdrant collection (production-oriented option)
        |-- grounded OpenRouter generation
        `-- evidence-ID validation -> answer + structured citations
```

The browser sends only `message` and an optional `conversation_id`. It never supplies trusted employee identity, role, manager, or authorization fields. The endpoint is strict and rejects extra identity fields.

## API contract

`POST /api/v1/agent/query`

```json
{"message":"What is the leave policy?","conversation_id":"optional UUID"}
```

The response contains `answer`, `sources`, `conversation_id`, and `request_id`. A source has only validated server metadata: `document`, `page`, `section`, and `subsection`. Model output cannot author citation metadata. Invalid or absent evidence IDs produce a safe answer with no citations; malformed provider output also fails safely.

The React Agent screen uses the employee's existing EMS session token, keeps its conversation ID in memory, renders model text as text rather than HTML, and presents grounding fallbacks as normal answers. Service failures are displayed separately.

## Provider selection

The provider is backend configuration, not a React contract. OpenRouter remains the backward-compatible default:

```sh
LLM_PROVIDER=openrouter
LLM_BASE_URL=https://openrouter.ai/api/v1
LLM_MODEL=provider-model-id
```

For local generation, use the non-secret launcher. It selects Ollama
explicitly and never falls back to OpenRouter when Ollama is unavailable:

```sh
cd RAG_Chatbot
bash scripts/run_local_ollama.sh
```

Install Ollama, pull the configured model, and run its local server before starting RAG. Hardware requirements and latency vary by laptop; `qwen3:8b` is not assumed to be suitable for every machine. Ollama receives the same system prompt and bounded evidence as OpenRouter through `/api/chat`, with non-streaming deterministic options, `think:false`, and the JSON schema for the grounded response. Only the final message content is parsed; reasoning/thinking fields and raw provider responses are never returned to an employee. `/ready` checks that the configured local Ollama model is available without issuing a generation request.

## Offline index lifecycle

Indexing is explicit and never occurs at startup or query time:

```sh
cd RAG_Chatbot
PYTHONPATH=backend .venv/bin/python -m app.rag.ingestion build
```

The builder deterministically discovers the five policy PDFs, extracts and cleans pages, chunks them, embeds with `BAAI/bge-small-en-v1.5`, writes FAISS and BM25 artifacts to a staging directory, validates them, then promotes them atomically. A manifest records source hashes, the embedding model/dimension, chunk settings, and artifact counts. Missing, stale, or corrupt artifacts fail readiness and policy queries closed; serving never silently rebuilds an index.

Local artifacts resolve to the ignored `data/runtime/` directory by default.
Build them explicitly before serving; startup and requests never rebuild an index:

```sh
export EMBEDDING_LOCAL_FILES_ONLY=true
export EMBEDDING_CACHE_DIR=/path/to/already-provisioned/huggingface/hub
PYTHONPATH=backend .venv/bin/python -m app.rag.ingestion build
```

Runtime indexes, model caches, and generated sparse artifacts are not committed. `RAG_RUNTIME_VECTOR_STORE_DIR`, `RAG_RUNTIME_SPARSE_INDEX_PATH`, `EMBEDDING_CACHE_DIR`, `EMBEDDING_LOCAL_FILES_ONLY`, and `EMBEDDING_DEVICE` are configuration names only; do not commit local paths or credentials. `EMBEDDING_DEVICE=cpu` is the deterministic local default; select another supported device only after operational validation. The local launcher also supplies macOS-safe `KMP_DUPLICATE_LIB_OK=TRUE`, `OMP_NUM_THREADS=1`, and `MKL_NUM_THREADS=1` defaults, which operators may override process-locally.

## Retrieval and evidence calibration

Local FAISS dense retrieval is the default: BGE dimension 384, candidate pool 30, top-K 5, context budget 1800. BM25/RRF hybrid retrieval and the cross-encoder reranker are available but disabled by default. On the 12-case manually reviewed synthetic/document-level fixture, dense retrieval measured Hit@5 **1.000**, MRR **0.9583**, Recall@5 **0.9583**, and average retrieval latency **17.74 ms**.

The evidence calibration experiment found overlap between answerable and unsupported dense-score distributions. No cosine threshold was selected because it would reject legitimate evidence or admit unsupported material. The generation contract therefore requires the provider to return evidence IDs that are validated against retrieved chunks; it is instructed to use only the supplied evidence and to say it is not sure when evidence is insufficient.

`VECTOR_STORE_BACKEND=faiss` is the default. `VECTOR_STORE_BACKEND=qdrant` validates a pre-existing compatible collection named by `QDRANT_COLLECTION`; it does not create, recreate, or index it during serving. A live production Qdrant deployment remains an operational follow-up.

## Local run

1. Start InfoTech infrastructure:

   ```sh
   cd infra
   docker compose -f compose.yaml up -d
   ```

2. Start EMS:

   ```sh
   cd apps/ems-api
   PYTHONPATH=. .venv/bin/alembic upgrade head
   PYTHONPATH=. .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8001 --workers 1
   ```

3. Build the explicit local index as above, then start Ollama and this service:

   ```sh
   cd RAG_Chatbot
   ollama pull qwen3:8b
   ollama serve
   # In another terminal:
   CORS_ALLOWED_ORIGINS='http://localhost:5173,http://127.0.0.1:5173' bash scripts/run_local_ollama.sh
   ```

4. Run the workspace:

   ```sh
   cd apps/web
   VITE_API_BASE_URL=http://127.0.0.1:8001 VITE_AGENT_API_BASE_URL=http://127.0.0.1:8000 npm run dev -- --host 127.0.0.1
   ```

For browser access, configure `CORS_ALLOWED_ORIGINS` with both supported Vite origins, `http://localhost:5173` and `http://127.0.0.1:5173`. CORS permits configured origins only and does not enable credentialed wildcard access. `/health` is process liveness; `/ready` additionally requires valid retrieval artifacts and the selected LLM provider (including the configured Ollama model) to be usable. Required deployment configuration names include `EMS_JWT_SECRET`, `EMS_API_BASE_URL`, `LLM_PROVIDER`, `LLM_API_KEY`, `LLM_MODEL`, and, if applicable, Qdrant configuration. Do not place secrets in Vite variables.

## Verification and limitations

Run the RAG regression suite with:

```sh
PYTHONPATH=backend .venv/bin/pytest backend/tests -q
```

The evaluation fixture is limited and is not a production-quality guarantee. OpenRouter is an external dependency. Local FAISS is not a distributed vector database, and live Qdrant operational validation remains pending. The confirmed Agent workflow uses a deliberately small, typed set of authorized EMS actions; it does not permit arbitrary tool execution.
