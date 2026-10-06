# MediNote IQ Step 53 — Candidate Evaluation & Human Review Queue

Status: **FOUNDATION ONLY — no autonomous release**

Step 53 turns repeated, organization-local learning patterns into explicit
improvement candidates and stores evaluation evidence before any human approval.

## Flow

```text
durable learning signals
  -> recurring pattern ready for review
  -> improvement candidate
  -> evaluation plan
  -> Golden Case / chart torture / regression / clinical safety
  -> module-specific checks
  -> baseline comparison
  -> blocked OR awaiting-human-approval
  -> separate governed promotion/release process
```

## Candidate records

A candidate stores:

- organization;
- originating pattern;
- source signal references;
- module and reason code;
- proposed change kind;
- target artifact/version;
- baseline release;
- evaluation set;
- intended-use-change flag.

Candidates are always created with `auto_apply=false` and
`production_mutation_allowed=false`.

## Evaluation records

Every evaluation run has its own `evaluation_ref`; results are append-only and
reconstructable. Passing evaluation requires every required suite to pass and
must not regress against any supplied baseline metric.

A passing evaluation ends in:

`awaiting-human-approval`

It does **not** change prompts, deterministic rules, clinical state, coding,
orders, medications, the chart, model versions, or deployment state.

## Required evaluation

All modules require:

- Golden Case;
- chart-torture suite;
- full regression;
- clinical safety.

Additional module-specific checks are required where applicable, including
coding/CDI, medication state, discharge safety, signout safety, and safety audit.

## Human approval boundary

The review queue is evidence presentation only. Promotion still uses the Step 51
governance gate and normal reviewed release controls, including physician/
clinical owner review, technical approval, rollback evidence, and regulatory
review when intended use changes.
