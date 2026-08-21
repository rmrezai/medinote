import os
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")

from datetime import datetime, timezone

from fastapi.routing import APIRoute
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.main import app
from app.models import (
    ClinicalFact, ClinicalProblem, Contradiction, Encounter, Medication,
    MedicationState, Organization, Patient, ProblemEvidence,
    ClinicalDocument, DocumentSection,
)
from app.services.progress_service import generate_progress_document


def _db():
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return Session(engine)


def _seed(db: Session):
    org = Organization(name="Hospitalist Group")
    db.add(org); db.flush()
    pt = Patient(organization_id=org.id, first_name="Jane", last_name="Doe")
    db.add(pt); db.flush()
    enc = Encounter(patient_id=pt.id, organization_id=org.id, status="active")
    db.add(enc); db.flush()
    aki = ClinicalProblem(encounter_id=enc.id, name="Acute kidney injury", normalized_name="acute_kidney_injury", certainty="confirmed", status="improving", acuity_rank=20)
    db.add(aki); db.flush()
    fact = ClinicalFact(encounter_id=enc.id, fact_type="lab", concept="creatinine", value_numeric=1.4, units="mg/dL", observed_datetime=datetime(2026,8,20,10,tzinfo=timezone.utc), fact_state="current", confidence="high", is_current=True)
    db.add(fact); db.flush()
    db.add(ProblemEvidence(problem_id=aki.id, fact_id=fact.id, relationship="trajectory_support", evidence_strength="supporting"))
    med = Medication(encounter_id=enc.id, normalized_name="losartan", display_name="Losartan")
    db.add(med); db.flush()
    db.add(MedicationState(medication_id=med.id, domain="discharge", status="requires_decision", is_current=True, physician_confirmed=False))
    db.commit()
    return enc, aki, fact


def test_progress_routes_exist():
    routes = {(r.path, tuple(sorted(r.methods or []))) for r in app.routes if isinstance(r, APIRoute)}
    assert ("/api/v1/encounters/{encounter_id}/documents/progress", ("POST",)) in routes
    assert ("/api/v1/documents/{document_id}/progress", ("GET",)) in routes


def test_progress_document_is_persisted_and_evidence_linked():
    db = _db(); enc, aki, fact = _seed(db)
    result = generate_progress_document(db, enc.id, "daily")
    assert result["document_type"] == "progress"
    assert result["variant"] == "daily"
    assert len(result["sections"]) >= 3
    problem = next(s for s in result["sections"] if s["section_type"] == "assessment_plan_problem")
    assert problem["problem_id"] == aki.id
    assert problem["evidence"][0]["fact_id"] == fact.id
    assert "Acute kidney injury" in problem["generated_content"]
    assert db.get(ClinicalDocument, result["document_id"]) is not None
    assert db.query(DocumentSection).filter(DocumentSection.document_id == result["document_id"]).count() >= 3


def test_interval_hpi_is_two_sentences_and_does_not_invent_actions():
    db = _db(); enc, _, _ = _seed(db)
    result = generate_progress_document(db, enc.id, "daily")
    hpi = next(s for s in result["sections"] if s["section_type"] == "interval_hpi")["generated_content"]
    assert hpi.count(".") == 2
    assert "resume losartan" not in hpi.lower()
    assert result["review_required"] is True
    assert any("medication" in reason.lower() for reason in result["review_reasons"])


def test_unsupported_variant_rejected():
    db = _db(); enc, _, _ = _seed(db)
    try:
        generate_progress_document(db, enc.id, "magic")
    except ValueError as exc:
        assert "Unsupported progress note variant" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def test_unresolved_contradiction_forces_review():
    db = _db(); enc, _, _ = _seed(db)
    db.add(Contradiction(encounter_id=enc.id, category="oxygen", description="conflict", severity="high", status="unresolved")); db.commit()
    result = generate_progress_document(db, enc.id, "daily")
    assert result["review_required"] is True
    assert any("contradiction" in reason.lower() for reason in result["review_reasons"])


def test_progress_section_can_be_physician_edited():
    from app.services.progress_service import update_progress_section
    db = _db(); enc, _, _ = _seed(db)
    result = generate_progress_document(db, enc.id, "daily")
    section = result["sections"][0]
    updated = update_progress_section(db, result["document_id"], section["id"], "Physician edited interval summary.", "edit")
    assert updated["approval_status"] == "edited"
    assert updated["physician_content"] == "Physician edited interval summary."
