from datetime import datetime, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db.base import Base

from app.models import ClinicalDocument, DocumentSection, Encounter, Organization, Patient, SourceDocument, User
from app.services.analysis_service import analyze_encounter
from app.services.audit_service import audit_document, finalize_document, refresh_document
from app.services.progress_service import generate_progress_document, update_progress_section, approve_progress_document
from app.services.state_version_service import bump_state_version


def make_db():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def seed(db):
    org = Organization(name="Step45")
    db.add(org); db.flush()
    user = User(organization_id=org.id, email="step45@example.test", display_name="Dr Test", role="attending", active=True)
    db.add(user); db.flush()
    pt = Patient(organization_id=org.id, mrn="S45", first_name="Test", last_name="Patient")
    db.add(pt); db.flush()
    enc = Encounter(patient_id=pt.id, organization_id=org.id, status="active", identity_status="created_verified", clinical_state_version=1)
    db.add(enc); db.flush()
    src = SourceDocument(encounter_id=enc.id, document_type="progress_note", source_datetime=datetime(2026,8,20,8,0,tzinfo=timezone.utc), raw_text="AKI. Creatinine 2.0.", identity_status="not_asserted")
    db.add(src); bump_state_version(db, enc.id); db.commit()
    analyze_encounter(db, enc.id)
    return user, enc


def accept_all(db, doc_id, user_id):
    sections=list(db.scalars(select(DocumentSection).where(DocumentSection.document_id==doc_id)))
    for sec in sections:
        update_progress_section(db, doc_id, sec.id, None, "accept", user_id)
    return approve_progress_document(db, doc_id, user_id)


def test_new_chart_data_blocks_finalization_until_refresh():
    db=make_db()
    user, enc=seed(db)
    generated=generate_progress_document(db, enc.id, "daily", user.id)
    doc_id=generated["document_id"]
    assert generated["generated_state_version"] == enc.clinical_state_version
    assert generated["stale"] is False
    assert accept_all(db, doc_id, user.id)["status"] == "approved"

    # New clinically relevant chart input arrives after physician approval.
    newer=SourceDocument(encounter_id=enc.id, document_type="lab", source_datetime=datetime(2026,8,20,12,0,tzinfo=timezone.utc), raw_text="Creatinine 1.4.", identity_status="not_asserted")
    db.add(newer); bump_state_version(db, enc.id); db.commit(); db.refresh(enc)

    audit=audit_document(db, doc_id)
    stale=[f for f in audit["flags"] if f.category=="stale_clinical_state"]
    assert len(stale)==1
    assert stale[0].severity=="critical"

    blocked=finalize_document(db, doc_id, user.id)
    assert blocked["status"] == "approved"
    assert blocked["blocking_flag_ids"]

    refreshed=refresh_document(db, doc_id, user.id)
    assert refreshed["stale"] is False
    assert refreshed["generated_state_version"] == refreshed["current_state_version"]
    assert refreshed["pending_review"] is True

    doc=db.get(ClinicalDocument, doc_id)
    assert doc.status == "in_review"
    sections=list(db.scalars(select(DocumentSection).where(DocumentSection.document_id==doc_id)))
    assert sections and all(s.approval_status=="pending" for s in sections)
    assert all(s.regeneration_count >= 1 for s in sections)

    # Cannot approve/finalize until physician re-reviews refreshed sections.
    pre=approve_progress_document(db, doc_id, user.id)
    assert pre["pending_section_ids"]
    assert accept_all(db, doc_id, user.id)["status"] == "approved"
    final=finalize_document(db, doc_id, user.id)
    assert final["status"] == "finalized"
    assert final["blocking_flag_ids"] == []


def test_finalized_document_is_immutable_on_refresh():
    db=make_db()
    user, enc=seed(db)
    generated=generate_progress_document(db, enc.id, "daily", user.id)
    doc_id=generated["document_id"]
    accept_all(db, doc_id, user.id)
    final=finalize_document(db, doc_id, user.id)
    assert final["status"] == "finalized"
    try:
        refresh_document(db, doc_id, user.id)
    except ValueError as exc:
        assert "immutable" in str(exc).lower()
    else:
        raise AssertionError("Finalized document refresh should fail")
