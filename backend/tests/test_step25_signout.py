from datetime import datetime, timezone
from uuid import uuid4

import os
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
import app.models  # noqa: F401
from app.models import Encounter, Organization, Patient, ClinicalProblem, ClinicalFact, PendingItem, Medication, MedicationState
from app.services.signout_service import generate_signout_document
from app.services.progress_service import update_progress_section, approve_progress_document, regenerate_progress_section
from app.services.audit_service import audit_document


def db_session():
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return Session(engine)


def seed(db):
    org = Organization(name="Test")
    db.add(org); db.flush()
    patient = Patient(organization_id=org.id, first_name="A", last_name="B")
    db.add(patient); db.flush()
    enc = Encounter(patient_id=patient.id, organization_id=org.id, admission_datetime=datetime.now(timezone.utc), service="Hospital Medicine")
    db.add(enc); db.flush()
    p = ClinicalProblem(encounter_id=enc.id, name="Acute kidney injury", normalized_name="acute_kidney_injury", certainty="confirmed", acuity_rank=2, status="improving")
    db.add(p)
    db.add(PendingItem(encounter_id=enc.id, item_type="lab", description="repeat BMP", status="pending"))
    med = Medication(encounter_id=enc.id, normalized_name="losartan", display_name="Losartan")
    db.add(med); db.flush()
    db.add(MedicationState(medication_id=med.id, domain="hospital", status="held", is_current=True, reason="AKI"))
    db.commit()
    return enc


def test_signout_generates_core_sections_without_invented_code_status():
    db = db_session(); enc = seed(db)
    doc = generate_signout_document(db, enc.id, "night")
    types = [s["section_type"] for s in doc["sections"]]
    assert "one_liner" in types
    assert "current_treatment" in types
    assert "pending_items" in types
    assert "overnight_risks" in types
    assert "contingencies" in types
    assert "code_status" in types
    code = next(s for s in doc["sections"] if s["section_type"] == "code_status")
    assert "not included" in code["generated_content"].lower()
    assert "full code" not in code["generated_content"].lower()


def test_signout_code_status_appears_only_when_documented():
    db = db_session(); enc = seed(db)
    db.add(ClinicalFact(encounter_id=enc.id, fact_type="administrative", concept="code_status", value_text="DNR/DNI", is_current=True))
    db.commit()
    doc = generate_signout_document(db, enc.id, "standard")
    code = next(s for s in doc["sections"] if s["section_type"] == "code_status")
    assert "DNR/DNI" in code["generated_content"]


def test_signout_uses_shared_accept_regenerate_approve_pipeline():
    db = db_session(); enc = seed(db)
    doc = generate_signout_document(db, enc.id, "short")
    for s in doc["sections"]:
        update_progress_section(db, doc["document_id"], s["id"], None, "accept")
    approved = approve_progress_document(db, doc["document_id"])
    assert approved["status"] == "approved"


def test_signout_regeneration_works_before_approval():
    db = db_session(); enc = seed(db)
    doc = generate_signout_document(db, enc.id, "standard")
    pending = next(s for s in doc["sections"] if s["section_type"] == "pending_items")
    regenerated = regenerate_progress_section(db, doc["document_id"], pending["id"])
    assert regenerated["regeneration_count"] == 1
    assert "repeat BMP" in regenerated["generated_content"]


def test_audit_flags_manually_invented_code_status():
    db = db_session(); enc = seed(db)
    doc = generate_signout_document(db, enc.id, "standard")
    code = next(s for s in doc["sections"] if s["section_type"] == "code_status")
    update_progress_section(db, doc["document_id"], code["id"], "Code status: Full Code.", "edit")
    result = audit_document(db, doc["document_id"])
    cats = {f.category for f in result["flags"]}
    assert "unsupported_code_status" in cats
