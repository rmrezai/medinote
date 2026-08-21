# MediNote — Common Objections

## “We already have an AI scribe.”
MediNote is positioned around longitudinal inpatient synthesis and reconciliation across multiple hospitalist workflows, not simply transcription-to-note generation. A pilot should determine whether that distinction adds measurable value alongside or instead of the existing tool.

## “AI hallucinates.”
That is a central design constraint. MediNote separates source facts, structured state, generated documentation, audit findings, and physician decisions. It preserves uncertainty and keeps the physician responsible for final documentation. The pilot specifically measures unsupported claims and consequential discrepancies.

## “We cannot put PHI into another tool.”
Do not proceed until the proposed deployment/data flow passes the organization's privacy, security, compliance, contracting, and vendor requirements. A controlled de-identified evaluation can precede PHI deployment.

## “Our doctors won't use another workflow.”
That is testable. The pilot measures adoption, time, edit burden, failures, and physician feedback. Poor workflow adoption is a legitimate reason not to expand.

## “Can it write directly into Epic?”
The initial pilot workflow is clinician-reviewed Copy-to-Epic. Deeper EHR integration should be treated as a separate implementation/security project.

## “Will this improve coding or revenue?”
MediNote may improve documentation structure, but do not promise DRG/revenue gains without measured evidence. Clinical truth takes precedence over coding optimization.

## “Who is liable if it is wrong?”
The product is designed as physician-supervised decision-support/documentation assistance, but contractual liability, regulatory posture, insurance, and institutional responsibilities require qualified legal review.

## “Why should we pay for a pilot?”
The pilot includes deployment, training, support, monitoring, validation, and an outcome report. A paid pilot also tests whether the problem is commercially meaningful rather than merely interesting.
