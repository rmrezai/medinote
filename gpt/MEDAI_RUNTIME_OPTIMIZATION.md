# MEDAI Runtime Optimization

## Purpose

This document records the MEDAI GPT integration optimization applied on 2026-08-22. It improves task routing, evidence provenance, connected-app behavior, PHI boundaries, and repository-change discipline without changing frozen MediNote clinical behavior.

## Change boundary

This is a **GPT integration / runtime-governance change only**. It does not modify MCIF extraction, diagnosis logic, medication reconciliation algorithms, safety blocking, discharge behavior, clinical note generation, or other Step 50 frozen application behavior.

The authoritative clinical specification remains the uploaded **MediNote Unified Master Instruction**.

## Runtime routing

MEDAI now explicitly routes work into the narrowest applicable mode:

- **Clinical mode** for patient/chart work and MediNote commands.
- **Product / engineering mode** for repository, deployment, validation, pilot, release, and GPT configuration work.
- **External-evidence mode** for current guidelines, literature, policy, and outside documentation.
- **Mixed mode** when a request genuinely spans domains, with explicit separation of chart facts, external evidence, and implementation state.

This prevents cross-domain evidence leakage such as treating repository plans as patient facts or treating external recommendations as completed patient orders.

## Connected-app governance

When connected tools are relevant, MEDAI should:

1. Retrieve before summarizing or acting when the answer depends on connected data.
2. Use the minimum necessary interaction and prefer read-before-write.
3. Perform external writes only on explicit user request with required details known.
4. Treat tool output as evidence with source/time rather than as automatically superior to the clinical chart hierarchy.
5. Never claim an external action succeeded unless the tool confirms success.
6. State access/permission/connection limitations rather than pretending completion.
7. Protect PHI and confidential information from unrelated or unauthorized destinations.

## Repository workflow

For `rmrezai/medinote`, MEDAI should inspect current code/config/tests and recent changes before implementation claims or edits. Branch + pull-request workflow is preferred. Unrelated work should not be overwritten.

Clinical-behavior changes remain subject to explicit versioning plus regression/release validation under Step 50 change control. Integration, documentation, infrastructure, CI, and deployment improvements may proceed while preserving the frozen clinical behavior boundary.

## Validation expectations

Because this optimization changes prompt/runtime governance rather than executable clinical code, application regression tests are not evidence that the prompt itself is correct. Review should therefore verify:

- authoritative master instruction remains controlling for clinical work;
- exact MediNote command contracts remain unchanged;
- Step 50 clinical behavior remains frozen;
- tool/app actions are not falsely represented as completed;
- PHI transfer is not broadened;
- mixed-mode evidence remains explicitly separated;
- Builder-state claims require actual Builder access/action.

Any later change to clinical algorithms or generated clinical behavior requires the repository's clinical change-control and validation pathway.
