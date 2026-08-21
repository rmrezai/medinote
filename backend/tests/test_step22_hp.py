import os
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")

from datetime import datetime, timezone

from fastapi.routing import APIRoute
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.main import app
from app.models import ClinicalFact, ClinicalProblem, Encounter, Organization, Patient, ProblemEvidence, ClinicalDocument
from app.services.hp_service import ALLOWED_VARIANTS, generate_hp_document
from app.services.progress_service import approve_progress_document, regenerate_progress_section, update_progress_section


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
    problem = ClinicalProblem(encounter_id=enc.id, name="Acute kidney injury", normalized_name="acute_kidney_injury", certainty="possible", status="improving", acuity_rank=10)
    db.add(problem); db.flush()
    fact = ClinicalFact(encounter_id=enc.id, fact_type="lab", concept="creatinine", value_numeric=1.4, units="mg/dL", observed_datetime=datetime(2026,8,20,10,tzinfo=timezone.utc), fact_state="current", confidence="high", is_current=True)
    db.add(fact); db.flush()
    db.add(ProblemEvidence(problem_id=problem.id, fact_id=fact.id, relationship="support", evidence_strength="supporting"))
    db.commit()
    return enc, problem


def test_hp_routes_exist():
    routes = {(r.path, tuple(sorted(r.methods or []))) for r in app.routes if isinstance(r, APIRoute)}
    assert ("/api/v1/encounters/{encounter_id}/documents/hp", ("POST",)) in routes
    assert ("/api/v1/documents/{document_id}/hp", ("GET",)) in routes


def test_all_hp_variants_generate():
    for variant in ALLOWED_VARIANTS:
        db = _db(); enc, _ = _seed(db)
        result = generate_hp_document(db, enc.id, variant)
        assert result["variant"] == variant
        assert result["document_type"] == "hp"
        assert db.get(ClinicalDocument, result["document_id"]) is not None


def test_hpi_is_exactly_two_sentences_and_preserves_uncertainty():
    db = _db(); enc, _ = _seed(db)
    result = generate_hp_document(db, enc.id, "admission")
    hpi = next(s for s in result["sections"] if s["section_type"] == "hpi")["generated_content"]
    assert hpi.count(".") == 2
    assert "possible" in hpi.lower()
    assert "Acute kidney injury" in hpi


def test_hp_does_not_invent_normal_exam():
    db = _db(); enc, _ = _seed(db)
    result = generate_hp_document(db, enc.id, "admission")
    exam = next(s for s in result["sections"] if s["section_type"] == "focused_exam")["generated_content"].lower()
    assert "lungs clear" not in exam
    assert "rrr" not in exam
    assert "physician examination required" in exam
    assert result["review_required"] is True


def test_hp_problem_preserves_certainty_and_evidence():
    db = _db(); enc, problem = _seed(db)
    result = generate_hp_document(db, enc.id, "admission")
    sec = next(s for s in result["sections"] if s["section_type"] == "assessment_plan_problem")
    assert sec["problem_id"] == problem.id
    assert "possible" in sec["generated_content"].lower()
    assert len(sec["evidence"]) == 1


def test_hp_uses_shared_accept_regenerate_approve_flow():
    db = _db(); enc, _ = _seed(db)
    result = generate_hp_document(db, enc.id, "admission")
    hpi = next(s for s in result["sections"] if s["section_type"] == "hpi")
    refreshed = regenerate_progress_section(db, result["document_id"], hpi["id"], "refresh")
    assert refreshed["regeneration_count"] == 1
    for section in result["sections"]:
        update_progress_section(db, result["document_id"], section["id"], None, "accept")
    approved = approve_progress_document(db, result["document_id"])
    assert approved["status"] == "approved"
