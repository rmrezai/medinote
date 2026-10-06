# MediNote IQ Regenerative Learning & Improvement

Status: **governed foundation — no autonomous self-modification**

MediNote IQ should improve continuously from physician use, adjudication,
validation, and safety review. The learning loop must preserve the existing
evidence-first design and physician authority.

## Core loop

```text
MediNote output
  -> physician accept/edit/reject/adjudicate
  -> structured learning signal
  -> recurring pattern / candidate improvement
  -> golden + torture + regression + safety evaluation
  -> physician adjudication
  -> clinical + technical approval
  -> regulatory review when intended use changes
  -> normal versioned release with rollback target
  -> post-release monitoring
```

## Native MediNote learning sources

Use structured metadata already available from the platform:

- physician edit ratio;
- validation pass/fail;
- consequential error count;
- reviewer score;
- adjudication status;
- contradiction resolution;
- safety-flag resolution;
- medication-state corrections;
- unsupported-claim findings;
- CDI/coding corrections;
- module-specific failure patterns.

Raw chart text, patient identifiers, full generated notes, and free-text
adjudication content do **not** belong in the generic learning envelope.

## Existing assets used by RLI

MediNote already has the right foundations:

- versioned validation cases;
- Golden Case;
- chart torture tests;
- physician contradiction adjudication;
- physician edit scoring;
- consequential-error tracking;
- append-only tamper-evident audit;
- stale-state protection;
- rollback/recovery concepts.

RLI organizes those assets into a controlled continuous-improvement cycle.

## Hard boundary

A learning signal may propose an improvement. It cannot:

- rewrite a production prompt;
- modify source-authority rules;
- change a diagnosis/problem list;
- alter a medication state;
- change a signed/final clinical document;
- train/fine-tune a production model automatically;
- change model/provider/version;
- deploy code;
- bypass physician adjudication;
- bypass regulatory review when intended use changes.

## Shared Clinistry + MediNote learning architecture

Clinistry and MediNote IQ may share compatible RLI metadata contracts, but their
authorities stay separate:

- MediNote IQ learns clinical/documentation/safety/CDI/coding behavior.
- Clinistry learns workflow, scheduling, RCM, billing, implementation, and
  organization operations.
- Cross-product signals use opaque references and structured reason codes.
- No raw PHI is copied into a shared learning stream.
- A cross-product change must identify which product owns the changed behavior.

## Initial code

`backend/app/core/regenerative_learning.py` defines:

- PHI-free structured learning signals;
- a bridge from validation/adjudication summaries;
- improvement candidates;
- validation and approval evidence;
- a fail-closed promotion decision.

"Eligible for reviewed release" means only that a candidate may enter the normal
release process. It does not mutate production behavior.
