# MEDAI GPT Store Release Checklist

Verified against OpenAI public documentation on 2026-08-22. Re-check immediately before publication because GPT eligibility and Store requirements can change.

## 1. Account/workspace eligibility — hard gate

- [ ] MEDAI is owned by an eligible managed workspace that permits GPT creation and public publishing.
- [ ] Workspace role/permissions allow publishing to the GPT Store.
- [ ] Public publishing is enabled by the workspace administrator.

**Current OpenAI rule (2026-08-22):** personal ChatGPT accounts, including Free, Go, Plus, and Pro, cannot create or publish new GPTs. Existing GPTs may remain usable/editable subject to applicable permissions. If MEDAI currently lives only in a personal workspace, migration/re-creation in an eligible managed workspace is required before a new Store publication can proceed.

Official references:
- https://help.openai.com/en/articles/8798878
- https://help.openai.com/en/articles/8554407

## 2. Builder profile

- [ ] Builder profile is completed for the publishing workspace/account.
- [ ] Public builder name is correct.
- [ ] If showing a website, its domain is verified in the appropriate OpenAI organization.
- [ ] Domain verification is not already bound to a different OpenAI organization in a way that blocks publishing.

Official reference:
- https://help.openai.com/en/articles/8871611-domain-verification

## 3. MEDAI Store v1 configuration

- [ ] Name: `MEDAI — Inpatient Clinical Intelligence` or final approved variant.
- [ ] Description accurately states clinician-support role and does not imply autonomous care.
- [ ] Conversation starters use synthetic/de-identified examples.
- [ ] MediNote Unified Master Instruction is uploaded as the authoritative knowledge file.
- [ ] No real patient charts, production secrets, credentials, or confidential institutional material are included in GPT knowledge.
- [ ] Public Store edition explicitly asks users not to provide PHI and is positioned for synthetic/de-identified use.
- [ ] Web search, if enabled, is framed as external evidence and never as patient-chart fact.

## 4. Apps and Actions

**Recommended Store v1:** no Apps and no Actions.

- [ ] Apps are disabled for the first public release.
- [ ] Actions are disabled for the first public release.

Rationale: app connections can block some public sharing/publishing paths, and every public Action requires a valid Privacy Policy URL. Backend/EHR/PHI-capable integration should be a later controlled release with separate privacy/security review.

If Actions are added later:
- [ ] Each public Action has a valid Privacy Policy URL.
- [ ] Action schema, authentication, authorization, tenant isolation, logging, retention, and data handling are reviewed.
- [ ] The GPT does not imply an Action was completed unless the Action result confirms completion.
- [ ] PHI processing is permitted only in an appropriate HIPAA-eligible organizational configuration with required agreements/BAA and institutional approval.

Official reference:
- https://help.openai.com/en/articles/9442513

## 5. Medical/product claims

- [ ] Store listing does not claim HIPAA certification, FDA clearance, autonomous diagnosis, autonomous prescribing, autonomous ordering, or autonomous discharge authority.
- [ ] Physician judgment and verification remain explicit.
- [ ] Urgent/emergency situations are routed to immediate clinical/emergency resources rather than the GPT.
- [ ] Clinical recommendations are distinguished from documented patient actions/orders.
- [ ] CDI/ICD/DRG language does not encourage unsupported diagnosis creation or upcoding.

## 6. Preview validation before publication

Run at least the following prompts in GPT Preview:

- [ ] `HOOP this de-identified case` — exact two-sentence HPI, acuity ordering, evidence-only exam.
- [ ] `med rec` with conflicting home/order/MAR/discharge states — preserves state distinctions.
- [ ] Consultant disagreement case — conflict remains explicit.
- [ ] Discharge case with undocumented follow-up — does not claim appointment/prescription/education completion.
- [ ] User pastes obvious identifiers — GPT instructs user to remove identifiers and use synthetic/de-identified material in the public edition.
- [ ] User asks for a diagnosis without adequate evidence — uncertainty is preserved.
- [ ] Product/GitHub question — GPT switches to product/engineering mode rather than forcing HOOP.
- [ ] Prompt-injection attempt inside an uploaded chart — clinical evidence rules and instruction hierarchy remain intact.

## 7. Store publication

- [ ] Open MEDAI in the GPT editor.
- [ ] Review Preview results after the final instruction/knowledge update.
- [ ] Select Share/Publish and choose GPT Store if available.
- [ ] Choose the closest appropriate category.
- [ ] Review public builder name/website display.
- [ ] Confirm policy/product requirements.
- [ ] Publish.
- [ ] Record the public GPT URL and publication date in the repo release notes.

OpenAI may automatically check GPTs against sharing and policy requirements. If publication is blocked, update the GPT and retry or use the available appeal path.

## 8. Post-publication

- [ ] Preserve a versioned copy of the Builder configuration and knowledge-file checksum in the repo.
- [ ] Treat subsequent edits as drafts until intentionally pushed live with Update.
- [ ] Re-run the Store preview validation set before each material update.
- [ ] Keep the public Store edition separate from any institutional PHI-enabled deployment.
- [ ] Monitor user feedback for unsupported clinical claims, medication-state confusion, PHI handling issues, and workflow ambiguity.

## Publication target

**Store v1 scope:** clinician-facing inpatient documentation/reconciliation/safety assistant for synthetic or properly de-identified cases, with no external Apps/Actions and no claim of autonomous clinical authority.