from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.candidate_evaluation import (
    SuiteResult,
    build_evaluation_plan,
    evaluate_candidate,
)
from app.core.regenerative_learning import LearningSignal, ImprovementCandidate, propose_improvement
from app.models.learning import (
    LearningCandidateRecord,
    LearningEvaluationRecord,
    LearningPatternRecord,
    LearningSignalRecord,
)


class CandidateReviewError(ValueError):
    pass


def _signal_from_record(record):
    return LearningSignal(
        signal_ref=record.signal_ref,
        signal_type=record.signal_type,
        module=record.module,
        disposition=record.disposition,
        source_ref=record.source_ref,
        artifact_version_ref=record.artifact_version_ref,
        reviewer_role=record.reviewer_role,
        reason_code=record.reason_code,
        consequential_error_count=record.consequential_error_count,
        physician_edit_ratio=(
            None if record.physician_edit_ratio is None else float(record.physician_edit_ratio)
        ),
        synthetic_or_deidentified=record.synthetic_or_deidentified,
        contains_raw_clinical_text=record.contains_raw_clinical_text,
        contains_direct_identifier=record.contains_direct_identifier,
    )


def create_candidate_from_pattern(
    db: Session,
    organization_id,
    pattern_id,
    *,
    candidate_ref,
    change_kind,
    target_artifact_ref,
    target_version_ref,
    baseline_ref,
    evaluation_set_ref,
    intended_use_changed=False,
):
    pattern = db.scalar(
        select(LearningPatternRecord).where(
            LearningPatternRecord.id == pattern_id,
            LearningPatternRecord.organization_id == organization_id,
        )
    )
    if pattern is None:
        raise CandidateReviewError("pattern-not-found")
    if pattern.ready_for_candidate_review is not True:
        raise CandidateReviewError("pattern-not-ready")

    records = list(
        db.scalars(
            select(LearningSignalRecord).where(
                LearningSignalRecord.organization_id == organization_id,
                LearningSignalRecord.signal_ref.in_(pattern.signal_refs),
            )
        )
    )
    if {r.signal_ref for r in records} != set(pattern.signal_refs):
        raise CandidateReviewError("pattern-signal-mismatch")

    signals = tuple(_signal_from_record(record) for record in records)
    candidate = propose_improvement(
        candidate_ref=candidate_ref,
        module=pattern.module,
        change_kind=change_kind,
        source_signals=signals,
        target_artifact_ref=target_artifact_ref,
        target_version_ref=target_version_ref,
        intended_use_changed=intended_use_changed,
    )
    plan = build_evaluation_plan(
        candidate,
        baseline_ref=baseline_ref,
        evaluation_set_ref=evaluation_set_ref,
    )

    existing = db.scalar(
        select(LearningCandidateRecord).where(
            LearningCandidateRecord.organization_id == organization_id,
            LearningCandidateRecord.candidate_ref == candidate.candidate_ref,
        )
    )
    if existing is not None:
        expected = {
            "pattern_id": pattern.id,
            "module": candidate.module,
            "reason_code": pattern.reason_code,
            "change_kind": candidate.change_kind,
            "target_artifact_ref": candidate.target_artifact_ref,
            "target_version_ref": candidate.target_version_ref,
            "source_signal_refs": sorted(candidate.source_signal_refs),
            "baseline_ref": plan.baseline_ref,
            "evaluation_set_ref": plan.evaluation_set_ref,
            "intended_use_changed": candidate.intended_use_changed,
        }
        current = {
            "pattern_id": existing.pattern_id,
            "module": existing.module,
            "reason_code": existing.reason_code,
            "change_kind": existing.change_kind,
            "target_artifact_ref": existing.target_artifact_ref,
            "target_version_ref": existing.target_version_ref,
            "source_signal_refs": sorted(existing.source_signal_refs),
            "baseline_ref": existing.baseline_ref,
            "evaluation_set_ref": existing.evaluation_set_ref,
            "intended_use_changed": existing.intended_use_changed,
        }
        if current == expected:
            return existing, plan, "duplicate"
        raise CandidateReviewError("candidate-ref-conflict")

    record = LearningCandidateRecord(
        organization_id=organization_id,
        pattern_id=pattern.id,
        candidate_ref=candidate.candidate_ref,
        module=candidate.module,
        reason_code=pattern.reason_code,
        change_kind=candidate.change_kind,
        target_artifact_ref=candidate.target_artifact_ref,
        target_version_ref=candidate.target_version_ref,
        source_signal_refs=list(candidate.source_signal_refs),
        baseline_ref=plan.baseline_ref,
        evaluation_set_ref=plan.evaluation_set_ref,
        intended_use_changed=candidate.intended_use_changed,
        status="evaluation-pending",
        auto_apply=False,
        production_mutation_allowed=False,
    )
    db.add(record)
    db.flush()
    return record, plan, "accepted"


def _candidate_from_record(record):
    return ImprovementCandidate(
        candidate_ref=record.candidate_ref,
        module=record.module,
        change_kind=record.change_kind,
        source_signal_refs=tuple(record.source_signal_refs),
        target_artifact_ref=record.target_artifact_ref,
        target_version_ref=record.target_version_ref,
        intended_use_changed=record.intended_use_changed,
        status="proposed",
        auto_apply=False,
        production_mutation_allowed=False,
    )


def record_candidate_evaluation(
    db: Session,
    organization_id,
    candidate_ref,
    *,
    evaluation_ref,
    suite_results,
):
    candidate_record = db.scalar(
        select(LearningCandidateRecord).where(
            LearningCandidateRecord.organization_id == organization_id,
            LearningCandidateRecord.candidate_ref == candidate_ref,
        )
    )
    if candidate_record is None:
        raise CandidateReviewError("candidate-not-found")
    if not isinstance(suite_results, tuple) or any(
        not isinstance(item, SuiteResult) for item in suite_results
    ):
        raise CandidateReviewError("invalid-suite-results")

    candidate = _candidate_from_record(candidate_record)
    plan = build_evaluation_plan(
        candidate,
        baseline_ref=candidate_record.baseline_ref,
        evaluation_set_ref=candidate_record.evaluation_set_ref,
    )
    result = evaluate_candidate(plan, suite_results)

    existing = db.scalar(
        select(LearningEvaluationRecord).where(
            LearningEvaluationRecord.organization_id == organization_id,
            LearningEvaluationRecord.evaluation_ref == evaluation_ref,
        )
    )
    serial_results = [
        {
            "suite": item.suite,
            "passed": item.passed,
            "baseline_score": item.baseline_score,
            "candidate_score": item.candidate_score,
            "lower_is_better": item.lower_is_better,
        }
        for item in result.suite_results
    ]
    if existing is not None:
        if (
            existing.candidate_ref == candidate_ref
            and existing.passed == result.passed
            and existing.reason == result.reason
            and existing.suite_results == serial_results
            and existing.review_queue_status == result.review_queue_status
        ):
            return existing, "duplicate"
        raise CandidateReviewError("evaluation-ref-conflict")

    record = LearningEvaluationRecord(
        organization_id=organization_id,
        candidate_id=candidate_record.id,
        candidate_ref=candidate_ref,
        evaluation_ref=evaluation_ref,
        passed=result.passed,
        reason=result.reason,
        suite_results=serial_results,
        improved_or_equal=result.improved_or_equal,
        review_queue_status=result.review_queue_status,
        automatic_promotion_allowed=False,
        production_mutation_performed=False,
    )
    db.add(record)
    candidate_record.status = result.review_queue_status
    db.flush()
    return record, "accepted"


def human_review_queue(db: Session, organization_id):
    return tuple(
        db.scalars(
            select(LearningEvaluationRecord).where(
                LearningEvaluationRecord.organization_id == organization_id,
                LearningEvaluationRecord.review_queue_status == "awaiting-human-approval",
                LearningEvaluationRecord.passed.is_(True),
            )
        )
    )
