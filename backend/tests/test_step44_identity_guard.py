from datetime import date, datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models import Encounter, Organization, Patient, SourceDocument, User
from app.services.analysis_service import analyze_encounter
from app.services.identity_service import (
    assert_encounter_identity_safe,
    evaluate_source_identity,
    verify_source_identity,
)

UTC = timezone.utc


def make_db():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()


def seed_patient(db, org, user, *, mrn, first="Alex", last="Morgan", dob=date(1960, 1, 2)):
    p = Patient(organization_id=org.id, mrn=mrn, first_name=first, last_name=last, date_of_birth=dob, sex="male")
    db.add(p); db.flush()
    e = Encounter(patient_id=p.id, organization_id=org.id, admission_datetime=datetime(2026, 8, 20, 8, tzinfo=UTC), service="Hospital Medicine", attending_user_id=user.id, identity_status="created_verified")
    db.add(e); db.flush()
    return p, e


def test_duplicate_names_and_similar_mrns_are_not_fuzzy_matched():
    db = make_db()
    org = Organization(name="Identity Group"); db.add(org); db.flush()
    user = User(organization_id=org.id, email="a@test", role="attending", active=True); db.add(user); db.flush()
    p1, e1 = seed_patient(db, org, user, mrn="123450")
    p2, e2 = seed_patient(db, org, user, mrn="123451")
    db.commit()
    assert p1.id != p2.id and e1.id != e2.id

    status, reason, evidence = evaluate_source_identity(p1, raw_text="Patient: Alex Morgan\nMRN: 123451\nDOB: 1960-01-02")
    assert status == "mismatch"
    assert "mrn" in evidence["mismatched_fields"]
    assert reason


def test_exact_identifier_mismatch_quarantines_and_blocks_analysis():
    db = make_db()
    org = Organization(name="Identity Group"); db.add(org); db.flush()
    user = User(organization_id=org.id, email="a@test", role="attending", active=True); db.add(user); db.flush()
    patient, enc = seed_patient(db, org, user, mrn="A100", dob=date(1955, 5, 5))
    state, reason, _ = evaluate_source_identity(patient, raw_text="MRN: A101\nDOB: 1955-05-05\nPneumonia.")
    assert state == "mismatch"
    source = SourceDocument(encounter_id=enc.id, document_type="progress_note", raw_text="MRN: A101\nDOB: 1955-05-05\nPneumonia.", identity_status=state, identity_reason=reason, imported_by=user.id)
    db.add(source); db.commit()

    with pytest.raises(ValueError, match="identity hard stop"):
        analyze_encounter(db, enc.id)
    with pytest.raises(ValueError, match="cannot be overridden"):
        verify_source_identity(db, source.id, user, confirmed_match=True, reason="wrong patient selected")


def test_name_only_source_is_ambiguous_until_physician_verifies_it():
    db = make_db()
    org = Organization(name="Identity Group"); db.add(org); db.flush()
    user = User(organization_id=org.id, email="a@test", role="attending", active=True); db.add(user); db.flush()
    patient, enc = seed_patient(db, org, user, mrn="A100")
    state, reason, _ = evaluate_source_identity(patient, raw_text="Patient: Alex Morgan\nPneumonia.")
    assert state == "ambiguous"
    source = SourceDocument(encounter_id=enc.id, document_type="progress_note", raw_text="Patient: Alex Morgan\nPneumonia.", identity_status=state, identity_reason=reason, imported_by=user.id)
    db.add(source); db.commit()

    with pytest.raises(ValueError, match="source has ambiguous identity"):
        assert_encounter_identity_safe(db, enc.id)

    result = verify_source_identity(db, source.id, user, confirmed_match=True, reason="Verified against selected EHR patient banner.")
    assert result["identity_status"] == "physician_verified"
    assert_encounter_identity_safe(db, enc.id)


def test_dob_mismatch_is_hard_mismatch_even_when_name_and_mrn_match():
    db = make_db()
    org = Organization(name="Identity Group"); db.add(org); db.flush()
    user = User(organization_id=org.id, email="a@test", role="attending", active=True); db.add(user); db.flush()
    patient, _ = seed_patient(db, org, user, mrn="A100", dob=date(1955, 5, 5))
    state, _, evidence = evaluate_source_identity(patient, raw_text="Patient: Alex Morgan\nMRN: A100\nDOB: 1955-05-06")
    assert state == "mismatch"
    assert "dob" in evidence["mismatched_fields"]

def test_security_middleware_covers_source_resources():
    from pathlib import Path
    text = (Path(__file__).resolve().parents[1] / "app" / "core" / "security_middleware.py").read_text()
    assert "SourceDocument" in text
    assert "parts[2] == 'sources'" in text


def test_identity_guard_is_called_before_overview_and_analysis():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / "app" / "services"
    assert "assert_encounter_identity_safe(db, encounter_id)" in (root / "analysis_service.py").read_text()
    assert "assert_encounter_identity_safe(db, encounter_id)" in (root / "overview_service.py").read_text()
