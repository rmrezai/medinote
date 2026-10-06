import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.base import Base
import app.models  # noqa: F401
from app.models import Organization, Patient
from app.services.mrn_service import (
    issue_patient_mrn,
    map_external_identifier,
    resolve_external_identifier,
)


def make_db():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    db = Session(engine)
    org = Organization(name="Synthetic Org")
    db.add(org)
    db.flush()
    return db, org


def test_patient_gets_one_stable_internal_mrn():
    db, org = make_db()
    patient = Patient(organization_id=org.id)
    db.add(patient)
    db.flush()

    first = issue_patient_mrn(db, org.id, patient.id)
    second = issue_patient_mrn(db, org.id, patient.id)

    assert first == second
    assert first.startswith("CLN-")
    assert len(first) == 16


def test_external_mrn_maps_without_replacing_internal_mrn():
    db, org = make_db()
    patient = Patient(organization_id=org.id)
    db.add(patient)
    db.flush()
    internal = issue_patient_mrn(db, org.id, patient.id)

    row, outcome = map_external_identifier(
        db,
        org.id,
        patient.id,
        source_system="epic",
        identifier_value="EXT-12345",
    )

    assert outcome == "accepted"
    assert patient.mrn == internal
    assert row.identifier_value == "EXT-12345"
    assert resolve_external_identifier(
        db,
        org.id,
        source_system="epic",
        identifier_value="EXT-12345",
    ).id == patient.id


def test_external_identifier_cannot_link_two_patients():
    db, org = make_db()
    p1 = Patient(organization_id=org.id)
    p2 = Patient(organization_id=org.id)
    db.add_all([p1, p2])
    db.flush()
    map_external_identifier(
        db,
        org.id,
        p1.id,
        source_system="lab",
        identifier_value="LAB-1",
    )
    try:
        map_external_identifier(
            db,
            org.id,
            p2.id,
            source_system="lab",
            identifier_value="LAB-1",
        )
        assert False, "expected linkage conflict"
    except ValueError as exc:
        assert str(exc) == "external-identifier-already-linked"
