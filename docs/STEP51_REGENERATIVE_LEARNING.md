# MediNote IQ Step 51 — Regenerative Learning & Improvement

Status: **FOUNDATION ONLY — structured metadata, no autonomous model mutation**

## Objective

MediNote IQ should learn from physician use without becoming a self-modifying
clinical system.

The regenerative loop is:

```text
MediNote output
    ↓
physician review / edit / adjudication
    ↓
structured learning signal
    ↓
pattern analysis
    ↓
versioned improvement candidate
    ↓
Golden Case + torture + regression + safety evaluation
    ↓
physician adjudication + clinical/technical approval
    ↓
normal reviewed release process
    ↓
post-release monitoring
```

## Learning sources

MediNote IQ may create structured learning signals from:

- physician accept/edit/reject behavior;
- contradiction adjudication;
- medication-reconciliation correction;
- safety-flag resolution;
- validation failures and successes;
- CDI correction;
- coding correction;
- workflow friction measured during controlled use.

The learning signal stores metadata and opaque references, not raw note text.

## What the system may learn

Candidate improvements can target:

- prompts/templates;
- deterministic extraction or reconciliation rules;
- source-authority rules;
- safety checks;
- validation cases;
- CDI/coding rules;
- workflow;
- documentation structure.

## Hard boundary

**Learning may propose a change. It may not apply a change.**

No learning signal or aggregate may directly:

- rewrite production prompts;
- alter deterministic clinical rules;
- fine-tune/retrain a production model;
- modify the chart or legal medical record;
- add/remove diagnoses or medications;
- alter orders, prescriptions, disposition, or discharge;
- change coding or submit a claim;
- deploy a model, rule, prompt, or code change;
- bypass physician adjudication, regression testing, safety review, or rollback planning.

## Existing MediNote foundations used by RLI

This builds on existing governance rather than replacing it:

- Step 29 simulation study;
- Step 40 Golden Case;
- Step 42 chart-torture testing;
- Step 43 physician contradiction adjudication;
- Step 45 stale-state protection;
- Step 46 concurrency protection;
- Step 47 idempotent recovery;
- Step 48 tamper-evident audit trail;
- Step 49 immutable retention/legal hold;
- the validation case library and physician edit/adjudication metrics.

## Promotion gate

A candidate can become only **eligible for reviewed release** when:

- Golden Case passes;
- torture set passes;
- full regression passes;
- safety review passes;
- physician adjudication is complete;
- clinical owner approves;
- technical owner approves;
- rollback target exists;
- evaluation set is versioned;
- regulatory review passes when intended use changes.

Eligibility does not deploy anything. Deployment remains a separate normal
release action.

## Clinistry interoperability

MediNote IQ and Clinistry share the regenerative-learning concept, but keep
authority separate.

- MediNote IQ owns clinical/documentation/CDI/coding intelligence learning.
- Clinistry owns workflow/orchestration/RCM/billing/organization learning.
- Cross-product learning uses opaque references and structured reason codes.
- Raw clinical text and PHI are not placed into the shared learning envelope in
  the current foundation.
- A Clinistry outcome can inform a MediNote candidate only through an explicitly
  scoped cross-product review; it cannot silently change MediNote behavior.

## Implementation

`backend/app/core/regenerative_learning.py` defines:

- safe learning signals;
- validation/adjudication-to-learning projection;
- versioned improvement candidates;
- promotion evidence;
- fail-closed promotion decisions.

The module intentionally contains no model-training client, no prompt mutation,
no deployment client, and no chart-write capability.
