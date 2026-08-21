from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models import (
    ClinicalDocument, ClinicalFact, Contradiction, DocumentSection, Encounter,
    Medication, MedicationState, Organization, Patient, User,
)
from app.schemas.med_rec import MedRecDecision
from app.services.concurrency_service import ConcurrencyConflict, acquire_lease
from app.services.med_rec_service import confirm_discharge_state
from app.services.progress_service import (
    approve_progress_document, generate_progress_document, update_progress_section,
)
from app.services.security_service import require_finalizer


def make_db():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def seed(db):
    org = Organization(name="Step46")
    db.add(org); db.flush()
    resident = User(organization_id=org.id, email="resident46@test", display_name="Resident", role="resident", active=True)
    attending = User(organization_id=org.id, email="attending46@test", display_name="Attending A", role="attending", active=True)
    attending2 = User(organization_id=org.id, email="attending46b@test", display_name="Attending B", role="attending", active=True)
    db.add_all([resident, attending, attending2]); db.flush()
    pt = Patient(organization_id=org.id, mrn="S46", first_name="Concurrent", last_name="Patient")
    db.add(pt); db.flush()
    enc = Encounter(patient_id=pt.id, organization_id=org.id, status="active", identity_status="created_verified")
    db.add(enc); db.commit()
    return org, resident, attending, attending2, enc


def test_two_sessions_cannot_silently_overwrite_same_section():
    db=make_db(); _, resident, attending, _, enc=seed(db)
    generated=generate_progress_document(db, enc.id, "daily", attending.id)
    doc_id=generated["document_id"]
    sec=db.scalar(select(DocumentSection).where(DocumentSection.document_id==doc_id).order_by(DocumentSection.sort_order))
    stale_version=sec.edit_version

    first=update_progress_section(db, doc_id, sec.id, "Resident current edit", "edit", resident.id, expected_section_version=stale_version)
    assert first["edit_version"] == stale_version + 1

    with pytest.raises(ConcurrencyConflict):
        update_progress_section(db, doc_id, sec.id, "Attending stale overwrite", "edit", attending.id, expected_section_version=stale_version)

    db.refresh(sec)
    assert sec.physician_content == "Resident current edit"


def test_stale_document_version_cannot_be_approved():
    db=make_db(); _, resident, attending, _, enc=seed(db)
    generated=generate_progress_document(db, enc.id, "daily", attending.id)
    doc_id=generated["document_id"]
    doc=db.get(ClinicalDocument, doc_id)
    stale_doc_version=doc.edit_version
    sections=list(db.scalars(select(DocumentSection).where(DocumentSection.document_id==doc_id)))
    for sec in sections:
        update_progress_section(db, doc_id, sec.id, None, "accept", resident.id, expected_section_version=sec.edit_version)
    with pytest.raises(ConcurrencyConflict):
        approve_progress_document(db, doc_id, attending.id, expected_document_version=stale_doc_version)

    db.refresh(doc)
    result=approve_progress_document(db, doc_id, attending.id, expected_document_version=doc.edit_version)
    assert result["status"] == "approved"


def test_med_rec_rejects_second_physician_using_stale_state():
    db=make_db(); _, _, attending, attending2, enc=seed(db)
    med=Medication(encounter_id=enc.id, normalized_name="losartan", display_name="Losartan")
    db.add(med); db.flush()
    old=MedicationState(medication_id=med.id, domain="discharge", status="requires_decision", is_current=True)
    db.add(old); db.commit()

    a=MedRecDecision(status="stop", reason="AKI", expected_current_state_id=old.id, confirmed_by=attending.id)
    new=confirm_discharge_state(db, med.id, a)
    assert new.status == "stop" and new.is_current

    b=MedRecDecision(status="resume", reason="stale screen", expected_current_state_id=old.id, confirmed_by=attending2.id)
    with pytest.raises(ConcurrencyConflict):
        confirm_discharge_state(db, med.id, b)

    current=db.scalar(select(MedicationState).where(MedicationState.medication_id==med.id, MedicationState.domain=="discharge", MedicationState.is_current.is_(True)))
    assert current.status == "stop"
    assert current.confirmed_by == attending.id


def test_edit_lease_warns_second_active_editor():
    db=make_db(); _, resident, attending, _, enc=seed(db)
    doc=ClinicalDocument(encounter_id=enc.id, document_type="progress", variant="daily", generated_by=attending.id)
    db.add(doc); db.commit()
    first=acquire_lease(db,user=resident,encounter_id=enc.id,resource_type="document",resource_id=doc.id)
    second=acquire_lease(db,user=attending,encounter_id=enc.id,resource_type="document",resource_id=doc.id)
    assert first["acquired"] is True
    assert second["acquired"] is False
    assert second["holder_user_id"] == resident.id


def test_resident_can_edit_but_cannot_use_finalizer_role():
    db=make_db(); _, resident, attending, _, _=seed(db)
    with pytest.raises(HTTPException) as exc:
        require_finalizer(resident)
    assert exc.value.status_code == 403
    assert require_finalizer(attending).id == attending.id

def test_stale_contradiction_revision_is_rejected_before_adjudication():
    from app.services.contradiction_service import adjudicate_contradiction
    db=make_db(); _, _, attending, _, enc=seed(db)
    c=Contradiction(encounter_id=enc.id, category="oxygen", severity="high", status="unresolved", revision=2)
    db.add(c); db.commit()
    with pytest.raises(ConcurrencyConflict):
        adjudicate_contradiction(db, c.id, "new_clinical_decision", "Current bedside assessment", attending.id, "room air", expected_revision=1)
    db.refresh(c)
    assert c.status == "unresolved"
