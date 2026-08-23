# MEDAI Repository Knowledge Layer

## Purpose

This file gives MEDAI a concise, repository-grounded map of the current MediNote implementation so product/engineering answers can be anchored to what exists in `rmrezai/medinote` rather than to older project narrative or assumptions.

This file is **not** a replacement for the MediNote Unified Master Instruction and does **not** change frozen clinical behavior. It is a product/engineering knowledge layer only.

## Current release state

- Repository: `rmrezai/medinote`
- Default branch: `main`
- Current frozen clinical release: **Pilot Release Candidate v0.1 / Step 50**
- Pilot status: **READY FOR DE-IDENTIFIED PILOT**
- Controlled PHI pilot remains conditional on institutional privacy/security/AI-governance approval, approved hosting and model/vendor handling, required agreements/BAAs, MFA/identity policy, TLS/secrets/key management, independently controlled immutable retention, security review, backup/restore verification, incident response, and local legal/compliance review.
- Pilot 001 / Step 51 is synthetic/de-identified only.

## Core architecture

MediNote is a physician-facing inpatient clinical intelligence and documentation system built around a structured clinical truth layer.

Permanent governance hierarchy:

**Chart -> MediNote/MCIF/Codex -> Audit Layer -> Physician -> Final Epic documentation**

The chart owns facts. MediNote organizes, extracts, reconciles, synthesizes, drafts, and audits. The physician retains authority over diagnosis, treatment, orders, medications, disposition, discharge, and signature.

## MCIF clinical state

The repository implements a structured MCIF data layer with provenance and state separation for:

- clinical facts and evidence spans
- acuity-ranked problems and problem-evidence links
- medications with independent Home / Hospital / Discharge states
- labs and vital signs, including oxygen context
- consultant recommendations
- pending items
- disposition snapshots
- contradictions
- encounter trajectories

The encounter state/overview layer is the shared structured truth source consumed by downstream documentation and safety workflows.

## Analyze -> reconcile -> synthesize pipeline

The analysis pipeline uses deterministic extraction from stored chart/source documents and preserves provenance.

Key safeguards:

- explicit negation is not promoted into a diagnosis
- uncertainty terms are preserved
- medication domains remain separate
- extracted medication states are not automatically physician-confirmed
- consultant implementation status remains unclear until reconciled
- source dates are not invented
- ambiguous narrative is not guessed into structured fact

Temporal reconciliation then:

- marks current versus historical/superseded state
- reconciles oxygen and lab trajectories
- reconciles medication state independently by domain
- preserves physician-confirmed discharge intent
- creates contradiction records when equal-time evidence conflicts
- never invents timestamps

Synthesis may characterize trajectory of an already documented problem but does not create a diagnosis from trend data alone.

## Patient Overview

The Patient Overview exposes the shared physician-facing clinical state, including:

- encounter/patient header
- current clinical picture
- active problems with evidence provenance
- current labs and descriptive trajectories
- Home/Hospital/Discharge medication states
- consultants
- pending items
- disposition
- unresolved contradictions
- attention counts

It is deliberately conservative and does not create new diagnoses or causality.

## Clinical document workflows

Implemented persisted document workflows include:

- H&P
- Progress Note
- Discharge
- Medication Reconciliation
- Signout / Handoff

Document generation consumes validated structured state rather than raw chart text.

Shared review lifecycle includes:

- section generation
- Accept
- Edit
- Regenerate
- immutable original-generation provenance
- physician edit history
- document approval
- safety audit
- finalization gate
- Copy-to-Epic final text

## HOOP-compatible constraints reflected in implementation

Current document-generation behavior includes core MediNote constraints such as:

- exact two-sentence HPI for supported H&P/progress workflows
- preservation of diagnostic uncertainty
- evidence-linked problems
- no invented normal physical exam
- medication-state reconciliation rather than list copying
- physician review placeholders where structured evidence is inadequate

The full HOOP command contract remains governed by the MediNote Unified Master Instruction, not by this repository summary.

## Safety and audit layer

The deterministic audit engine checks for issues including:

- diagnostic certainty escalation
- medication-state conflicts
- unsupported templated exam claims
- unresolved contradictions
- pending/final mismatches
- procedure-state errors
- stale objective values
- unsupported discharge completion claims

Unresolved high/critical findings block finalization.

The model is not allowed to silently self-certify its own output.

## Medication reconciliation

Medication reconciliation is implemented as state reconciliation across Home, Hospital, and Discharge domains.

Supported physician-confirmed discharge states include:

- continue
- stop
- resume
- changed_dose
- changed_route
- changed_frequency
- newly_started
- inpatient_only
- completed
- unclear
- requires_decision

Historical state rows are preserved for provenance.

## Identity protection

Step 44 adds patient/source identity guards before analysis and document generation.

Important behavior:

- exact MRN/DOB mismatch -> quarantine hard stop
- name-only match -> ambiguous until physician verified
- wrong-chart sources cannot be silently merged
- source resources remain tenant-isolated

## Stale-state protection

Documents are version-bound to MCIF encounter state.

New chart input invalidates older drafts until they are refreshed, re-reviewed, re-audited, and re-approved.

## Multi-user concurrency

The repository includes optimistic concurrency protections for:

- document sections
- documents
- medication reconciliation state
- contradiction revisions
- active editor leases
- attending-versus-resident approval separation

## Failure recovery and idempotency

High-risk clinical mutations support idempotent handling and uncertain-outcome recovery patterns.

The frontend preserves unsent draft content, and transaction rollback behavior is covered by tests.

## Audit integrity and retention

The repository includes:

- organization-scoped SHA-256 audit hash chaining
- mutation resistance at the application layer
- tamper detection during chain verification
- administrator forensic exports with PHI minimization
- external audit hash anchoring
- encrypted retention snapshots using AES-256-GCM
- WORM-style pilot retention simulation
- encounter/organization legal holds
- retention eligibility and verification endpoints

Production immutable retention still requires independently administered storage and approved key-management infrastructure.

## Security and authentication

Pilot security controls include:

- PBKDF2-SHA256 password hashing
- opaque bearer sessions with stored token hashes
- 12-hour session expiry
- temporary lockout after repeated failed login
- tenant isolation
- roles: attending, resident, APP, administrator
- server-side finalization restriction to attending/administrator
- audit events for key workflow/security actions

MFA readiness exists in the model, but full MFA challenge/verification is not implemented in the pilot release.

## Frontend

The physician-facing frontend supports:

- login and first-time pilot setup
- encounter roster
- patient creation
- chart/source paste
- MCIF analysis
- Patient Overview
- H&P / Progress / Discharge / Med Rec / Signout navigation
- section Accept/Edit/Regenerate
- approval
- safety review
- finalization
- Copy-to-Epic
- physician-confirmed discharge medication decisions

The interface remains a pilot UI; direct Epic/FHIR write-back is not authorized in RC v0.1.

## Validation and release evidence

The release candidate documents:

- full regression suite: **113/113 passed**
- frontend JavaScript syntax: PASS
- release secret-pattern scan: no candidate embedded production secrets found
- SBOM and dependency/license inventory generated
- release manifest and SHA-256 checksums generated

Validation assets include:

- synthetic/de-identified core case library
- controlled physician simulation study
- Golden Case
- text-only ingestion validation
- multi-day chart torture testing
- contradiction adjudication tests
- identity-guard tests
- stale-state tests
- concurrency tests
- failure-recovery tests
- audit-integrity tests
- immutable-retention tests

Automated testing and synthetic validation do not substitute for prospective physician adjudication or regulatory review.

## Pilot 001

Pilot 001 is the first real-user usability/engineering evaluation package around the frozen RC.

It includes:

- master protocol
- facilitator guide
- observer rubric
- physician feedback form
- issue capture template
- readiness checklist
- Day-1 review template
- Day-7 go/no-go template

Pilot 001 permits synthetic/de-identified data only.

## Deployment boundary

The repository contains Docker-based pilot deployment scaffolding, including reverse proxy/TLS configuration, backup/restore scripts, preflight checks, readiness checks, and PHI-safe logging guidance.

This is an engineering deployment scaffold, not proof of HIPAA compliance or production authorization.

## MEDAI product/engineering source precedence

When MEDAI answers repository/product questions, use this order:

1. current repository code/config/tests
2. current release and pilot documentation
3. current GPT integration documentation
4. older project narrative
5. roadmap/proposed work

Never present roadmap or proposed functionality as implemented.

## Clinical source precedence

For patient-specific clinical work, this repository knowledge layer does not replace the clinical hierarchy. The authoritative hierarchy remains the MediNote Unified Master Instruction and current chart evidence.

## Change-control rule

Step 50 clinical behavior is frozen. Any material clinical-rule, ingestion, model, audit, medication-state, or document-generation change requires a new version, regression run, and release manifest. Documentation, GPT integration, infrastructure, deployment, and other non-clinical changes may proceed while preserving that boundary.
