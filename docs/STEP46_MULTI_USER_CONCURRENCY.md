# Step 46 — Multi-User / Concurrent Physician Protection

## Purpose
Prevent a stale browser/session from silently overwriting newer physician work when multiple clinicians are using the same encounter.

## Controls implemented

### 1. Optimistic concurrency
`ClinicalDocument` and `DocumentSection` now carry `edit_version` counters.

Section edits/regeneration may submit `expected_section_version`; document approval/finalization may submit `expected_document_version`.

If the stored version no longer matches the version the client loaded, the API rejects the write with HTTP 409 and requires refresh.

This permits clinicians to work on different sections while preventing lost updates to the same section.

### 2. Medication reconciliation concurrency
Med Rec decisions send the discharge-state ID that was current when the physician opened the workspace.

If another clinician has since confirmed a newer discharge state, the stale decision is rejected with HTTP 409. The newer confirmed state is preserved.

### 3. Contradiction adjudication concurrency
Contradictions carry a revision number. Adjudication may send `expected_revision`.

A stale contradiction screen cannot adjudicate over a newer revision.

### 4. Active editor leases
MediNote now supports short-lived edit leases for document, medication, contradiction, and encounter resources.

A lease is advisory: it tells a second clinician that another user is actively editing. Safety does not depend on the lease; optimistic concurrency remains the hard protection against lost updates.

Endpoints:
- `POST /api/v1/edit-leases/{resource_type}/{resource_id}`
- `DELETE /api/v1/edit-leases/{resource_type}/{resource_id}`

Default lease duration: 5 minutes, renewable.

### 5. Role separation
Residents and APPs may draft/review/edit allowed documentation, but physician-level approval/finalization remains restricted to attending/administrator roles.

The following consequential actions require attending/administrator role:
- document approval;
- document finalization;
- discharge medication-state confirmation;
- contradiction adjudication.

This is a pilot authorization model and should later become organization-configurable.

## Conflict behavior
Example:
1. Resident and attending both load Section v1.
2. Resident saves an edit, creating Section v2.
3. Attending attempts to save the old v1 screen.
4. Server returns HTTP 409: section changed; refresh required.
5. Resident's newer content remains intact.

The same pattern applies to document approval/finalization, Med Rec decisions, and contradiction adjudications.

## UI behavior
The physician web app now:
- sends section/document versions with write requests;
- sends the current Med Rec state ID with medication decisions;
- sends contradiction revision with adjudication;
- obtains an advisory edit lease when opening/reloading a document;
- displays the active editor when another clinician holds the lease;
- converts HTTP 409 responses into a clinician-facing concurrent-edit/refresh prompt.

## Validation
Step 46 adds simultaneous-session tests covering:
- stale section overwrite rejection;
- stale document approval rejection;
- stale Med Rec decision rejection;
- active-editor lease warning;
- resident vs attending role enforcement;
- stale contradiction revision rejection.

Full regression result: 100/100 tests passed.
Frontend JavaScript syntax validation: PASS.

## Governance
Concurrency protection never chooses the clinical answer. It only prevents an older session from silently replacing newer physician work. When clinical disagreement exists, the explicit contradiction/adjudication workflow remains authoritative.
