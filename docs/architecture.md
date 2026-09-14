# InfoTech Workspace architecture

```text
React Workspace -> EMS API -> PostgreSQL / Redis
                -> Agentic RAG service (future) -> Qdrant / OpenRouter (future)
```

## Phase 2 identity and access boundary

The EMS API is the authority for identity and authorization. An access token is
issued only after an employee authenticates with `employee_code` and a password;
`company_email` is a distinct company identity and is not a login identifier.
The authenticated employee is always resolved from the JWT subject on the
server. No API endpoint accepts a frontend-supplied role or employee identity as
an authorization authority.

Roles (`ADMIN`, `MANAGER`, and `EMPLOYEE`) control backend authority. Job
designation is independent: for example, the `Team Lead` designation does not
automatically grant the `MANAGER` role. Frontend route and button visibility is
only a user-experience aid; backend dependency checks enforce ADMIN and MANAGER
authorization.

Employee and Manager development identities use
`employee_code@infotech.local`. The Admin seed identity remains a separate
administrative identity. These local addresses are placeholders: a later Admin
provisioning integration may create managed Google Workspace accounts, but EMS
must never store Google passwords. Employee and Manager account local-parts
should continue to use the employee code.

## Authentication lifecycle

New accounts activate through a one-time first-login flow:

```text
Employee ID + Temporary Password + New Password + Confirmation
        -> activate account -> invalidate temporary credential
        -> later login: Employee ID + own password
```

Passwords are encoded with Argon2id; plaintext credentials are never stored.
A successful activation clears the temporary credential. An inactive account
cannot log in, activate with a temporary credential, or use an already-issued
JWT. A rejected inactive first-login attempt leaves its onboarding state and
temporary credential unchanged. An Admin can reactivate an account.

The current React client keeps its access token in `sessionStorage` for the
browser session. This limits persistence but remains exposed to XSS. A future
production hardening phase should evaluate an HttpOnly cookie/session strategy
appropriate to the deployment.

## Reporting hierarchy

Employees and Managers may have a `manager_id`; managers can report to other
managers and a top-level manager can have no manager. Server-side validation
rejects self-management and all cyclic reporting relationships, while allowing
valid multi-level hierarchies. Employee code and company email are unique.

## Future agent privacy invariant

The future agent never writes the database directly: user -> agent -> typed EMS
API tool -> authorization and business validation -> database -> confirmed
result. ADMIN authority must not grant access to private employee chat content
merely because of the ADMIN role.
