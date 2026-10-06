"""Governed Regenerative Learning & Improvement for MediNote IQ.

MediNote may learn from physician adjudication, edits, validation results, safety
review, and coding/CDI review. Learning creates improvement candidates; it does
not rewrite prompts/rules, retrain production behavior, modify charts, or deploy
changes automatically.

The current contract is structured-metadata only and rejects raw clinical text.
"""
from dataclasses import dataclass
import re


RLI_VERSION = "medinote-rli-v1"

_ALLOWED_MODULES = frozenset({
    "overview",
    "hp",
    "progress",
    "discharge",
    "med_rec",
    "signout",
    "safety",
    "cdi",
    "coding",
    "medication-profile",
    "allergy-profile",
    "external-ehr",
    "laboratory",
    "radiology",
    "referral",
    "longitudinal-record",
})
_ALLOWED_SIGNAL_TYPES = frozenset({
    "physician-edit",
    "physician-adjudication",
    "validation-failure",
    "validation-success",
    "safety-flag-resolution",
    "coding-correction",
    "cdi-correction",
    "workflow-friction",
    "medication-reconciliation-correction",
    "allergy-reconciliation-correction",
    "external-record-reconciliation",
    "lab-result-followup-correction",
    "radiology-followup-correction",
    "referral-followup-correction",
    "history-reconciliation-correction",
})
_ALLOWED_DISPOSITIONS = frozenset({
    "accepted",
    "edited",
    "rejected",
    "resolved",
    "overridden",
    "passed",
    "failed",
})
_ALLOWED_CHANGE_KINDS = frozenset({
    "prompt",
    "deterministic-rule",
    "source-authority-rule",
    "validation-case",
    "safety-check",
    "coding-rule",
    "workflow",
    "documentation",
    "reconciliation-rule",
    "source-mapping-rule",
    "result-followup-rule",
    "history-rule",
})
_SAFE_REF = re.compile(r"^[A-Za-z0-9._:-]{1,160}$")


class RegenerativeLearningError(ValueError):
    """Stable RLI validation errors."""


def _ref(value, reason):
    if not isinstance(value, str) or not _SAFE_REF.fullmatch(value.strip()):
        raise RegenerativeLearningError(reason)
    return value.strip()


@dataclass(frozen=True)
class LearningSignal:
    signal_ref: str
    signal_type: str
    module: str
    disposition: str
    source_ref: str
    artifact_version_ref: str
    reviewer_role: str
    reason_code: str
    consequential_error_count: int = 0
    physician_edit_ratio: float | None = None
    synthetic_or_deidentified: bool = True
    contains_raw_clinical_text: bool = False
    contains_direct_identifier: bool = False


@dataclass(frozen=True)
class ImprovementCandidate:
    candidate_ref: str
    module: str
    change_kind: str
    source_signal_refs: tuple[str, ...]
    target_artifact_ref: str
    target_version_ref: str
    intended_use_changed: bool = False
    status: str = "proposed"
    auto_apply: bool = False
    production_mutation_allowed: bool = False


@dataclass(frozen=True)
class PromotionEvidence:
    golden_set_passed: bool
    torture_set_passed: bool
    regression_passed: bool
    safety_review_passed: bool
    physician_adjudication_complete: bool
    clinical_owner_approved: bool
    technical_owner_approved: bool
    regulatory_review_passed: bool
    evaluation_set_ref: str
    rollback_target_ref: str


@dataclass(frozen=True)
class PromotionDecision:
    eligible_for_reviewed_release: bool
    reason: str
    automatic_promotion_allowed: bool = False
    production_mutation_performed: bool = False
    policy_version: str = RLI_VERSION


def build_learning_signal(
    *,
    signal_ref,
    signal_type,
    module,
    disposition,
    source_ref,
    artifact_version_ref,
    reviewer_role,
    reason_code,
    consequential_error_count=0,
    physician_edit_ratio=None,
):
    """Create a structured learning signal without raw clinical content."""
    if signal_type not in _ALLOWED_SIGNAL_TYPES:
        raise RegenerativeLearningError("unsupported-signal-type")
    if module not in _ALLOWED_MODULES:
        raise RegenerativeLearningError("unsupported-module")
    if disposition not in _ALLOWED_DISPOSITIONS:
        raise RegenerativeLearningError("unsupported-disposition")
    if type(consequential_error_count) is not int or consequential_error_count < 0:
        raise RegenerativeLearningError("invalid-consequential-error-count")
    if physician_edit_ratio is not None and (
        isinstance(physician_edit_ratio, bool)
        or not isinstance(physician_edit_ratio, (int, float))
        or not 0 <= float(physician_edit_ratio) <= 1
    ):
        raise RegenerativeLearningError("invalid-physician-edit-ratio")
    return LearningSignal(
        signal_ref=_ref(signal_ref, "invalid-signal-ref"),
        signal_type=signal_type,
        module=module,
        disposition=disposition,
        source_ref=_ref(source_ref, "invalid-source-ref"),
        artifact_version_ref=_ref(artifact_version_ref, "invalid-artifact-version-ref"),
        reviewer_role=_ref(reviewer_role, "invalid-reviewer-role"),
        reason_code=_ref(reason_code, "invalid-reason-code"),
        consequential_error_count=consequential_error_count,
        physician_edit_ratio=(
            None if physician_edit_ratio is None else float(physician_edit_ratio)
        ),
    )


def validation_signal(
    *,
    run_ref,
    module,
    adjudication_status,
    artifact_version_ref,
    reviewer_role,
    reason_code,
    consequential_error_count,
    physician_edit_ratio,
):
    """Map an existing validation/adjudication summary into RLI metadata."""
    signal_type = (
        "validation-failure"
        if consequential_error_count > 0 or adjudication_status == "rejected"
        else "validation-success"
    )
    disposition = (
        adjudication_status
        if adjudication_status in _ALLOWED_DISPOSITIONS
        else ("failed" if signal_type == "validation-failure" else "passed")
    )
    return build_learning_signal(
        signal_ref=f"validation:{_ref(run_ref, 'invalid-run-ref')}",
        signal_type=signal_type,
        module=module,
        disposition=disposition,
        source_ref=run_ref,
        artifact_version_ref=artifact_version_ref,
        reviewer_role=reviewer_role,
        reason_code=reason_code,
        consequential_error_count=consequential_error_count,
        physician_edit_ratio=physician_edit_ratio,
    )


def propose_improvement(
    *,
    candidate_ref,
    module,
    change_kind,
    source_signals,
    target_artifact_ref,
    target_version_ref,
    intended_use_changed=False,
):
    """Create a candidate change without applying it."""
    if module not in _ALLOWED_MODULES:
        raise RegenerativeLearningError("unsupported-module")
    if change_kind not in _ALLOWED_CHANGE_KINDS:
        raise RegenerativeLearningError("unsupported-change-kind")
    if not isinstance(source_signals, tuple) or not source_signals:
        raise RegenerativeLearningError("source-signals-required")
    if any(not isinstance(item, LearningSignal) for item in source_signals):
        raise RegenerativeLearningError("invalid-learning-signal")
    if any(
        not item.synthetic_or_deidentified
        or item.contains_raw_clinical_text
        or item.contains_direct_identifier
        for item in source_signals
    ):
        raise RegenerativeLearningError("safe-learning-signal-required")
    if any(item.module != module for item in source_signals):
        raise RegenerativeLearningError("cross-module-candidate-requires-explicit-design")
    refs = tuple(item.signal_ref for item in source_signals)
    if len(refs) != len(set(refs)):
        raise RegenerativeLearningError("duplicate-signal-ref")

    return ImprovementCandidate(
        candidate_ref=_ref(candidate_ref, "invalid-candidate-ref"),
        module=module,
        change_kind=change_kind,
        source_signal_refs=refs,
        target_artifact_ref=_ref(target_artifact_ref, "invalid-target-artifact-ref"),
        target_version_ref=_ref(target_version_ref, "invalid-target-version-ref"),
        intended_use_changed=bool(intended_use_changed),
    )


def evaluate_promotion(candidate, evidence):
    """Gate a candidate for the normal human-reviewed release process."""
    if not isinstance(candidate, ImprovementCandidate):
        return PromotionDecision(False, "invalid-candidate")
    if not isinstance(evidence, PromotionEvidence):
        return PromotionDecision(False, "invalid-evidence")
    if candidate.auto_apply or candidate.production_mutation_allowed:
        return PromotionDecision(False, "autonomous-mutation-forbidden")

    checks = (
        ("golden-set-required", evidence.golden_set_passed),
        ("torture-set-required", evidence.torture_set_passed),
        ("regression-required", evidence.regression_passed),
        ("safety-review-required", evidence.safety_review_passed),
        ("physician-adjudication-required", evidence.physician_adjudication_complete),
        ("clinical-owner-approval-required", evidence.clinical_owner_approved),
        ("technical-owner-approval-required", evidence.technical_owner_approved),
    )
    for reason, passed in checks:
        if passed is not True:
            return PromotionDecision(False, reason)

    if candidate.intended_use_changed and evidence.regulatory_review_passed is not True:
        return PromotionDecision(False, "regulatory-review-required")

    try:
        _ref(evidence.evaluation_set_ref, "evaluation-set-required")
        _ref(evidence.rollback_target_ref, "rollback-target-required")
    except RegenerativeLearningError as exc:
        return PromotionDecision(False, str(exc))

    return PromotionDecision(True, "eligible-for-reviewed-release")


__all__ = [
    "RLI_VERSION",
    "RegenerativeLearningError",
    "LearningSignal",
    "ImprovementCandidate",
    "PromotionEvidence",
    "PromotionDecision",
    "build_learning_signal",
    "validation_signal",
    "propose_improvement",
    "evaluate_promotion",
]
