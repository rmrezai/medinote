
## Step 27 - Pilot authentication and security controls

Step 27 adds the first pilot security boundary. It is designed for controlled evaluation, not as a claim of full HIPAA/security certification.

### Authentication

- First-run `POST /api/v1/auth/bootstrap` creates the initial organization administrator and disables itself once a user exists.
- `POST /api/v1/auth/login` uses PBKDF2-SHA256 password hashing with per-password random salt.
- Successful login returns an opaque 256-bit-style bearer session token; only its SHA-256 hash is stored server-side.
- Sessions expire after 12 hours and can be revoked with `POST /api/v1/auth/logout`.
- Five failed login attempts trigger a temporary 15-minute lockout.
- The user model is MFA-ready (`mfa_enabled`) but MFA challenge/verification is intentionally not implemented yet.

### Roles

Pilot roles are `attending`, `resident`, `app`, and `administrator`.

- Residents/APPs can participate in drafting/review workflows.
- Finalization is restricted server-side to `attending` and `administrator` roles.
- Administrators can create pilot users with `POST /api/v1/auth/users`.

### Tenant isolation

Authenticated users are bound to one organization. The security middleware checks organization ownership for encounter-, document-, medication-, and safety-flag resources. A cross-organization object request returns `404` rather than revealing whether the object exists.

Encounter creation is also server-validated against the authenticated user's organization; a client-supplied organization ID cannot be used to create an encounter in another tenant.

### Audit events

A dedicated `audit_events` table records consequential security/workflow events such as bootstrap, login, logout, user creation, encounter creation, chart-source import, and document finalization. Organization administrators can inspect the latest audit events with `GET /api/v1/auth/audit-events`.

Audit metadata must never contain raw chart text, names, MRNs, dates of birth, note bodies, or other PHI. The audit service intentionally accepts only small metadata fields needed to explain the event.

### Frontend

The physician UI now starts at a login screen. First deployment can use **First-time pilot setup** to create the initial administrator. The browser stores the opaque session token and adds it as a bearer token to API calls. Sign-out revokes the server session and removes the local token.

### Validation

The full regression suite passes with the test-only authentication bypass enabled. A separate authenticated smoke test verifies:

- unauthenticated protected API request -> `401`
- authenticated same-organization encounter access -> `200`
- deliberate cross-organization encounter access -> `404`
- normal credential login -> `200`

The test bypass is disabled by default and must never be enabled in a pilot or production deployment.
