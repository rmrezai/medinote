# Step 49 — Immutable Retention, External Anchoring, and Legal Hold

## Purpose
Step 49 extends the Step 48 tamper-evident audit chain with independently verifiable anchor artifacts, encrypted retention snapshots, and legal-hold controls.

## Controls implemented

### 1. External audit anchors
`POST /api/v1/retention/audit-anchors`

The service first verifies the organization audit chain. It then writes a WORM-style anchor artifact containing:
- audit event count;
- audit chain head SHA-256;
- previous anchor artifact SHA-256;
- anchor sequence;
- organization ID and timestamp.

The application filesystem implementation uses create-once (`O_EXCL`) read-only artifacts for development/pilot simulation. Production should map this storage abstraction to independently administered object-lock/WORM storage (for example, an approved cloud object-lock service) so a privileged MediNote database administrator cannot rewrite both systems.

`GET /api/v1/retention/audit-anchors/verify` recomputes each artifact hash and verifies the external anchor chain.

### 2. Encrypted retention snapshots
`POST /api/v1/retention/encounters/{encounter_id}/snapshot`

The forensic package is serialized and encrypted with AES-256-GCM. The encryption key is supplied only through `RETENTION_ENCRYPTION_KEY_HEX` and is not written into the application database. The encrypted artifact is then written create-once and its ciphertext SHA-256 stored in PostgreSQL.

`GET /api/v1/retention/snapshots/{snapshot_id}/verify` verifies ciphertext integrity without decryption. `include_decrypted_payload=true` is administrator-only and requires the external key.

### 3. Legal hold
`POST /api/v1/retention/legal-holds`

A hold can apply to one encounter or the whole organization. While an applicable hold is active:
- a retention snapshot receives no deletion eligibility date;
- retention status reports `legal_hold_active=true`;
- deletion eligibility is always false.

Releasing a hold requires an explicit reason and creates an audit event:
`POST /api/v1/retention/legal-holds/{hold_id}/release`.

Both placement and release remain in the append-only audit ledger.

### 4. Retention status
`GET /api/v1/retention/encounters/{encounter_id}/status`

Returns active holds, latest immutable snapshot, retention date, and whether the record is eligible for deletion under the current application policy.

Step 49 intentionally does **not** auto-delete clinical records merely because a date has elapsed. Destructive deletion must remain a separate institution-approved operation with policy, contractual, legal-hold, backup, and audit checks. The service computes eligibility; it does not silently purge.

## Production boundary
The included filesystem store is a test/pilot WORM simulation, not a claim of certified immutable storage. Production deployment should use:
- independently controlled object-lock/WORM storage;
- separate IAM credentials from the application database administrator;
- encryption keys in an approved secrets/KMS/HSM service;
- retention mode and duration matching institutional/legal requirements;
- periodic automated anchoring and independent verification;
- backup/object-lock policy aligned with legal hold.

## Security requirements
- `RETENTION_ENCRYPTION_KEY_HEX` must be 64 hexadecimal characters (32 bytes).
- Never commit the key to source control.
- Key rotation and recovery procedures must be documented before production PHI use.
- Forensic content-inclusive exports remain administrator-only and purpose-limited.

## Validation
Step 49 tests verify:
- valid external anchor creation;
- external artifact tamper detection;
- refusal to anchor an invalid internal audit chain;
- encrypted snapshot confidentiality/integrity;
- legal hold freezes retention eligibility;
- hold release restores normal policy behavior.
