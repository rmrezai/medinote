# MediNote Controlled Physician Simulation Study - v1.0

## Purpose
Evaluate MediNote's structured extraction, clinical-state synthesis, documentation modules, medication reconciliation, handoff, and safety-audit behavior on de-identified/synthetic inpatient scenarios before a live hospitalist-group pilot.

## Study library
- 60 versioned de-identified/synthetic inpatient scenarios.
- Core high-risk domains include AKI, respiratory support, sepsis ambiguity, anticoagulation, altered mental status, anemia etiology, procedures, preliminary microbiology, disposition conflicts, aspiration risk, cardiorenal conflict, steroid hyperglycemia, AF/RVR, electrolyte trends, asymptomatic bacteriuria, myocardial injury, COPD, DKA transitions, and placement authorization.
- Each case defines ground-truth facts, expected medication states, diagnostic certainty, prohibited claims, expected safety flags, target modules, hazard tags, and difficulty.

## Modules evaluated
- Patient Overview
- H&P
- Progress Note
- Discharge
- Medication Reconciliation
- Signout/Handoff

## Required physician workflow
1. Review the source scenario without viewing ground truth.
2. Run the assigned MediNote module.
3. Record observed facts, medication states, diagnostic certainty, claims, and safety flags.
4. Edit the generated text exactly as clinically required.
5. Score factual accuracy, usefulness, prioritization, medication accuracy, and safety-alert quality.
6. Submit the validation run.
7. A second physician or designated adjudicator reviews disagreements/high-risk failures and marks the run accepted, rejected, or resolved.

## Primary metrics
- Fact precision
- Fact recall
- Medication-state accuracy
- Diagnostic-certainty accuracy
- Expected-safety-flag recall
- Unsupported-claim rate
- Consequential errors per 100 runs
- Physician edit ratio
- Module-specific pass rate

## Initial engineering gate
A build may be labeled **CANDIDATE** only when:
- At least 50 versioned simulation cases exist.
- Every case has at least one completed run.
- Mean fact precision is at least 98%.
- Mean medication-state accuracy is at least 99%.
- Mean diagnostic-certainty accuracy is at least 99%.
- No consequential validation errors remain.

`CANDIDATE` is an internal engineering label only. It does not establish clinical validation, regulatory clearance, HIPAA compliance, or fitness for autonomous patient care.

## High-risk failure examples
- Suspected/possible diagnosis promoted to confirmed.
- Held anticoagulant documented as continued/resumed.
- Planned procedure documented as completed.
- Preliminary result documented as final.
- Unsupported respiratory failure, sepsis, encephalopathy, acute blood-loss anemia, or aspiration pneumonia.
- Consultant disagreement silently collapsed.
- Unresolved discharge medication or destination represented as resolved.

## API workflow
- `GET /api/v1/validation/cases`
- `POST /api/v1/validation/cases/{case_id}/evaluate`
- `POST /api/v1/validation/runs/{run_id}/adjudicate`
- `GET /api/v1/validation/dashboard`
- `GET /api/v1/validation/report`

## Governance
Simulation results are validation evidence, not physician orders or patient-care decisions. MediNote continues to preserve the physician-review boundary for any future clinical deployment.
