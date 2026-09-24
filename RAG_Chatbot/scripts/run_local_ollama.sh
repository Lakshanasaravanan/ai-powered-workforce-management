#!/usr/bin/env bash
# Start the RAG service with a local Ollama provider and ignored local runtime
# artifacts.  All values are process-local; this script never reads or writes
# .env files and does not build an index.
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# The application package lives below backend/, not the RAG project root.
# Preserve a caller-supplied path while making this launcher self-contained.
export PYTHONPATH="$project_dir/backend${PYTHONPATH:+:$PYTHONPATH}"

export LLM_PROVIDER="${LLM_PROVIDER:-ollama}"
export OLLAMA_BASE_URL="${OLLAMA_BASE_URL:-http://127.0.0.1:11434}"
export OLLAMA_MODEL="${OLLAMA_MODEL:-qwen3:8b}"
export REDIS_ENABLED="${REDIS_ENABLED:-true}"
export REDIS_URL="${REDIS_URL:-redis://localhost:6379/0}"
export RAG_RUNTIME_VECTOR_STORE_DIR="${RAG_RUNTIME_VECTOR_STORE_DIR:-$project_dir/data/runtime/vectorstore}"
export RAG_RUNTIME_SPARSE_INDEX_PATH="${RAG_RUNTIME_SPARSE_INDEX_PATH:-$project_dir/data/runtime/sparse/bm25_corpus.json}"
export EMBEDDING_DEVICE="${EMBEDDING_DEVICE:-cpu}"
export EMBEDDING_LOCAL_FILES_ONLY="${EMBEDDING_LOCAL_FILES_ONLY:-true}"

# macOS/OpenMP stability defaults.  Callers can explicitly override them.
export KMP_DUPLICATE_LIB_OK="${KMP_DUPLICATE_LIB_OK:-TRUE}"
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"
export MKL_NUM_THREADS="${MKL_NUM_THREADS:-1}"

cd "$project_dir"
exec "$project_dir/.venv/bin/python" -m uvicorn app.main:app --host "${RAG_HOST:-127.0.0.1}" --port "${RAG_PORT:-8000}"
