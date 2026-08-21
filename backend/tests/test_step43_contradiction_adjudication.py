from datetime import date, datetime, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models import (
    ClinicalDocument, ClinicalFact, ConsultantRecommendation, Contradiction,
    DocumentSection, Encounter, Medication, MedicationState, Organization,
    Patient, SourceDocument, User,
)
from app.services.analysis_service import analyze_encounter
from app.services.audit_service import audit_document, finalize_document
from app.services.contradiction_service import adjudicate_contradiction
from app.services.overview_service import build_patient_overview
from app.services.progress_service import approve_progress_document, generate_progress_document, update_progress_section
from app.services.signout_service import generate_signout_document

UTC = timezone.utc


def make_db():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    org = Organization(name="Step43 Group"); db.add(org); db.flush()
    user = User(organization_id=org.id, email="attending@step43.test", display_name="Attending", role="attending", active=True); db.add(user); db.flush()
    patient = Patient(organization_id=org.id, mrn="S43-001", first_name="Synthetic", last_name="Adjudication", date_of_birth=date(1950,1,1), sex="male"); db.add(patient); db.flush()
    enc = Encounter(patient_id=patient.id, organization_id=org.id, admission_datetime=datetime(2026,8,18,8,tzinfo=UTC), service="Hospital Medicine", attending_user_id=user.id); db.add(enc); db.commit()
    return db, enc, user


def source(db, enc, user, dtype, when, text, service=None):
    row = SourceDocument(encounter_id=enc.id, document_type=dtype, source_datetime=when, raw_text=text, author_service=service, source_system="step43", imported_by=user.id)
    db.add(row); db.commit(); return row


def test_step43_physician_adjudication_updates_state_regenerates_and_finalizes():
    db, enc, user = make_db()
    source(db, enc, user, "hp", datetime(2026,8,18,8,tzinfo=UTC), "Pneumonia. Acute kidney injury. Cr 2.5. Currently on 4 L NC.")
    source(db, enc, user, "progress_note", datetime(2026,8,19,10,tzinfo=UTC), "Copied forward: currently on 4 L NC.")
    source(db, enc, user, "nursing_note", datetime(2026,8,19,10,tzinfo=UTC), "Patient is on room air.")
    source(db, enc, user, "consult_note", datetime(2026,8,19,9,tzinfo=UTC), "Cardiology recommends continue furosemide.", "Cardiology")
    source(db, enc, user, "consult_note", datetime(2026,8,19,9,tzinfo=UTC), "Nephrology recommends hold furosemide.", "Nephrology")
    analyze_encounter(db, enc.id)

    progress = generate_progress_document(db, enc.id, "daily", user.id)
    signout = generate_signout_document(db, enc.id, "night", user.id)

    contradictions = list(db.scalars(select(Contradiction).where(Contradiction.encounter_id == enc.id, Contradiction.status == "unresolved")))
    assert {c.category for c in contradictions} >= {"temporal_fact_conflict", "consultant_recommendation_conflict"}

    oxygen = next(c for c in contradictions if c.category == "temporal_fact_conflict")
    # Select the source whose fact is room air, regardless of A/B ordering.
    a = db.get(ClinicalFact, oxygen.source_a_id) if oxygen.source_a_type == "clinical_fact" else None
    b = db.get(ClinicalFact, oxygen.source_b_id) if oxygen.source_b_type == "clinical_fact" else None
    oxygen_choice = "select_source_a" if a and a.value_text == "room_air" else "select_source_b"
    result1 = adjudicate_contradiction(db, oxygen.id, oxygen_choice, "Nursing bedside oxygen documentation is the current same-time source.", user.id)
    assert result1["status"] == "resolved"
    assert result1["regenerated_section_ids"]

    consult_conflict = db.scalar(select(Contradiction).where(Contradiction.encounter_id == enc.id, Contradiction.category == "consultant_recommendation_conflict", Contradiction.status == "unresolved"))
    ca = db.get(ConsultantRecommendation, consult_conflict.source_a_id)
    cb = db.get(ConsultantRecommendation, consult_conflict.source_b_id)
    consult_choice = "select_source_a" if ca.service == "Nephrology" else "select_source_b"
    result2 = adjudicate_contradiction(db, consult_conflict.id, consult_choice, "Treating physician adopts Nephrology recommendation to hold diuresis today.", user.id)
    assert result2["status"] == "resolved"

    overview = build_patient_overview(db, enc.id)
    assert overview["attention_counts"]["unresolved_contradictions"] == 0

    current_o2 = list(db.scalars(select(ClinicalFact).where(ClinicalFact.encounter_id == enc.id, ClinicalFact.fact_type == "oxygen_support", ClinicalFact.is_current.is_(True))))
    assert len(current_o2) == 1 and current_o2[0].value_text == "room_air"

    med = db.scalar(select(Medication).where(Medication.encounter_id == enc.id, Medication.normalized_name == "furosemide"))
    assert med is not None
    med_state = db.scalar(select(MedicationState).where(MedicationState.medication_id == med.id, MedicationState.domain == "hospital", MedicationState.is_current.is_(True)))
    assert med_state is not None and med_state.status == "held" and med_state.physician_confirmed is True

    signout_doc = db.get(ClinicalDocument, signout["document_id"])
    treatment = db.scalar(select(DocumentSection).where(DocumentSection.document_id == signout_doc.id, DocumentSection.section_type == "current_treatment"))
    active_text = treatment.current_generated_content or treatment.generated_content
    assert "furosemide: held" in active_text.lower()

    # Both documents were automatically re-audited after adjudication; unresolved contradiction flags are gone.
    for doc_id in [progress["document_id"], signout["document_id"]]:
        audit = audit_document(db, doc_id)
        assert not any(f.category == "unresolved_contradiction" for f in audit["flags"])
        for section in db.scalars(select(DocumentSection).where(DocumentSection.document_id == doc_id)):
            update_progress_section(db, doc_id, section.id, None, "accept", user.id)
        approval = approve_progress_document(db, doc_id, user.id)
        assert approval["status"] == "approved"
        final = finalize_document(db, doc_id, user.id)
        assert final["status"] == "finalized"

    resolved = list(db.scalars(select(Contradiction).where(Contradiction.encounter_id == enc.id, Contradiction.status == "resolved")))
    assert len(resolved) >= 2
    assert all(c.physician_resolution and c.adjudication_reason and c.decision_fact_id for c in resolved)


def test_step43_new_clinical_decision_requires_text():
    db, enc, user = make_db()
    c = Contradiction(encounter_id=enc.id, category="manual", description="Two interpretations", severity="high", status="unresolved")
    db.add(c); db.commit()
    try:
        adjudicate_contradiction(db, c.id, "new_clinical_decision", "Physician resolves after bedside assessment.", user.id, None)
        assert False, "Expected ValueError"
    except ValueError as exc:
        assert "decision_text" in str(exc)
