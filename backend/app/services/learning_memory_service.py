from collections import Counter, defaultdict
from dataclasses import asdict
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.regenerative_learning import LearningSignal
from app.models.learning import LearningPatternRecord, LearningSignalRecord


class LearningMemoryError(ValueError):
    pass


def _validate(signal):
    if not isinstance(signal, LearningSignal):
        raise LearningMemoryError("invalid-learning-signal")
    if signal.synthetic_or_deidentified is not True:
        raise LearningMemoryError("safe-learning-signal-required")
    if signal.contains_raw_clinical_text or signal.contains_direct_identifier:
        raise LearningMemoryError("safe-learning-signal-required")
    return signal


def persist_learning_signal(db: Session, organization_id, signal: LearningSignal):
    """Append one safe learning signal with organization-local idempotency."""
    signal = _validate(signal)
    existing = db.scalar(
        select(LearningSignalRecord).where(
            LearningSignalRecord.organization_id == organization_id,
            LearningSignalRecord.signal_ref == signal.signal_ref,
        )
    )
    if existing:
        current = {
            "signal_type": existing.signal_type,
            "module": existing.module,
            "disposition": existing.disposition,
            "source_ref": existing.source_ref,
            "artifact_version_ref": existing.artifact_version_ref,
            "reviewer_role": existing.reviewer_role,
            "reason_code": existing.reason_code,
            "consequential_error_count": existing.consequential_error_count,
            "physician_edit_ratio": existing.physician_edit_ratio,
        }
        expected = {
            "signal_type": signal.signal_type,
            "module": signal.module,
            "disposition": signal.disposition,
            "source_ref": signal.source_ref,
            "artifact_version_ref": signal.artifact_version_ref,
            "reviewer_role": signal.reviewer_role,
            "reason_code": signal.reason_code,
            "consequential_error_count": signal.consequential_error_count,
            "physician_edit_ratio": signal.physician_edit_ratio,
        }
        if current == expected:
            return existing, "duplicate"
        raise LearningMemoryError("signal-ref-conflict")

    record = LearningSignalRecord(
        organization_id=organization_id,
        signal_ref=signal.signal_ref,
        signal_type=signal.signal_type,
        module=signal.module,
        disposition=signal.disposition,
        source_ref=signal.source_ref,
        artifact_version_ref=signal.artifact_version_ref,
        reviewer_role=signal.reviewer_role,
        reason_code=signal.reason_code,
        consequential_error_count=signal.consequential_error_count,
        physician_edit_ratio=signal.physician_edit_ratio,
        synthetic_or_deidentified=signal.synthetic_or_deidentified,
        contains_raw_clinical_text=signal.contains_raw_clinical_text,
        contains_direct_identifier=signal.contains_direct_identifier,
        metadata_json={},
    )
    db.add(record)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise LearningMemoryError("signal-ref-conflict") from None
    return record, "accepted"


def rebuild_learning_patterns(db: Session, organization_id, *, min_occurrences=2):
    """Recompute organization-local patterns from safe append-only signals."""
    if type(min_occurrences) is not int or min_occurrences < 2:
        raise LearningMemoryError("invalid-min-occurrences")

    records = list(
        db.scalars(
            select(LearningSignalRecord).where(
                LearningSignalRecord.organization_id == organization_id
            )
        )
    )
    groups = defaultdict(list)
    for record in records:
        groups[(record.module, record.reason_code, record.artifact_version_ref)].append(record)

    summaries = []
    for (module, reason_code, version_ref), items in sorted(groups.items()):
        dispositions = Counter(item.disposition for item in items)
        refs = sorted(item.signal_ref for item in items)
        ready = len(items) >= min_occurrences
        existing = db.scalar(
            select(LearningPatternRecord).where(
                LearningPatternRecord.organization_id == organization_id,
                LearningPatternRecord.module == module,
                LearningPatternRecord.reason_code == reason_code,
                LearningPatternRecord.source_artifact_version_ref == version_ref,
            )
        )
        if existing is None:
            existing = LearningPatternRecord(
                organization_id=organization_id,
                module=module,
                reason_code=reason_code,
                source_artifact_version_ref=version_ref,
                occurrences=len(items),
                dispositions=dict(sorted(dispositions.items())),
                signal_refs=refs,
                ready_for_candidate_review=ready,
            )
            db.add(existing)
        else:
            existing.occurrences = len(items)
            existing.dispositions = dict(sorted(dispositions.items()))
            existing.signal_refs = refs
            existing.ready_for_candidate_review = ready
        summaries.append(existing)
    db.flush()
    return tuple(summaries)


def patterns_ready_for_review(db: Session, organization_id):
    return tuple(
        db.scalars(
            select(LearningPatternRecord).where(
                LearningPatternRecord.organization_id == organization_id,
                LearningPatternRecord.ready_for_candidate_review.is_(True),
            )
        )
    )
