# MediNote Step 42 — Multi-Day Chart Ingestion Torture Test

## Purpose
Stress the longitudinal ingestion/reconciliation layer with realistic chart messiness rather than a clean chronological record.

## Injected hazards
- copied-forward stale oxygen and diagnosis text;
- explicit diagnosis later ruled out, followed by stale reappearance;
- same-time nursing vs clinician narrative conflict;
- conflicting consultant medication recommendations;
- duplicate home-medication formatting;
- planned procedure later canceled, followed by stale copied-forward planned status;
- early and amended lab results;
- preliminary/pending microbiology later finalized;
- late-entered documentation with an old clinical timestamp;
- changing PT/discharge destination recommendations.

## Required behavior
1. Current source hierarchy must follow MediNote governance: objective > consultant > MAR/orders > nursing > clinician narrative > copied/old text.
2. Ruled-out diagnoses must not be silently resurrected by a bare copied-forward mention.
3. Conflicting consultants must remain visible for physician adjudication.
4. Duplicate medication identities must normalize without merging Home/Hospital/Discharge state domains.
5. A canceled/completed procedure must not regress to planned because of stale text.
6. Amended/later objective results supersede earlier values while preserving history.
7. Late-imported but clinically old documentation must not become current merely because it arrived last.
8. The latest documented disposition recommendation must replace an older plan without implying completed discharge.

## Scope limitation
This is a deterministic synthetic engineering torture test, not clinical validation. Consultant-opposition detection is intentionally narrow and currently targets explicit opposing action/medication language. Recurrence of a previously ruled-out diagnosis requires a future explicit recurrence rule rather than automatic reactivation from bare copied text.
