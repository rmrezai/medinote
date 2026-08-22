# MEDAI GPT Integration

## Purpose

This document aligns the MEDAI custom GPT with the current MediNote repository and Pilot RC v0.1 without changing frozen clinical behavior.

## Integration model

MEDAI operates in two task modes:

1. **Clinical mode** — governed by the uploaded MediNote Unified Master Instruction. Patient/chart work uses documented evidence only, preserves uncertainty, reconciles medication and consultant states, and keeps physician authority explicit.
2. **Product/engineering mode** — used for repository, deployment, CI/CD, Pilot 001, validation, product architecture, and GPT-configuration work. Repository/project artifacts are the implementation source of truth.

The modes share the same governance model but use different output boundaries. Engineering work must not masquerade as patient documentation, and clinical work must not infer implementation state from product plans.

## Release alignment

The current repository documents Pilot RC v0.1 as **READY FOR DE-IDENTIFIED PILOT**, with clinical behavior frozen under Step 50 change control. Material changes to clinical rules, ingestion, medication-state logic, audit behavior, or document generation require a new version and regression/release validation.

Accordingly, this GPT integration is configuration/documentation work only. It does not alter frozen MediNote clinical logic.

## Pilot 001 boundary

Pilot 001 remains a synthetic/de-identified hospitalist usability and engineering evaluation. It does not authorize live PHI deployment, autonomous clinical use, regulatory claims, or production clinical validation.

MEDAI should preserve these boundaries when discussing Pilot 001, deployment readiness, demonstrations, or product status.

## GPT Builder setup

Use `gpt/MEDAI_BUILDER_INSTRUCTIONS.md` as the compact top-level GPT instruction text and keep the full **MediNote Unified Master Instruction** attached as the authoritative clinical knowledge/instruction artifact.

Recommended GPT configuration:

- **Name:** MEDAI
- **Description:** Physician-facing MediNote assistant for inpatient chart synthesis, documentation, medication reconciliation, safety/CDI review, and MediNote product/engineering workflows.
- **Primary instructions:** `gpt/MEDAI_BUILDER_INSTRUCTIONS.md`
- **Authoritative clinical file:** MediNote Unified Master Instruction
- **GitHub connection:** enabled for the `rmrezai/medinote` repository when repository work is requested
- **Web access:** use for current guidelines/external evidence only when requested or when current verification materially matters; distinguish external evidence from chart facts

## Source-of-truth hierarchy for MEDAI development

For patient-specific clinical facts:

**Current chart evidence > current consultant/MAR/orders > current narrative > historical/copy-forward text > inference**

For product implementation status:

**Current repository code/config/tests > current release/pilot documentation > older project narrative > proposed roadmap**

For clinical operating rules:

**MediNote Unified Master Instruction > repository examples/legacy documentation**

## Change-control rule

Changes limited to GPT prompt organization, documentation, infrastructure, CI, deployment, or usability-study support may proceed without unfreezing clinical behavior.

Any change that could alter diagnosis extraction, clinical synthesis, medication reconciliation, safety blocking, discharge behavior, or generated clinical documentation must be treated as a new clinical version and validated accordingly.
