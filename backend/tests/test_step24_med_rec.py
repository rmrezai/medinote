import os
os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import Encounter, Medication, MedicationState, Organization, Patient

engine = create_engine("sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base.metadata.create_all(bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


def seed_medication():
    db = TestingSessionLocal()
    org = Organization(name="Test Group")
    db.add(org); db.flush()
    patient = Patient(organization_id=org.id, first_name="Jane", last_name="Doe")
    db.add(patient); db.flush()
    encounter = Encounter(patient_id=patient.id, organization_id=org.id, status="active")
    db.add(encounter); db.flush()
    med = Medication(encounter_id=encounter.id, normalized_name="losartan", display_name="Losartan", dose="50 mg", route="PO", frequency="daily")
    db.add(med); db.flush()
    db.add(MedicationState(medication_id=med.id, domain="home", status="active", is_current=True))
    db.add(MedicationState(medication_id=med.id, domain="hospital", status="held", reason="AKI", restart_criteria="Reassess with renal recovery", is_current=True))
    db.add(MedicationState(medication_id=med.id, domain="discharge", status="requires_decision", is_current=True, physician_confirmed=False))
    db.commit()
    ids = encounter.id, med.id
    db.close()
    return ids


def test_med_rec_workspace_exposes_three_domains_and_unresolved():
    encounter_id, _ = seed_medication()
    response = client.get(f"/api/v1/encounters/{encounter_id}/med-rec")
    assert response.status_code == 200
    data = response.json()
    assert data["unresolved_count"] == 1
    row = data["medications"][0]
    assert row["home"]["status"] == "active"
    assert row["hospital"]["status"] == "held"
    assert row["discharge"]["status"] == "requires_decision"
    assert row["unresolved"] is True


def test_confirm_discharge_state_creates_physician_confirmed_current_state():
    encounter_id, med_id = seed_medication()
    response = client.post(
        f"/api/v1/medications/{med_id}/confirm-discharge-state",
        json={"status": "stop", "reason": "AKI; reassess outpatient", "restart_criteria": "Renal function and BP recover"},
    )
    assert response.status_code == 200
    assert response.json()["physician_confirmed"] is True
    workspace = client.get(f"/api/v1/encounters/{encounter_id}/med-rec").json()
    row = workspace["medications"][0]
    assert row["discharge"]["status"] == "stop"
    assert row["discharge"]["physician_confirmed"] is True
    assert row["unresolved"] is False


def test_invalid_discharge_state_rejected():
    _, med_id = seed_medication()
    response = client.post(
        f"/api/v1/medications/{med_id}/confirm-discharge-state",
        json={"status": "definitely_restart_without_review"},
    )
    assert response.status_code == 422
