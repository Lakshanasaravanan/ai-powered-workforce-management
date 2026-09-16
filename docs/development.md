# InfoTech Workspace development guide

## Phase 2 local identity model

Normal EMS login uses an **Employee ID** (`employee_code`) and password. It does
not use `company_email` as the login identifier. For local development, Employee
and Manager company emails follow `employee_code@infotech.local`; the Admin is
a separate administrative identity.

Roles and designations are deliberately different. `ADMIN`, `MANAGER`, and
`EMPLOYEE` are authorization roles enforced by the API. A designation such as
Team Lead or Senior Engineer is a job attribute and does not grant a role.

## First login

Use the `/first-login` screen with:

1. Employee ID
2. Temporary Password
3. New Password
4. Confirm New Password

On success, the account is activated and the one-time temporary credential is
invalidated. Subsequent login uses Employee ID and the employee's own password.
Inactive accounts cannot complete this flow; a rejected inactive request does
not consume or replace the temporary credential.

Passwords are stored only as Argon2id encoded hashes. Plaintext passwords and
Google Workspace passwords are never stored by EMS.

## Authorization and account status

JWT-derived identity is authoritative. Backend dependencies enforce ADMIN and
MANAGER authorization; hiding routes or buttons in the frontend is not a
security boundary. Inactive users cannot log in, activate a first-login account,
or access protected endpoints with an existing token. An Admin may reactivate an
account.

Reporting structures support managers reporting to other managers and a
top-level manager with `manager_id = null`. The backend rejects self-management
and cyclic reporting chains.

## Running locally

Start the new InfoTech PostgreSQL and Redis services from the repository root:

```sh
docker compose -f infra/compose.yaml up -d
```

Prepare the EMS database and local development identities:

```sh
cd apps/ems-api
PYTHONPATH=. .venv/bin/alembic upgrade head
PYTHONPATH=. .venv/bin/python -m app.seed
PYTHONPATH=. .venv/bin/uvicorn app.main:app --port 8001
```

Run the web workspace in another terminal:

```sh
cd apps/web
npm install
npm run dev
```

The React client currently stores the access token in `sessionStorage`. This is
not a complete defense against XSS; a production deployment should move toward
an appropriate HttpOnly cookie/session design.

Google Workspace provisioning is intentionally not implemented in Phase 2. A
future Admin workflow may provision managed accounts, retaining the employee
code local-part convention for Employee and Manager identities. EMS must never
retain Google passwords.

## Privacy invariant for future chat work

Administrative role membership alone must never grant access to private employee
chat content.

## Leave management and inbox

The Leave page uses the EMS API directly. Casual and Emergency leave require a direct Manager decision. Day Off is a half-day request and requires Morning or Afternoon plus a direct Manager decision. Medical/Sick leave is immediately approved, has `approval_required=false`, has no Manager approver, and uses the `AUTOMATIC_POLICY` decision source. The direct Manager receives an awareness notification for Medical leave, not an approval task.

Decisions are terminal: only pending approval-required requests can transition to Approved or Rejected. ADMIN is not an approval authority. A Manager cannot decide their own request or bypass another Manager in the reporting chain; a Manager can decide another Manager's leave only when they are that person's direct Manager.

The inbox is recipient-private and supports `LEAVE`, `CHAT`, `CALENDAR`, and `SYSTEM` categories. Only Leave events are currently emitted. Use the Inbox to view notifications, see the unread count, mark an item read, or mark all of the current user's items read. ADMIN and Managers cannot inspect another employee's inbox. Leave creation plus its notification, and Manager decision plus its notification, are each committed as one transaction. The pending-state decision uses a conditional atomic transition.

The frontend provides My Leave, Apply Leave, Manager Team Leave, direct-manager Approve/Reject controls, a real Inbox, and its unread badge. Browser role checks are presentation-only; all authorization remains server-side.

### Unresolved leave policy

Do not present balances or quotas to users. Leave accrual, carry-forward, annual quota, monthly reset, half-year reset, and balance enforcement are not implemented because the entitlement policy has not yet been finalized.

## Phase 4 policy assistant

The workspace `/agent` route is a Company Policy Assistant. It reuses the existing EMS session token and calls the standalone RAG service; it cannot apply leave, approve leave, regularize attendance, or modify employee data.

Build a local index explicitly before starting RAG. To avoid replacing historical generated artifacts, use an ignored runtime directory:

```sh
cd RAG_Chatbot
export RAG_RUNTIME_VECTOR_STORE_DIR=data/runtime/vectorstore
export RAG_RUNTIME_SPARSE_INDEX_PATH=data/runtime/sparse/bm25_corpus.json
export EMBEDDING_LOCAL_FILES_ONLY=true
export EMBEDDING_DEVICE=cpu
export EMBEDDING_CACHE_DIR=/path/to/provisioned/huggingface/hub
PYTHONPATH=backend .venv/bin/python -m app.rag.ingestion build
PYTHONPATH=backend .venv/bin/uvicorn app.main:app --port 8000
```

The manifest validates PDF hashes, BGE model/dimension, chunk settings, FAISS records, and BM25 consistency. Do not commit generated indexes, model caches, or local paths. A stale index makes `/ready` and policy requests fail safely until an operator performs the explicit build.

Set the non-secret browser location with `VITE_AGENT_API_BASE_URL=http://localhost:8000`. Set `CORS_ALLOWED_ORIGINS` on RAG to the web origin (the local default is `http://localhost:5173`). Deployment-side RAG configuration includes `EMS_JWT_SECRET`, `EMS_API_BASE_URL`, `LLM_PROVIDER`, `LLM_API_KEY`, and `LLM_MODEL`; never put their values in frontend variables or documentation.

Dense BGE/FAISS is the default. Qdrant is a production-oriented option that validates an existing compatible collection. Hybrid and reranking remain off, and no score threshold is enabled because evidence calibration did not show a safe separating threshold. The server validates model-supplied evidence IDs before returning citations.

### Local Ollama generation

OpenRouter remains the default provider. To keep policy context local for development, install and run Ollama, pull an appropriate local model, then select it through environment configuration (do not commit local values):

```sh
export LLM_PROVIDER=ollama
export OLLAMA_BASE_URL=http://localhost:11434
export OLLAMA_MODEL=qwen3:8b
```

The RAG service calls Ollama's non-streaming chat API with deterministic temperature, JSON schema output, and thinking disabled. It never falls back from Ollama to OpenRouter. If Ollama or the configured model is unavailable, readiness reports it and policy requests fail safely. Local model performance and hardware compatibility vary by machine.

## Phase 5 confirmed Agent actions

The authenticated Agent retains grounded policy RAG and adds deterministic
intent routing, read-only EMS tools, and a small typed action set: apply leave,
approve a direct report's leave, and reject a direct report's leave. Pending
team decisions are represented by opaque `LR-*` references. The UI presents an
action proposal card; Confirm and Cancel use the server-issued action ID and do
not reconstruct action arguments in the browser.

Confirmation uses server-stored immutable arguments and an actor/conversation
binding. Redis manages the pending-action lifecycle, while EMS persists the
final idempotency, audit, notification, and business-state effects. EMS remains
the RBAC and business-rule authority: neither an Employee nor an Admin can make
a Manager decision. Medical leave remains automatically approved according to
its existing policy semantics.

The relevant deployment-side variables are `EMS_API_BASE_URL`,
`EMS_JWT_SECRET`, `REDIS_ENABLED`, and `REDIS_URL`. Keep their values in local
or deployment configuration only; do not expose them to the browser or commit
them.

Live Phase 5 verification completed approve and reject actions and verified
their authoritative persisted effects. A later live replay was unavailable
because the original ephemeral Redis pending-action records had expired or were
no longer present locally. Replay, idempotency, concurrency, and lost-response
recovery remain covered by automated Phase 5 tests; this does not claim that a
later live replay passed.
