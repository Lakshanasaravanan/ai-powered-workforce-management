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
