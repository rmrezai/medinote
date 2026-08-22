# MEDAI Publication Handoff

## Purpose

This file is the operational handoff from the version-controlled MediNote repository to the live MEDAI GPT Builder configuration and eventual GPT Store release.

## Publication source set

Use these repository artifacts together:

- `gpt/MEDAI_BUILDER_INSTRUCTIONS.md`
- `gpt/MEDAI_BUILDER_CONFIGURATION.md`
- `gpt/GPT_STORE_RELEASE_CHECKLIST.md`
- current MediNote Unified Master Instruction

The master instruction remains the authoritative clinical specification. Builder and publication files organize deployment and public-use boundaries; they do not override clinical safety or data-integrity rules.

## Current repository state at handoff creation

- Base branch: `main`
- Main revision incorporated during conflict resolution: `715c47ac82cb8ff5951652d04f011edf5560351c`.
- PR #2 (`Run backend regression suite in CI`) is merged; it runs the backend suite from `backend/` using `python -m pytest -q` with PostgreSQL 16.
- PR #4 (`Optimize MEDAI runtime governance and connected-tool behavior`) is merged.
- This branch preserves PR #4's runtime, evidence-provenance, connected-tool, and PHI-governance changes while adding the publication synchronization contract.
- CI was green before the conflict-resolution update; verify the new head revision is green before merge or publication.

Do not treat this snapshot as a permanent release identifier. Before publication, replace it with the final merged release revision and verify its checks.

## Release gates

Publication is blocked until all applicable gates are satisfied:

1. **Repository gate** — intended release revision identified; no unintended clinical-behavior change; required CI/regression checks green.
2. **Clinical freeze gate** — Step 50 frozen clinical behavior preserved unless a deliberately versioned clinical change has been approved and validated.
3. **Builder synchronization gate** — live MEDAI Builder instructions/configuration updated from the repository source set; current authoritative master instruction attached.
4. **Preview validation gate** — Store validation prompts in `GPT_STORE_RELEASE_CHECKLIST.md` pass, including HOOP contract, medication-state reconciliation, consultant conflict, discharge completion safety, PHI handling, uncertainty preservation, engineering-mode switching, and prompt-injection resistance.
5. **Publishing-account gate** — workspace/account permissions, builder profile, public publishing controls, and any applicable domain requirements are satisfied.
6. **Public configuration gate** — Store v1 uses synthetic/de-identified public-use framing, does not claim autonomous care or HIPAA/FDA status, and keeps Apps/Actions disabled unless separately reviewed.
7. **Release-record gate** — final repository revision, public GPT URL, and publication date are recorded after successful publication.

## Builder application order

1. Set the public name/description and other Builder metadata from `MEDAI_BUILDER_CONFIGURATION.md`.
2. Replace the live instruction text with the current `MEDAI_BUILDER_INSTRUCTIONS.md`.
3. Upload the current MediNote Unified Master Instruction as the authoritative clinical knowledge artifact.
4. Ensure public knowledge contains no real patient charts, credentials, secrets, or confidential institutional material.
5. Configure capabilities according to the Store v1 recommendations.
6. Run the full Preview validation set.
7. Publish only after all release gates pass.

## Post-publication record

After successful Store publication, update this file or the designated release notes with:

- Released repository revision: `PENDING`
- Public GPT URL: `PENDING`
- Publication date: `PENDING`
- Builder configuration revision/checksum: `PENDING`
- Master instruction revision/checksum: `PENDING`

Do not populate these fields speculatively.
