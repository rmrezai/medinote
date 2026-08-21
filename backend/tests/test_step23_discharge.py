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
    ClinicalDocument, ClinicalFact, ClinicalProblem, DispositionState, Encounter,
    Medication, MedicationState, Organization, Patient, PendingItem, ProblemEvidence,
)
from app.services.audit_service import audit_document
from app.services.discharge_service import ALLOWED_VARIANTS, generate_discharge_document
from app.services.progress_service import approve_progress_document, regenerate_progress_section, update_progress_section


def _db():
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return Session(engine)


def _seed(db: Session, unresolved_med=False, pending=False, disposition=True):
    org = Organization(name="Hospitalist Group")
    db.add(org); db.flush()
    pt = Patient(organization_id=org.id, first_name="Jane", last_name="Doe")
    db.add(pt); db.flush()
    enc = Encounter(patient_id=pt.id, organization_id=org.id, status="active")
    db.add(enc); db.flush()
    problem = ClinicalProblem(encounter_id=enc.id, name="Acute kidney injury", normalized_name="acute_kidney_injury", certainty="possible", status="improving", acuity_rank=10)
    db.add(problem); db.flush()
    fact = ClinicalFact(encounter_id=enc.id, fact_type="lab", concept="creatinine", value_numeric=1.4, units="mg/dL", observed_datetime=datetime(2026,8,20,10,tzinfo=timezone.utc), fact_state="current", confidence="high", is_current=True)
    db.add(fact); db.flush()
    db.add(ProblemEvidence(problem_id=problem.id, fact_id=fact.id, relationship="support", evidence_strength="supporting"))
    med = Medication(encounter_id=enc.id, normalized_name="losartan", display_name="Losartan")
    db.add(med); db.flush()
    db.add(MedicationState(medication_id=med.id, domain="hospital", status="held", is_current=True, reason="AKI"))
    db.add(MedicationState(medication_id=med.id, domain="discharge", status="requires_decision" if unresolved_med else "stop", is_current=True, reason="AKI"))
    if pending:
        db.add(PendingItem(encounter_id=enc.id, item_type="lab", description="final blood culture", status="pending", clinical_significance="review result"))
    if disposition:
        db.add(DispositionState(encounter_id=enc.id, anticipated_destination="home", pt_recommendation="home", source_datetime=datetime.now(timezone.utc)))
    db.commit()
    return enc, problem


def test_discharge_routes_exist():
    routes = {(r.path, tuple(sorted(r.methods or []))) for r in app.routes if isinstance(r, APIRoute)}
    assert ("/api/v1/encounters/{encounter_id}/documents/discharge", ("POST",)) in routes
    assert ("/api/v1/documents/{document_id}/discharge", ("GET",)) in routes


def test_all_discharge_variants_generate():
    for variant in ALLOWED_VARIANTS:
        db = _db(); enc, _ = _seed(db)
        result = generate_discharge_document(db, enc.id, variant)
        assert result["variant"] == variant
        assert result["document_type"] == "discharge"
        assert db.get(ClinicalDocument, result["document_id"]) is not None


def test_summary_is_diagnosis_organized_and_preserves_uncertainty_and_evidence():
    db = _db(); enc, problem = _seed(db)
    result = generate_discharge_document(db, enc.id, "summary")
    course = next(s for s in result["sections"] if s["section_type"] == "hospital_course_problem")
    assert course["problem_id"] == problem.id
    assert "possible" in course["generated_content"].lower()
    assert "creatinine" in course["generated_content"].lower()
    assert len(course["evidence"]) == 1


def test_unresolved_discharge_medication_requires_review():
    db = _db(); enc, _ = _seed(db, unresolved_med=True)
    result = generate_discharge_document(db, enc.id, "summary")
    med = next(s for s in result["sections"] if s["section_type"] == "medication_transitions")
    assert "requires_decision" in med["generated_content"]
    assert result["review_required"] is True
    assert any("medication" in r.lower() for r in result["review_reasons"])


def test_pending_items_and_owner_uncertainty_are_explicit():
    db = _db(); enc, _ = _seed(db, pending=True)
    result = generate_discharge_document(db, enc.id, "summary")
    pending = next(s for s in result["sections"] if s["section_type"] == "pending_results")
    assert "final blood culture" in pending["generated_content"]
    assert "owner not established" in pending["generated_content"]


def test_discharge_uses_shared_review_regenerate_approve_flow():
    db = _db(); enc, _ = _seed(db)
    result = generate_discharge_document(db, enc.id, "short")
    section = result["sections"][0]
    refreshed = regenerate_progress_section(db, result["document_id"], section["id"], "refresh")
    assert refreshed["regeneration_count"] == 1
    for s in result["sections"]:
        update_progress_section(db, result["document_id"], s["id"], None, "accept")
    approved = approve_progress_document(db, result["document_id"])
    assert approved["status"] == "approved"


def test_audit_flags_unsupported_discharge_completion_claim():
    db = _db(); enc, _ = _seed(db)
    result = generate_discharge_document(db, enc.id, "summary")
    followup = next(s for s in result["sections"] if s["section_type"] == "follow_up")
    update_progress_section(db, result["document_id"], followup["id"], "Follow-up appointment is scheduled. Return precautions were reviewed.", "edit")
    audit = audit_document(db, result["document_id"])
    cats = {f.category for f in audit["flags"]}
    assert "unsupported_discharge_completion" in cats
    assert audit["blocking_flags"] >= 1


def test_disposition_without_destination_is_review_required_and_audit_flagged():
    db = _db(); enc, _ = _seed(db, disposition=False)
    result = generate_discharge_document(db, enc.id, "summary")
    assert any("destination" in r.lower() for r in result["review_reasons"])
    audit = audit_document(db, result["document_id"])
    assert any(f.category == "discharge_destination_unconfirmed" for f in audit["flags"])
