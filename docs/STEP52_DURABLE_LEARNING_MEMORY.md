# MediNote IQ Step 52 — Durable Learning Memory

Status: **FOUNDATION ONLY — no autonomous clinical behavior change**

Step 52 persists safe structured learning metadata and aggregates recurring
patterns so physician corrections do not disappear as isolated events.

## Architecture

```text
physician edit / adjudication / validation / safety or CDI correction
    -> safe RLI learning signal
    -> append-only organization-scoped learning memory
    -> pattern aggregation
    -> pattern ready for candidate review
    -> Step 51 improvement candidate
    -> Golden / torture / regression / safety evaluation
    -> physician + clinical + technical approval
    -> normal reviewed release
```

## Persistence

`LearningSignalRecord` stores organization-scoped structured metadata only.
The pair `organization_id + signal_ref` is unique and idempotent. Reusing a
signal reference with different metadata fails closed.

The record intentionally excludes raw clinical note text and direct identifiers.

`LearningPatternRecord` is derived state. It groups recurring feedback by:

- organization;
- MediNote module;
- structured reason code;
- source artifact version.

Patterns reaching the configured minimum occurrence threshold become
`ready_for_candidate_review`. That flag does **not** change production behavior.

## Tenant boundary

Patterns are computed only inside one organization. Cross-customer learning is
not enabled by this implementation.

A future cross-organization learning program requires separate governance for:

- de-identification/aggregation;
- contractual/data-use rights;
- bias and representativeness;
- privacy/BAA implications;
- minimum cohort thresholds;
- clinical validation and regulatory review.

## No self-modification

Durable memory cannot:

- rewrite a prompt;
- change source-authority or medication rules;
- mutate a chart;
- change diagnosis, order, prescription or disposition;
- change coding or transmit a claim;
- alter a deployed model;
- publish a release.

It provides evidence for the governed Step 51 promotion process only.
