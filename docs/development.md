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

Before starting EMS, create an ignored local `apps/ems-api/.env` from the
example and set `JWT_SECRET` to a locally generated value of at least 32 bytes.
EMS rejects short values and never echoes them in validation errors. Do not use
the example placeholder or commit a real secret.
When the local RAG Agent integration is enabled, its ignored
`EMS_JWT_SECRET` must be set to the same local value so it can verify EMS
sessions; do not place either value in frontend configuration.

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

## Policy RAG capability

The workspace `/agent` route reuses the existing EMS session token and calls the standalone RAG service. Policy answers remain grounded in the policy index. The later Agent workflow can also prepare only its small, typed set of workforce actions; those actions require an explicit server-side confirmation and EMS remains the authorization authority.

Build a local index explicitly before starting RAG. Generated local artifacts
resolve under the ignored `data/runtime/` directory by default:

```sh
cd RAG_Chatbot
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

OpenRouter remains the normal configuration default. For local policy
generation, install and run Ollama, pull an appropriate local model, then use
the non-secret launcher rather than maintaining a long shell export block:

```sh
ollama pull qwen3:8b
ollama serve
# In another terminal, from RAG_Chatbot:
bash scripts/run_local_ollama.sh
```

The launcher selects Ollama, project-relative runtime artifacts, CPU
embeddings, local-files-only model loading, and macOS-safe OpenMP defaults
(`KMP_DUPLICATE_LIB_OK=TRUE`, `OMP_NUM_THREADS=1`, and
`MKL_NUM_THREADS=1`). Each is process-local and can be explicitly overridden.
The RAG service calls Ollama's non-streaming chat API with deterministic
temperature, JSON schema output, and thinking disabled. It never falls back
from Ollama to OpenRouter. `/health` is liveness; `/ready` fails closed when
the selected provider or retrieval artifacts are unavailable. Local model
performance and hardware compatibility vary by machine.

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

## Phase 6 chat

Use the Workspace Chat screen to search active employees, open direct or group
conversations, and send messages. Messages are persisted through the EMS REST
API; active members receive post-commit `message.created` WebSocket events and
non-senders receive recipient-private CHAT notifications. A participant's
`last_read_at` controls their own unread count only.

The local WebSocket endpoint is `/api/v1/chat/ws`. The browser first requests a
short-lived, single-use ticket from authenticated `POST /api/v1/chat/ws-ticket`
and passes that ticket only in the WebSocket subprotocol; the long-lived JWT is
never placed in the WebSocket URL. Redis stores only a hash of the opaque ticket
and atomically consumes it at connection time. Connections require an allowed
Origin, an active server-resolved employee, and the normal chat membership
checks. This keeps the credential out of normal URL access logs; EMS does not
log WebSocket protocol headers or ticket values. Redis is therefore required for
WebSocket ticket issuance and validation.
The connection manager is single-instance only; horizontally scaled event
delivery requires Redis Pub/Sub or equivalent. Chat is not E2EE and does not use
Gmail or Google Chat.

## Phase 7 built-in Calendar

Run the EMS migration before using Calendar:

```sh
cd apps/ems-api
PYTHONPATH=. .venv/bin/alembic upgrade head
```

The `/calendar` workspace view uses runtime browser dates for Today and month
navigation. It loads an authenticated date-range feed containing persisted
company `CalendarEvent` records plus authorized projections of approved leave.
Leave remains a `LeaveRequest`; it is not copied into `calendar_events`.
Employees see their own approved leave, direct Managers see a direct report's
approved leave, and ADMIN has no automatic private-leave access. Calendar event
controls are convenience UI only; EMS enforces JWT-derived identity and mutation
authorization. Google Calendar, Meet, and OAuth are not part of this phase.

## Local startup and recovery runbook

### Prerequisites and first-time setup

Install Docker Desktop with Compose, Python environments compatible with the
checked-in `.venv` dependencies, Node/npm, and Ollama. Pull the local model once:

```sh
ollama pull qwen3:8b
```

Create ignored local configuration files from `apps/ems-api/.env.example` and
`RAG_Chatbot/.env.example`. Generate the required local JWT values separately;
never put their values in documentation, frontend variables, or Git. Build the
policy index explicitly only when it is absent or stale, as described above.

### Normal daily startup

Use separate terminals, in this order:

```sh
cd infra
docker compose up -d postgres redis
docker compose ps
```

```sh
cd apps/ems-api
PYTHONPATH=. .venv/bin/alembic upgrade head
PYTHONPATH=. .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8001 --workers 1
```

If Ollama is not already listening on `127.0.0.1:11434`, start `ollama serve` in
another terminal. Do not start a second instance when it is already running.

```sh
cd RAG_Chatbot
CORS_ALLOWED_ORIGINS='http://localhost:5173,http://127.0.0.1:5173' bash scripts/run_local_ollama.sh
```

The launcher is self-contained: it sets its project-relative Python import and
runtime-artifact paths, selects local Ollama `qwen3:8b`, uses CPU/offline
embeddings, and enables the Redis pending-action store. It never falls back to a
cloud provider.

```sh
cd apps/web
npm run dev -- --host 127.0.0.1
```

The services are available at the following local URLs:

- Workspace: `http://127.0.0.1:5173/`
- EMS: `http://127.0.0.1:8001/health`
- Agent liveness: `http://127.0.0.1:8000/health`
- Agent readiness: `http://127.0.0.1:8000/ready`

The frontend defaults use `localhost` for API URLs, which is supported by the
configured CORS allowlists. When a local setup explicitly uses `127.0.0.1` API
variables, keep the same two origins in both EMS and Agent CORS configuration.

### Health checks, shutdown, and recovery

After startup, `docker compose ps` must show healthy PostgreSQL and Redis; EMS
`/health`, Agent `/health`, and Agent `/ready` must succeed. Readiness also
confirms the FAISS/BM25 artifacts, Ollama model, and Redis pending-action store.

Closing a frontend terminal only requires restarting the frontend. Closing EMS
only requires the EMS command above after PostgreSQL is healthy. Closing Agent
only requires the launcher command above; generated runtime artifacts remain on
disk. If Ollama is unavailable, Agent readiness fails closed. If Redis is
unavailable, secure WebSocket tickets and Agent write preparation fail closed;
they recover after Redis returns. If PostgreSQL is unavailable, EMS remains
unavailable until PostgreSQL returns.

For a normal infrastructure stop/start, preserve volumes and data:

```sh
cd infra
docker compose stop
docker compose start
```

Never use `docker compose down -v` as a normal recovery command: `-v` removes
the local database volume. Do not run `app.seed` on every start; it is a
bootstrap/recovery utility and routine seeding is intentionally non-destructive.
The development-only cleanup command is explicit and idempotent:

```sh
cd apps/ems-api
PYTHONPATH=. .venv/bin/python -m app.cleanup_development_data
```

It removes only its documented allowlisted development records; do not use it as
a general data-deletion tool.
