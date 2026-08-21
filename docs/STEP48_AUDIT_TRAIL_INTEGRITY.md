# Step 48 — Audit-Trail Integrity & Medico-Legal Reconstruction

## Objective
Provide an append-only, tamper-evident clinical audit ledger that can reconstruct who did what, against which encounter/document state, while minimizing unnecessary PHI in routine audit exports.

## Hash-chain design
Each organization audit event records:
- monotonic sequence number;
- previous event SHA-256;
- SHA-256 of sanitized metadata;
- SHA-256 of the canonical event payload.

Application ORM updates/deletes of AuditEvent rows are rejected. Direct database tampering is detectable because chain verification recomputes every hash and validates sequence continuity.

## Captured lifecycle events
The ledger now records key events including patient/encounter access, source import and identity decisions, document generation, section edits/regeneration, approval, safety-audit execution, safety-flag resolution, contradiction adjudication, medication discharge-state confirmation, refresh, and finalization.

Raw note/source text is not placed in audit metadata. Clinical text mutations are represented by cryptographic fingerprints and object/version references.

## Forensic export
Administrator-only endpoints:
- `GET /api/v1/forensics/audit-chain/verify`
- `GET /api/v1/forensics/encounters/{encounter_id}/export`

Default export is PHI-minimized and includes source/document/section/edit hashes, model/generator/state versions, safety flags, actors/timestamps, and the full organization hash-chain required for independent integrity verification.

An explicit `?include_content=true` option includes source and document text for an authorized forensic review. It is intentionally opt-in.

## Important boundary
A hash chain makes retroactive alteration detectable; it does not replace protected database backups, access controls, legal-hold procedures, validated time sources, SIEM/WORM retention, or external notarization. Production deployments should consider anchoring periodic chain-head hashes in independent immutable storage.
