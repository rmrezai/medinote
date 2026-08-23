# Inpatient Clinical Intelligence | MediNote

## What Is Inpatient Clinical Intelligence?

Inpatient clinical intelligence is the capacity to maintain a continuously reconciled, physician-reviewed picture of a patient's clinical state across an entire hospital admission — and to translate that state into accurate, safety-audited documentation without asking the physician to reconstruct it from scratch on every shift.

Traditional documentation tools draft prose. Inpatient clinical intelligence organizes the underlying facts first: what is known, when it was known, which source said it, whether it conflicts with another source, and whether it is still current.

## The MediNote Approach

MediNote is a physician-facing inpatient clinical intelligence and documentation system built around a structured clinical truth layer.

The permanent governance hierarchy is:

**Chart → MediNote / MCIF / Codex → Audit Layer → Physician → Final Epic documentation**

The chart owns the facts. MediNote organizes, extracts, reconciles, synthesizes, drafts, and audits. The physician retains authority over diagnosis, treatment, orders, medications, disposition, discharge, and signature.

---

## Core Clinical State — the MCIF Layer

The MediNote Clinical Intelligence Framework (MCIF) maintains a structured, provenance-tracked patient state across the entire admission. Each field is derived from chart evidence with explicit source attribution.

| Clinical domain | What MediNote tracks |
|---|---|
| Problems | Acuity-ranked active problems with evidence spans |
| Medications | Independent Home / Hospital / Discharge states |
| Labs & vitals | Current values with oxygen context and trajectory |
| Consultants | Recommendations and implementation status |
| Pending items | Outstanding studies, decisions, and orders |
| Disposition | Current snapshot with discharge intent |
| Contradictions | Unresolved conflicts between equal-time sources |
| Encounter trajectory | Multi-day clinical course |

---

## The Analyze → Reconcile → Synthesize Pipeline

### Analysis

MediNote extracts clinical facts from stored chart and source documents using deterministic extraction rules. Key safeguards:

- Explicit negation is not promoted into a diagnosis
- Uncertainty terms (rule out, possible, suspected) are preserved in structured form
- Medication domains remain separate; home medications are not silently carried forward
- Extracted medication states are not automatically marked physician-confirmed
- Consultant implementation status remains unclear until explicitly reconciled
- Source dates are not invented
- Ambiguous narrative is not guessed into structured fact

### Reconciliation

Temporal reconciliation marks current versus historical and superseded state:

- Oxygen and lab trajectories are reconciled across time
- Medication state is reconciled independently by domain (Home / Hospital / Discharge)
- Physician-confirmed discharge intent is preserved
- Contradiction records are created when equal-time evidence conflicts
- Timestamps are never invented

### Synthesis

Synthesis characterizes the trajectory of an already-documented problem but does not create a diagnosis from trend data alone. The physician reviews the structured state before it becomes the basis for any document.

---

## Five Physician-Facing Workflows

Every workflow consumes the validated MCIF state rather than raw chart text.

### H&P (History and Physical)

- Exact two-sentence HPI format with evidence linkage
- No invented normal physical exam
- Diagnostic uncertainty preserved
- Evidence-linked problem list with provenance

### Progress Note

- Grounded in current structured state, not copy-forward from yesterday
- Highlights state changes since last update
- Uncertainty terms preserved

### Discharge Summary

- Discharge medication reconciliation state drives discharge med list
- Completion blocked if high or critical safety findings are unresolved
- Physician-confirmed discharge intent required before finalization

### Medication Reconciliation

Medication reconciliation is state reconciliation across three independent domains:

| Physician-confirmed discharge states |
|---|
| Continue / Stop / Resume |
| Changed dose / Changed route / Changed frequency |
| Newly started / Inpatient only / Completed |
| Unclear / Requires decision |

Historical state rows are preserved for provenance. No domain is silently assumed to match another.

### Signout / Handoff

- Structured current state with pending items and disposition snapshot
- Contradiction flags surfaced for the receiving physician
- Attention count highlights unresolved issues

---

## Document Lifecycle and Physician Control

Every document passes through a shared review lifecycle:

1. **Section generation** — from validated MCIF state
2. **Accept / Edit / Regenerate** — physician controls each section
3. **Immutable generation provenance** — original generated text is preserved
4. **Physician edit history** — all edits recorded
5. **Document approval** — attending or resident approval
6. **Safety audit** — deterministic engine runs before finalization
7. **Finalization gate** — high/critical findings block finalization
8. **Copy-to-Epic** — final text copied; no direct chart write-back in RC v0.1

Finalization is restricted to attending physicians and administrators.

---

## Safety and Audit Engine

The deterministic audit engine checks for:

- Diagnostic certainty escalation (suspected → confirmed without evidence)
- Medication-state conflicts between domains
- Unsupported templated exam claims
- Unresolved contradictions
- Pending/final mismatches
- Procedure-state errors
- Stale objective values
- Unsupported discharge completion claims

The model is not permitted to silently self-certify its own output. Unresolved high or critical findings block finalization.

---

## Identity and Stale-State Protection

### Identity protection

- Exact MRN/DOB mismatch → hard-stop quarantine
- Name-only match → ambiguous until physician verified
- Wrong-chart sources cannot be silently merged
- Source resources remain tenant-isolated

### Stale-state protection

Documents are version-bound to MCIF encounter state. New chart input invalidates older drafts until they are refreshed, re-reviewed, re-audited, and re-approved.

---

## Integrity and Retention

- Organization-scoped SHA-256 audit hash chaining
- Mutation resistance at the application layer
- Tamper detection during chain verification
- Administrator forensic exports with PHI minimization
- External audit hash anchoring
- Encrypted retention snapshots (AES-256-GCM)
- WORM-style pilot retention simulation
- Encounter/organization legal holds
- Retention eligibility and verification endpoints

Production immutable retention requires independently administered storage and approved key-management infrastructure.

---

## Security Controls (Pilot Release)

- PBKDF2-SHA256 password hashing
- Opaque bearer sessions with stored token hashes
- 12-hour session expiry
- Temporary lockout after repeated failed login
- Tenant isolation
- Roles: attending, resident, APP, administrator
- Server-side finalization restricted to attending/administrator
- Audit events for all key workflow and security actions

---

## Validation Evidence (RC v0.1 / Step 50)

| Validation artifact | Result |
|---|---|
| Backend regression suite | 113 / 113 passed |
| Frontend JavaScript syntax | PASS |
| Release secret-pattern scan | No embedded production secrets found |
| SBOM and license inventory | Generated |
| Release manifest and SHA-256 checksums | Generated |

Validation case library includes synthetic/de-identified core cases, Golden Case, multi-day chart torture testing, contradiction adjudication, identity-guard, stale-state, concurrency, failure-recovery, audit-integrity, and immutable-retention tests.

Automated testing and synthetic validation do not substitute for prospective physician adjudication or regulatory review.

---

## Current Pilot Status

- Frozen clinical release: **Pilot Release Candidate v0.1 / Step 50**
- Pilot status: **READY FOR DE-IDENTIFIED PILOT**
- Pilot 001: synthetic/de-identified data only; up to 10 hospitalists; 30 days
- Controlled PHI pilot remains conditional on institutional privacy/security/AI-governance approval, approved hosting and model/vendor handling, required BAAs, MFA/identity policy, TLS/secrets/key management, independently controlled immutable retention, security review, backup/restore verification, incident response, and local legal/compliance review

---

## What MediNote Does Not Do

- Does not independently diagnose
- Does not issue orders or prescriptions
- Does not discharge or sign the medical record
- Does not write back to Epic or FHIR in RC v0.1
- Does not invent chart facts, timestamps, or normal exam findings
- Does not promote uncertainty into confirmed diagnosis
- Does not self-certify its own output

**The physician remains in control at every step.**
