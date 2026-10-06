import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.candidate_evaluation import SuiteResult
from app.core import regenerative_learning as rli
from app.db.base import Base
import app.models  # noqa: F401
from app.models.learning import LearningPatternRecord
from app.services.learning_memory_service import (
    persist_learning_signal,
    rebuild_learning_patterns,
)
from app.services.candidate_review_service import (
    create_candidate_from_pattern,
    human_review_queue,
    record_candidate_evaluation,
)


def make_db():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return Session(engine)


def signal(ref):
    return rli.build_learning_signal(
        signal_ref=ref,
        signal_type="physician-edit",
        module="progress",
        disposition="edited",
        source_ref=f"run-{ref}",
        artifact_version_ref="progress-v1",
        reviewer_role="attending",
        reason_code="factual-correction",
        physician_edit_ratio=0.1,
    )


def ready_pattern(db, org_id):
    persist_learning_signal(db, org_id, signal("sig-1"))
    persist_learning_signal(db, org_id, signal("sig-2"))
    rebuild_learning_patterns(db, org_id, min_occurrences=2)
    return db.query(LearningPatternRecord).filter_by(
        organization_id=org_id,
        reason_code="factual-correction",
    ).one()


def passing_results():
    return (
        SuiteResult("golden-case", True, 0.98, 0.99),
        SuiteResult("chart-torture", True),
        SuiteResult("full-regression", True),
        SuiteResult("clinical-safety", True),
    )


def test_step53_ready_pattern_creates_candidate_without_auto_apply():
    db = make_db()
    org_id = uuid.uuid4()
    pattern = ready_pattern(db, org_id)
    candidate, plan, outcome = create_candidate_from_pattern(
        db,
        org_id,
        pattern.id,
        candidate_ref="cand-1",
        change_kind="deterministic-rule",
        target_artifact_ref="progress-reconciliation",
        target_version_ref="v1",
        baseline_ref="release-v1",
        evaluation_set_ref="eval-v2",
    )
    assert outcome == "accepted"
    assert candidate.auto_apply is False
    assert candidate.production_mutation_allowed is False
    assert plan.human_review_required is True
    assert plan.auto_deploy_allowed is False


def test_step53_passing_evaluation_enters_human_review_queue_only():
    db = make_db()
    org_id = uuid.uuid4()
    pattern = ready_pattern(db, org_id)
    create_candidate_from_pattern(
        db,
        org_id,
        pattern.id,
        candidate_ref="cand-2",
        change_kind="deterministic-rule",
        target_artifact_ref="progress-reconciliation",
        target_version_ref="v1",
        baseline_ref="release-v1",
        evaluation_set_ref="eval-v2",
    )
    evaluation, outcome = record_candidate_evaluation(
        db,
        org_id,
        "cand-2",
        evaluation_ref="evalrun-1",
        suite_results=passing_results(),
    )
    assert outcome == "accepted"
    assert evaluation.passed is True
    assert evaluation.review_queue_status == "awaiting-human-approval"
    assert evaluation.automatic_promotion_allowed is False
    assert evaluation.production_mutation_performed is False
    queue = human_review_queue(db, org_id)
    assert [x.evaluation_ref for x in queue] == ["evalrun-1"]


def test_step53_regression_blocks_queue_entry():
    db = make_db()
    org_id = uuid.uuid4()
    pattern = ready_pattern(db, org_id)
    create_candidate_from_pattern(
        db,
        org_id,
        pattern.id,
        candidate_ref="cand-3",
        change_kind="deterministic-rule",
        target_artifact_ref="progress-reconciliation",
        target_version_ref="v1",
        baseline_ref="release-v1",
        evaluation_set_ref="eval-v2",
    )
    bad = (
        SuiteResult("golden-case", True, 0.99, 0.98),
        SuiteResult("chart-torture", True),
        SuiteResult("full-regression", True),
        SuiteResult("clinical-safety", True),
    )
    evaluation, _ = record_candidate_evaluation(
        db,
        org_id,
        "cand-3",
        evaluation_ref="evalrun-2",
        suite_results=bad,
    )
    assert evaluation.passed is False
    assert evaluation.reason == "baseline-regression"
    assert human_review_queue(db, org_id) == ()


def test_step53_evaluation_is_append_only_by_evaluation_ref():
    db = make_db()
    org_id = uuid.uuid4()
    pattern = ready_pattern(db, org_id)
    create_candidate_from_pattern(
        db,
        org_id,
        pattern.id,
        candidate_ref="cand-4",
        change_kind="deterministic-rule",
        target_artifact_ref="progress-reconciliation",
        target_version_ref="v1",
        baseline_ref="release-v1",
        evaluation_set_ref="eval-v2",
    )
    first, outcome1 = record_candidate_evaluation(
        db,
        org_id,
        "cand-4",
        evaluation_ref="evalrun-3",
        suite_results=passing_results(),
    )
    second, outcome2 = record_candidate_evaluation(
        db,
        org_id,
        "cand-4",
        evaluation_ref="evalrun-3",
        suite_results=passing_results(),
    )
    assert outcome1 == "accepted"
    assert outcome2 == "duplicate"
    assert first.id == second.id
