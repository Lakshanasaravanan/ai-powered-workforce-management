# Agentic RAG service

This directory contains the standalone AI-assistant service for the Workforce Management Platform. It does not access the `SLAMS` database; future workforce integration will use authenticated REST clients.

## Phase 1

Phase 1 provides a FastAPI foundation, development JWT authentication, request-scoped structured logs, health endpoints, and a placeholder authenticated chat endpoint. RAG, vector databases, workforce tools, and the frontend are intentionally deferred.

## Local setup

```bash
cd RAG_Chatbot
python -m venv .venv
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

## Tests

```bash
cd RAG_Chatbot
PYTHONPATH=backend .venv/bin/pytest backend/tests -q
```
