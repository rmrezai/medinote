# MediNote Step 47 — Failure Recovery and Idempotency

## Objective
Prevent lost physician work, duplicate clinical actions, partial document finalization, and unsafe replay after network/service/database interruption.

## Server-side idempotency
High-risk mutating requests accept `Idempotency-Key` and persist a per-user/per-organization operation receipt containing request hash, endpoint, state, and completed response.

Covered in v0.1:
- H&P / Progress / Discharge / Signout generation
- document section save/edit
- section regeneration
- document approval
- document finalization
- discharge medication reconciliation decisions
- contradiction adjudication

A completed request retried with the same key and identical payload returns the stored outcome instead of executing again. The same key used with a different request is rejected.

If a process interruption leaves an operation `in_progress`, MediNote treats the outcome as uncertain and refuses blind replay. The user must refresh the target resource. Operation status is available at:

`GET /api/v1/operations/idempotency/{key}`

## Transaction safety
Clinical generation writes remain transactional. The Step 47 regression suite injects a simulated database commit failure and verifies rollback leaves no partially persisted document or sections.

## Client-side draft recovery
The physician web client stores current section textarea content in browser local storage while editing. A network failure does not force a document reload or erase the unsent physician draft. The local recovery draft is removed only after confirmed successful server persistence.

Mutating UI operations reuse a stable idempotency key across uncertain retries.

## Failure behavior
- Network failure before confirmed save: preserve local draft and operation key.
- Network failure after server committed: retry with same key returns cached result.
- Duplicate submission: no duplicate physician edit/clinical action.
- Service interruption with uncertain request: operation remains `in_progress`; blind replay blocked.
- Database commit failure: rollback; no partial generated document.
- Stale concurrent write: Step 46 optimistic concurrency still returns 409.
- Stale clinical state: Step 45 state-version safety gate still blocks finalization.
- Finalized document: remains immutable.

## Known boundary
This is an application-level recovery foundation, not a substitute for infrastructure-level high availability. Production deployment still requires database durability, managed backups, monitoring, restart policy, load-balancer/reverse-proxy behavior, and tested disaster recovery.
