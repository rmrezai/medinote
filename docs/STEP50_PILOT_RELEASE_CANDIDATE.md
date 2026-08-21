# MediNote Pilot Release Candidate v0.1 — Step 50

## Release decision
**READY FOR DE-IDENTIFIED PILOT.**

**CONTROLLED PHI PILOT: CONDITIONALLY READY ONLY AFTER institutional privacy/security/AI-governance approval, approved hosting and model/vendor data handling, required agreements/BAAs, MFA/identity policy, production TLS/secrets/key management, independently controlled immutable retention, penetration/security review, backup/restore verification, incident response, and local legal/compliance review.**

This designation is an engineering release decision, not HIPAA certification, regulatory clearance, or authorization for autonomous clinical care.

## Frozen clinical governance
Chart facts -> MCIF/Codex -> Audit Layer -> Physician -> Final Epic documentation. The chart owns facts; MediNote structures, drafts, reconciles and audits; the physician decides, orders and signs.

## Release verification
- Full regression suite: 113/113 passed using the test SQLite configuration.
- Frontend JavaScript syntax: PASS.
- Secret-pattern scan: no candidate embedded production secrets found by the release scan.
- Minimal SBOM and dependency/license inventory generated.
- Release manifest and SHA-256 checksums generated.

## Included safety milestones
Golden Case; text-only ingestion; chart torture testing; physician contradiction adjudication; patient-identity hard stops; stale-state/version protection; multi-user optimistic concurrency; failure recovery/idempotency; append-only tamper-evident audit; encrypted retention snapshots; external audit anchoring; legal hold.

## Known limitations / pre-PHI gates
1. No claim of HIPAA certification, SOC 2, FDA clearance, or clinical autonomy.
2. Production identity/MFA/SSO requirements remain customer/institution dependent.
3. Pilot filesystem WORM is a simulation; production retention must use independently administered immutable storage.
4. External retention encryption key management must use an approved secrets/KMS process.
5. Penetration testing and formal threat modeling remain required before production PHI deployment.
6. Vendor/model subprocessors, BAAs/data-use terms, retention/deletion, and institutional AI governance must be approved for the actual deployment.
7. EHR write-back is not authorized in this release; physician-reviewed Copy-to-Epic remains the intended pilot boundary.
8. Deterministic ingestion has validated scenarios but cannot guarantee extraction of every real-world chart format; unsupported/conflicting state must remain reviewable.
9. Automated tests and synthetic/de-identified validation do not substitute for prospective physician adjudication.
10. Dependency license metadata marked UNKNOWN/ambiguous in the inventory requires manual upstream verification before commercial distribution.

## Change control
Clinical behavior is frozen for RC v0.1. Any material clinical-rule, ingestion, model, audit, medication-state, or document-generation change requires a new version, regression run, and release manifest.
