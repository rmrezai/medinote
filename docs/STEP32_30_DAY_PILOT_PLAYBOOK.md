# MediNote Step 32 — 30-Day Hospitalist Pilot Playbook

## Purpose
Run a controlled, physician-supervised evaluation. MediNote drafts, structures, reconciles, and audits; the physician remains responsible for clinical decisions, orders, final documentation, and Epic entry.

## Days -14 to 0 — Readiness
- Complete institutional privacy/security/compliance review and required agreements.
- Verify approved hosting/model/vendor arrangements, identity/MFA policy, encrypted backups/restore, audit logging, and incident response.
- Assign pilot owner, clinical safety lead, technical owner, and privacy/security contact.
- Train physicians on Overview, H&P, Progress, Discharge, Med Rec, Signout, Safety Review, and Copy-to-Epic.
- Complete de-identified competency cases.

## Days 1–3 — Controlled start
- Start with a small trained physician cohort and eligible lower-complexity encounters.
- Require physician review of every generated section and safety flag.
- Review safety/technical issues daily.

## Days 4–14 — Stabilization
- Expand volume only if no unresolved critical safety issue exists.
- Review accuracy, medication state, edits, alert burden, failures, and workflow time daily.
- Freeze major clinical behavior except urgent safety fixes.

## Days 15–30 — Evaluation
- Continue controlled use and weekly physician adjudication.
- Compare workflow with baseline.
- Produce Day-30 go/no-go report.

## Default inclusion
- Adult hospital-medicine encounter.
- Trained participating physician owns final documentation.
- Required source information is available through the approved workflow.
- Encounter fits an enabled MediNote module.

## Default exclusion
- Pediatric or obstetric encounters.
- ICU/critical-care workflow unless separately validated/approved.
- Unsupported specialty workflows.
- Material source-data incompleteness or unreconciled identity.
- Any use prohibited by local policy or pilot approval.

## Hard stops
Pause affected workflow and escalate for wrong-patient/cross-tenant exposure, material PHI/security disclosure, consequential medication-state failure not intercepted, fabricated completed actions with plausible safety impact, repeated consequential certainty escalation, loss of auditability, or any risk deemed unacceptable by the clinical safety lead.

## Daily review
System readiness; critical/high flags; sampled finalized outputs vs source truth; consequential errors; false-positive alerts; physician edits; technical failures.

## Weekly review
Volume/module use; adjudicated accuracy; medication-state accuracy; certainty preservation; unsupported claims; consequential discrepancies/100 encounters; alert performance; edit ratio; workflow time; failures/downtime; overrides; physician feedback.

## Day-30 decision
GO / GO WITH CONDITIONS / HOLD / STOP. Automated metrics alone never establish clinical readiness.
