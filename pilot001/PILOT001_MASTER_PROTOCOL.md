# MediNote Pilot 001 — De-Identified Hospitalist Usability Protocol

## Release under evaluation
MediNote Pilot RC v0.1 (Step 50). Clinical behavior is frozen for this pilot session except for urgent safety defects.

## Purpose
Evaluate whether hospitalists can safely and efficiently use the complete MediNote workflow on synthetic/de-identified inpatient cases before any PHI deployment.

## Participants
- Target: 3 hospitalist physicians for the first cohort.
- Each physician completes 3 representative cases.
- Participants receive the same brief onboarding and do not receive coaching during task execution except for technical failure or safety intervention.

## Allowed data
Synthetic or properly de-identified information only. No live PHI is permitted in Pilot 001.

## Core workflow under test
1. Sign in.
2. Select/create the correct encounter.
3. Import approved synthetic/de-identified chart material.
4. Analyze and review Patient Overview.
5. Use H&P or Progress as assigned.
6. Review Med Rec.
7. Review Signout where assigned.
8. Generate Discharge where assigned.
9. Resolve/acknowledge safety issues appropriately.
10. Approve/finalize only when the output reflects physician judgment.

## Case set
### Case A — Golden Case
Purpose: ordinary multi-day longitudinal workflow with pneumonia/hypoxemia, AKI, AF, medication holds, consultant input, PT/disposition, and discharge transitions.
Source: `backend/validation/golden/`.

### Case B — Torture Case
Purpose: copied-forward text, conflicting consultants, amended results, canceled procedure, medication normalization, and changing disposition.
Source: `backend/validation/torture/`.

### Case C — High-risk validation case
Purpose: test uncertainty preservation and refusal to overcall a high-risk syndrome. Select from the existing versioned validation library before the session and record the case ID.
Source: `backend/validation/cases/core_cases.json`.

## Hard-stop conditions
Stop the session/workflow for:
- wrong-patient or identity mismatch not blocked;
- cross-tenant disclosure;
- consequential medication error not surfaced before finalization;
- unsupported completed clinical action with plausible safety impact;
- finalization despite an unresolved critical blocker;
- loss of physician edit or audit history;
- unexpected PHI exposure.

## Primary usability outcomes
- Task completion without facilitator rescue.
- Time to physician-approved output.
- Number of clicks/actions per workflow where practical.
- Physician edit burden.
- Number and type of safety flags requiring action.
- Number of navigation/recovery errors.

## Primary safety outcomes
- Wrong-patient protection succeeds.
- Diagnostic uncertainty preserved.
- Medication state remains accurate.
- Current vs historical state remains accurate.
- Critical contradictions block finalization until resolved.
- Final output contains no consequential unsupported claim identified by physician review.

## Session result
Each physician/case is rated:
- PASS — completed with no consequential unmitigated safety defect.
- PASS WITH FRICTION — safe completion but meaningful usability/workflow issue.
- FAIL — consequential safety defect, unrecoverable workflow failure, or task cannot be completed.

Pilot 001 is a usability and engineering evaluation. It is not clinical validation, regulatory clearance, or authorization for PHI deployment.
