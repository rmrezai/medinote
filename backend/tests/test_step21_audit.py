import os
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from fastapi.routing import APIRoute

from app.db.base import Base
from app.main import app
from app.models import Organization, Patient, Encounter, ClinicalProblem, Medication, MedicationState, Contradiction, Procedure, SafetyFlag
from app.services.progress_service import generate_progress_document, update_progress_section, approve_progress_document
from app.services.audit_service import audit_document, resolve_flag, finalize_document


def _db():
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return Session(engine)


def _seed(db):
    org=Organization(name="Group"); db.add(org); db.flush()
    pt=Patient(organization_id=org.id, first_name="Test", last_name="Patient"); db.add(pt); db.flush()
    enc=Encounter(patient_id=pt.id, organization_id=org.id, status="active"); db.add(enc); db.flush()
    p=ClinicalProblem(encounter_id=enc.id, name="Aspiration pneumonia", normalized_name="aspiration_pneumonia", certainty="possible", status="active", acuity_rank=10); db.add(p)
    med=Medication(encounter_id=enc.id, normalized_name="losartan", display_name="Losartan"); db.add(med); db.flush()
    db.add(MedicationState(medication_id=med.id, domain="hospital", status="held", is_current=True))
    db.commit(); return enc


def test_step21_routes_exist():
    routes={(r.path, tuple(sorted(r.methods or []))) for r in app.routes if isinstance(r, APIRoute)}
    assert ("/api/v1/documents/{document_id}/audit", ("POST",)) in routes
    assert ("/api/v1/documents/{document_id}/safety-flags", ("GET",)) in routes
    assert ("/api/v1/safety-flags/{flag_id}/resolve", ("POST",)) in routes
    assert ("/api/v1/documents/{document_id}/finalize", ("POST",)) in routes


def test_audit_flags_certainty_and_medication_conflict():
    db=_db(); enc=_seed(db)
    doc=generate_progress_document(db, enc.id, "daily")
    sec=doc["sections"][0]
    update_progress_section(db, doc["document_id"], sec["id"], "Aspiration pneumonia. Continue Losartan.", "edit")
    result=audit_document(db, doc["document_id"])
    cats={f.category for f in result["flags"]}
    assert "certainty_mismatch" in cats
    assert "medication_conflict" in cats
    assert result["blocking_flags"] >= 2


def test_audit_flags_unsupported_exam_and_procedure_state():
    db=_db(); enc=_seed(db)
    db.add(Procedure(encounter_id=enc.id, procedure_name="bronchoscopy", status="planned")); db.commit()
    doc=generate_progress_document(db, enc.id, "daily")
    sec=doc["sections"][0]
    update_progress_section(db, doc["document_id"], sec["id"], "Lungs clear. Patient underwent bronchoscopy.", "edit")
    result=audit_document(db, doc["document_id"])
    cats={f.category for f in result["flags"]}
    assert "unsupported_exam" in cats
    assert "procedure_state_error" in cats


def test_unresolved_contradiction_becomes_safety_flag():
    db=_db(); enc=_seed(db)
    db.add(Contradiction(encounter_id=enc.id, category="respiratory", severity="high", description="Room air conflicts with 2 L NC", status="unresolved")); db.commit()
    doc=generate_progress_document(db, enc.id, "daily")
    result=audit_document(db, doc["document_id"])
    assert any(f.category == "unresolved_contradiction" for f in result["flags"])


def test_finalization_requires_approval_and_no_blockers():
    db=_db(); enc=_seed(db)
    doc=generate_progress_document(db, enc.id, "daily")
    try:
        finalize_document(db, doc["document_id"])
    except ValueError as exc:
        assert "approved" in str(exc)
    else:
        raise AssertionError("Expected pre-approval finalization to fail")

    # Approve clean generated sections.
    for s in doc["sections"]:
        update_progress_section(db, doc["document_id"], s["id"], None, "accept")
    approve_progress_document(db, doc["document_id"])
    finalized=finalize_document(db, doc["document_id"])
    assert finalized["status"] == "finalized"


def test_blocking_flag_can_be_resolved_but_reaudit_recreates_if_text_unchanged():
    db=_db(); enc=_seed(db)
    doc=generate_progress_document(db, enc.id, "daily")
    sec=doc["sections"][0]
    update_progress_section(db, doc["document_id"], sec["id"], "Continue Losartan.", "edit")
    result=audit_document(db, doc["document_id"])
    flag=next(f for f in result["flags"] if f.category == "medication_conflict")
    resolved=resolve_flag(db, flag.id, "Reviewed")
    assert resolved.status == "resolved"
    rerun=audit_document(db, doc["document_id"])
    assert any(f.category == "medication_conflict" for f in rerun["flags"])
