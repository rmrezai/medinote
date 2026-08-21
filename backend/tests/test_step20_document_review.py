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
    ClinicalFact, ClinicalProblem, Encounter, Organization, Patient,
    ProblemEvidence, ClinicalDocument, DocumentSection, PhysicianEdit, SectionRevision,
)
from app.services.progress_service import (
    approve_progress_document, generate_progress_document, list_physician_edits,
    regenerate_progress_section, update_progress_section,
)


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
    db.commit()
    return enc


def test_step20_routes_exist():
    routes = {(r.path, tuple(sorted(r.methods or []))) for r in app.routes if isinstance(r, APIRoute)}
    assert ("/api/v1/documents/{document_id}/sections/{section_id}/regenerate", ("POST",)) in routes
    assert ("/api/v1/documents/{document_id}/approve", ("POST",)) in routes
    assert ("/api/v1/documents/{document_id}/edits", ("GET",)) in routes


def test_regeneration_preserves_original_and_creates_revision():
    db = _db(); enc = _seed(db)
    result = generate_progress_document(db, enc.id, "daily")
    section_data = next(s for s in result["sections"] if s["section_type"] == "assessment_plan_problem")
    section = db.get(DocumentSection, section_data["id"])
    original = section.generated_content

    # Make the structured problem state change, then regenerate from MCIF.
    problem = db.get(ClinicalProblem, section_data["problem_id"])
    problem.status = "worsening"
    db.commit()

    refreshed = regenerate_progress_section(db, result["document_id"], section.id, "Refresh from latest MCIF state")
    db.refresh(section)
    assert section.generated_content == original
    assert refreshed["original_generated_content"] == original
    assert refreshed["generated_content"] != original
    assert refreshed["regeneration_count"] == 1
    assert refreshed["approval_status"] == "pending"
    assert db.query(SectionRevision).filter(SectionRevision.section_id == section.id).count() == 1


def test_edit_history_records_accept_edit_and_regenerate():
    db = _db(); enc = _seed(db)
    result = generate_progress_document(db, enc.id, "daily")
    hpi = result["sections"][0]
    update_progress_section(db, result["document_id"], hpi["id"], "Physician revised HPI.", "edit")
    regenerate_progress_section(db, result["document_id"], hpi["id"], "Refresh")
    update_progress_section(db, result["document_id"], hpi["id"], None, "accept")
    edits = list_physician_edits(db, result["document_id"])
    assert [e.action for e in edits] == ["edit", "regenerate", "accept"]
    assert edits[0].original_generated_content
    assert edits[-1].final_physician_content
    assert db.query(PhysicianEdit).filter(PhysicianEdit.document_id == result["document_id"]).count() == 3


def test_document_cannot_be_approved_until_every_section_reviewed():
    db = _db(); enc = _seed(db)
    result = generate_progress_document(db, enc.id, "daily")
    pending = approve_progress_document(db, result["document_id"])
    assert pending["status"] == "draft"
    assert len(pending["pending_section_ids"]) == len(result["sections"])

    for section in result["sections"]:
        update_progress_section(db, result["document_id"], section["id"], None, "accept")
    approved = approve_progress_document(db, result["document_id"])
    assert approved["status"] == "approved"
    assert approved["approved_at"] is not None
    assert approved["pending_section_ids"] == []
    doc = db.get(ClinicalDocument, result["document_id"])
    assert doc.status == "approved"


def test_approved_document_blocks_further_section_mutation():
    db = _db(); enc = _seed(db)
    result = generate_progress_document(db, enc.id, "daily")
    for section in result["sections"]:
        update_progress_section(db, result["document_id"], section["id"], None, "accept")
    approve_progress_document(db, result["document_id"])
    section_id = result["sections"][0]["id"]
    try:
        regenerate_progress_section(db, result["document_id"], section_id)
    except ValueError as exc:
        assert "Approved/finalized" in str(exc)
    else:
        raise AssertionError("Expected approved document to block regeneration")
