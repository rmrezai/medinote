# MediNote v0.1

Initial runnable backend scaffold for the MediNote hospitalist MVP.

## Included
- FastAPI API
- PostgreSQL database
- Organization/User/Patient/Encounter/SourceDocument models
- Create/read encounter endpoints
- Add/list source document endpoints
- SHA-256 duplicate source detection
- Docker Compose local stack

## Run
```bash
docker compose up --build
```

Then open API docs at `http://localhost:8000/docs`.

## Current endpoints
- `GET /api/v1/health`
- `POST /api/v1/encounters`
- `GET /api/v1/encounters/{encounter_id}`
- `POST /api/v1/encounters/{encounter_id}/sources`
- `GET /api/v1/encounters/{encounter_id}/sources`

## Not yet implemented
Authentication, MCIF extraction, clinical facts, medications, problems, audit engine, document generation, frontend, and production PHI controls.

## Step 14 - MCIF clinical data layer
Added structured persistence and APIs for:
- Clinical facts with provenance/evidence spans
- Acuity-ranked clinical problems and problem-evidence links
- Medications and independent Home/Hospital/Discharge states
- Labs and vital signs (including oxygen context)
- Consultant recommendations
- Pending items
- Disposition snapshots
- First-class contradictions
- Aggregated `GET /api/v1/encounters/{encounter_id}/state` endpoint

### New endpoints
- `POST/GET /api/v1/encounters/{encounter_id}/facts`
- `POST/GET /api/v1/encounters/{encounter_id}/problems`
- `POST /api/v1/problems/{problem_id}/evidence`
- `POST /api/v1/encounters/{encounter_id}/medications`
- `POST /api/v1/medications/{medication_id}/states`
- `POST /api/v1/encounters/{encounter_id}/labs`
- `POST /api/v1/encounters/{encounter_id}/vitals`
- `POST /api/v1/encounters/{encounter_id}/consultants`
- `POST /api/v1/encounters/{encounter_id}/pending-items`
- `POST /api/v1/encounters/{encounter_id}/disposition`
- `POST /api/v1/encounters/{encounter_id}/contradictions`
- `GET /api/v1/encounters/{encounter_id}/state`

The state endpoint is the shared clinical truth layer that future H&P, Progress Note, Discharge, Med Rec, Signout, and Audit modules will consume.

## Step 15 - MCIF Analyze Pipeline

The MVP now includes `POST /api/v1/encounters/{encounter_id}/analyze`.

Current flow:

1. Read stored `source_documents` for the encounter.
2. Classify source authority by document type.
3. Conservatively extract high-confidence candidate data from chart text.
4. Preserve evidence spans and source provenance on clinical facts.
5. Populate MCIF tables for facts, labs, oxygen/vitals, problems, medications/states, consultant recommendations, and pending items.
6. Avoid silently increasing diagnostic certainty or marking AI-derived medication states as physician-confirmed.
7. Re-running analysis is idempotent for the same extracted source spans/states where implemented.

Step 15 intentionally uses deterministic extraction only. Ambiguous narrative remains unstructured rather than guessed. A later provider-backed extraction adapter can add broader clinical-language coverage while retaining the same validation and persistence boundary.

### Example

```bash
curl -X POST http://localhost:8000/api/v1/encounters/<encounter-id>/analyze
```

Then inspect the shared state:

```bash
curl http://localhost:8000/api/v1/encounters/<encounter-id>/state
```

### Safety boundaries in Step 15

- Explicit negation is not promoted into a diagnosis for supported patterns.
- Diagnostic uncertainty terms such as `possible`, `suspected`, `probable`, and `concern for` are preserved.
- Home/hospital/discharge medication domains remain separate.
- Extracted medication states are never physician-confirmed automatically.
- Consultant recommendations are stored with implementation status `unclear` until reconciled.
- Source dates are not invented when absent.

## Step 16 - Temporal reconciliation and contradictions

`POST /api/v1/encounters/{encounter_id}/analyze` now automatically runs a reconciliation pass after deterministic extraction. A reconciliation-only endpoint is also available at `POST /api/v1/encounters/{encounter_id}/reconcile`.

The Step 16 engine:

- marks one fact representation current and preserves older facts as historical/superseded,
- treats oxygen flow and room-air/device statements as one temporal support domain,
- builds descriptive lab trajectories (`rising`, `falling`, `stable`) without inferring diagnoses,
- builds oxygen-support trajectories (`increasing_support`, `decreasing_support`, `stable`),
- reconciles medication states independently within Home/Hospital/Discharge domains,
- preserves physician-confirmed discharge intent separately from inpatient status,
- creates contradiction records for incompatible equal-time facts or medication states rather than silently choosing a clinical conclusion,
- never invents timestamps when source time is unavailable.

`GET /api/v1/encounters/{encounter_id}/state` now includes `trajectories`.

## Step 17 - Problem / Clinical Synthesis Engine

Step 17 adds a conservative synthesis stage after temporal reconciliation.

- `POST /api/v1/encounters/{encounter_id}/synthesize`
- `/analyze` now runs extraction -> reconciliation -> synthesis.
- Existing documented AKI can be labeled improving/worsening/stable from creatinine direction.
- Existing documented acute hypoxemic respiratory failure can be labeled improving/worsening/stable from oxygen-support direction.
- Trends never create diagnoses on their own.
- Diagnostic certainty is never promoted by the synthesis engine.
- Problems receive a deterministic default synthesis priority (`acuity_rank`) for UI ordering; this is not physician approval.
- Objective current facts can be linked to problems through `problem_evidence` and are returned with encounter state.

The enabled v0.1 problem-to-trajectory mappings are intentionally narrow. More nuanced clinical synthesis should be introduced only with explicit validation and physician-review safeguards.

## Step 18 - Patient Overview contract

`GET /api/v1/encounters/{encounter_id}/overview` returns the physician-facing shared MCIF state for the dashboard. It includes encounter/patient header data, a deterministic current clinical picture, acuity-ranked active problems with evidence provenance, latest lab values with descriptive trajectories, Home/Hospital/Discharge medication states, consultant recommendations, pending items, latest disposition state, unresolved contradictions, and attention counts.

The current clinical picture is deliberately conservative: it summarizes only established structured problems and review counts. It does not generate new diagnoses or clinical causality.

## Step 19 - Progress Note generator

MediNote now includes the first persisted document-generation workflow built on validated MCIF state rather than raw source text.

### Endpoints

- `POST /api/v1/encounters/{encounter_id}/documents/progress`
  - variants: `standard`, `daily`, `short`, `mini`, `complex`, `interval`
- `GET /api/v1/documents/{document_id}/progress`
- `PATCH /api/v1/documents/{document_id}/sections/{section_id}`
  - actions: `edit`, `accept`

### Safety behavior

- The generator consumes the Patient Overview / structured MCIF state, not raw chart text.
- Each assessment/problem section retains the originating problem ID and supporting fact IDs.
- Diagnostic certainty and current problem status are preserved.
- Problems without structured evidence are explicitly marked for physician review.
- Unresolved contradictions and unresolved medication decisions mark the draft as review-required.
- No medication action is inferred from an unresolved medication state.
- The interval HPI is two sentences and summarizes only established structured state and review needs.

### Persistence

New tables:

- `clinical_documents`
- `document_sections`

This provides the foundation for section-level Accept / Edit / Regenerate, later audit gating, physician edit history, and final Copy-to-Epic output.

## Step 20 - Section regeneration, physician edit history, and document approval

Step 20 completes the first document review loop for Progress Notes.

### New endpoints

- `POST /api/v1/documents/{document_id}/sections/{section_id}/regenerate`
- `POST /api/v1/documents/{document_id}/approve`
- `GET /api/v1/documents/{document_id}/edits`

### Provenance and review behavior

- The first generated section text is immutable provenance and is never overwritten.
- A regeneration creates a new `section_revisions` record and becomes the current generated draft.
- Regeneration resets that section to `pending` and clears prior physician approval/content so it must be reviewed again.
- Free-text regeneration instructions are stored for audit/provenance in v0.1; deterministic regeneration refreshes from the latest MCIF state. Semantic instruction-following will belong to the later model-provider adapter.
- Every physician `edit`, `accept`, and `regenerate` event is retained in `physician_edits` with the original generated text, active generated text, prior physician text, final physician text, actor (when supplied), and timestamp.
- A document cannot enter `approved` state until every section is either `accepted` or `edited`.
- Once a document is approved/finalized, section mutation is blocked until a future explicit reopen workflow is implemented.

### New tables

- `section_revisions`
- `physician_edits`

`clinical_documents` and `document_sections` now also store approval provenance/timestamps and section regeneration count.

## Step 21 - Safety/Audit Engine v0.1

Added deterministic document auditing against MCIF state. The audit checks diagnostic certainty escalation, medication-state conflicts, unsupported templated exam claims, unresolved encounter contradictions, pending/final mismatches, procedure-state errors, and stale objective values. Safety findings persist as `SafetyFlag` records and can be reviewed/resolved. Finalization now requires physician approval and automatically re-audits the approved document; unresolved high/critical findings block finalization.

Endpoints:
- `POST /api/v1/documents/{document_id}/audit`
- `GET /api/v1/documents/{document_id}/safety-flags`
- `POST /api/v1/safety-flags/{flag_id}/resolve`
- `POST /api/v1/documents/{document_id}/finalize`

The v0.1 audit engine is intentionally deterministic. Semantic claim auditing will be added as a separate layer rather than allowing the language model to silently self-certify its own output.

## Step 22 - H&P generator

MediNote now includes a persisted H&P workflow built on the same validated MCIF state, section review/history, and safety-audit infrastructure used by Progress Notes.

### Endpoints
- `POST /api/v1/encounters/{encounter_id}/documents/hp`
- `GET /api/v1/documents/{document_id}/hp`

### Variants
- `standard`
- `admission`
- `short`
- `complex`
- `updated`
- `consult_style`

### H&P safety behavior
- The core HPI is exactly two sentences and is generated only from established structured state/review needs.
- Diagnostic uncertainty is preserved in both HPI and Assessment/Plan.
- Problems retain evidence links and provenance.
- No default normal physical exam is invented; absent structured exam data produces an explicit physician-review placeholder.
- Medication reconciliation reports current structured states without converting unresolved states into orders.
- H&P sections use the existing Accept/Edit/Regenerate/Approve workflow, immutable original-generation provenance, edit history, and Step 21 audit/finalization gate.

## Step 23 - Discharge module

The MVP now includes a persisted Discharge workflow built from the same validated MCIF state and document-review infrastructure as H&P and Progress Notes.

Endpoints:

- `POST /api/v1/encounters/{encounter_id}/documents/discharge`
- `GET /api/v1/documents/{document_id}/discharge`

Supported variants: `summary`, `short`, `clinical_course`, `med_reconciliation`, `avs`, and `addendum`.

The discharge generator is diagnosis-organized, preserves diagnostic uncertainty and problem evidence, exposes Home/Hospital/Discharge medication transitions, lists pending items without inventing follow-up ownership, and carries disposition forward only when documented. It shares Accept/Edit/Regenerate/Approve/Audit/Finalize with the other reviewable clinical documents.

Discharge-specific audit rules flag unsupported claims that follow-up, education, prescriptions, transportation, or home oxygen were completed/arranged when no verified structured completion state exists, and flag missing structured final destination.

## Step 24 - Dedicated Medication Reconciliation API

Step 24 adds a physician-facing Med Rec workspace over the existing MCIF medication state model.

Endpoints:

- `GET /api/v1/encounters/{encounter_id}/med-rec`
- `POST /api/v1/medications/{medication_id}/confirm-discharge-state`

The workspace presents independent Home, Hospital, and Discharge states, identifies unresolved medications, highlights common high-risk medication classes, and provides a transition summary. A physician-confirmed discharge decision supersedes any prior current discharge state but preserves historical rows for provenance. The confirmed state is stored in the same `medication_states` table already consumed by H&P, Patient Overview, Audit, and Discharge, so confirmation becomes the encounter's shared medication source of truth rather than a note-specific decision.

Supported physician-confirmed discharge states are: `continue`, `stop`, `resume`, `changed_dose`, `changed_route`, `changed_frequency`, `newly_started`, `inpatient_only`, `completed`, `unclear`, and `requires_decision`.

## Step 25 - Signout / Handoff module

Adds a persisted Signout document on the shared MCIF patient state.

Variants:
- `standard`
- `night`
- `weekend`
- `short`
- `complex`

Endpoints:
- `POST /api/v1/encounters/{encounter_id}/documents/signout`
- `GET /api/v1/documents/{document_id}/signout`

Generated sections include one-liner, active problems, current hospital medication/treatment state, pending items, overnight risks, if/then contingency placeholder, code status only when explicitly structured/documented, and disposition. Signout participates in the same Accept/Edit/Regenerate/Approve/Audit/Finalize lifecycle as other MediNote documents.

## Step 26 - Physician web interface

Step 26 adds a dependency-light physician-facing frontend under `frontend/` and connects it to the existing FastAPI API.

Visible workflow:

- Patient dashboard and encounter roster
- New patient encounter creation
- Chart/source paste and MCIF analysis
- Patient Overview with problems, evidence, latest labs, medication states, consultants, pending items, disposition, and contradictions
- H&P, Progress Note, Discharge, Med Rec, and Signout navigation
- Document generation by variant
- Section-level Accept / Edit / Regenerate
- Document approval
- Safety audit review
- Finalization gate
- Copy-to-Epic final text
- Physician-confirmed discharge medication decisions

### Run with Docker Compose

```bash
docker compose up --build
```

Then open:

- Frontend: `http://localhost:5173`
- API docs: `http://localhost:8000/docs`

### Run the frontend without Docker

The frontend is plain browser JavaScript/CSS and has no runtime framework dependency. If `http-server` is installed:

```bash
cd frontend
http-server . -p 5173 -c-1
```

The default API base is `http://localhost:8000/api/v1`.

### Current MVP boundary

This interface is intentionally a pilot UI. Authentication/SSO, production PHI deployment controls, direct Epic/FHIR integration, and institutional role configuration remain later workstreams. The final chart still only receives clinician-reviewed output.

## Step 27 - Pilot authentication and security controls

Step 27 adds the first pilot security boundary. It is designed for controlled evaluation, not as a claim of full HIPAA/security certification.

### Authentication

- First-run `POST /api/v1/auth/bootstrap` creates the initial organization administrator and disables itself once a user exists.
- `POST /api/v1/auth/login` uses PBKDF2-SHA256 password hashing with per-password random salt.
- Successful login returns an opaque bearer session token; only its SHA-256 hash is stored server-side.
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

Audit metadata must never contain raw chart text, names, MRNs, dates of birth, note bodies, or other PHI.

### Frontend

The physician UI now starts at a login screen. First deployment can use **First-time pilot setup** to create the initial administrator. The browser stores the opaque session token and adds it as a bearer token to API calls. Sign-out revokes the server session and removes the local token.

### Validation

The regression suite uses a test-only authentication bypass. A separate authenticated smoke test verifies unauthenticated `401`, same-organization `200`, deliberate cross-organization `404`, and credential login `200` behavior. The bypass is disabled by default and must never be enabled in pilot or production.

## Step 28 - Pilot validation framework

MediNote now includes a de-identified/synthetic validation harness with a versioned core case library covering AKI/medication hold, pneumonia/hypoxemia, sepsis ambiguity, GI bleed/anticoagulation, confusion vs encephalopathy, anemia etiology, procedure state, preliminary cultures, disposition conflict, and aspiration-risk/CDI safety.

Validation APIs:
- `GET /api/v1/validation/cases`
- `GET /api/v1/validation/cases/{case_id}`
- `POST /api/v1/validation/cases/{case_id}/evaluate`
- `GET /api/v1/validation/dashboard`

Tracked metrics include fact precision/recall, medication-state accuracy, diagnostic-certainty accuracy, unsupported-claim rate, consequential errors per 100 cases, and physician edit ratio. The dashboard reports a conservative pilot gate (`not_ready` or `candidate`); it is an internal engineering/clinical validation signal, not regulatory clearance or proof of clinical safety.

## Step 29 - Controlled Physician Simulation Study

The validation framework now contains 60 versioned de-identified/synthetic inpatient cases with module targets, hazard tags, difficulty levels, expected safety flags, physician edit scoring, adjudication, module-specific performance summaries, and a formal validation report endpoint.

New endpoints:
- `POST /api/v1/validation/runs/{run_id}/adjudicate`
- `GET /api/v1/validation/report`

The pilot engineering gate now requires at least 50 simulation cases, coverage of every case, >=98% mean fact precision, >=99% medication-state accuracy, >=99% diagnostic-certainty accuracy, and zero consequential validation errors. This is an internal engineering gate only and is not clinical/regulatory clearance.

See `docs/STEP29_CONTROLLED_PHYSICIAN_SIMULATION.md` for the study protocol.

## Step 31 - Pilot Deployment Package

A production-oriented small-group pilot deployment scaffold is included:

- `docker-compose.pilot.yml`
- `.env.pilot.example`
- `deploy/caddy/Caddyfile`
- `deploy/scripts/preflight.sh`
- `deploy/scripts/deploy.sh`
- `deploy/scripts/backup.sh`
- `deploy/scripts/restore.sh`
- `deploy/scripts/status.sh`
- `docs/STEP31_PILOT_DEPLOYMENT.md`
- `docs/PHI_SAFE_LOGGING_POLICY.md`
- `docs/PILOT_ONBOARDING_CHECKLIST.md`

Pilot deployment publishes only TLS proxy ports 80/443; PostgreSQL and API remain internal. The API now supports environment-controlled CORS/session duration/API-doc exposure and a database-aware `/api/v1/ready` endpoint. The production frontend defaults to same-origin `/api/v1`, while localhost development retains the direct port-8000 behavior.

This remains an engineering deployment scaffold. Real PHI use requires organizational security/privacy/compliance review, appropriate vendor/model data-processing terms and BAAs where required, host/volume encryption, incident-response integration, and other controls documented in the Step 31 guide.


## Step 32 — Pilot Operations Package
See `docs/STEP32_30_DAY_PILOT_PLAYBOOK.md`, `docs/PILOT_PROTOCOL.md`, `docs/PILOT_SUCCESS_METRICS.md`, `docs/ISSUE_REPORT_AND_ESCALATION.md`, and `docs/PHYSICIAN_PILOT_QUICKSTART.md`.


## Step 34 — Commercial Sales Package
See the `sales/` directory for the one-pager, demo script, pilot proposal, pricing, ROI calculator, medical-director pitch, objection handling, agreement outline, and first-customer checklist.

## Step 40 — Golden Case Test
Run `PYTHONPATH=. DATABASE_URL='sqlite+pysqlite:///:memory:' TEST_BYPASS_AUTH=true python validation/golden/run_golden_case.py` from `backend/`.
See `docs/STEP40_GOLDEN_CASE.md` and `backend/validation/golden/outputs/` for the reproducible report and final documents.


## Step 41 — Text-Only Golden Case Ingestion
Step 41 closes the Step 40 ingestion gaps for explicit physical exam, home medication, therapy/disposition, and pending-result lifecycle language. The Golden Case now runs those domains from source text without manual structured augmentation. See `docs/STEP41_TEXT_ONLY_INGESTION.md`.


## Step 42 — Multi-Day Chart Ingestion Torture Test
Run `PYTHONPATH=. python validation/torture/run_chart_torture.py` from `backend/`. Final result: 10/10 torture assertions and 84/84 regression tests. See `docs/STEP42_CHART_INGESTION_TORTURE_TEST.md` and `docs/STEP42_FINDINGS.md`.

## Step 43 — Physician Contradiction Adjudication
Step 43 adds physician-controlled contradiction resolution with source selection/new clinical decision, adjudication provenance, structured state updates, automatic Progress/Signout regeneration, and re-audit. See `docs/STEP43_PHYSICIAN_ADJUDICATION.md`.

## Step 44 — Patient Identity Guard
MediNote now enforces patient/source identity checks before MCIF analysis and document generation. Exact MRN/DOB mismatches are quarantined hard stops, name-only matches are ambiguous until physician verified, source resources are tenant-isolated, and wrong-chart sources cannot be silently merged into the selected encounter. See `docs/STEP44_PATIENT_IDENTITY_GUARD.md`.


## Step 45 — Stale-State / Race-Condition Protection
Documents are version-bound to MCIF encounter state. New chart input invalidates older drafts until they are refreshed, re-reviewed, re-audited, and re-approved. See `docs/STEP45_STALE_STATE_RACE_CONDITION.md`.


## Step 46 — Multi-User Concurrency Protection
Optimistic section/document versions, Med Rec state guards, contradiction revisions, active editor leases, and attending-vs-resident approval separation are documented in `docs/STEP46_MULTI_USER_CONCURRENCY.md`.


## Step 47 — Failure Recovery
Adds idempotent high-risk clinical mutations, uncertain-outcome recovery receipts, client-side unsent draft preservation, and transaction rollback tests. See `docs/STEP47_FAILURE_RECOVERY.md`.


## Step 48 — Tamper-Evident Audit & Forensic Reconstruction
MediNote now maintains an organization-scoped SHA-256 hash chain for audit events, rejects application-level audit row mutation, detects direct database tampering during chain verification, records key document/medication/safety/adjudication events, and provides administrator-only PHI-minimized forensic exports. See `docs/STEP48_AUDIT_TRAIL_INTEGRITY.md`.


## Step 49 — Immutable Retention + Legal Hold
Adds external audit hash anchors, AES-256-GCM encrypted WORM-style retention snapshots, organization/encounter legal holds, hold release auditability, retention eligibility reporting, and verification endpoints. See `docs/STEP49_IMMUTABLE_RETENTION_LEGAL_HOLD.md`.

## Step 50 — Pilot Release Candidate v0.1
Clinical behavior is frozen for this release candidate. See `docs/STEP50_PILOT_RELEASE_CANDIDATE.md` and `release/` for readiness decision, SBOM/license inventory, security scan result, manifest, and checksums.

## Pilot 001 — De-Identified Hospitalist Usability Study
Step 51 creates the first real-user evaluation package around frozen Pilot RC v0.1. See `pilot001/` for the master protocol, facilitator guide, observer rubric, physician feedback form, issue capture template, readiness checklist, and Day-1/Day-7 review templates. Pilot 001 permits synthetic/de-identified data only.
