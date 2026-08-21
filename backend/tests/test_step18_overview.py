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
    ClinicalFact,
    ClinicalProblem,
    ClinicalTrajectory,
    Contradiction,
    Encounter,
    LabResult,
    Medication,
    MedicationState,
    Organization,
    Patient,
    PendingItem,
    ProblemEvidence,
)
from app.services.overview_service import build_patient_overview


def _db():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return Session(engine)


def _seed(db: Session):
    org = Organization(name="Test Hospitalists")
    db.add(org); db.flush()
    patient = Patient(organization_id=org.id, first_name="John", last_name="Doe", mrn="123")
    db.add(patient); db.flush()
    enc = Encounter(patient_id=patient.id, organization_id=org.id, status="active", service="Hospital Medicine")
    db.add(enc); db.flush()

    aki = ClinicalProblem(encounter_id=enc.id, name="Acute kidney injury", normalized_name="acute_kidney_injury", certainty="confirmed", status="improving", acuity_rank=48)
    db.add(aki); db.flush()
    fact = ClinicalFact(encounter_id=enc.id, fact_type="lab", concept="creatinine", value_numeric=1.4, units="mg/dL", fact_state="current", confidence="high", is_current=True)
    db.add(fact); db.flush()
    db.add(ProblemEvidence(problem_id=aki.id, fact_id=fact.id, relationship="trajectory_support", evidence_strength="supporting"))
    db.add(LabResult(encounter_id=enc.id, test_name="creatinine", value_numeric=1.4, units="mg/dL", collection_datetime=datetime(2026,8,20,10,tzinfo=timezone.utc)))
    db.add(ClinicalTrajectory(encounter_id=enc.id, category="lab", concept="creatinine", trend="falling", earliest_value="2.4", latest_value="1.4"))

    med = Medication(encounter_id=enc.id, normalized_name="losartan", display_name="Losartan")
    db.add(med); db.flush()
    db.add(MedicationState(medication_id=med.id, domain="hospital", status="held", reason="AKI", is_current=True, physician_confirmed=False))
    db.add(MedicationState(medication_id=med.id, domain="discharge", status="requires_decision", is_current=True, physician_confirmed=False))
    db.add(PendingItem(encounter_id=enc.id, item_type="lab", description="Repeat BMP", status="pending"))
    db.add(Contradiction(encounter_id=enc.id, category="medication", description="Narrative says continue; current state held", severity="high", status="unresolved"))
    db.commit()
    return enc


def test_overview_route_exists():
    routes = {(r.path, tuple(sorted(r.methods or []))) for r in app.routes if isinstance(r, APIRoute)}
    assert ("/api/v1/encounters/{encounter_id}/overview", ("GET",)) in routes


def test_overview_is_physician_facing_and_ranked():
    db = _db()
    enc = _seed(db)
    data = build_patient_overview(db, enc.id)
    assert data["patient_display_name"] == "John Doe"
    assert data["problems"][0]["name"] == "Acute kidney injury"
    assert data["problems"][0]["evidence"][0]["concept"] == "creatinine"
    assert data["latest_labs"][0]["trend"] == "falling"
    assert data["medications"][0]["unresolved"] is True
    assert data["attention_counts"]["high_severity_contradictions"] == 1
    assert "AKI" not in data["current_clinical_picture"] or "Acute kidney injury" in data["current_clinical_picture"]


def test_overview_does_not_invent_missing_disposition():
    db = _db()
    enc = _seed(db)
    data = build_patient_overview(db, enc.id)
    assert data["disposition"] is None
