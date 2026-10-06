import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.base import Base
import app.models  # noqa: F401
from app.core import regenerative_learning as rli
from app.services.learning_memory_service import (
    LearningMemoryError,
    patterns_ready_for_review,
    persist_learning_signal,
    rebuild_learning_patterns,
)


def make_db():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return Session(engine)


def make_signal(ref, *, reason="factual-correction", module="progress", disposition="edited"):
    return rli.build_learning_signal(
        signal_ref=ref,
        signal_type="physician-edit",
        module=module,
        disposition=disposition,
        source_ref=f"run-{ref}",
        artifact_version_ref="progress-v1",
        reviewer_role="attending",
        reason_code=reason,
        physician_edit_ratio=0.1,
    )


def test_step52_learning_memory_is_append_only_and_idempotent():
    db = make_db()
    org_id = uuid.uuid4()
    signal = make_signal("sig-1")
    first, outcome1 = persist_learning_signal(db, org_id, signal)
    second, outcome2 = persist_learning_signal(db, org_id, signal)
    assert outcome1 == "accepted"
    assert outcome2 == "duplicate"
    assert first.id == second.id


def test_step52_conflicting_signal_ref_fails_closed():
    db = make_db()
    org_id = uuid.uuid4()
    persist_learning_signal(db, org_id, make_signal("sig-2"))
    try:
        persist_learning_signal(db, org_id, make_signal("sig-2", reason="different-reason"))
        assert False, "expected conflict"
    except LearningMemoryError as exc:
        assert str(exc) == "signal-ref-conflict"


def test_step52_recurring_pattern_becomes_review_candidate_only():
    db = make_db()
    org_id = uuid.uuid4()
    persist_learning_signal(db, org_id, make_signal("sig-3"))
    persist_learning_signal(db, org_id, make_signal("sig-4"))
    persist_learning_signal(db, org_id, make_signal("sig-5", reason="other"))
    patterns = rebuild_learning_patterns(db, org_id, min_occurrences=2)
    repeated = next(x for x in patterns if x.reason_code == "factual-correction")
    assert repeated.occurrences == 2
    assert repeated.ready_for_candidate_review is True
    ready = patterns_ready_for_review(db, org_id)
    assert [x.reason_code for x in ready] == ["factual-correction"]


def test_step52_pattern_scope_is_tenant_local():
    db = make_db()
    org_a = uuid.uuid4()
    org_b = uuid.uuid4()
    persist_learning_signal(db, org_a, make_signal("sig-a1"))
    persist_learning_signal(db, org_a, make_signal("sig-a2"))
    persist_learning_signal(db, org_b, make_signal("sig-b1"))
    rebuild_learning_patterns(db, org_a, min_occurrences=2)
    rebuild_learning_patterns(db, org_b, min_occurrences=2)
    assert len(patterns_ready_for_review(db, org_a)) == 1
    assert len(patterns_ready_for_review(db, org_b)) == 0
