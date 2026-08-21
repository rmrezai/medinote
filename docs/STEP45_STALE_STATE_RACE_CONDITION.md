# Step 45 — Stale-State / Race-Condition Protection

## Safety objective
A document may only be finalized against the MCIF clinical-state version from which it was generated. New chart input increments the encounter clinical-state version. If the document version differs from the encounter version, the audit creates a critical `stale_clinical_state` flag and finalization is blocked.

## Workflow
1. Generate document at state version N.
2. New source/clinician-confirmed medication decision/adjudication advances encounter to N+1.
3. Existing document becomes stale.
4. Audit/finalize produces a critical stale-state blocker.
5. Physician invokes document refresh.
6. MediNote analyzes/reconciles/synthesizes current sources and regenerates all document sections.
7. The document is rebound to the current state version and all sections return to pending physician review.
8. Physician accepts/edits sections, approves, re-audits, and finalizes.

## Design boundaries
- Finalized documents are immutable historical records; new clinical data require a new document rather than mutation.
- Refresh never silently preserves prior physician approval. New clinical state requires new review.
- New chart data are not allowed to bypass identity checks.
- Version mismatch is treated as a critical safety condition, even if the newer source ultimately proves clinically trivial; later work can add a validated consequentiality classifier.
