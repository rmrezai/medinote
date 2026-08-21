# Step 44 — Patient Identity and Wrong-Chart Protection

## Purpose
Prevent information from one patient or encounter from silently entering another patient's MCIF state or documentation.

## Identity rules
- Exact MRN matching is deterministic; similar/fuzzy MRNs are never treated as matches.
- DOB mismatch is a hard mismatch when both source and selected patient DOB are known.
- Name alone is insufficient proof of identity.
- A name-only matching source is marked `ambiguous` and requires physician source verification before analysis/document generation.
- An exact MRN or DOB mismatch is marked `mismatch` and quarantined.
- Exact identifier mismatch cannot be overridden by a click-through physician confirmation; the source must be removed/corrected.
- Sources with no asserted/extractable identifiers remain `not_asserted`; they do not create identity evidence by themselves.

## Hard-stop boundary
Before MCIF analysis, reconciliation, synthesis, Patient Overview, or downstream document generation, MediNote calls the encounter identity guard. Any `mismatch`, `ambiguous`, or explicitly blocked encounter prevents the workflow from proceeding.

## Source lifecycle
`matched` → allowed

`not_asserted` → allowed only as non-identity evidence within an otherwise selected encounter; does not prove identity

`ambiguous` → hard stop until physician verifies source or removes it

`physician_verified` → allowed, with audit trail

`mismatch` → quarantined hard stop; cannot be overridden; remove/correct source

## Physician verification
A physician may verify an ambiguous source after confirming it against the selected EHR patient banner/approved identity source. Verification records the user, timestamp, and whether a reason was documented. Raw PHI is not copied into audit metadata.

## Tenant isolation
Source-document resource paths are covered by the same organization-level middleware used for encounters, documents, medications, and safety flags. Cross-organization resources return 404 to avoid existence leakage.

## API
- `GET /api/v1/encounters/{encounter_id}/identity`
- `POST /api/v1/encounters/{encounter_id}/identity/verify`
- `POST /api/v1/sources/{source_id}/identity/verify`
- `DELETE /api/v1/sources/{source_id}` for quarantined/untrusted sources

`POST /api/v1/encounters/{encounter_id}/analyze` returns HTTP 409 while the identity hard stop is active.

## UI
The physician workspace now shows Patient Identity status and a visible HARD STOP when an ambiguous or mismatched source is present. Source import accepts optional source MRN, DOB, and patient name fields and also conservatively extracts common identity headers from pasted source text.

## Step 44 validation
- Duplicate patient names remain separate patient/encounter records.
- One-digit MRN difference is a mismatch, not a fuzzy match.
- DOB mismatch is a hard mismatch even when name/MRN otherwise match.
- Name-only source is ambiguous until physician verified.
- Exact identifier mismatch cannot be physician-overridden.
- Quarantined source blocks analysis.
- Removing the wrong source clears the hard stop.
- Source resources are included in tenant-isolation middleware.

Full automated regression suite: 92 passed.
Separate API smoke test: PASS.
